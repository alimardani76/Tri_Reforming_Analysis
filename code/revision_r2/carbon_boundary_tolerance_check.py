"""
Carbon-boundary numerical-tolerance robustness audit.

Purpose:
- Uses the exact held-out split and frozen ANN/scalers.
- Keeps Aspen truth fixed: Aspen FCARBON > 0 is carbon-forming.
- Varies only the ANN decision threshold epsilon.
- No retraining and no Aspen runs.

Run from repository root:
    python code/revision_r2/carbon_boundary_tolerance_check.py

Required:
    data/added2.csv
    ann_optimization_results/ann.keras
    ann_optimization_results/scalers.pkl

Output:
    ann_optimization_results/revision_carbon_boundary/
        carbon_boundary_tolerance_summary.csv
"""

from pathlib import Path
import pickle
import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.model_selection import train_test_split

ROOT = Path(".")
DATA_PATH = ROOT / "data" / "added2.csv"
MODEL_PATH = ROOT / "ann_optimization_results" / "ann.keras"
SCALER_PATH = ROOT / "ann_optimization_results" / "scalers.pkl"
OUT = ROOT / "ann_optimization_results" / "revision_carbon_boundary"
OUT.mkdir(parents=True, exist_ok=True)

RNG = 42
TEST_SIZE = 0.20
EPSILONS = [0.0, 1e-6, 1e-4, 1e-3]

INPUTS = ["T", "P", "Fw", "Fc", "Fo"]
OUTPUTS = ["FCH4", "FH2O", "FCO2", "FCO", "FH2", "FCARBON", "Q"]

for p in [DATA_PATH, MODEL_PATH, SCALER_PATH]:
    if not p.exists():
        raise FileNotFoundError(p)

data = pd.read_csv(DATA_PATH)
expected = INPUTS + OUTPUTS
if list(data.columns) != expected:
    raise ValueError(f"Unexpected columns.\nExpected: {expected}\nActual: {list(data.columns)}")

data = data.apply(pd.to_numeric, errors="raise")
if not np.isfinite(data.to_numpy()).all():
    raise ValueError("Dataset contains missing/nonfinite values.")

# Exact pre-split shuffle used by the frozen ANN workflow.
data = data.sample(frac=1, random_state=RNG)

X = data[INPUTS].to_numpy(dtype=float)
Y = data[OUTPUTS].to_numpy(dtype=float)

with SCALER_PATH.open("rb") as f:
    saved = pickle.load(f)

scalerx = saved["scalerx"]
scalery = saved["scalery"]
model = tf.keras.models.load_model(MODEL_PATH, compile=False)

positions = np.arange(len(data))
_, test_pos = train_test_split(
    positions,
    test_size=TEST_SIZE,
    random_state=RNG,
)

X_test = X[test_pos]
Y_test = Y[test_pos]

pred_scaled = model.predict(scalerx.transform(X_test), verbose=0)
Y_pred = scalery.inverse_transform(pred_scaled)

cidx = OUTPUTS.index("FCARBON")
aspen_c = Y_test[:, cidx]
ann_c = Y_pred[:, cidx]

# Physical reference remains unchanged for every epsilon.
aspen_positive = aspen_c > 0.0
n_pos = int(aspen_positive.sum())
n_zero = int((~aspen_positive).sum())

rows = []
for eps in EPSILONS:
    ann_positive = ann_c > eps

    TP = int(np.sum(aspen_positive & ann_positive))
    FN = int(np.sum(aspen_positive & ~ann_positive))
    FP = int(np.sum(~aspen_positive & ann_positive))
    TN = int(np.sum(~aspen_positive & ~ann_positive))

    recall = TP / n_pos if n_pos else np.nan
    fcf = FN / n_pos if n_pos else np.nan
    specificity = TN / n_zero if n_zero else np.nan
    precision = TP / (TP + FP) if (TP + FP) else np.nan
    accuracy = (TP + TN) / len(aspen_c)

    missed = aspen_c[aspen_positive & ~ann_positive]

    rows.append({
        "ann_threshold_epsilon": eps,
        "test_rows": len(aspen_c),
        "aspen_positive": n_pos,
        "aspen_zero_or_negative": n_zero,
        "TP": TP,
        "FN_false_carbon_free": FN,
        "FP_false_carbon_positive": FP,
        "TN": TN,
        "false_carbon_free_rate": fcf,
        "false_carbon_free_percent": 100 * fcf,
        "recall": recall,
        "recall_percent": 100 * recall,
        "specificity": specificity,
        "precision": precision,
        "accuracy": accuracy,
        "max_Aspen_FCARBON_among_false_carbon_free":
            float(missed.max()) if len(missed) else np.nan,
    })

out = pd.DataFrame(rows)
out.to_csv(
    OUT / "carbon_boundary_tolerance_summary.csv",
    index=False,
    float_format="%.17g",
)

print("\nCARBON-BOUNDARY TOLERANCE ROBUSTNESS")
print("Aspen truth: FCARBON > 0 is positive for every row.")
print("Only ANN threshold epsilon changes.\n")
print(out.to_string(index=False))
print("\nSaved:")
print(OUT / "carbon_boundary_tolerance_summary.csv")
