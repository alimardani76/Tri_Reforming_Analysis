"""Select traceable cases, execute equilibria, and regenerate the full evidence."""
import argparse
import contextlib
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter
import warnings

import numpy as np
import pandas as pd

from cases import INPUTS, read_grid, select_cases
from equilibrium import A, FLOW_KEYS, feed, solve, solve_cantera
from reporting import derived, pressure_metrics, summarize

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def sha256(path):
    # Git converts text line endings on Windows; canonical LF hashes travel with the commit.
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def run(args):
    out = args.out.resolve()
    if not out.is_relative_to(HERE):
        raise ValueError("Keep generated scientific work inside open_source_benchmark/")
    out.mkdir(parents=True, exist_ok=True)
    start = perf_counter()
    grid = read_grid(ROOT / "data/added2.csv")
    optima = pd.read_csv(ROOT / "results/revision_r2/aspen_results.csv")
    manifest, strata = select_cases(grid, optima)
    manifest.to_csv(out / "case_manifest.csv", index=False, float_format="%.17g")
    pd.DataFrame(strata).to_csv(out / "strata.csv", index=False)
    engines = {"scipy": solve}
    cantera_status = "not requested (--cantera enables execution)"
    if args.cantera:
        try:
            import cantera
            cantera_status = "executed: " + cantera.__version__
            engines["cantera"] = solve_cantera
        except ImportError as error:
            cantera_status = "not executed: " + str(error)
    raw, logs = [], []
    for engine, solver in engines.items():
        for row in manifest.to_dict("records"):
            record = {k: row[k] for k in ["case_id", "source", "source_row", "group"]+INPUTS}
            record.update(engine=engine, cohort="optima" if row["group"] == "published_optima" else "grid")
            record.update({"aspen_"+k: row[k] for k in FLOW_KEYS if k in row})
            # Grid has no FO2 column. It remains unknown, never inferred as measured zero.
            record.update(derived(record, "aspen_"))
            captured = io.StringIO()
            case_start = perf_counter()
            with warnings.catch_warnings(record=True) as caught, contextlib.redirect_stdout(captured):
                warnings.simplefilter("always")
                try:
                    n, diagnostics = solver(*(row[k] for k in INPUTS))
                    record.update({"pred_"+k: float(n[i]) for i, k in enumerate(FLOW_KEYS)})
                    record.update(derived(record, "pred_"))
                    record.update(diagnostics, status="ok", error="")
                except Exception as error:
                    record.update(status="failed", error=f"{type(error).__name__}: {error}",
                                  elapsed_s=perf_counter()-case_start)
                messages = [str(w.message) for w in caught]
            if captured.getvalue().strip():
                messages.append(captured.getvalue().strip())
            for message in messages:
                logs.append(dict(engine=engine, case_id=row["case_id"], message=message))
            raw.append(record)
        print(f"{engine}: {sum(r['status']=='ok' for r in raw if r['engine']==engine)}/{len(manifest)} successful", flush=True)
    raw = pd.DataFrame(raw)
    raw.to_csv(out / "predictions.csv", index=False, float_format="%.17g")
    metrics, confusion, runtime = summarize(raw)
    metrics.to_csv(out / "metrics.csv", index=False, float_format="%.17g")
    confusion.to_csv(out / "carbon_confusion.csv", index=False)
    pressure_metrics(raw).to_csv(out / "pressure_metrics.csv", index=False, float_format="%.17g")
    raw[raw.status != "ok"].to_csv(out / "failures.csv", index=False)
    (out / "warnings.json").write_text(json.dumps(logs, indent=2)+"\n")
    # Aspen grid: C/H closure and accounted O residual only (outlet O2 absent).
    residuals = []
    for row in manifest.to_dict("records"):
        known = np.array([row[k] if k != "FO2" else (row.get(k) if pd.notna(row.get(k)) else 0.) for k in FLOW_KEYS])
        difference = A @ known - A @ feed(row["Fw"], row["Fc"], row["Fo"])
        residuals.append(dict(case_id=row["case_id"], C_residual=difference[0], H_residual=difference[1],
                              O_accounted_residual=difference[2], O2_known=bool(pd.notna(row.get("FO2")))))
    pd.DataFrame(residuals).to_csv(out / "aspen_balance.csv", index=False, float_format="%.17g")
    pairs = raw[raw.status == "ok"].pivot(index="case_id", columns="engine", values=["pred_"+k for k in FLOW_KEYS])
    cross = None
    if {"scipy", "cantera"} <= set(raw.engine):
        differences = []
        for key in FLOW_KEYS:
            both = pairs["pred_"+key].dropna(subset=["scipy", "cantera"])
            differences.append(dict(output=key, N=len(both), max_abs_difference=float(abs(both.scipy-both.cantera).max())))
        cross = differences
        pd.DataFrame(cross).to_csv(out / "engine_agreement.csv", index=False, float_format="%.17g")
    try:
        commit = subprocess.check_output(["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unavailable"
    summary = dict(command="python " + " ".join(["open_source_benchmark/run_benchmark.py"] + sys.argv[1:]),
                   base_commit=commit, source_rows=len(grid), grid_N=int((manifest.group != "published_optima").sum()),
                   optima_N=int((manifest.group == "published_optima").sum()), exclusions=0,
                   cantera=cantera_status, dwsim="not executed; no configured executable/flowsheet",
                   runtime=runtime, cross_engine_agreement=cross, warning_count=len(logs),
                   cantera_fallback_N=int((raw.get("cantera_method", pd.Series(dtype=str)) == "gibbs-fallback").sum()),
                   versions={k: importlib.metadata.version(k) for k in ["numpy", "scipy", "pandas", "matplotlib", "pytest"]},
                   environment=dict(python=sys.version, platform=platform.platform(), processor=platform.processor(),
                                    processor_identifier=os.environ.get("PROCESSOR_IDENTIFIER", "unknown"), logical_cpus=os.cpu_count()),
                   source_sha256={p.relative_to(ROOT).as_posix(): sha256(p) for p in [ROOT/"data/added2.csv", ROOT/"results/revision_r2/aspen_results.csv", HERE/"thermo.json"]},
                   hash_normalization="source_sha256 and implementation_sha256 normalize CRLF to LF; BOM retained",
                   source_raw_sha256={p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                      for p in [ROOT/"data/added2.csv", ROOT/"results/revision_r2/aspen_results.csv"]},
                   implementation_sha256={p.relative_to(HERE).as_posix(): sha256(p)
                                           for p in sorted(list(HERE.glob("*.py")) + list((HERE/"tests").glob("*.py")))},
                   elapsed_before_figures_s=perf_counter()-start)
    (out / "summary.json").write_text(json.dumps(summary, indent=2)+"\n")
    from make_figures import make_figures
    make_figures(out)
    from write_report import write_report
    write_report(out)
    return int((raw.status != "ok").any())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cantera", action="store_true", help="Execute the optional seven-species multiphase Cantera engine")
    parser.add_argument("--out", type=Path, default=HERE / "results")
    raise SystemExit(run(parser.parse_args()))
