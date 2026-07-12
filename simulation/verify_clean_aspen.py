"""
verify_clean_aspen.py
Validate the clean Aspen file (S-1 removed) against added2.csv.
Feed fixed at 500 C / 1 bar / CH4=1 kmol/h. Vary B1 T,P and feed WATER,CO2,O2.
Q_kW = QCALC_cal_per_s * 4.184 / 1000
"""

from pathlib import Path
import time
import traceback
import numpy as np
import pandas as pd

# --- paths resolve relative to this script; no manual editing needed ---
HERE = Path(__file__).resolve().parent           # .../simulation
ROOT = HERE.parent                                # repo root
CLEAN_APW = HERE / "TRM_automation_no_S1.apw"     # same folder
DATA_CSV  = ROOT / "data" / "added2.csv"

FEED_T_C = 500.0
FEED_P_BAR = 1.0
FEED_CH4 = 1.0
CAL_S_TO_KW = 4.184 / 1000.0
TIMEOUT_S = 120.0
FLOW_REL_TOL = 0.02
FLOW_ABS_TOL = 1e-4
Q_REL_TOL = 0.01
Q_ABS_TOL = 0.05

TEST_POINTS = [
    dict(T=800,  P=5,  Fw=0.5, Fc=0.5, Fo=0.3),
    dict(T=500,  P=1,  Fw=0.0, Fc=0.0, Fo=0.0),
    dict(T=1000, P=29, Fw=1.0, Fc=1.0, Fo=0.7),
    dict(T=700,  P=13, Fw=0.3, Fc=0.7, Fo=0.0),
]

INPUT_PATHS = {
    "feed_T":  r"\Data\Streams\1\Input\TEMP\MIXED",
    "feed_P":  r"\Data\Streams\1\Input\PRES\MIXED",
    "CH4":     r"\Data\Streams\1\Input\FLOW\MIXED\CH4",
    "WATER":   r"\Data\Streams\1\Input\FLOW\MIXED\WATER",
    "CO2":     r"\Data\Streams\1\Input\FLOW\MIXED\CO2",
    "O2":      r"\Data\Streams\1\Input\FLOW\MIXED\O2",
    "H2":      r"\Data\Streams\1\Input\FLOW\MIXED\H2",
    "CO":      r"\Data\Streams\1\Input\FLOW\MIXED\CO",
    "CARBON":  r"\Data\Streams\1\Input\FLOW\MIXED\CARBON",
    "block_T": r"\Data\Blocks\B1\Input\TEMP",
    "block_P": r"\Data\Blocks\B1\Input\PRES",
}

OUTPUT_PATHS = {
    "FCH4":    r"\Data\Streams\2\Output\MOLEFLOW\MIXED\CH4",
    "FH2O":    r"\Data\Streams\2\Output\MOLEFLOW\MIXED\WATER",
    "FCO2":    r"\Data\Streams\2\Output\MOLEFLOW\MIXED\CO2",
    "FO2":     r"\Data\Streams\2\Output\MOLEFLOW\MIXED\O2",
    "FCO":     r"\Data\Streams\2\Output\MOLEFLOW\MIXED\CO",
    "FH2":     r"\Data\Streams\2\Output\MOLEFLOW\MIXED\H2",
    "FCARBON": r"\Data\Streams\2\Output\MOLEFLOW\MIXED\CARBON",
    "QCALC":   r"\Data\Blocks\B1\Output\QCALC",
}

CSV_COMPARE_COLS = ["FCH4", "FH2O", "FCO2", "FCO", "FH2", "FCARBON", "Q"]


def fatal(msg):
    raise SystemExit(f"FATAL: {msg}")


def node(aspen, path, required=True):
    n = aspen.Tree.FindNode(path)
    if n is None and required:
        fatal(f"Aspen node not found: {path}")
    return n


def write_value(aspen, path, value):
    try:
        node(aspen, path).Value = float(value)
    except Exception as exc:
        fatal(f"Cannot write {path} = {value}: {exc}")


def read_value(aspen, path):
    n = node(aspen, path)
    v = n.Value
    if v is None:
        fatal(f"Node returned None (bad path?): {path}")
    return float(v)


