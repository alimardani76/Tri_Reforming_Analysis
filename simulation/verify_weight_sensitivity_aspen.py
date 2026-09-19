"""
Aspen verification of the 11 normalized weight-sensitivity optima.

Purpose
-------
Reviewer #2, Comment 3 asks for a true weight-sensitivity analysis with
dimensionless objective components while keeping the objective structure fixed.

This script DOES NOT retrain or re-optimize anything. It:
  1. reads weight_sensitivity_best.csv;
  2. re-evaluates the 11 ANN-selected operating points in Aspen Plus;
  3. checks C/H/O elemental closure for every point;
  4. compares ANN and Aspen outputs;
  5. recomputes the normalized weighted objective using Aspen outputs and
     the exact reference ranges used during optimization;
  6. writes four compact CSV files only.

Place this file in:
    simulation/verify_weight_sensitivity_aspen.py

Run from repository root:
    python ./simulation/verify_weight_sensitivity_aspen.py

Required existing files:
    simulation/TRM_automation_no_S1.apw
    ann_optimization_results/revision_weight_sensitivity/weight_sensitivity_best.csv
    ann_optimization_results/revision_weight_sensitivity/normalization_ranges.csv

Requires:
    numpy, pandas, pywin32, Aspen Plus
"""

from pathlib import Path
import argparse
import time
import traceback

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent if HERE.name.lower() == "simulation" else HERE

INPUTS = ["T", "P", "Fw", "Fc", "Fo"]
OUTPUTS = ["FCH4", "FH2O", "FCO2", "FCO", "FH2", "FCARBON", "Q"]

WEIGHT_COLS = [
    "w_XCH4", "w_H2", "w_CO", "w_Coke", "w_CO2", "w_Duty"
]

COMPONENTS = {
    "CH4": "FCH4",
    "WATER": "FH2O",
    "CO2": "FCO2",
    "O2": "FO2",
    "CO": "FCO",
    "H2": "FH2",
    "CARBON": "FCARBON",
}

# C, H, O atoms in each modeled species.
ATOMS = {
    "FCH4": (1, 4, 0),
    "FH2O": (0, 2, 1),
    "FCO2": (1, 0, 2),
    "FO2": (0, 0, 2),
    "FCO": (1, 0, 1),
    "FH2": (0, 2, 0),
    "FCARBON": (1, 0, 0),
}

CAL_S_TO_KW = 4.184 / 1000.0


# ============================================================
# Aspen helpers
# ============================================================

def node(app, path):
    result = app.Tree.FindNode(path)
    if result is None:
        raise RuntimeError(f"Aspen node not found: {path}")
    return result


def number(n):
    if n.Value is None:
        raise RuntimeError(f"Aspen returned no value for {n.Name}")
    value = float(n.Value)
    if not np.isfinite(value):
        raise RuntimeError(f"Nonfinite Aspen value for {n.Name}")
    return value


def write(app, path, value):
    n = node(app, path)
    n.Value = float(value)
    if not np.isclose(number(n), value, atol=1e-9, rtol=1e-9):
        raise RuntimeError(f"Input readback does not match: {path}")


def nominal_feed(p):
    return {
        "FCH4": 1.0,
        "FH2O": p["Fw"],
        "FCO2": p["Fc"],
        "FO2": p["Fo"],
        "FCO": 0.0,
        "FH2": 0.0,
        "FCARBON": 0.0,
    }


def set_case(app, p):
    # Feed conditions inherited from supplied Aspen automation.
    write(app, r"\Data\Streams\1\Input\TEMP\MIXED", 500.0)
    write(app, r"\Data\Streams\1\Input\PRES\MIXED", 1.0)

    feed = nominal_feed(p)
    for component, key in COMPONENTS.items():
        write(
            app,
            rf"\Data\Streams\1\Input\FLOW\MIXED\{component}",
            feed[key],
        )

    write(app, r"\Data\Blocks\B1\Input\TEMP", p["T"])
    write(app, r"\Data\Blocks\B1\Input\PRES", p["P"])


