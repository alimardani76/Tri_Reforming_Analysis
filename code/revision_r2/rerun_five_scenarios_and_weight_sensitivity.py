# ============================================================
# R2 REVISION PIPELINE
# 1) Reload the already-trained selected ANN
# 2) Re-run the five manuscript scenarios with GA mutation = 0.1
# 3) Run normalized weight-sensitivity analysis for Reviewer #2, Comment 3
#
# NO ANN RETRAINING.
#
# Required existing files:
#   ann_optimization_results/ann.keras
#   ann_optimization_results/scalers.pkl
#   added2.csv   OR   data/added2.csv
#
# Outputs:
#   ann_optimization_results/revision_weight_sensitivity/
#       normalization_ranges.csv
#       five_scenarios_all_seed_runs_mut01.csv
#       five_scenarios_best_mut01.csv
#       aspen_operating_points_mut01.csv
#       weight_sensitivity_all_seed_runs.csv
#       weight_sensitivity_best.csv
#       weight_sensitivity_operating_points.csv
#       weight_sensitivity_shifts_from_baseline.csv
#
# Dependencies:
#   numpy pandas tensorflow scikit-learn scikit-opt
# ============================================================

from pathlib import Path
import pickle
import random
import warnings

import numpy as np
import pandas as pd
import tensorflow as tf

from tensorflow.keras.layers import Dense
from sko.GA import GA
from sko.tools import set_run_mode

warnings.filterwarnings("ignore")

# ============================================================
# 0. Configuration
# ============================================================

ROOT = Path(".")
BASE = ROOT / "ann_optimization_results"

MODEL_PATH = BASE / "ann.keras"
SCALER_PATH = BASE / "scalers.pkl"

DATA_PATH = ROOT / "added2.csv"
if not DATA_PATH.exists():
    DATA_PATH = ROOT / "data" / "added2.csv"

OUT = BASE / "revision_weight_sensitivity"
OUT.mkdir(parents=True, exist_ok=True)

INPUTS = ["T", "P", "Fw", "Fc", "Fo"]
OUTPUTS = ["FCH4", "FH2O", "FCO2", "FCO", "FH2", "FCARBON", "Q"]

# Same physical search bounds used previously.
LB = np.array([500.0, 1.0, 0.15, 0.15, 0.0], dtype=float)
UB = np.array([1000.0, 29.0, 1.0, 1.0, 0.7], dtype=float)

# IMPORTANT: use the revised manuscript GA setting.
POPULATION = 50
GENERATIONS = 1000
MUTATION = 0.1
PRECISION = 1e-7

# Three seeds are enough to separate weight effects from a single stochastic GA run.
# For a stronger final audit, change this to [0, 1, 2, 3, 4].
SEEDS = [0, 1, 2]

# Weight-sensitivity design:
# methane-conversion weight stays fixed at 1.
# Each of the five reviewer-named weights is varied one-at-a-time.
WEIGHT_CASES = [
    ("baseline",   1.0, 1.0, 1.0, 1.0, 1.0),
    ("H2_0.5",     0.5, 1.0, 1.0, 1.0, 1.0),
    ("H2_2.0",     2.0, 1.0, 1.0, 1.0, 1.0),
    ("CO_0.5",     1.0, 0.5, 1.0, 1.0, 1.0),
    ("CO_2.0",     1.0, 2.0, 1.0, 1.0, 1.0),
    ("Coke_0.5",   1.0, 1.0, 0.5, 1.0, 1.0),
    ("Coke_2.0",   1.0, 1.0, 2.0, 1.0, 1.0),
    ("CO2_0.5",    1.0, 1.0, 1.0, 0.5, 1.0),
    ("CO2_2.0",    1.0, 1.0, 1.0, 2.0, 1.0),
    ("Duty_0.5",   1.0, 1.0, 1.0, 1.0, 0.5),
    ("Duty_2.0",   1.0, 1.0, 1.0, 1.0, 2.0),
]
# tuple fields:
# case_name, w_H2, w_CO, w_Coke, w_CO2, w_Duty

random.seed(42)
np.random.seed(42)
tf.random.set_seed(42)

# ============================================================
# 1. Load data, model, and scalers
# ============================================================

for p in [MODEL_PATH, SCALER_PATH, DATA_PATH]:
    if not p.exists():
        raise FileNotFoundError(f"Required file not found: {p.resolve()}")