def connect_aspen():
    try:
        import win32com.client
    except ImportError:
        fatal("pywin32 missing. Run: py -m pip install pywin32")
    if not CLEAN_APW.exists():
        fatal(f"Clean APW not found: {CLEAN_APW}")
    t0 = time.perf_counter()
    aspen = win32com.client.Dispatch("Apwn.Document")
    aspen.InitFromArchive2(str(CLEAN_APW.resolve()))
    aspen.Visible = 0
    aspen.SuppressDialogs = 1
    return aspen, time.perf_counter() - t0


def set_case(aspen, p):
    write_value(aspen, INPUT_PATHS["feed_T"], FEED_T_C)
    write_value(aspen, INPUT_PATHS["feed_P"], FEED_P_BAR)
    write_value(aspen, INPUT_PATHS["CH4"], FEED_CH4)
    write_value(aspen, INPUT_PATHS["H2"], 0.0)
    write_value(aspen, INPUT_PATHS["CO"], 0.0)
    write_value(aspen, INPUT_PATHS["CARBON"], 0.0)
    write_value(aspen, INPUT_PATHS["WATER"], p["Fw"])
    write_value(aspen, INPUT_PATHS["CO2"], p["Fc"])
    write_value(aspen, INPUT_PATHS["O2"], p["Fo"])
    write_value(aspen, INPUT_PATHS["block_T"], p["T"])
    write_value(aspen, INPUT_PATHS["block_P"], p["P"])


def wait_until_done(aspen):
    t0 = time.perf_counter()
    while bool(aspen.Engine.IsRunning):
        if time.perf_counter() - t0 > TIMEOUT_S:
            raise TimeoutError(f"Aspen exceeded {TIMEOUT_S}s")
        time.sleep(0.02)


def run_case(aspen, p):
    set_case(aspen, p)
    t0 = time.perf_counter()
    aspen.Reinit()
    t1 = time.perf_counter()
    aspen.Engine.Run2()
    wait_until_done(aspen)
    t2 = time.perf_counter()
    out = {}
    for k in ["FCH4", "FH2O", "FCO2", "FO2", "FCO", "FH2", "FCARBON"]:
        out[k] = read_value(aspen, OUTPUT_PATHS[k])
    q_raw = read_value(aspen, OUTPUT_PATHS["QCALC"])
    out["QCALC_cal_s"] = q_raw
    out["Q"] = q_raw * CAL_S_TO_KW
    t3 = time.perf_counter()
    timing = {"reinit_s": t1 - t0, "solve_s": t2 - t1,
              "read_s": t3 - t2, "total_s": t3 - t0}
    return out, timing


def find_csv_row(df, p):
    mask = (np.isclose(df["T"], p["T"]) & np.isclose(df["P"], p["P"])
            & np.isclose(df["Fw"], p["Fw"]) & np.isclose(df["Fc"], p["Fc"])
            & np.isclose(df["Fo"], p["Fo"]))
    rows = df.loc[mask]
    if len(rows) != 1:
        fatal(f"Expected 1 CSV row for {p}; found {len(rows)}")
    return rows.iloc[0]


def assess(var, got, expected):
    abs_err = abs(got - expected)
    rel_err = np.nan if abs(expected) < 1e-12 else abs_err / abs(expected)
    if var == "Q":
        ok = abs_err <= Q_ABS_TOL or (not np.isnan(rel_err) and rel_err <= Q_REL_TOL)
    else:
        ok = abs_err <= FLOW_ABS_TOL or (not np.isnan(rel_err) and rel_err <= FLOW_REL_TOL)
    return abs_err, rel_err, "PASS" if ok else "FAIL"