def stream_flows(app, stream):
    """
    Sum every MOLEFLOW substream for the seven modeled chemical species.
    Unknown nonzero species cause a hard failure rather than being ignored.
    """
    parent = node(app, rf"\Data\Streams\{stream}\Output\MOLEFLOW")

    totals = dict.fromkeys(ATOMS, 0.0)
    found = set()
    count = 0

    for substream in parent.Elements:
        for component in substream.Elements:
            count += 1
            name = str(component.Name).upper()
            value = number(component)

            if name not in COMPONENTS:
                if abs(value) > 1e-14:
                    raise RuntimeError(
                        f"Unmapped nonzero component {name} in stream {stream}, "
                        f"substream {substream.Name}: {value}"
                    )
                continue

            key = COMPONENTS[name]
            totals[key] += value
            found.add(key)

    if count == 0:
        raise RuntimeError(f"No component MOLEFLOW results for stream {stream}")

    missing = set(ATOMS) - found
    if missing:
        raise RuntimeError(
            f"Missing modeled species results in stream {stream}: {sorted(missing)}"
        )

    return totals


def atom_totals(flows):
    return np.array([
        sum(flows.get(key, 0.0) * counts[i] for key, counts in ATOMS.items())
        for i in range(3)
    ])


def balance_records(case, feed, product, atol, rtol):
    incoming = atom_totals(feed)
    outgoing = atom_totals(product)

    records = []
    for i, element in enumerate(["C", "H", "O"]):
        residual = outgoing[i] - incoming[i]
        allowed = atol + rtol * abs(incoming[i])

        records.append({
            "case": case,
            "element": element,
            "atoms_in": incoming[i],
            "atoms_out": outgoing[i],
            "residual_out_minus_in": residual,
            "relative_residual": (
                residual / incoming[i] if incoming[i] != 0 else np.nan
            ),
            "residual_percent": (
                100.0 * residual / incoming[i] if incoming[i] != 0 else np.nan
            ),
            "allowed_absolute_residual": allowed,
            "status": "PASS" if abs(residual) <= allowed else "FAIL",
        })

    return records


def raw_run_status(app):
    status = {}
    for name in ["PER_ERROR", "RUN_STATUS"]:
        p = rf"\Data\Results Summary\Run-Status\Output\{name}"
        n = app.Tree.FindNode(p)
        status[name] = str(n.Value) if n is not None else "unavailable"
    return status


# ============================================================
# Objective helpers
# ============================================================

def derived_metrics(p, x):
    return {
        "XCH4": 1.0 - x["FCH4"],
        "YCO": x["FCO"],
        "YH2": x["FH2"],
        "Coke": max(x["FCARBON"], 0.0),
        "E_CO2": x["FCO2"] - p["Fc"],
        "AbsQ": abs(x["Q"]),
    }


def load_ranges(path):
    r = pd.read_csv(path)

    required = {
        "component", "reference_min", "reference_max", "reference_span"
    }
    missing = required - set(r.columns)
    if missing:
        raise ValueError(
            f"Normalization-range CSV missing columns: {sorted(missing)}"
        )

    expected = {"XCH4", "YCO", "YH2", "Coke", "E_CO2", "AbsQ"}
    if set(r["component"]) != expected:
        raise ValueError(
            "Normalization-range CSV must contain exactly: "
            + ", ".join(sorted(expected))
        )

    ranges = {}
    for _, row in r.iterrows():
        name = str(row["component"])
        lo = float(row["reference_min"])
        hi = float(row["reference_max"])

        if not np.isfinite([lo, hi]).all() or hi <= lo:
            raise ValueError(f"Invalid normalization range for {name}: {lo}, {hi}")

        ranges[name] = (lo, hi)

    return ranges


def z(value, name, ranges):
    lo, hi = ranges[name]
    return (float(value) - lo) / (hi - lo)