data = pd.read_csv(DATA_PATH)

missing = [c for c in INPUTS + OUTPUTS if c not in data.columns]
if missing:
    raise ValueError(
        "Dataset is missing expected columns: "
        + ", ".join(missing)
        + f"\nActual columns: {list(data.columns)}"
    )

# Reorder explicitly so all downstream calculations use documented mapping.
data = data[INPUTS + OUTPUTS].copy()
data = data.apply(pd.to_numeric, errors="raise")

if not np.isfinite(data.to_numpy()).all():
    raise ValueError("Dataset contains missing or nonfinite values.")

model = tf.keras.models.load_model(MODEL_PATH, compile=False)

with SCALER_PATH.open("rb") as f:
    saved = pickle.load(f)

scalerx = saved["scalerx"]
scalery = saved["scalery"]

print("Loaded model:", MODEL_PATH.resolve())
print("Loaded scalers:", SCALER_PATH.resolve())
print("Loaded dataset:", DATA_PATH.resolve())
print(f"Dataset rows: {len(data):,}")
print(f"GA: population={POPULATION}, generations={GENERATIONS}, mutation={MUTATION}")
print("Seeds:", SEEDS)

# ============================================================
# 2. Fast NumPy ANN forward pass
# ============================================================

dense_layers = [layer for layer in model.layers if isinstance(layer, Dense)]
if not dense_layers:
    raise RuntimeError("No Dense layers found in loaded ANN.")

Ws = [layer.get_weights()[0] for layer in dense_layers]
bs = [layer.get_weights()[1] for layer in dense_layers]

def ann_np(scaled_inputs):
    """Scaled inputs -> scaled ANN outputs."""
    a = np.asarray(scaled_inputs, dtype=np.float32)
    for W, b in zip(Ws[:-1], bs[:-1]):
        a = np.maximum(0.0, a @ W + b)  # ReLU hidden layers
    return a @ Ws[-1] + bs[-1]          # linear output layer

def predict_physical(points):
    """Physical input matrix -> physical ANN outputs."""
    points = np.atleast_2d(np.asarray(points, dtype=float))
    scaled_x = scalerx.transform(points)
    scaled_y = ann_np(scaled_x)
    physical_y = scalery.inverse_transform(scaled_y)

    if not np.isfinite(physical_y).all():
        raise ValueError("ANN produced nonfinite predictions.")
    return physical_y

# Sanity check against Keras on a few actual rows.
chk_x = data[INPUTS].iloc[:32].to_numpy(dtype=float)
keras_scaled = model.predict(scalerx.transform(chk_x), verbose=0)
numpy_scaled = ann_np(scalerx.transform(chk_x))
max_diff = float(np.max(np.abs(keras_scaled - numpy_scaled)))
print("Max scaled-output difference, NumPy vs Keras:", max_diff)

if not np.allclose(keras_scaled, numpy_scaled, rtol=1e-4, atol=1e-5):
    raise RuntimeError("NumPy ANN forward pass does not match Keras.")

# ============================================================
# 3. Helper: raw derived metrics
# ============================================================

def derived_from_predictions(points, predictions):
    points = np.atleast_2d(np.asarray(points, dtype=float))
    predictions = np.atleast_2d(np.asarray(predictions, dtype=float))

    FCH4, FH2O, FCO2, FCO, FH2, FCARBON, Q = predictions.T

    XCH4 = 1.0 - FCH4
    YCO = FCO
    YH2 = FH2
    E_CO2 = FCO2 - points[:, 3]  # outlet CO2 - inlet CO2 ratio
    COKE_RAW = FCARBON
    COKE_OBJECTIVE = np.maximum(FCARBON, 0.0)
    ABS_Q = np.abs(Q)

    return {
        "XCH4": XCH4,
        "YCO": YCO,
        "YH2": YH2,
        "E_CO2": E_CO2,
        "COKE_RAW": COKE_RAW,
        "COKE_OBJECTIVE": COKE_OBJECTIVE,
        "ABS_Q": ABS_Q,
    }

# ============================================================
# 4. Normalization ranges from the ORIGINAL 46,464-point Aspen dataset
# ============================================================

ref = pd.DataFrame({
    "XCH4": 1.0 - data["FCH4"],
    "YCO": data["FCO"],
    "YH2": data["FH2"],
    "Coke": data["FCARBON"],
    "E_CO2": data["FCO2"] - data["Fc"],
    "AbsQ": data["Q"].abs(),
})