def main():
    print("=" * 78)
    print("CLEAN ASPEN VALIDATION - NO SENSITIVITY BLOCK")
    print("=" * 78)
    print(f"Clean APW : {CLEAN_APW}")
    print(f"Dataset   : {DATA_CSV}")
    print(f"Fixed feed: T={FEED_T_C}C P={FEED_P_BAR}bar CH4={FEED_CH4}")
    print("Q formula : Q_kW = QCALC_cal/s * 4.184/1000")

    if not DATA_CSV.exists():
        fatal(f"Dataset not found: {DATA_CSV}")
    df = pd.read_csv(DATA_CSV)
    needed = {"T", "P", "Fw", "Fc", "Fo", *CSV_COMPARE_COLS}
    missing = sorted(needed - set(df.columns))
    if missing:
        fatal(f"CSV missing columns: {missing}")

    aspen = None
    comparisons, timings, overall_pass = [], [], True
    try:
        aspen, boot_s = connect_aspen()
        print(f"Aspen boot/open: {boot_s:.3f} s")

        # PRE-FLIGHT: INPUT nodes only. Output nodes don't exist until first run.
        print("\nChecking INPUT nodes only...")
        for path in INPUT_PATHS.values():
            node(aspen, path)
        print("All INPUT nodes found. (Outputs validated after first solve.)")

        for case_no, p in enumerate(TEST_POINTS, 1):
            print("\n" + "=" * 78)
            print(f"CASE {case_no}: {p}")
            print("=" * 78)
            ref = find_csv_row(df, p)
            out, timing = run_case(aspen, p)
            print(f"Timing: Reinit={timing['reinit_s']:.3f}s | "
                  f"Solve={timing['solve_s']:.3f}s | "
                  f"Read={timing['read_s']:.3f}s | Total={timing['total_s']:.3f}s")
            print(f"Raw QCALC: {out['QCALC_cal_s']:.6f} cal/s")
            print(f"Converted Q: {out['Q']:.6f} kW")
            print(f"{'Var':<10}{'Aspen':>15}{'CSV':>15}{'AbsErr':>14}{'Rel%':>12}{'Stat':>8}")
            print("-" * 74)
            for var in CSV_COMPARE_COLS:
                got, expected = float(out[var]), float(ref[var])
                abs_err, rel_err, status = assess(var, got, expected)
                if status == "FAIL":
                    overall_pass = False
                rel_txt = "n/a" if np.isnan(rel_err) else f"{100*rel_err:.4f}"
                print(f"{var:<10}{got:>15.7f}{expected:>15.7f}"
                      f"{abs_err:>14.3e}{rel_txt:>12}{status:>8}")
                comparisons.append({"case": case_no, **p, "variable": var,
                                    "aspen": got, "csv": expected,
                                    "absolute_error": abs_err,
                                    "relative_error": rel_err, "status": status})
            print(f"FO2 (not in CSV): {out['FO2']:.6e}")
            timings.append({"case": case_no, **p, **timing,
                           "QCALC_cal_s": out["QCALC_cal_s"], "Q_kW": out["Q"]})

        out_dir = ROOT / "data" / "metrics"
        out_dir.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(comparisons).to_csv(out_dir / "aspen_clean_verification.csv", index=False)
        tdf = pd.DataFrame(timings)
        tdf.to_csv(out_dir / "aspen_clean_timing.csv", index=False)

        print("\n" + "=" * 78)
        print("SPEED SUMMARY")
        print("=" * 78)
        print(f"Boot/open       : {boot_s:.3f} s")
        print(f"Mean Reinit     : {tdf['reinit_s'].mean():.3f} s")
        print(f"Mean solve      : {tdf['solve_s'].mean():.3f} s")
        print(f"Mean read       : {tdf['read_s'].mean():.3f} s")
        print(f"Mean total/case : {tdf['total_s'].mean():.3f} s")
        print(f"Fastest         : {tdf['total_s'].min():.3f} s")
        print(f"Slowest         : {tdf['total_s'].max():.3f} s")
        print(f"Projected 243   : {243*tdf['total_s'].mean():.1f} s")

        print("\n" + "=" * 78)
        if overall_pass:
            print("OVERALL RESULT: PASS")
        else:
            print("OVERALL RESULT: FAIL - do not generate off-grid data yet.")
            raise SystemExit(2)
    except Exception:
        traceback.print_exc()
        raise
    finally:
        if aspen is not None:
            try:
                aspen.Close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
