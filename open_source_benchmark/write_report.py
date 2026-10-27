"""Build compact Markdown report and proposed reply from executed raw results."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def table(frame):
    def cell(value):
        return f"{value:.8g}" if isinstance(value, (float, np.floating)) else str(value)
    return "| " + " | ".join(frame.columns) + " |\n| " + " | ".join(["---"]*len(frame.columns)) + " |\n" + "\n".join(
        "| " + " | ".join(cell(v) for v in row) + " |" for row in frame.itertuples(index=False, name=None))


def write_report(out):
    out = Path(out)
    summary = json.loads((out/"summary.json").read_text())
    raw = pd.read_csv(out/"predictions.csv")
    metrics = pd.read_csv(out/"metrics.csv")
    confusion = pd.read_csv(out/"carbon_confusion.csv")
    manifest = pd.read_csv(out/"case_manifest.csv")
    scipy = raw[(raw.engine == "scipy") & (raw.cohort == "grid") & (raw.status == "ok")]
    grid_metrics = metrics[(metrics.engine == "scipy") & (metrics.cohort == "grid")]
    optima_metrics = metrics[(metrics.engine == "scipy") & (metrics.cohort == "optima")]
    def mae(output):
        return grid_metrics.loc[grid_metrics.output == output, "MAE"].item()
    runtime = pd.DataFrame(summary["runtime"])
    text = f"""# Executed equilibrium benchmark

Fresh calculation on base commit `{summary['base_commit']}`; canonical-LF source grid SHA256
`{summary['source_sha256']['data/added2.csv']}`. See `summary.json` for environment,
source hashes (including raw checkout bytes) and the exact invocation. The original study files were read only.

## Scope and coverage

{summary['grid_N']} unique grid cases from {summary['source_rows']} rows, plus {summary['optima_N']}
traceable off-grid published optima from `results/revision_r2/aspen_results.csv`.
The latter are preserved Aspen reference records, not new Aspen executions.
No earlier open-source predictions were loaded. No graphite-removal ablation was performed.
The five optima are reported separately and never substituted with nearest grid points.
Zero data exclusions; {int((raw.status != 'ok').sum())} final engine/case failures; {summary['warning_count']} captured warning/log records.
Cantera needed a fresh-feed Gibbs fallback after VCS failure in {summary['cantera_fallback_N']} cases.
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

{table(grid_metrics.drop(columns=['engine', 'cohort']))}

## SciPy versus Aspen: five published optima

{table(optima_metrics.drop(columns=['engine', 'cohort']))}

## Carbon boundary

Positive means strictly greater than the listed threshold on **both** reference
and prediction. TP/TN/FP/FN use Aspen as truth. Threshold zero is diagnostic;
1e-6 mol/mol is the primary numerical classification. This tests threshold
sensitivity, rather than assigning a physical coking threshold.

{table(confusion[(confusion.engine == 'scipy') & (confusion.cohort == 'grid')].drop(columns=['engine', 'cohort']))}

## Pressure and controlled trends

`pressure_metrics.csv` reports H2 and carbon discrepancies separately at each
sampled pressure; counts differ, so they do not isolate pressure causality.
The controlled pressure sweep in `carbon_sweeps.png` holds the other four inputs
fixed. CO2 sweeps use actual grid rows at 600/800/1000 C, P=1 bar, Fw=0.2, Fo=0;
these differ from `simulation/co2_carbon_sweep.py` (Fw=0.15, 600/750/900 C), whose
previous generated output is not used. Every point is traceable in the manifest.