ranges = {}
range_rows = []

for name in ref.columns:
    vmin = float(ref[name].min())
    vmax = float(ref[name].max())
    span = vmax - vmin
    if span <= 0:
        raise ValueError(f"Reference range for {name} is zero.")
    ranges[name] = (vmin, vmax)
    range_rows.append({
        "component": name,
        "reference_min": vmin,
        "reference_max": vmax,
        "reference_span": span,
    })

pd.DataFrame(range_rows).to_csv(
    OUT / "normalization_ranges.csv", index=False, float_format="%.17g"
)

print("\nNormalization ranges from original Aspen dataset:")
print(pd.DataFrame(range_rows).to_string(index=False))

def minmax(value, name):
    lo, hi = ranges[name]
    return (np.asarray(value, dtype=float) - lo) / (hi - lo)

# ============================================================
# 5. Original five manuscript objectives
#    Re-run ONLY because final manuscript states mutation = 0.1.
# ============================================================

FIVE_SCENARIO_FORMULAS = {
    1: "-XCH4 - YCO - YH2 + Coke + E_CO2 + abs(Q)/10",
    2: "-XCH4 - YCO - YH2 + Coke + abs(Q)/10",
    3: "-XCH4 - YCO - YH2 + Coke + E_CO2",
    4: "-XCH4 - YCO - YH2 + Coke + abs(E_CO2) + abs(Q)/10",
    5: "-XCH4 - YH2 + Coke + abs(E_CO2) + abs(Q)/10",
}

def make_manuscript_objective(scenario):
    if scenario not in FIVE_SCENARIO_FORMULAS:
        raise ValueError(f"Unknown scenario {scenario}")

    def objective(points):
        points = np.atleast_2d(np.asarray(points, dtype=float))
        pred = predict_physical(points)
        m = derived_from_predictions(points, pred)

        base = -m["XCH4"] - m["YH2"] + m["COKE_OBJECTIVE"]
        duty = m["ABS_Q"] / 10.0

        if scenario == 1:
            return base - m["YCO"] + m["E_CO2"] + duty
        elif scenario == 2:
            return base - m["YCO"] + duty
        elif scenario == 3:
            return base - m["YCO"] + m["E_CO2"]
        elif scenario == 4:
            return base - m["YCO"] + np.abs(m["E_CO2"]) + duty
        elif scenario == 5:
            return base + np.abs(m["E_CO2"]) + duty

    set_run_mode(objective, "vectorization")
    return objective

# ============================================================
# 6. Reviewer #2 Comment 3:
#    fixed objective structure, dimensionless components,
#    one-at-a-time weight sensitivity.
#
#    J = -wX*z(XCH4)
#        -wCO*z(YCO)
#        -wH2*z(YH2)
#        +wC*z(Coke)
#        +wE*z(E_CO2)
#        +wQ*z(|Q|)
#
#    wX is held fixed at 1.
# ============================================================

def make_normalized_weight_objective(
    w_H2=1.0,
    w_CO=1.0,
    w_Coke=1.0,
    w_CO2=1.0,
    w_Duty=1.0,
    w_XCH4=1.0,
):
    def objective(points):
        points = np.atleast_2d(np.asarray(points, dtype=float))
        pred = predict_physical(points)
        m = derived_from_predictions(points, pred)

        z_x = minmax(m["XCH4"], "XCH4")
        z_co = minmax(m["YCO"], "YCO")
        z_h2 = minmax(m["YH2"], "YH2")
        z_c = minmax(m["COKE_OBJECTIVE"], "Coke")
        z_e = minmax(m["E_CO2"], "E_CO2")
        z_q = minmax(m["ABS_Q"], "AbsQ")

        return (
            -w_XCH4 * z_x
            -w_CO * z_co
            -w_H2 * z_h2
            +w_Coke * z_c
            +w_CO2 * z_e
            +w_Duty * z_q
        )

    set_run_mode(objective, "vectorization")
    return objective

# ============================================================
# 7. Common GA runner
# ============================================================

def run_ga_once(objective, seed):
    np.random.seed(seed)
    random.seed(seed)

    ga = GA(
        func=objective,
        n_dim=5,
        size_pop=POPULATION,
        max_iter=GENERATIONS,
        prob_mut=MUTATION,
        lb=LB,
        ub=UB,
        precision=PRECISION,
    )

    best_x, _ = ga.run()
    best_x = np.asarray(best_x, dtype=float).reshape(5)
    best_obj = float(np.asarray(objective(best_x[None, :])).ravel()[0])

    return best_x, best_obj

