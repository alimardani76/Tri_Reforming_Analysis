# Executed equilibrium benchmark

Fresh calculation on base commit `e4e49b3e95b06810dbbae3252728490aaef6678d`; canonical-LF source grid SHA256
`e3b6d6696cf46f72df11b6fa2c0526e2c4848d205fafe7cc09a223b0731c2e61`. See `summary.json` for environment,
source hashes (including raw checkout bytes) and the exact invocation. The original study files were read only.

## Scope and coverage

88 unique grid cases from 46464 rows, plus 5
traceable off-grid published optima from `results/revision_r2/aspen_results.csv`.
The latter are preserved Aspen reference records, not new Aspen executions.
No earlier open-source predictions were loaded. No graphite-removal ablation was performed.
The five optima are reported separately and never substituted with nearest grid points.
Zero data exclusions; 0 final engine/case failures; 20 captured warning/log records.
Cantera needed a fresh-feed Gibbs fallback after VCS failure in 10 cases.
Failed VCS attempts and their messages remain in `warnings.json`; `cantera_method`
and `attempts` in `predictions.csv` identify each fallback. A development probe at
VCS rtol=1e-11 also failed on ten cases; the final rtol=1e-9 run still needs the fallback.

Sampling uses five SHA256-ranked rows per T-band/P-band/carbon-regime stratum
(60 rows), plus controlled source-grid CO2 and pressure sweeps and two oxygen-free
edge cases, with duplicates removed. This purposefully balanced sample is not
a random population estimate. Manifest source_row is the 1-based CSV physical line,
including the header. All five input ranges and source strata are recorded in CSVs.

## Thermodynamic qualification

Aspen truth uses SRK; SciPy uses six ideal-gas species and pure graphite with
NASA7 data from Cantera 3.1.0. The optional Cantera engine uses identical data.
These errors measure
combined model/data differences, not pure solver error or SRK replication.
Graphite is equilibrium propensity, not measured catalyst coke. Q is excluded:
feed conditions and duty conversions exist in repository scripts, but an identical
SRK inlet/product enthalpy reference and property basis are not implemented here.
Grid outlet O2 is unrecorded; Aspen C/H closure can be checked, while the O residual
is only accounted closure. All seven predicted species are included in balance checks.

## SciPy versus Aspen: grid

All flows/yields/errors are mol/mol inlet CH4; X_CH4 errors are dimensionless.
X_CH4=1-FCH4, Y_H2=FH2, Y_CO=FCO, E_CO2=FCO2-Fc.

| output | N | MAE | RMSE | max_abs_error |
| --- | --- | --- | --- | --- |
| FCH4 | 88 | 0.0066023256 | 0.0096595626 | 0.027161447 |
| FH2O | 88 | 0.0098955845 | 0.015075293 | 0.040731528 |
| FCO2 | 88 | 0.0028875047 | 0.004328699 | 0.016158868 |
| FCO | 88 | 0.0097668216 | 0.015934022 | 0.065116132 |
| FH2 | 88 | 0.0043428046 | 0.0067331222 | 0.033601934 |
| FCARBON | 88 | 0.015328984 | 0.02421351 | 0.076523996 |
| X_CH4 | 88 | 0.0066023256 | 0.0096595626 | 0.027161447 |
| Y_H2 | 88 | 0.0043428046 | 0.0067331222 | 0.033601934 |
| Y_CO | 88 | 0.0097668216 | 0.015934022 | 0.065116132 |
| E_CO2 | 88 | 0.0028875047 | 0.004328699 | 0.016158868 |

## SciPy versus Aspen: five published optima

| output | N | MAE | RMSE | max_abs_error |
| --- | --- | --- | --- | --- |
| FCH4 | 5 | 0.00012137681 | 0.00015464058 | 0.0003020823 |
| FH2O | 5 | 0.00047730848 | 0.00051622665 | 0.00071689608 |
| FCO2 | 5 | 0.00059868524 | 0.00065207151 | 0.00087238012 |
| FCO | 5 | 0.00072006233 | 0.00079481545 | 0.001174463 |
| FH2 | 5 | 0.00024810004 | 0.00030423193 | 0.00044582468 |
| FCARBON | 5 | 0 | 0 | 0 |
| X_CH4 | 5 | 0.00012137681 | 0.00015464058 | 0.0003020823 |
| Y_H2 | 5 | 0.00024810004 | 0.00030423193 | 0.00044582468 |
| Y_CO | 5 | 0.00072006233 | 0.00079481545 | 0.001174463 |
| E_CO2 | 5 | 0.00059868524 | 0.00065207151 | 0.00087238012 |

