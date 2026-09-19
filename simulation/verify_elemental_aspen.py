"""Verify the five ANN-selected operating points with the clean Aspen flowsheet.

Place this file in the repository's simulation/ folder, next to
TRM_automation_no_S1.apw. From the repository root run:
    python simulation/verify_elemental_aspen.py

Requires: numpy, pandas, pywin32, and a working local Aspen installation.
No ANN training, optimization, or dataset-grid lookup is performed.

Flowsheet basis inherited from verify_clean_aspen.py:
  stream 1 is the only feed; stream 2 is the complete reactor outlet;
  B1 is the reactor; feed CH4=1 kmol/h, T=500 C, P=1 bar;
  component MOLEFLOW values share the source script's kmol/h basis;
  QCALC is cal/s, converted to kW with 4.184/1000.
All MOLEFLOW substreams are inspected, including solid substreams.
Unknown nonzero components stop the calculation instead of being omitted.
Balance PASS means atom closure only, not proof of solver convergence,
nonnegative species, optimality, or agreement between Aspen and the ANN.
"""

from pathlib import Path
import argparse
import json
import time
import traceback

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent if HERE.name.lower() == "simulation" else HERE
INPUTS = ["T", "P", "Fw", "Fc", "Fo"]
OUTPUTS = ["FCH4", "FH2O", "FCO2", "FCO", "FH2", "FCARBON", "Q"]
COMPONENTS = {
    "CH4": "FCH4", "WATER": "FH2O", "CO2": "FCO2", "O2": "FO2",
    "CO": "FCO", "H2": "FH2", "CARBON": "FCARBON",
}
# Number of C, H and O atoms in each modeled molecule (or carbon atom).
ATOMS = {
    "FCH4": (1, 4, 0), "FH2O": (0, 2, 1), "FCO2": (1, 0, 2),
    "FO2": (0, 0, 2), "FCO": (1, 0, 1), "FH2": (0, 2, 0),
    "FCARBON": (1, 0, 0),
}
CAL_S_TO_KW = 4.184 / 1000.0


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
    return dict(FCH4=1.0, FH2O=p["Fw"], FCO2=p["Fc"], FO2=p["Fo"],
                FCO=0.0, FH2=0.0, FCARBON=0.0)


def set_case(app, p):
    write(app, r"\Data\Streams\1\Input\TEMP\MIXED", 500.0)
    write(app, r"\Data\Streams\1\Input\PRES\MIXED", 1.0)
    feed = nominal_feed(p)
    for component, key in COMPONENTS.items():
        write(app, rf"\Data\Streams\1\Input\FLOW\MIXED\{component}", feed[key])
    write(app, r"\Data\Blocks\B1\Input\TEMP", p["T"])
    write(app, r"\Data\Blocks\B1\Input\PRES", p["P"])


def stream_flows(app, stream, scenario, inventory):
    parent = node(app, rf"\Data\Streams\{stream}\Output\MOLEFLOW")
    totals = dict.fromkeys(ATOMS, 0.0)
    found = set()
    count = 0
    units_seen = set()
    for substream in parent.Elements:
        for component in substream.Elements:
            count += 1
            name = str(component.Name).upper()
            value = number(component)
            try:
                units = str(component.UnitString)
            except Exception:
                units = "unavailable; source-script unit basis assumed"
            if units and not units.startswith("unavailable"):
                units_seen.add(units)
            inventory.append(dict(
                scenario=scenario, stream=stream, substream=str(substream.Name),
                component=name, flow=value, reported_units=units,
            ))
            if name not in COMPONENTS:
                if value != 0.0:
                    raise RuntimeError(
                        f"Unmapped nonzero component {name} in stream {stream}, "
                        f"substream {substream.Name}: {value}. Add its stoichiometry first."
                    )
                continue
            key = COMPONENTS[name]
            totals[key] += value
            found.add(key)
    if not count:
        raise RuntimeError(f"No component MOLEFLOW results for stream {stream}")
    if len(units_seen) > 1:
        raise RuntimeError(f"Mixed component flow units in stream {stream}: {units_seen}")
    # Do not silently assume a missing O2/carbon node has zero flow.
    missing = set(ATOMS) - found
    if missing:
        raise RuntimeError(f"Missing species results in stream {stream}: {sorted(missing)}")
    return totals


def atom_totals(flows):
    return np.array([
        sum(flows.get(key, 0.0) * counts[i] for key, counts in ATOMS.items())
        for i in range(3)
    ])