def full_result_row(best_x, objective_value):
    pred = predict_physical(best_x)[0]
    m = derived_from_predictions(best_x[None, :], pred[None, :])

    row = {
        "objective": float(objective_value),
        **dict(zip(INPUTS, best_x)),
        **dict(zip(OUTPUTS, pred)),
        "XCH4": float(m["XCH4"][0]),
        "YCO": float(m["YCO"][0]),
        "YH2": float(m["YH2"][0]),
        "E_CO2": float(m["E_CO2"][0]),
        "Coke_raw": float(m["COKE_RAW"][0]),
        "Coke_objective": float(m["COKE_OBJECTIVE"][0]),
        "AbsQ": float(m["ABS_Q"][0]),
    }
    return row

# ============================================================
# 8. Re-run five manuscript scenarios at mutation = 0.1
# ============================================================

five_all = []

for scenario in range(1, 6):
    objective = make_manuscript_objective(scenario)
    print(f"\n=== Manuscript Scenario {scenario} ===")
    print(FIVE_SCENARIO_FORMULAS[scenario])

    for seed in SEEDS:
        x, obj = run_ga_once(objective, seed)
        row = full_result_row(x, obj)
        row.update({
            "scenario": scenario,
            "seed": seed,
            "formula": FIVE_SCENARIO_FORMULAS[scenario],
            "population": POPULATION,
            "generations": GENERATIONS,
            "mutation": MUTATION,
        })
        five_all.append(row)

        print(
            f"seed={seed} obj={obj:.8f} "
            f"T={row['T']:.4f} P={row['P']:.4f} "
            f"Fw={row['Fw']:.5f} Fc={row['Fc']:.5f} Fo={row['Fo']:.5f}"
        )

five_all_df = pd.DataFrame(five_all)

five_all_df.to_csv(
    OUT / "five_scenarios_all_seed_runs_mut01.csv",
    index=False,
    float_format="%.17g",
)

# Lowest objective = best because all objectives are minimized.
five_best_df = (
    five_all_df.sort_values(["scenario", "objective"])
    .groupby("scenario", as_index=False)
    .first()
)

five_best_df.to_csv(
    OUT / "five_scenarios_best_mut01.csv",
    index=False,
    float_format="%.17g",
)

five_best_df[["scenario"] + INPUTS].to_csv(
    OUT / "aspen_operating_points_mut01.csv",
    index=False,
    float_format="%.17g",
)

print("\n=== Best mutation=0.1 result for each manuscript scenario ===")
print(
    five_best_df[
        ["scenario", "seed", "objective"] + INPUTS
        + ["XCH4", "YCO", "YH2", "E_CO2", "FCARBON", "Q"]
    ].to_string(index=False)
)

# ============================================================
# 9. Run normalized weight sensitivity
# ============================================================

weight_all = []

for case_name, w_H2, w_CO, w_Coke, w_CO2, w_Duty in WEIGHT_CASES:
    print(f"\n=== Weight case: {case_name} ===")
    print(
        f"wX=1, wH2={w_H2}, wCO={w_CO}, "
        f"wCoke={w_Coke}, wCO2={w_CO2}, wDuty={w_Duty}"
    )

    objective = make_normalized_weight_objective(
        w_H2=w_H2,
        w_CO=w_CO,
        w_Coke=w_Coke,
        w_CO2=w_CO2,
        w_Duty=w_Duty,
        w_XCH4=1.0,
    )

    for seed in SEEDS:
        x, obj = run_ga_once(objective, seed)
        row = full_result_row(x, obj)

        # Normalized component values at the selected optimum.
        row.update({
            "z_XCH4": float(minmax(row["XCH4"], "XCH4")),
            "z_YCO": float(minmax(row["YCO"], "YCO")),
            "z_YH2": float(minmax(row["YH2"], "YH2")),
            "z_Coke": float(minmax(row["Coke_objective"], "Coke")),
            "z_E_CO2": float(minmax(row["E_CO2"], "E_CO2")),
            "z_AbsQ": float(minmax(row["AbsQ"], "AbsQ")),
        })

        row.update({
            "case": case_name,
            "seed": seed,
            "w_XCH4": 1.0,
            "w_H2": w_H2,
            "w_CO": w_CO,
            "w_Coke": w_Coke,
            "w_CO2": w_CO2,
            "w_Duty": w_Duty,
            "population": POPULATION,
            "generations": GENERATIONS,
            "mutation": MUTATION,
        })

        weight_all.append(row)

        print(
            f"seed={seed} obj={obj:.8f} "
            f"T={row['T']:.4f} P={row['P']:.4f} "
            f"Fw={row['Fw']:.5f} Fc={row['Fc']:.5f} Fo={row['Fo']:.5f}"
        )

