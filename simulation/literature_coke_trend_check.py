"""
Small literature-consistency check for Reviewer #2 Comment 7.

This does NOT claim quantitative experimental validation of coke.
It asks only whether the Aspen equilibrium model reproduces the same
DIRECTIONAL tendencies reported experimentally by Lino et al. (2020):
  - more O2 -> less coke
  - more steam -> less coke

Experimental source:
A. V. P. Lino, E. M. Assaf, J. M. Assaf,
Energy & Fuels 2020, 34, 16522-16531.
DOI: 10.1021/acs.energyfuels.0c02895

The paper reports tests at 750 C and 1 atm and identifies
CH4/CO2/H2O/O2/N2 = 3:1.5:1.4:0.25:1 as its most stable condition.

Our Aspen model has no N2 in its modeled feed set, so this script uses
the reactive-gas ratios normalized to CH4 = 1:
  Fc = 0.5
  Fw = 1.4/3 = 0.4666667
  Fo = 0.25/3 = 0.0833333

The two sweeps are controlled analogues, not exact reproductions of
the experimental campaign, because the abstract does not specify the
fixed co-feed value used in each separate experimental sweep and N2
is absent from the current Aspen component set.

Place in:
    simulation/literature_coke_trend_check.py

Run:
    python ./simulation/literature_coke_trend_check.py

Outputs:
    ann_optimization_results/revision_literature_coke/
        literature_coke_sweeps.csv
        literature_coke_summary.csv
"""

from pathlib import Path
import argparse
import time
import traceback

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent if HERE.name.lower() == "simulation" else HERE

T = 750.0
P = 1.0
FC = 0.5

FW_ANCHOR = 1.4 / 3.0
FO_ANCHOR = 0.25 / 3.0

# Experimental ranges reported by Lino et al.
O2_CO2_RATIOS = [0.0, 0.17, 0.50, 1.00, 1.50]
H2O_CO2_RATIOS = [0.0, 0.35, 0.70, 1.05, 1.40]

CAL_S_TO_KW = 4.184 / 1000.0


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
    node(app, path).Value = float(value)