def balance_rows(scenario, source, feed, product, atol, rtol, oxygen_known=True):
    incoming, outgoing = atom_totals(feed), atom_totals(product)
    rows = []
    for i, element in enumerate(["C", "H", "O"]):
        residual = outgoing[i] - incoming[i]
        limit = atol + rtol * abs(incoming[i])
        status = "PASS" if abs(residual) <= limit else "FAIL"
        if element == "O" and not oxygen_known:
            status = "INCOMPLETE_NO_ANN_O2"
        rows.append(dict(
            scenario=scenario, source=source, element=element,
            atoms_in=incoming[i], atoms_out_accounted=outgoing[i],
            residual_out_minus_in=residual,
            relative_residual=residual / incoming[i] if incoming[i] else np.nan,
            residual_percent=100 * residual / incoming[i] if incoming[i] else np.nan,
            absolute_tolerance=atol, relative_tolerance=rtol,
            allowed_absolute_residual=limit, status=status,
        ))
    return rows


def objective(scenario, x, p):
    # Same reporting/penalty convention as the ANN optimization script.
    base = -(1 - x["FCH4"]) - x["FH2"] + max(x["FCARBON"], 0.0)
    emission = x["FCO2"] - p["Fc"]
    duty = abs(x["Q"]) / 10
    return {
        1: base - x["FCO"] + emission + duty,
        2: base - x["FCO"] + duty,
        3: base - x["FCO"] + emission,
        4: base - x["FCO"] + abs(emission) + duty,
        5: base + abs(emission) + duty,
    }[scenario]