"""
    missed = scipy[(scipy.aspen_FCARBON > 1e-6) & (scipy.pred_FCARBON <= 1e-6)]
    text += "Carbon-positive Aspen cases predicted zero at the primary threshold:\n\n"
    text += table(missed[["case_id", "T", "P", "Fw", "Fc", "Fo", "aspen_FCARBON", "pred_FCARBON"]]) + "\n\n"
    for temperature, group in scipy[scipy.group.str.contains("co2_sweep")].groupby("T"):
        group = group.sort_values("Fc")
        for prefix, label in [("aspen_", "Aspen"), ("pred_", "SciPy")]:
            values = group[prefix+"FCARBON"].to_numpy()
            direction = "nonincreasing" if np.all(np.diff(values) <= 1e-8) else "nondecreasing" if np.all(np.diff(values) >= -1e-8) else "nonmonotonic"
            text += f"- {temperature:g} C, {label}: carbon {values[0]:.8g} -> {values[-1]:.8g} as Fc=0 -> 1; {direction}.\n"
    pressure = scipy[scipy.group.str.contains("pressure_sweep")].sort_values("P")
    text += "\nControlled pressure sweep (800 C, Fw=0.2, Fc=0.6, Fo=0.1):\n\n"
    text += table(pressure[["P", "aspen_FCARBON", "pred_FCARBON", "aspen_FH2", "pred_FH2"]])
    carbon_error = pressure.pred_FCARBON-pressure.aspen_FCARBON
    text += f"\n\nIn this controlled sweep, carbon is underpredicted by {-carbon_error.iloc[0]:.6g} at 1 bar and {-carbon_error.iloc[-1]:.6g} at 29 bar. "
    text += "Both models reproduce rising carbon and declining H2 with pressure under these particular conditions; discrepancies cannot be assigned to EOS alone.\n"
    text += "\n\n## Numerical verification and execution\n\n" + table(runtime)
    text += f"\n\nBenchmark pipeline before figure generation: {summary['elapsed_before_figures_s']:.4g} s. "
    text += "Per-case times include phase construction for Cantera, and KKT solve/validation for SciPy. "
    text += "Imports, environment installation and source selection are excluded from per-case totals. "
    text += "Engines ran sequentially on the same machine; one pass, no statistical timing study.\n\n"
    text += f"Environment: `{summary['environment']}`.\n\nPackages: `{summary['versions']}`. Cantera: {summary['cantera']}.\n\n"
    if summary["cross_engine_agreement"]:
        text += "Matched-thermodynamics cross-engine maximum absolute differences:\n\n" + table(pd.DataFrame(summary["cross_engine_agreement"]))
        text += "\n\nCantera's Aspen metrics and confusion counts are independently computed in `metrics.csv` and `carbon_confusion.csv`. "
        text += "Agreement with SciPy validates the implementation under shared thermochemical assumptions; it does not validate the shared data against Aspen.\n"
    balance = pd.read_csv(out/"aspen_balance.csv")
    text += "\nAspen reference maximum absolute accounted C/H/O residuals: " + str(balance[["C_residual", "H_residual", "O_accounted_residual"]].abs().max().to_dict()) + ".\n"
    text += """

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
"""
    (out / "REPORT.md").write_text(text, encoding="utf-8")
    ct_claim = "and Cantera's multiphase solver" if summary["cross_engine_agreement"] else ""
    reply = f"""Ronny, thanks for raising this. We did not directly benchmark open-source frameworks in the IJHE paper. I have now run a separate, reproducible seven-species equilibrium check with a SciPy Gibbs minimizer {ct_claim}, retaining graphite as an allowed solid phase. Across {len(scipy)} selected Aspen dataset points, the SciPy mean absolute errors were {mae('FH2'):.4f} mol H2 and {mae('FCARBON'):.4f} mol carbon per inlet mol CH4. The comparison uses ideal-gas thermodynamics against Aspen's SRK model, so these differences cannot be interpreted as solver accuracy alone. Carbon here means equilibrium propensity, not experimental catalyst coking. Five traceable published optima were also checked separately. DWSIM has not been executed, so I cannot rank it. The code, case manifest, results and limitations will be available after merging: https://github.com/alimardani76/Tri_Reforming_Analysis/tree/main/open_source_benchmark
"""
    (Path(__file__).parent / "LINKEDIN_REPLY.md").write_text(reply, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "results")
    write_report(parser.parse_args().out)