def normalized_objective(metrics, weights, ranges):
    """
    Same fixed normalized objective used for Reviewer #2 Comment 3:

      J = -wX*z(XCH4)
          -wCO*z(YCO)
          -wH2*z(YH2)
          +wC*z(Coke)
          +wE*z(E_CO2)
          +wQ*z(|Q|)
    """
    return (
        -weights["w_XCH4"] * z(metrics["XCH4"], "XCH4", ranges)
        -weights["w_CO"]   * z(metrics["YCO"], "YCO", ranges)
        -weights["w_H2"]   * z(metrics["YH2"], "YH2", ranges)
        +weights["w_Coke"] * z(metrics["Coke"], "Coke", ranges)
        +weights["w_CO2"]  * z(metrics["E_CO2"], "E_CO2", ranges)
        +weights["w_Duty"] * z(metrics["AbsQ"], "AbsQ", ranges)
    )


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--apw",
        type=Path,
        default=ROOT / "simulation" / "TRM_automation_no_S1.apw",
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=(
            ROOT
            / "ann_optimization_results"
            / "revision_weight_sensitivity"
            / "weight_sensitivity_best.csv"
        ),
    )
    parser.add_argument(
        "--ranges",
        type=Path,
        default=(
            ROOT
            / "ann_optimization_results"
            / "revision_weight_sensitivity"
            / "normalization_ranges.csv"
        ),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=(
            ROOT
            / "ann_optimization_results"
            / "revision_weight_sensitivity"
            / "aspen_verification"
        ),
    )

    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--balance-atol", type=float, default=1e-6)
    parser.add_argument("--balance-rtol", type=float, default=1e-6)
    parser.add_argument("--visible", action="store_true")

    args = parser.parse_args()

    if args.timeout <= 0:
        parser.error("Timeout must be positive.")
    if min(args.balance_atol, args.balance_rtol) < 0:
        parser.error("Balance tolerances must be nonnegative.")

    for p in [args.apw, args.cases, args.ranges]:
        if not p.exists():
            raise FileNotFoundError(p)

    df = pd.read_csv(args.cases)
    ranges = load_ranges(args.ranges)

    needed = ["case"] + INPUTS + OUTPUTS + WEIGHT_COLS + ["objective"]
    missing = set(needed) - set(df.columns)
    if missing:
        raise ValueError(
            f"Weight-sensitivity CSV missing columns: {sorted(missing)}"
        )

    if df["case"].duplicated().any():
        raise ValueError("Each weight-sensitivity case must appear exactly once.")

    if "baseline" not in set(df["case"].astype(str)):
        raise ValueError("A case named 'baseline' is required.")

    numeric_cols = INPUTS + OUTPUTS + WEIGHT_COLS + ["objective"]
    if not np.isfinite(df[numeric_cols].to_numpy(dtype=float)).all():
        raise ValueError("Weight-sensitivity CSV contains missing/nonfinite values.")

    if (df[["Fw", "Fc", "Fo"]] < 0).any().any() or (df["P"] <= 0).any():
        raise ValueError("Invalid feed ratio or pressure in selected cases.")

    import win32com.client

    args.out.mkdir(parents=True, exist_ok=True)

    # Clean only outputs produced by THIS script.
    output_files = {
        "results": args.out / "weight_sensitivity_aspen.csv",
        "compare": args.out / "weight_sensitivity_ann_vs_aspen.csv",
        "balances": args.out / "weight_sensitivity_balances.csv",
        "summary": args.out / "weight_sensitivity_summary.csv",
    }
    for p in output_files.values():
        if p.exists():
            p.unlink()

    results = []
    comparisons = []
    balances = []

    print(f"Checking {len(df)} normalized weight-sensitivity optima in Aspen.")
    print("No ANN training and no optimization will be performed.")
    print(
        f"Balance tolerance: {args.balance_atol:g} + "
        f"{args.balance_rtol:g} * abs(atoms_in)"
    )

    # Preserve file order: baseline, H2, CO, Coke, CO2, Duty cases.
    for _, record in df.iterrows():
        case = str(record["case"])
        p = {key: float(record[key]) for key in INPUTS}
        ann = {key: float(record[key]) for key in OUTPUTS}
        weights = {key: float(record[key]) for key in WEIGHT_COLS}

        ann_metrics = derived_metrics(p, ann)
        ann_obj_recomputed = normalized_objective(
            ann_metrics, weights, ranges
        )

        # Sanity check: the CSV's optimization objective should match
        # recomputation using the same saved reference ranges.
        objective_from_csv = float(record["objective"])
        objective_diff = ann_obj_recomputed - objective_from_csv

        if abs(objective_diff) > 5e-5:
            raise RuntimeError(
                f"{case}: recomputed ANN objective ({ann_obj_recomputed}) "
                f"does not match CSV objective ({objective_from_csv}); "
                f"difference={objective_diff}. Stop before Aspen verification."
            )

        app = None
        started = time.perf_counter()

        print(f"\n{case}: {p}", flush=True)

        try:
            app = win32com.client.DispatchEx("Apwn.Document")
            app.InitFromArchive2(str(args.apw.resolve()))
            app.Visible = int(args.visible)
            app.SuppressDialogs = 1
            app.Reinit()

            set_case(app, p)

            app.Engine.Run2(True)
            solve_start = time.perf_counter()

            while bool(app.Engine.IsRunning):
                if time.perf_counter() - solve_start > args.timeout:
                    try:
                        app.Engine.Stop()
                    finally:
                        raise TimeoutError(
                            f"{case}: Aspen exceeded {args.timeout}s"
                        )
                time.sleep(0.05)

            status = raw_run_status(app)

            feed = stream_flows(app, "1")
            product = stream_flows(app, "2")
            requested_feed = nominal_feed(p)

            for key in requested_feed:
                if not np.isclose(
                    feed[key],
                    requested_feed[key],
                    atol=1e-6,
                    rtol=1e-6,
                ):
                    raise RuntimeError(
                        f"{case}: actual feed differs from requested feed "
                        f"for {key}: requested={requested_feed[key]}, "
                        f"actual={feed[key]}"
                    )

            q_raw = number(
                node(app, r"\Data\Blocks\B1\Output\QCALC")
            )
            product["Q"] = q_raw * CAL_S_TO_KW

            case_balances = balance_records(
                case,
                feed,
                product,
                args.balance_atol,
                args.balance_rtol,
            )
            balances.extend(case_balances)

            closure = all(r["status"] == "PASS" for r in case_balances)

            aspen_metrics = derived_metrics(p, product)
            aspen_obj = normalized_objective(
                aspen_metrics, weights, ranges
            )

            # ANN vs Aspen comparison for every surrogate output.
            for key in OUTPUTS:
                error = ann[key] - product[key]

                comparisons.append({
                    "case": case,
                    "variable": key,
                    "ann": ann[key],
                    "aspen": product[key],
                    "signed_error_ann_minus_aspen": error,
                    "absolute_error": abs(error),
                    "relative_error_percent": (
                        100.0 * error / abs(product[key])
                        if abs(product[key]) > 1e-12
                        else np.nan
                    ),
                })

            result = {
                "case": case,
                **weights,
                **p,

                # ANN optimization objective from original sensitivity run.
                "objective_ann_csv": objective_from_csv,
                "objective_ann_recomputed": ann_obj_recomputed,

                # Direct Aspen-evaluated normalized objective.
                "objective_aspen": aspen_obj,
                "objective_aspen_minus_ann": aspen_obj - ann_obj_recomputed,

                # Aspen species outputs.
                **{f"Aspen_{k}": product[k] for k in OUTPUTS},
                "Aspen_FO2": product["FO2"],

                # Aspen-derived performance quantities.
                "Aspen_XCH4": aspen_metrics["XCH4"],
                "Aspen_YCO": aspen_metrics["YCO"],
                "Aspen_YH2": aspen_metrics["YH2"],
                "Aspen_Coke": aspen_metrics["Coke"],
                "Aspen_E_CO2": aspen_metrics["E_CO2"],
                "Aspen_AbsQ": aspen_metrics["AbsQ"],

                # Same dimensionless components used in optimization.
                "Aspen_z_XCH4": z(
                    aspen_metrics["XCH4"], "XCH4", ranges
                ),
                "Aspen_z_YCO": z(
                    aspen_metrics["YCO"], "YCO", ranges
                ),
                "Aspen_z_YH2": z(
                    aspen_metrics["YH2"], "YH2", ranges
                ),
                "Aspen_z_Coke": z(
                    aspen_metrics["Coke"], "Coke", ranges
                ),
                "Aspen_z_E_CO2": z(
                    aspen_metrics["E_CO2"], "E_CO2", ranges
                ),
                "Aspen_z_AbsQ": z(
                    aspen_metrics["AbsQ"], "AbsQ", ranges
                ),

                "atom_closure": "PASS" if closure else "FAIL",
                "minimum_aspen_species": min(
                    product[k] for k in ATOMS
                ),
                "elapsed_s": time.perf_counter() - started,
                "PER_ERROR": status["PER_ERROR"],
                "RUN_STATUS": status["RUN_STATUS"],
            }

            results.append(result)

            # Save incrementally after every completed Aspen point.
            pd.DataFrame(results).to_csv(
                output_files["results"],
                index=False,
                float_format="%.17g",
            )
            pd.DataFrame(comparisons).to_csv(
                output_files["compare"],
                index=False,
                float_format="%.17g",
            )
            pd.DataFrame(balances).to_csv(
                output_files["balances"],
                index=False,
                float_format="%.17g",
            )

            print(
                f"  H2={product['FH2']:.9g}, "
                f"CO={product['FCO']:.9g}, "
                f"carbon={product['FCARBON']:.9g}, "
                f"Q={product['Q']:.9g} kW"
            )
            print(
                f"  normalized objective: "
                f"ANN={ann_obj_recomputed:.8f}, "
                f"Aspen={aspen_obj:.8f}, "
                f"delta={aspen_obj-ann_obj_recomputed:+.3e}"
            )

            for b in case_balances:
                print(
                    f"  {b['element']}: "
                    f"residual={b['residual_out_minus_in']:+.3e} "
                    f"-> {b['status']}"
                )

        finally:
            if app is not None:
                try:
                    app.Close()
                except Exception:
                    pass

    # ========================================================
    # Compact reviewer-facing summary
    # ========================================================

    result_df = pd.DataFrame(results)

    baseline = result_df.loc[
        result_df["case"] == "baseline"
    ].iloc[0]

    # Shift of each Aspen-verified output from the Aspen baseline.
    summary_rows = []

    for _, r in result_df.iterrows():
        summary_rows.append({
            "case": r["case"],
            **{w: r[w] for w in WEIGHT_COLS},
            **{x: r[x] for x in INPUTS},

            "XCH4_Aspen": r["Aspen_XCH4"],
            "YCO_Aspen": r["Aspen_YCO"],
            "YH2_Aspen": r["Aspen_YH2"],
            "Coke_Aspen": r["Aspen_Coke"],
            "E_CO2_Aspen": r["Aspen_E_CO2"],
            "Q_Aspen_kW": r["Aspen_Q"],

            "objective_ANN": r["objective_ann_recomputed"],
            "objective_Aspen": r["objective_aspen"],
            "objective_delta_Aspen_minus_ANN":
                r["objective_aspen_minus_ann"],

            "dXCH4_from_baseline": (
                r["Aspen_XCH4"] - baseline["Aspen_XCH4"]
            ),
            "dYCO_from_baseline": (
                r["Aspen_YCO"] - baseline["Aspen_YCO"]
            ),
            "dYH2_from_baseline": (
                r["Aspen_YH2"] - baseline["Aspen_YH2"]
            ),
            "dCoke_from_baseline": (
                r["Aspen_Coke"] - baseline["Aspen_Coke"]
            ),
            "dE_CO2_from_baseline": (
                r["Aspen_E_CO2"] - baseline["Aspen_E_CO2"]
            ),
            "dQ_from_baseline_kW": (
                r["Aspen_Q"] - baseline["Aspen_Q"]
            ),

            "atom_closure": r["atom_closure"],
            "PER_ERROR": r["PER_ERROR"],
            "RUN_STATUS": r["RUN_STATUS"],
        })

    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(
        output_files["summary"],
        index=False,
        float_format="%.17g",
    )

    print("\n============================================================")
    print("ASPEN-VERIFIED WEIGHT-SENSITIVITY SUMMARY")
    print("============================================================")

    print(
        summary_df[
            [
                "case",
                "w_H2", "w_CO", "w_Coke", "w_CO2", "w_Duty",
                "XCH4_Aspen", "YCO_Aspen", "YH2_Aspen",
                "Coke_Aspen", "E_CO2_Aspen", "Q_Aspen_kW",
                "objective_ANN", "objective_Aspen",
                "atom_closure",
            ]
        ].to_string(index=False)
    )

    print(f"\nSaved only these four files in:\n{args.out.resolve()}")
    for p in output_files.values():
        print(" ", p.name)

    if not (result_df["atom_closure"] == "PASS").all():
        raise SystemExit(
            "One or more Aspen points failed elemental closure."
        )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)