def run_status(app):
    # Export raw status, without guessing version-specific status-code meanings.
    status = {}
    for name in ["PER_ERROR", "RUN_STATUS"]:
        path = rf"\Data\Results Summary\Run-Status\Output\{name}"
        n = app.Tree.FindNode(path)
        status[name] = str(n.Value) if n is not None else "unavailable"
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apw", type=Path,
                        default=ROOT / "simulation" / "TRM_automation_no_S1.apw")
    parser.add_argument("--predictions", type=Path,
                        default=ROOT / "ann_optimization_results" / "revision_weight_sensitivity" / "five_scenarios_best_mut01.csv")
    parser.add_argument("--out", type=Path,
                        default=ROOT / "ann_optimization_results" / "aspen_verification")
    parser.add_argument("--timeout", type=float, default=120.0)
    # Numerical closure thresholds, not fitted to observed errors.
    parser.add_argument("--balance-atol", type=float, default=1e-6,
                        help="Absolute tolerance in kmol atoms/h on the inherited flow basis")
    parser.add_argument("--balance-rtol", type=float, default=1e-6)
    parser.add_argument("--visible", action="store_true")
    args = parser.parse_args()
    if args.timeout <= 0 or min(args.balance_atol, args.balance_rtol) < 0:
        parser.error("Timeout must be positive and tolerances nonnegative.")
    for path in [args.apw, args.predictions]:
        if not path.exists():
            raise FileNotFoundError(path)
    df = pd.read_csv(args.predictions)
    needed = ["scenario"] + INPUTS + OUTPUTS
    missing = set(needed) - set(df.columns)
    if missing:
        raise ValueError(f"Prediction CSV missing columns: {sorted(missing)}")
    if not np.isfinite(df[needed].to_numpy(dtype=float)).all():
        raise ValueError("Prediction CSV contains missing/nonfinite values.")
    if df.scenario.duplicated().any() or set(df.scenario) != {1, 2, 3, 4, 5}:
        raise ValueError("Expected exactly one row for each of scenarios 1 to 5.")
    if (df[["Fw", "Fc", "Fo"]] < 0).any().any() or (df.P <= 0).any():
        raise ValueError("Negative feed ratios or nonpositive pressure.")
    import win32com.client
    args.out.mkdir(parents=True, exist_ok=True)
    metadata = dict(
        predictions=str(args.predictions.resolve()), apw=str(args.apw.resolve()),
        flow_basis="kmol/h, inherited from supplied driver",
        atom_balance_basis="kmol atoms/h (H is full hydrogen atoms, not H2 equivalents)",
        balance_atol=args.balance_atol, balance_rtol=args.balance_rtol,
        q_conversion="QCALC cal/s times 4.184/1000 = kW; inherited from supplied driver",
        balance_scope="single feed stream 1 and complete product stream 2, all MOLEFLOW substreams",
        solver_convergence="raw codes exported; confirm successful completion in Aspen",
    )
    (args.out / "settings.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    balances, comparisons, results, inventory, statuses = [], [], [], [], []

    def save():
        for name, records in [
            ("elemental_balances.csv", balances), ("ann_vs_aspen.csv", comparisons),
            ("aspen_results.csv", results), ("stream_inventory.csv", inventory),
            ("run_status.csv", statuses),
        ]:
            if records:
                pd.DataFrame(records).to_csv(args.out / name, index=False, float_format="%.17g")

    print("Checking five selected points; no training or optimization.")
    print("PASS applies to atom closure only. Confirm solver completion in Aspen.")
    print(f"Balance tolerance: {args.balance_atol:g} + {args.balance_rtol:g} * abs(atoms_in)")
    for _, record in df.sort_values("scenario").iterrows():
        scenario = int(record.scenario)
        p = {key: float(record[key]) for key in INPUTS}
        ann = {key: float(record[key]) for key in OUTPUTS}
        app = None
        started = time.perf_counter()
        print(f"\nScenario {scenario}: {p}", flush=True)
        try:
            # Dedicated clean document per point avoids reusing prior-case outputs.
            app = win32com.client.DispatchEx("Apwn.Document")
            app.InitFromArchive2(str(args.apw.resolve()))
            app.Visible = int(args.visible)
            app.SuppressDialogs = 1
            app.Reinit()
            set_case(app, p)
            app.Engine.Run2(True)  # asynchronous, so the polling timeout can work
            solve_start = time.perf_counter()
            while bool(app.Engine.IsRunning):
                if time.perf_counter() - solve_start > args.timeout:
                    try:
                        app.Engine.Stop()
                    finally:
                        raise TimeoutError(f"Scenario {scenario}: Aspen exceeded {args.timeout}s")
                time.sleep(0.05)
            raw_status = run_status(app)
            feed = stream_flows(app, "1", scenario, inventory)
            product = stream_flows(app, "2", scenario, inventory)
            nominal = nominal_feed(p)
            for key in nominal:
                if not np.isclose(feed[key], nominal[key], atol=1e-6, rtol=1e-6):
                    raise RuntimeError(f"Feed output differs from requested input: {key}, "
                                       f"requested={nominal[key]}, actual={feed[key]}")
            q_raw = number(node(app, r"\Data\Blocks\B1\Output\QCALC"))
            product["Q"] = q_raw * CAL_S_TO_KW
            aspen_balances = balance_rows(scenario, "ASPEN", feed, product,
                                          args.balance_atol, args.balance_rtol)
            balances.extend(aspen_balances)
            balances.extend(balance_rows(scenario, "ANN", nominal, ann,
                                         args.balance_atol, args.balance_rtol, oxygen_known=False))
            for key in OUTPUTS:
                error = ann[key] - product[key]
                comparisons.append(dict(
                    scenario=scenario, variable=key, ann=ann[key], aspen=product[key],
                    signed_error_ann_minus_aspen=error, absolute_error=abs(error),
                    relative_error_percent=(100 * error / abs(product[key])
                                            if abs(product[key]) > 1e-12 else np.nan),
                ))
            closure = all(b["status"] == "PASS" for b in aspen_balances)
            results.append(dict(
                scenario=scenario, **p, **product, QCALC_cal_s=q_raw,
                XCH4=1-product["FCH4"], YCO=product["FCO"], YH2=product["FH2"],
                E_CO2=product["FCO2"]-p["Fc"],
                Coke_objective=max(product["FCARBON"], 0.0),
                objective_aspen=objective(scenario, product, p),
                objective_ann=objective(scenario, ann, p),
                atom_closure="PASS" if closure else "FAIL",
                minimum_aspen_species=min(product[k] for k in ATOMS),
                minimum_ann_species=min(ann[k] for k in ATOMS if k in ann),
            ))
            statuses.append(dict(scenario=scenario, extraction="COMPLETED",
                                 elapsed_s=time.perf_counter()-started,
                                 solver_convergence="CHECK_ASPEN_STATUS", **raw_status))
            for b in aspen_balances:
                print(f"  Aspen {b['element']}: residual={b['residual_out_minus_in']:+.6e}, "
                      f"relative={b['residual_percent']:+.6g}% -> {b['status']}")
            print(f"  Aspen H2={product['FH2']:.9g}, carbon={product['FCARBON']:.9g}, "
                  f"O2={product['FO2']:.9g}, Q={product['Q']:.9g} kW")
            print(f"  Aspen raw run status: {raw_status}")
        except Exception as exc:
            statuses.append(dict(scenario=scenario, extraction="ERROR", error=str(exc)))
            raise
        finally:
            save()
            if app is not None:
                try:
                    app.Close()  # Do not save modifications to the source flowsheet.
                except Exception:
                    pass
    print(f"\nSaved: {args.out.resolve()}")
    print("ANN oxygen balance is incomplete because the ANN has no O2 output.")
    print("Review aspen_results.csv and elemental_balances.csv; confirm Aspen convergence.")
    if any(r["atom_closure"] != "PASS" for r in results):
        raise SystemExit(2)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)