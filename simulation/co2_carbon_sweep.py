"""
Reviewer #2 Comment 6: controlled Aspen CO2-feed sweep.

Purpose
-------
Vary only Fc while holding T, P, Fw and Fo fixed, so the direct Aspen
equilibrium response of carbon to CO2 feed can be separated from SHAP
association.

Design
------
Three representative temperatures:
    600, 750, 900 C

Fixed:
    P  = 1 bar
    Fw = 0.15
    Fo = 0.0

CO2/CH4 sweep:
    Fc = 0.15, 0.30, 0.50, 0.70, 1.00

Total Aspen runs: 15

Place in:
    simulation/co2_carbon_sweep.py

Run from repository root:
    python ./simulation/co2_carbon_sweep.py

Outputs only:
    ann_optimization_results/revision_co2_sweep/co2_carbon_sweep.csv
    ann_optimization_results/revision_co2_sweep/co2_carbon_sweep_summary.csv
"""

from pathlib import Path
import argparse
import time
import traceback

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent if HERE.name.lower() == "simulation" else HERE

CAL_S_TO_KW = 4.184 / 1000.0

TEMPERATURES = [600.0, 750.0, 900.0]
FC_VALUES = [0.15, 0.30, 0.50, 0.70, 1.00]

P_FIXED = 1.0
FW_FIXED = 0.15
FO_FIXED = 0.0

COMPONENTS = ["CH4", "WATER", "CO2", "O2", "CO", "H2", "CARBON"]


def node(app, path):
    n = app.Tree.FindNode(path)
    if n is None:
        raise RuntimeError(f"Aspen node not found: {path}")
    return n


def number(n):
    v = n.Value
    if v is None:
        raise RuntimeError(f"Aspen returned no value for {n.Name}")
    v = float(v)
    if not np.isfinite(v):
        raise RuntimeError(f"Nonfinite Aspen value for {n.Name}")
    return v


def write(app, path, value):
    n = node(app, path)
    n.Value = float(value)


def set_case(app, T, Fc):
    # Feed conditions used by the supplied Aspen driver.
    write(app, r"\Data\Streams\1\Input\TEMP\MIXED", 500.0)
    write(app, r"\Data\Streams\1\Input\PRES\MIXED", 1.0)

    feed = {
        "CH4": 1.0,
        "WATER": FW_FIXED,
        "CO2": Fc,
        "O2": FO_FIXED,
        "CO": 0.0,
        "H2": 0.0,
        "CARBON": 0.0,
    }

    for component, value in feed.items():
        write(
            app,
            rf"\Data\Streams\1\Input\FLOW\MIXED\{component}",
            value,
        )

    write(app, r"\Data\Blocks\B1\Input\TEMP", T)
    write(app, r"\Data\Blocks\B1\Input\PRES", P_FIXED)


def read_output(app, component):
    # Search all MOLEFLOW substreams because carbon may be in a solid substream.
    parent = node(app, r"\Data\Streams\2\Output\MOLEFLOW")
    total = 0.0
    found = False

    for substream in parent.Elements:
        for item in substream.Elements:
            if str(item.Name).upper() == component.upper():
                total += number(item)
                found = True

    if not found:
        raise RuntimeError(f"Output component not found: {component}")

    return total


