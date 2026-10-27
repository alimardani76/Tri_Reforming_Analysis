# Open-source tri-reforming equilibrium benchmark

This addition executes a transparent NumPy/SciPy Gibbs minimizer and Cantera
3.1.0 multiphase equilibrium against actual Aspen reference records. It requires
no Aspen installation. Graphite is available in every calculation. It does not
retrain the study models, perform optimization, or run a graphite-removal ablation.

**Measured results:** [report](results/REPORT.md), [raw predictions](results/predictions.csv),
[metrics](results/metrics.csv), [carbon confusion](results/carbon_confusion.csv),
[figures](results/carbon_sweeps.png), [proposed reply](LINKEDIN_REPLY.md).
Aspen uses **SRK**; this benchmark uses **ideal gas plus pure graphite**. Agreement
is conditional on thermodynamic assumptions, not an SRK reimplementation or proof
of catalyst coking performance. DWSIM is assessed but **not executed**.

## Reproduce from the repository root

Use Python 3.11 (verified: 3.11.9). An isolated environment keeps the original
study's ML dependencies separate. In PowerShell:

```powershell
python -m venv open_source_benchmark/.venv
& open_source_benchmark/.venv/Scripts/python.exe -m pip install -r open_source_benchmark/requirements-cantera.txt
& open_source_benchmark/.venv/Scripts/python.exe open_source_benchmark/run_benchmark.py --cantera
& open_source_benchmark/.venv/Scripts/python.exe -m pytest open_source_benchmark/tests -v --junitxml=open_source_benchmark/results/pytest.xml
```

On Unix, replace `open_source_benchmark/.venv/Scripts/python.exe` with
`open_source_benchmark/.venv/bin/python`. No activation is necessary. For an
independent SciPy-only installation, install `requirements.txt` and omit
`--cantera`; optional Cantera property tests skip when it is unavailable. The
committed thermochemical extract is sufficient to run SciPy without Cantera.
`environment-lock.txt` records **all installed package versions** in the verified
Windows environment; top-level requirements pin the scientific packages.

The full verified workflow, including saved benchmark/test transcripts and JUnit
counts, can be repeated with `python open_source_benchmark/verify.py` using the
environment's Python. This explicitly requests the optional Cantera run.

`run_benchmark.py` reads original source CSVs, deterministically selects cases,
solves them from the feed, checks each result, and overwrites this module's
manifest, raw CSVs, summaries, report, figures and proposed reply. It never reads
previous benchmark predictions. Use `--out open_source_benchmark/my_run` to keep
another run's CSVs/report/figures. Output directories outside this module are
rejected. `LINKEDIN_REPLY.md` is regenerated in the module root.
The CLI exits nonzero if any attempted case fails; failures remain in the CSV.

To regenerate just figures or report from the recorded raw evidence:

```text
python open_source_benchmark/make_figures.py
python open_source_benchmark/write_report.py
```

Those commands support `--out` for another run directory. The report writer
expects a benchmark containing both grid cases and the five optima. Tests check
the committed `results/` evidence, so regenerate there before testing a new run.

## Thermodynamic specification

Molar basis: inlet CH4 = 1 mol, H2O = Fw, CO2 = Fc, O2 = Fo. No inlet CO, H2 or
graphite. The outlet amounts are mol per inlet mol CH4, equivalent to the
normalized study flows. `T_K = T_C + 273.15`; `P_Pa = 100000 P_bar`.
The pressure in all logarithms is **absolute**. Reference pressure is
**101325 Pa (1 atm), not 1 bar**, as verified from each source species object.
R = 8.31446261815324 J mol^-1 K^-1.

Species order: CH4, H2O(g), CO2, O2, CO, H2, C(graphite). Atom matrix rows are
C/H/O:

```text
A = [[1, 0, 1, 0, 1, 0, 1],
     [4, 2, 0, 0, 0, 2, 0],
     [0, 1, 2, 2, 1, 0, 0]]
b = [1+Fc, 4+2*Fw, Fw+2*Fc+2*Fo]
```

For N_g = sum of the six gas amounts, minimize at fixed T and P:

```text
G/(RT) = sum_g n_i [g_i^0(T)/(RT) + ln((n_i/N_g) P/P0)]
          + n_C [g_C^0(T)/(RT) + V_C(P-P0)/(RT)]
subject to A n = b, n >= 0.
```