def set_case(app, fw, fc, fo):
    # Feed state inherited from the supplied Aspen automation.
    write(app, r"\Data\Streams\1\Input\TEMP\MIXED", 500.0)
    write(app, r"\Data\Streams\1\Input\PRES\MIXED", 1.0)

    feed = {
        "CH4": 1.0,
        "WATER": fw,
        "CO2": fc,
        "O2": fo,
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
    write(app, r"\Data\Blocks\B1\Input\PRES", P)


def output_component(app, component):
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


def run_case(app_path, fw, fc, fo, timeout, visible):
    import win32com.client

    app = None
    try:
        app = win32com.client.DispatchEx("Apwn.Document")
        app.InitFromArchive2(str(app_path.resolve()))
        app.Visible = int(visible)
        app.SuppressDialogs = 1
        app.Reinit()

        set_case(app, fw, fc, fo)

        app.Engine.Run2(True)
        t0 = time.perf_counter()

        while bool(app.Engine.IsRunning):
            if time.perf_counter() - t0 > timeout:
                try:
                    app.Engine.Stop()
                finally:
                    raise TimeoutError(
                        f"Aspen timeout for Fw={fw}, Fc={fc}, Fo={fo}"
                    )
            time.sleep(0.05)

        out = {
            "FCH4": output_component(app, "CH4"),
            "FH2O": output_component(app, "WATER"),
            "FCO2": output_component(app, "CO2"),
            "FO2": output_component(app, "O2"),
            "FCO": output_component(app, "CO"),
            "FH2": output_component(app, "H2"),
            "FCARBON": output_component(app, "CARBON"),
        }

        q_raw = number(node(app, r"\Data\Blocks\B1\Output\QCALC"))
        out["Q_kW"] = q_raw * CAL_S_TO_KW

        return out

    finally:
        if app is not None:
            try:
                app.Close()
            except Exception:
                pass


def trend(values):
    d = np.diff(np.asarray(values, dtype=float))
    if np.all(d <= 1e-12):
        return "nonincreasing"
    if np.all(d >= -1e-12):
        return "nondecreasing"
    return "nonmonotonic"


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
        default=ROOT / "ann_optimization_results" / "revision_literature_coke",
    )
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--visible", action="store_true")
    args = parser.parse_args()

    if not args.apw.exists():
        raise FileNotFoundError(args.apw)

    args.out.mkdir(parents=True, exist_ok=True)

    rows = []

    print("Lino et al. (2020) directional coke-trend check")
    print("750 C, 1 atm, CH4 basis = 1, Fc = 0.5")
    print("N2 from the experimental feed is omitted because it is not")
    print("part of the current Aspen component set.")
    print()

    # --------------------------------------------------------
    # Sweep 1: O2/CO2, hold steam at the reported stable-feed value
    # --------------------------------------------------------
    print("O2 sweep")
    for ratio in O2_CO2_RATIOS:
        fo = ratio * FC

        print(
            f"  O2/CO2={ratio:.2f} -> "
            f"Fw={FW_ANCHOR:.6f}, Fc={FC:.6f}, Fo={fo:.6f}",
            flush=True,
        )

        out = run_case(
            args.apw,
            FW_ANCHOR,
            FC,
            fo,
            args.timeout,
            args.visible,
        )

        rows.append({
            "sweep": "O2_CO2",
            "sweep_ratio": ratio,
            "T": T,
            "P": P,
            "Fw": FW_ANCHOR,
            "Fc": FC,
            "Fo": fo,
            **out,
        })

        print(f"    Aspen carbon = {out['FCARBON']:.9g}")

    # --------------------------------------------------------
    # Sweep 2: H2O/CO2, hold oxygen at stable-feed value
    # --------------------------------------------------------
    print("\nSteam sweep")
    for ratio in H2O_CO2_RATIOS:
        fw = ratio * FC

        print(
            f"  H2O/CO2={ratio:.2f} -> "
            f"Fw={fw:.6f}, Fc={FC:.6f}, Fo={FO_ANCHOR:.6f}",
            flush=True,
        )

        out = run_case(
            args.apw,
            fw,
            FC,
            FO_ANCHOR,
            args.timeout,
            args.visible,
        )

        rows.append({
            "sweep": "H2O_CO2",
            "sweep_ratio": ratio,
            "T": T,
            "P": P,
            "Fw": fw,
            "Fc": FC,
            "Fo": FO_ANCHOR,
            **out,
        })

        print(f"    Aspen carbon = {out['FCARBON']:.9g}")

    df = pd.DataFrame(rows)
    df.to_csv(
        args.out / "literature_coke_sweeps.csv",
        index=False,
        float_format="%.17g",
    )

    summaries = []

    for name, g in df.groupby("sweep", sort=False):
        g = g.sort_values("sweep_ratio")
        carbon = g["FCARBON"].to_numpy(float)

        first = float(carbon[0])
        last = float(carbon[-1])

        if first > 0:
            reduction_fraction = (first - last) / first
            reduction_percent = 100.0 * reduction_fraction
            fold_reduction = first / last if last > 0 else np.inf
        else:
            reduction_fraction = np.nan
            reduction_percent = np.nan
            fold_reduction = np.nan

        expected = "carbon decreases as ratio increases"
        observed = trend(carbon)

        summaries.append({
            "sweep": name,
            "expected_experimental_direction": expected,
            "Aspen_response_direction": observed,
            "carbon_at_low_ratio": first,
            "carbon_at_high_ratio": last,
            "delta_carbon_high_minus_low": last - first,
            "Aspen_carbon_reduction_percent": reduction_percent,
            "Aspen_fold_reduction": fold_reduction,
            "direction_matches_experiment": observed == "nonincreasing",
        })

    summary = pd.DataFrame(summaries)
    summary.to_csv(
        args.out / "literature_coke_summary.csv",
        index=False,
        float_format="%.17g",
    )

    print("\n============================================================")
    print("LITERATURE DIRECTIONAL CONSISTENCY")
    print("============================================================")
    print(summary.to_string(index=False))

    print("\nInterpretation rule:")
    print("  MATCH = useful qualitative support only.")
    print("  MISMATCH = do not use this paper as validation of our carbon trend.")
    print("  Do not compare Aspen fold reductions quantitatively with experimental")
    print("  coke amounts because equilibrium carbon != deposited catalyst coke.")

    print("\nSaved:")
    print(args.out / "literature_coke_sweeps.csv")
    print(args.out / "literature_coke_summary.csv")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)