## Carbon boundary

Positive means strictly greater than the listed threshold on **both** reference
and prediction. TP/TN/FP/FN use Aspen as truth. Threshold zero is diagnostic;
1e-6 mol/mol is the primary numerical classification. This tests threshold
sensitivity, rather than assigning a physical coking threshold.

| threshold | N | TP | TN | FP | FN |
| --- | --- | --- | --- | --- | --- |
| 0 | 88 | 55 | 31 | 0 | 2 |
| 1e-08 | 88 | 55 | 31 | 0 | 2 |
| 1e-06 | 88 | 55 | 31 | 0 | 2 |
| 0.0001 | 88 | 55 | 31 | 0 | 2 |
| 0.001 | 88 | 54 | 31 | 0 | 3 |

## Pressure and controlled trends

`pressure_metrics.csv` reports H2 and carbon discrepancies separately at each
sampled pressure; counts differ, so they do not isolate pressure causality.
The controlled pressure sweep in `carbon_sweeps.png` holds the other four inputs
fixed. CO2 sweeps use actual grid rows at 600/800/1000 C, P=1 bar, Fw=0.2, Fo=0;
these differ from `simulation/co2_carbon_sweep.py` (Fw=0.15, 600/750/900 C), whose
previous generated output is not used. Every point is traceable in the manifest.

Carbon-positive Aspen cases predicted zero at the primary threshold:

| case_id | T | P | Fw | Fc | Fo | aspen_FCARBON | pred_FCARBON |
| --- | --- | --- | --- | --- | --- | --- | --- |
| grid-02936 | 800 | 1 | 0.2 | 1 | 0 | 0.008225792 | 0 |
| grid-20881 | 800 | 17 | 0.6 | 0.3 | 0.3 | 0.023047304 | 0 |

- 600 C, Aspen: carbon 0.5575337 -> 0.8391733 as Fc=0 -> 1; nondecreasing.
- 600 C, SciPy: carbon 0.55075263 -> 0.82452758 as Fc=0 -> 1; nondecreasing.
- 800 C, Aspen: carbon 0.74860291 -> 0.008225792 as Fc=0 -> 1; nonincreasing.
- 800 C, SciPy: carbon 0.74135753 -> 0 as Fc=0 -> 1; nonincreasing.
- 1000 C, Aspen: carbon 0.7870113 -> 0 as Fc=0 -> 1; nonincreasing.
- 1000 C, SciPy: carbon 0.78401959 -> 0 as Fc=0 -> 1; nonincreasing.

Controlled pressure sweep (800 C, Fw=0.2, Fc=0.6, Fo=0.1):

| P | aspen_FCARBON | pred_FCARBON | aspen_FH2 | pred_FH2 |
| --- | --- | --- | --- | --- |
| 1 | 0.13546975 | 0.11819709 | 2.0007572 | 2.0013761 |
| 5 | 0.3462084 | 0.3087888 | 1.5605027 | 1.5566751 |
| 9 | 0.42038802 | 0.37756912 | 1.3317609 | 1.3251919 |
| 13 | 0.45859367 | 0.41326365 | 1.1837352 | 1.1758494 |
| 17 | 0.48198295 | 0.43513816 | 1.0773426 | 1.0688584 |
| 21 | 0.49783825 | 0.44991283 | 0.99589495 | 0.98719309 |
| 25 | 0.50934516 | 0.46055364 | 0.93084027 | 0.92213465 |
| 29 | 0.51811833 | 0.46857473 | 0.8772631 | 0.86867897 |

In this controlled sweep, carbon is underpredicted by 0.0172727 at 1 bar and 0.0495436 at 29 bar. Both models reproduce rising carbon and declining H2 with pressure under these particular conditions; discrepancies cannot be assigned to EOS alone.


