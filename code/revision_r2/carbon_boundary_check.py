"""
Reviewer #2 Comment 4: carbon/no-carbon boundary check.

This is intentionally simple:
- no retraining
- no Aspen reruns
- no 0.2 threshold
- uses the held-out ANN test set
- treats Aspen FCARBON == 0 as carbon-free and FCARBON > 0 as carbon-forming
- reports false-carbon-free predictions directly

Place in:
    code/revision_r2/carbon_boundary_check.py

Run from repository root:
    python ./code/revision_r2/carbon_boundary_check.py

Outputs:
    ann_optimization_results/revision_carbon_boundary/
        carbon_boundary_summary.csv
        carbon_boundary_misclassified.csv
"""

from pathlib import Path
import pickle

import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.model_selection import train_test_split


# ============================================================
# Configuration
# ============================================================

ROOT = Path(".")
DATA_PATH = ROOT / "data" / "added2.csv"
MODEL_PATH = ROOT / "ann_optimization_results" / "ann.keras"
SCALER_PATH = ROOT / "ann_optimization_results" / "scalers.pkl"

OUT = ROOT / "ann_optimization_results" / "revision_carbon_boundary"
OUT.mkdir(parents=True, exist_ok=True)

RNG = 42
TEST_SIZE = 0.20

INPUTS = ["T", "P", "Fw", "Fc", "Fo"]
OUTPUTS = ["FCH4", "FH2O", "FCO2", "FCO", "FH2", "FCARBON", "Q"]


# ============================================================
# Load exact data/model/scalers used in the revision ANN
# ============================================================

for p in [DATA_PATH, MODEL_PATH, SCALER_PATH]:
    if not p.exists():
        raise FileNotFoundError(p)

data = pd.read_csv(DATA_PATH)

expected = INPUTS + OUTPUTS
if list(data.columns) != expected:
    raise ValueError(
        "Unexpected CSV columns/order.\n"
        f"Expected: {expected}\n"
        f"Actual:   {list(data.columns)}"
    )

data = data.apply(pd.to_numeric, errors="raise")

if not np.isfinite(data.to_numpy()).all():
    raise ValueError("Dataset contains missing/nonfinite values.")

# Preserve the exact pre-split shuffle used when the saved ANN was trained.
data = data.sample(frac=1, random_state=RNG)

X = data[INPUTS].to_numpy(dtype=float)
Y = data[OUTPUTS].to_numpy(dtype=float)

with SCALER_PATH.open("rb") as f:
    saved = pickle.load(f)

scalerx = saved["scalerx"]
scalery = saved["scalery"]

model = tf.keras.models.load_model(MODEL_PATH, compile=False)

# Reconstruct the exact held-out 20% positions.
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

carbon_idx = OUTPUTS.index("FCARBON")
aspen_c = Y_test[:, carbon_idx]
ann_c = Y_pred[:, carbon_idx]


# ============================================================
# Carbon/no-carbon boundary metrics
# ============================================================

# No engineering cutoff: use the Aspen equilibrium result itself.
aspen_positive = aspen_c > 0.0
ann_positive = ann_c > 0.0

TP = int(np.sum(aspen_positive & ann_positive))
FN = int(np.sum(aspen_positive & ~ann_positive))   # dangerous: Aspen carbon, ANN says free
FP = int(np.sum(~aspen_positive & ann_positive))
TN = int(np.sum(~aspen_positive & ~ann_positive))

n = len(aspen_c)
n_pos = int(np.sum(aspen_positive))
n_zero = int(np.sum(~aspen_positive))

false_carbon_free_rate = FN / n_pos if n_pos else np.nan
carbon_recall = TP / n_pos if n_pos else np.nan
false_carbon_positive_rate = FP / n_zero if n_zero else np.nan
specificity = TN / n_zero if n_zero else np.nan
precision = TP / (TP + FP) if (TP + FP) else np.nan
accuracy = (TP + TN) / n if n else np.nan

positive_values = aspen_c[aspen_positive]

smallest_positive = (
    float(np.min(positive_values)) if len(positive_values) else np.nan
)

