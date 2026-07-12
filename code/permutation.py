# ============================================================
# permutation.py
# Carbon-specific permutation importance for the ANN (Fig. 8)
# Manual permutation loop (sklearn-version independent)
# Data: added2.csv -> T P Fw Fc Fo | FCH4 FH2O FCO2 FCO FH2 FCARBON Q
# ============================================================

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from sklearn.preprocessing import MinMaxScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score

import tensorflow as tf
from tensorflow.keras import Sequential
from tensorflow.keras.layers import Dense, Input
from tensorflow.keras.callbacks import EarlyStopping

# ---------- config ----------
RNG = 42
np.random.seed(RNG)
tf.random.set_seed(RNG)

plt.rcParams.update({"font.family":"Arial","font.weight":"bold",
                     "axes.labelweight":"bold","axes.titleweight":"bold",
                     "text.color":"black","axes.labelcolor":"black",
                     "xtick.color":"black","ytick.color":"black"})

N_IN = 5
INPUT_NAMES  = ["T", "P", "Fw", "Fc", "Fo"]
OUTPUT_NAMES = ["FCH4", "FH2O", "FCO2", "FCO", "FH2", "FCARBON", "Q"]
CARBON_IDX   = OUTPUT_NAMES.index("FCARBON")   # = 5 within the output block

# ---------- 1. load & scale ----------
data = pd.read_csv("added2.csv").sample(frac=1, random_state=RNG)
assert data.shape[1] == N_IN + len(OUTPUT_NAMES), \
    f"expected {N_IN + len(OUTPUT_NAMES)} columns, got {data.shape[1]}"

scaler = MinMaxScaler()
df = pd.DataFrame(scaler.fit_transform(data), columns=data.columns)

X_tr, X_te, y_tr, y_te = train_test_split(
    df.iloc[:, :N_IN].to_numpy(),
    df.iloc[:, N_IN:].to_numpy(),
    test_size=0.20, random_state=RNG,
)

# ---------- 2. ANN (3 layers x 128) with early stopping ----------
def build_ann(layers=3, nodes=128, ac="relu", lr=1e-3):
    m = Sequential()
    m.add(Input(shape=(N_IN,)))
    m.add(Dense(nodes, activation=ac))
    for _ in range(layers):
        m.add(Dense(nodes, activation=ac))
    m.add(Dense(len(OUTPUT_NAMES)))
    m.compile(optimizer=tf.keras.optimizers.Adam(lr), loss="mse")
    return m

early = EarlyStopping(monitor="val_loss", patience=10,
                      restore_best_weights=True, verbose=1)

model = build_ann()
model.fit(X_tr, y_tr, epochs=100, batch_size=32,
          validation_split=0.2, verbose=1, callbacks=[early])

# ---------- 3. CARBON-ONLY permutation importance (manual) ----------
def carbon_r2(Xarr):
    pred = model.predict(Xarr, verbose=0)
    return r2_score(y_te[:, CARBON_IDX], pred[:, CARBON_IDX])

baseline = carbon_r2(X_te)
print(f"\nbaseline carbon R2 = {baseline:.6f}")

N_REPEATS = 10
rng = np.random.default_rng(0)
means, stds = [], []

for j, name in enumerate(INPUT_NAMES):
    drops = []
    for _ in range(N_REPEATS):
        Xp = X_te.copy()
        rng.shuffle(Xp[:, j])              # permute feature j only
        drops.append(baseline - carbon_r2(Xp))   # drop in carbon R2
    means.append(np.mean(drops))
    stds.append(np.std(drops))
    print(f"{name:>3}: mean={np.mean(drops):.6f}  std={np.std(drops):.6f}")

imp = (pd.DataFrame({"feature": INPUT_NAMES,
                     "importance_mean": means,
                     "importance_std":  stds})
       .sort_values("importance_mean", ascending=False))
imp.to_csv("perm_importance_carbon.csv", index=False)

print("\n=== Carbon-specific permutation importance (test set, n_repeats=10) ===")
print(imp.to_string(index=False))

# ---------- 4. bar plot (Fig. 8 style) ----------
fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
ax.bar(imp["feature"], imp["importance_mean"],
       yerr=imp["importance_std"], capsize=5)
n = 1.5
ax.tick_params(axis="both", which="major", labelsize=16 * n)
for s in ax.spines.values():
    s.set_linewidth(4)
ax.tick_params(width=4)
ax.set_xlabel("Feature", fontsize=18 * n)
ax.set_ylabel("Importance score", fontsize=18 * n)
fig.tight_layout()
fig.savefig("Figure8_carbon_importance.png", dpi=300, bbox_inches="tight")
plt.show()