def raw_status(app):
    out = {}
    for name in ["PER_ERROR", "RUN_STATUS"]:
        p = rf"\Data\Results Summary\Run-Status\Output\{name}"
        n = app.Tree.FindNode(p)
        out[name] = str(n.Value) if n is not None else "unavailable"
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apw",
        type=Path,
        default=ROOT / "simulation" / "TRM_automation_no_S1.apw",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "ann_optimization_results" / "revision_co2_sweep",
    )
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--visible", action="store_true")
    args = parser.parse_args()

    if not args.apw.exists():
        raise FileNotFoundError(args.apw)

    import win32com.client

    args.out.mkdir(parents=True, exist_ok=True)

    rows = []

    print("Controlled Aspen Fc sweep")
    print(f"Fixed P={P_FIXED}, Fw={FW_FIXED}, Fo={FO_FIXED}")
    print(f"T values: {TEMPERATURES}")
    print(f"Fc values: {FC_VALUES}")
    print(f"Total runs: {len(TEMPERATURES) * len(FC_VALUES)}")

    for T in TEMPERATURES:
        for Fc in FC_VALUES:
            app = None
            started = time.perf_counter()

            print(f"\nT={T:.0f} C, Fc={Fc:.2f}", flush=True)

            try:
                app = win32com.client.DispatchEx("Apwn.Document")
                app.InitFromArchive2(str(args.apw.resolve()))
                app.Visible = int(args.visible)
                app.SuppressDialogs = 1
                app.Reinit()

                set_case(app, T, Fc)

                app.Engine.Run2(True)
                t0 = time.perf_counter()

                while bool(app.Engine.IsRunning):
                    if time.perf_counter() - t0 > args.timeout:
                        try:
                            app.Engine.Stop()
                        finally:
                            raise TimeoutError(
                                f"Aspen timeout at T={T}, Fc={Fc}"
                            )
                    time.sleep(0.05)

                outputs = {
                    "FCH4": read_output(app, "CH4"),
                    "FH2O": read_output(app, "WATER"),
                    "FCO2": read_output(app, "CO2"),
                    "FO2": read_output(app, "O2"),
                    "FCO": read_output(app, "CO"),
                    "FH2": read_output(app, "H2"),
                    "FCARBON": read_output(app, "CARBON"),
                }

                q_raw = number(
                    node(app, r"\Data\Blocks\B1\Output\QCALC")
                )
                Q = q_raw * CAL_S_TO_KW

                status = raw_status(app)

                row = {
                    "T": T,
                    "P": P_FIXED,
                    "Fw": FW_FIXED,
                    "Fc": Fc,
                    "Fo": FO_FIXED,
                    **outputs,
                    "Q_kW": Q,
                    "PER_ERROR": status["PER_ERROR"],
                    "RUN_STATUS": status["RUN_STATUS"],
                    "elapsed_s": time.perf_counter() - started,
                }
                rows.append(row)

                pd.DataFrame(rows).to_csv(
                    args.out / "co2_carbon_sweep.csv",
                    index=False,
                    float_format="%.17g",
                )

                print(
                    f"  carbon={outputs['FCARBON']:.9g}, "
                    f"CO={outputs['FCO']:.9g}, "
                    f"CO2_out={outputs['FCO2']:.9g}, "
                    f"H2={outputs['FH2']:.9g}, "
                    f"Q={Q:.6g} kW"
                )

            finally:
                if app is not None:
                    try:
                        app.Close()
                    except Exception:
                        pass

    df = pd.DataFrame(rows)

    summary_rows = []
    for T, g in df.groupby("T", sort=True):
        g = g.sort_values("Fc")

        c0 = float(g.iloc[0]["FCARBON"])
        c1 = float(g.iloc[-1]["FCARBON"])

        # Simple monotonicity descriptor.
        diffs = np.diff(g["FCARBON"].to_numpy(float))
        if np.all(diffs <= 1e-12):
            direction = "nonincreasing"
        elif np.all(diffs >= -1e-12):
            direction = "nondecreasing"
        else:
            direction = "nonmonotonic"

        summary_rows.append({
            "T": T,
            "P": P_FIXED,
            "Fw": FW_FIXED,
            "Fo": FO_FIXED,
            "carbon_at_Fc_0.15": c0,
            "carbon_at_Fc_1.00": c1,
            "delta_carbon_Fc1_minus_Fc0.15": c1 - c0,
            "response_direction": direction,
            "minimum_carbon": float(g["FCARBON"].min()),
            "maximum_carbon": float(g["FCARBON"].max()),
        })

    summary = pd.DataFrame(summary_rows)
    summary.to_csv(
        args.out / "co2_carbon_sweep_summary.csv",
        index=False,
        float_format="%.17g",
    )

    print("\n============================================================")
    print("CONTROLLED CO2 EFFECT ON EQUILIBRIUM CARBON")
    print("============================================================")
    print(summary.to_string(index=False))

    print("\nSaved:")
    print(args.out / "co2_carbon_sweep.csv")
    print(args.out / "co2_carbon_sweep_summary.csv")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)