# Magnitude of carbon in the false-carbon-free cases.
if FN:
    missed_actual = aspen_c[aspen_positive & ~ann_positive]
    missed_pred = ann_c[aspen_positive & ~ann_positive]

    missed_actual_mean = float(np.mean(missed_actual))
    missed_actual_median = float(np.median(missed_actual))
    missed_actual_max = float(np.max(missed_actual))
    missed_pred_min = float(np.min(missed_pred))
else:
    missed_actual_mean = np.nan
    missed_actual_median = np.nan
    missed_actual_max = np.nan
    missed_pred_min = np.nan


summary = pd.DataFrame([{
    "test_rows": n,
    "aspen_zero_carbon_rows": n_zero,
    "aspen_positive_carbon_rows": n_pos,
    "smallest_positive_Aspen_FCARBON": smallest_positive,

    "true_positive": TP,
    "false_carbon_free": FN,
    "false_carbon_positive": FP,
    "true_negative": TN,

    "false_carbon_free_rate": false_carbon_free_rate,
    "false_carbon_free_percent": 100.0 * false_carbon_free_rate,
    "carbon_onset_recall": carbon_recall,
    "carbon_onset_recall_percent": 100.0 * carbon_recall,

    "false_carbon_positive_rate": false_carbon_positive_rate,
    "false_carbon_positive_percent": 100.0 * false_carbon_positive_rate,
    "specificity": specificity,
    "precision": precision,
    "accuracy": accuracy,

    "mean_actual_FCARBON_in_false_carbon_free_cases": missed_actual_mean,
    "median_actual_FCARBON_in_false_carbon_free_cases": missed_actual_median,
    "max_actual_FCARBON_in_false_carbon_free_cases": missed_actual_max,
    "most_negative_ANN_FCARBON_in_false_carbon_free_cases": missed_pred_min,
}])

summary.to_csv(
    OUT / "carbon_boundary_summary.csv",
    index=False,
    float_format="%.17g",
)


# ============================================================
# Save only misclassified boundary cases for inspection
# ============================================================

mis = (aspen_positive != ann_positive)

misclassified = pd.DataFrame(X_test[mis], columns=INPUTS)
misclassified["Aspen_FCARBON"] = aspen_c[mis]
misclassified["ANN_FCARBON"] = ann_c[mis]
misclassified["error_ANN_minus_Aspen"] = ann_c[mis] - aspen_c[mis]
misclassified["classification"] = np.where(
    aspen_positive[mis] & ~ann_positive[mis],
    "FALSE_CARBON_FREE",
    "FALSE_CARBON_POSITIVE",
)

misclassified = misclassified.sort_values(
    ["classification", "Aspen_FCARBON"],
    ascending=[True, False],
)

misclassified.to_csv(
    OUT / "carbon_boundary_misclassified.csv",
    index=False,
    float_format="%.17g",
)


# ============================================================
# Console report
# ============================================================

print("\n============================================================")
print("CARBON / NO-CARBON BOUNDARY CHECK — HELD-OUT TEST SET")
print("============================================================")
print(f"Test rows:                    {n}")
print(f"Aspen carbon-free rows:       {n_zero}")
print(f"Aspen carbon-forming rows:    {n_pos}")
print(f"Smallest positive Aspen C:    {smallest_positive:.9g}")
print()
print(f"True carbon-forming:          {TP}")
print(f"False carbon-free:            {FN}")
print(f"False carbon-positive:        {FP}")
print(f"True carbon-free:             {TN}")
print()
print(
    f"False-carbon-free rate:       "
    f"{100.0 * false_carbon_free_rate:.4f}%"
)
print(
    f"Carbon-onset recall:          "
    f"{100.0 * carbon_recall:.4f}%"
)
print(
    f"False-carbon-positive rate:   "
    f"{100.0 * false_carbon_positive_rate:.4f}%"
)
print(f"Overall boundary accuracy:    {100.0 * accuracy:.4f}%")

if FN:
    print()
    print("False-carbon-free cases:")
    print(f"  mean actual carbon:         {missed_actual_mean:.9g}")
    print(f"  median actual carbon:       {missed_actual_median:.9g}")
    print(f"  maximum actual carbon:      {missed_actual_max:.9g}")

print("\nSaved:")
print(OUT / "carbon_boundary_summary.csv")
print(OUT / "carbon_boundary_misclassified.csv")