The pure graphite phase has activity one: it has no gas mixing entropy. The
constant-volume correction uses density 2160 kg/m^3 and molar volume
0.012011/2160 m^3/mol, matching Cantera's graphite model. It is small but included
in both engines. Standard enthalpy and entropy use the NASA7 two-range polynomial
integrals; `g^0/(RT) = h^0/(RT) - s^0/R`. Coefficients and valid temperature ranges
are in [thermo.json](thermo.json). Extrapolation is rejected. All evaluated
temperatures are 773.15–1273.15 K, within the relevant data ranges.

### Independent numerical minimizer

`equilibrium.py` minimizes this convex objective through its element-potential
Karush–Kuhn–Tucker equations. With dimensionless element potentials lambda,
gas amounts satisfy `ln(n_i/N_g) = A_i.T lambda - g_i^0/(RT) - ln(P/P0)`.
Unknowns are element potentials, log(N_g), and the scaled graphite amount when
the graphite constraint is active. SciPy `least_squares` solves element closure,
gas-fraction normalization and graphite phase stationarity. It never calls
Cantera's equilibrium solver or loads precomputed outlet tables.

The graphite-active stationary equations are tried first. If their graphite
amount is negative, the zero-amount boundary is solved and accepted only when
`mu_C/(RT) - A_C.T lambda >= -1e-8`. This is an internal active-set procedure for
the **same graphite-enabled optimization**, not a graphite-removal experiment.
An absent element removes its species exactly (e.g. an oxygen-free feed), avoiding
artificial trace feeds. The objective has nonnegative gas Hessian and a linear
solid term, so feasibility and KKT conditions certify a global minimum, within
the stated numerical tolerances and thermodynamic model.

Solver settings: xtol/ftol/gtol = 1e-13, at most 1500 function evaluations per
active-set branch. Maximum scaled equation residual must be <=1e-9; absolute
atom closure <=1e-8 mol atoms/mol inlet CH4; amounts nonnegative; graphite
complementarity <=1e-8 in RT units. Gas stationarity is built into the log-amount
representation. No negative amount is clipped into a reported solution.
`gibbs_RT`, phase affinity and solver evaluations are retained in the raw CSV.

### Actual Cantera calculation

A fresh `Solution(thermo='ideal-gas')` includes only the six specified gas species
from `gri30.yaml`; `graphite.yaml` supplies a separate pure condensed phase.
No radicals, N2, other hydrocarbons or reactions are added. Equilibrium depends
on the thermochemical species data, not a kinetic reaction mechanism.
`Mixture.equilibrate('TP', solver='vcs', rtol=1e-9, max_steps=5000)` starts from
the exact feed and zero initial graphite. On `CanteraError`, the implementation
records the failed attempt and retries a **fresh feed**, independently of SciPy,
using Cantera's `gibbs` solver at the same tolerance/iteration limit. Both engines
use exactly the same exported NASA7 gas and graphite data. All 93 cases complete
with this policy; ten require the Gibbs fallback. `warnings.json` preserves the
failure messages and `predictions.csv` records the method/attempt count.

### Sources, attribution and license

The coefficient extract is derived from **Cantera v3.1.0** distributed input
files, whose redistribution notice is retained in [CANTERA_LICENSE.txt](CANTERA_LICENSE.txt)
(BSD 3-clause terms). The original data attribution is preserved here:

- Six gas species: [v3.1.0 gri30.yaml](https://github.com/Cantera/cantera/blob/v3.1.0/data/gri30.yaml),
  GRI-Mech 3.0 thermodynamics dated 1999-07-30 (CHEMKIN-II/NASA7). Upstream
  species notes include CH4 L8/88, H2O L8/89, CO2 L7/88, O2 TPIS89,
  CO TPIS79 and H2 TPIS78. These are thermochemical fits, not measured TRM data.
- [v3.1.0 graphite.yaml](https://github.com/Cantera/cantera/blob/v3.1.0/data/graphite.yaml)
  attributes graphite to Gordon & McBride, NASA SP-273 (1971), and McBride,
  Gordon & Reno, NASA TM-4513 (1993).
- [NASA7 equations](https://cantera.org/3.1/reference/thermo/species-thermo.html),
  [Cantera multiphase graphite example](https://cantera.org/3.1/examples/python/thermo/adiabatic.html)
  (the example is HP; this benchmark explicitly uses TP).
- [DWSIM Gibbs reactor](https://dwsim.org/help/main/25-reactors.html),
  [phase settings](https://dwsim.org/help/main/06-simulation.html): documentation
  assessment only, no executed flowsheet or verified SRK/graphite setup here.

`prepare_thermo.py` regenerates the coefficient extract and license from the
pinned Cantera installation; `thermo.json` records SHA256 hashes of the full
source YAML files. Tests compare polynomial values with Cantera at five
temperatures, including both sides of the 1000 K branch transition, and check
the solid pressure correction.

## Case provenance and limitations

`data/added2.csv` has 46,464 unique input rows, six T levels (500–1000 C), eight
P levels (1–29 bar), eleven Fw/Fc levels (0–1), and eight Fo levels (0–0.7).
It contains 19,716 exact-zero carbon outputs and 26,748 positive carbon outputs;
none are strictly between zero and 1e-6. No Q comparison is attempted: even
though the Aspen scripts document feed T=500 C/P=1 bar and QCALC conversion,
an identical enthalpy/property-model basis has not been implemented or verified.
No Aspen process was launched; original Aspen truth records are read only.

`cases.py` selects five rows per each of 12 strata: three temperature bands
(500/600, 700/800, 900/1000 C), two pressure bands (<=13 and >13 bar), and two
Aspen carbon regimes (<=1e-6 and >1e-6). Within a stratum, sort by SHA256 of
`trm-v1:` followed by comma-separated `.12g` inputs. Add 18 controlled CO2 sweep
rows (600/800/1000 C, P=1, Fw=0.2, Fo=0; Fc=0,0.2,...,1), eight pressure-sweep
rows (800 C, Fw=0.2, Fc=0.6, Fo=0.1), and two oxygen-free edge cases (500/1000 C,
P=1, all inlet ratios zero). Deduplication gives **88 unique grid cases**.
Five optima come directly from `results/revision_r2/aspen_results.csv`, with
provenance in its README and `simulation/verify_elemental_aspen.py`. They are
compared separately. We do not rerun the ANN, GA, or Aspen, nor infer off-grid
truth from the grid. Source line numbers, inputs, truth and selection reasons
are in `case_manifest.csv`; source hashes are in `summary.json`.
Source and implementation hashes normalize CRLF to LF so a Git checkout on
another operating system can verify the same content. Raw source-file byte
hashes from the executed Windows checkout are also retained separately.

Sampling deliberately uses truth carbon strata and includes controlled sweeps;
the reported average errors apply to these cases, not the full grid. Errors
include SRK versus ideal-gas and potentially different standard-state data.
Threshold sensitivity at 0, 1e-8, 1e-6, 1e-4 and 1e-3 is reported using the same
threshold on Aspen and prediction. Two Aspen carbon-positive cases are classified
zero by SciPy at the primary 1e-6 threshold. Their actual operating points are
listed in the report; this is not a validated carbon-free design criterion.

Full predicted C/H/O closure is checked with all seven species. Original grid
FO2 was not recorded, so its Aspen oxygen balance is only accounted closure;
an absent column is never represented as a measured zero. `aspen_balance.csv`
explicitly identifies which references include O2. Equilibrium graphite is
not catalyst-dependent coke, a kinetic rate, or a time-on-stream prediction.

## Evidence files and verification

- `results/case_manifest.csv`, `strata.csv`: source truth, source lines, selection.
- `predictions.csv`: complete raw pairs, status, diagnostics and measured timings.
- `metrics.csv`, `carbon_confusion.csv`, `pressure_metrics.csv`: computed summaries.
- `engine_agreement.csv`: matched-thermo cross-engine numerical differences.
- `aspen_balance.csv`, `failures.csv`, `warnings.json`: closure/failure evidence.
- `summary.json`, `environment-lock.txt`, `execution.txt`, `tests.txt`, `pytest.xml`:
  environment, hashes, exact commands, observed runtime and test results.
- `REPORT.md`, `parity.png`, `carbon_sweeps.png`: generated report and figures.

All 27 tests execute in the recorded environment: atom closure, nonnegative
phases, bounds, graphite stability, absent-element treatment, unit/reference
pressure conversion, polynomial checks, feasible Gibbs perturbations, engine
agreement, deterministic source sampling, raw-row metric/confusion recomputation,
failure exclusion and explicit fallback accounting. The original repository
contains no other test suite. Figure labels and layout were visually checked.

For this equilibrium-screening scope, Cantera provides an executed application
API and the SciPy implementation provides an auditable reference. Neither
establishes a full-process Aspen replacement. DWSIM would need an independently
validated seven-species SRK/graphite flowsheet before any accuracy/runtime ranking.