weight_all_df = pd.DataFrame(weight_all)

weight_all_df.to_csv(
    OUT / "weight_sensitivity_all_seed_runs.csv",
    index=False,
    float_format="%.17g",
)

weight_best_df = (
    weight_all_df.sort_values(["case", "objective"])
    .groupby("case", as_index=False)
    .first()
)

# Restore intended case ordering.
case_order = [c[0] for c in WEIGHT_CASES]
weight_best_df["case"] = pd.Categorical(
    weight_best_df["case"], categories=case_order, ordered=True
)
weight_best_df = weight_best_df.sort_values("case").reset_index(drop=True)
weight_best_df["case"] = weight_best_df["case"].astype(str)

# ============================================================
# 10. Quantify shift from the baseline optimum
# ============================================================

baseline = weight_best_df.loc[weight_best_df["case"] == "baseline"].iloc[0]

# Normalize input displacement by the physical search ranges.
input_spans = UB - LB

shift_rows = []

for _, row in weight_best_df.iterrows():
    x = row[INPUTS].to_numpy(dtype=float)
    x0 = baseline[INPUTS].to_numpy(dtype=float)
    dx_norm = (x - x0) / input_spans

    shift = {
        "case": row["case"],
        "input_shift_L2_normalized": float(np.sqrt(np.sum(dx_norm ** 2))),
        "dT_C": float(row["T"] - baseline["T"]),
        "dP_bar": float(row["P"] - baseline["P"]),
        "dFw": float(row["Fw"] - baseline["Fw"]),
        "dFc": float(row["Fc"] - baseline["Fc"]),
        "dFo": float(row["Fo"] - baseline["Fo"]),
        "dXCH4": float(row["XCH4"] - baseline["XCH4"]),
        "dYCO": float(row["YCO"] - baseline["YCO"]),
        "dYH2": float(row["YH2"] - baseline["YH2"]),
        "dCoke": float(row["Coke_objective"] - baseline["Coke_objective"]),
        "dE_CO2": float(row["E_CO2"] - baseline["E_CO2"]),
        "dQ": float(row["Q"] - baseline["Q"]),
    }
    shift_rows.append(shift)

shift_df = pd.DataFrame(shift_rows)

weight_best_df = weight_best_df.merge(
    shift_df[["case", "input_shift_L2_normalized"]],
    on="case",
    how="left",
)

weight_best_df.to_csv(
    OUT / "weight_sensitivity_best.csv",
    index=False,
    float_format="%.17g",
)

weight_best_df[["case"] + INPUTS].to_csv(
    OUT / "weight_sensitivity_operating_points.csv",
    index=False,
    float_format="%.17g",
)

shift_df.to_csv(
    OUT / "weight_sensitivity_shifts_from_baseline.csv",
    index=False,
    float_format="%.17g",
)

# ============================================================
# 11. Final console summary
# ============================================================

print("\n\n============================================================")
print("NORMALIZED WEIGHT-SENSITIVITY RESULTS")
print("============================================================")

summary_cols = [
    "case",
    "w_H2", "w_CO", "w_Coke", "w_CO2", "w_Duty",
    "seed", "objective",
    "T", "P", "Fw", "Fc", "Fo",
    "XCH4", "YCO", "YH2",
    "Coke_objective", "E_CO2", "Q",
    "input_shift_L2_normalized",
]

print(weight_best_df[summary_cols].to_string(index=False))

print("\nFiles written to:")
print(OUT.resolve())

print("\nNEXT:")
print("1) Use aspen_operating_points_mut01.csv for the new direct Aspen checks.")
print("2) Rebuild Comment 1 and Comment 2 tables from those Aspen results.")
print("3) Send weight_sensitivity_best.csv back for the Comment 3 interpretation/LaTeX response.")