## Numerical verification and execution

| engine | cohort | attempted_N | evaluated_N | failed_N | elapsed_s | median_case_s | max_atom_residual |
| --- | --- | --- | --- | --- | --- | --- | --- |
| cantera | grid | 88 | 88 | 0 | 0.517684 | 0.00285525 | 8.8498098e-12 |
| cantera | optima | 5 | 5 | 0 | 0.0151844 | 0.0029015 | 1.7763568e-15 |
| scipy | grid | 88 | 88 | 0 | 1.189224 | 0.0130382 | 1.0924595e-13 |
| scipy | optima | 5 | 5 | 0 | 0.0911758 | 0.0149766 | 9.7699626e-15 |

Benchmark pipeline before figure generation: 2.996 s. Per-case times include phase construction for Cantera, and KKT solve/validation for SciPy. Imports, environment installation and source selection are excluded from per-case totals. Engines ran sequentially on the same machine; one pass, no statistical timing study.

Environment: `{'python': '3.11.9 (tags/v3.11.9:de54cf5, Apr  2 2024, 10:12:12) [MSC v.1938 64 bit (AMD64)]', 'platform': 'Windows-10-10.0.26220-SP0', 'processor': 'Intel64 Family 6 Model 154 Stepping 4, GenuineIntel', 'processor_identifier': 'Intel64 Family 6 Model 154 Stepping 4, GenuineIntel', 'logical_cpus': 8}`.

Packages: `{'numpy': '2.2.6', 'scipy': '1.15.3', 'pandas': '2.2.3', 'matplotlib': '3.10.3', 'pytest': '8.3.5'}`. Cantera: executed: 3.1.0.

Matched-thermodynamics cross-engine maximum absolute differences:

| output | N | max_abs_difference |
| --- | --- | --- |
| FCH4 | 93 | 2.8395569e-09 |
| FH2O | 93 | 4.8953772e-09 |
| FCO2 | 93 | 2.2226774e-09 |
| FO2 | 93 | 4.2410195e-23 |
| FCO | 93 | 3.9387259e-09 |
| FH2 | 93 | 2.9998739e-09 |
| FCARBON | 93 | 6.7462084e-09 |

Cantera's Aspen metrics and confusion counts are independently computed in `metrics.csv` and `carbon_confusion.csv`. Agreement with SciPy validates the implementation under shared thermochemical assumptions; it does not validate the shared data against Aspen.

Aspen reference maximum absolute accounted C/H/O residuals: {'C_residual': 4.999999969612644e-09, 'H_residual': 1.2000000104706032e-08, 'O_accounted_residual': 1.0999999577876451e-08}.


## Framework assessment

For this bounded reproducible Python equilibrium screen, Cantera provides an
application framework with existing multiphase VCS/Gibbs APIs; its execution
status and measured agreement with the transparent SciPy reference are above.
When both engines are validated under matched thermo, Cantera is the practical
application framework choice for this screening scope.
The SciPy implementation is useful for auditing the objective and optimality
conditions. Neither has demonstrated Aspen SRK equivalence or full flowsheet
replacement. Timings above apply only to these implementations and setup costs.

DWSIM was **not executed**: no configured executable or validated seven-species
SRK/graphite flowsheet is available in this environment. Its official
[Gibbs-reactor documentation](https://dwsim.org/help/main/25-reactors.html) and
[solid-phase settings](https://dwsim.org/help/main/06-simulation.html) make it a
candidate for a separate flowsheet replication exercise. No DWSIM accuracy,
carbon-boundary, robustness, or runtime claim follows from this assessment.
Matching the SRK property package, species data, phases and heat-duty basis
would be required before recommending it as an Aspen replacement for this case.

## Validation commands

```text
python open_source_benchmark/run_benchmark.py --cantera
python -m pytest open_source_benchmark/tests -v --junitxml=open_source_benchmark/results/pytest.xml
python open_source_benchmark/make_figures.py
python open_source_benchmark/write_report.py
```

The test execution transcript and JUnit results are committed alongside this report.
See `tests.txt` and `pytest.xml` for the verified pass count and test duration.
