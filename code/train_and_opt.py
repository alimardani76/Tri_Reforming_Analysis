# ============================================================
# TRM surrogate modeling + GA optimization + GA sensitivity
# Single-file clean pipeline
# ============================================================

# ---------- ALL IMPORTS (verify these load first) ----------
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from sklearn.preprocessing import MinMaxScaler
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import r2_score
from sklearn.ensemble import RandomForestRegressor
from sklearn import tree

from xgboost import XGBRegressor

import tensorflow as tf
from tensorflow.keras import Sequential
from tensorflow.keras.layers import Dense

from sko.GA import GA
from sko.tools import set_run_mode
# -----------------------------------------------------------

# ---------- global config ----------
RNG = 42
np.random.seed(RNG)
tf.random.set_seed(RNG)
plt.rcParams["font.family"] = "Times New Roman"
warnings.filterwarnings("ignore")


# ============================================================
# 1. Load & preprocess
# ============================================================
data = pd.read_csv("added2.csv").sample(frac=1, random_state=RNG)

N_IN = 5                       # inputs: T, P, Fw, Fc, Fo
N_OUT = data.shape[1] - N_IN   # outputs: FCH4, FH2O, FCO2, FCO, FH2, FCARBON, Q

# single scaler on full frame (for train/test of the models)
scaler = MinMaxScaler()
df = pd.DataFrame(scaler.fit_transform(data), columns=data.columns)

X_tr, X_te, y_tr, y_te = train_test_split(
    df.iloc[:, :N_IN].to_numpy(),
    df.iloc[:, N_IN:].to_numpy(),
    test_size=0.20, random_state=RNG,
)

# separate input/output scalers for GA (physical <-> scaled units)
scalerx = MinMaxScaler().fit(data.iloc[:, :N_IN])
scalery = MinMaxScaler().fit(data.iloc[:, N_IN:])


# ============================================================
# 2. ANN builder
# ============================================================
def build_ann(layers=3, nodes=128, ac="relu", lr=1e-3):
    m = Sequential()
    m.add(Dense(nodes, input_dim=N_IN, activation=ac))
    for _ in range(layers):
        m.add(Dense(nodes, activation=ac))
    m.add(Dense(N_OUT))                          # linear output
    m.compile(optimizer=tf.keras.optimizers.Adam(lr), loss="mse")
    return m


# ============================================================
# 3. Hyperparameter sweeps  (saved to CSV for the figures)
# ============================================================
# 3a. XGBoost: learning rate x n_estimators  (Fig 5a)
lrs, ns = [0.1, 0.25, 0.5, 0.75, 1.0], [10, 25, 50, 75, 100]
xgb_rows = []
for lr in lrs:
    for n in ns:
        cv = cross_val_score(XGBRegressor(eta=lr, n_estimators=n),
                             X_tr, y_tr, cv=5, scoring="r2", n_jobs=-1)
        xgb_rows.append((lr, n, cv.mean()))
        print("XGB", lr, n, cv.mean())
pd.DataFrame(xgb_rows, columns=["learning_rate", "n_estimators", "R2"]
             ).to_csv("cv_xgb.csv", index=False)

# 3b. Random forest: max_depth  (Fig 4b)
rf_rows = []
for depth in range(1, 16):
    cv = cross_val_score(RandomForestRegressor(max_depth=depth),
                         X_tr, y_tr, cv=5, scoring="r2", n_jobs=-1)
    rf_rows.append((depth, cv.mean()))
    print("RF", depth, cv.mean())
pd.DataFrame(rf_rows, columns=["max_depth", "R2"]).to_csv("cv_rf.csv", index=False)

# 3c. Decision tree: max_depth  (Fig 4a)
dt_rows = []
for depth in range(1, 16):
    cv = cross_val_score(tree.DecisionTreeRegressor(max_depth=depth),
                         X_tr, y_tr, cv=5, scoring="r2", n_jobs=-1)
    dt_rows.append((depth, cv.mean()))
    print("DT", depth, cv.mean())
pd.DataFrame(dt_rows, columns=["max_depth", "R2"]).to_csv("cv_dt.csv", index=False)

# 3d. ANN: hidden layers x nodes  (Fig 5b) [proper held-out split]
ann_rows = []
for layers in [2, 3, 4, 5]:
    for nodes in [16, 32, 64, 128]:
        scores = []
        for rep in range(5):
            xa, xb, ya, yb = train_test_split(X_tr, y_tr, test_size=0.20,
                                              random_state=rep)
            m = build_ann(layers=layers, nodes=nodes)
            m.fit(xa, ya, epochs=15, batch_size=32, verbose=0)
            scores.append(r2_score(yb, m.predict(xb, verbose=0)))
        ann_rows.append((layers, nodes, np.mean(scores)))
        print("ANN", layers, nodes, np.mean(scores))
pd.DataFrame(ann_rows, columns=["hidden_layers", "nodes", "R2"]
             ).to_csv("cv_ann.csv", index=False)


# ============================================================
# 4. Final ANN (3 layers x 128 nodes)
# ============================================================
model = build_ann(layers=3, nodes=128)
model.fit(X_tr, y_tr, epochs=100, batch_size=32,
          validation_split=0.2, verbose=1)


# ============================================================
# 5. Test-set model comparison  (Table 3 / Fig 7)
# ============================================================
xgb_final = XGBRegressor().fit(X_tr, y_tr)
dt_final  = tree.DecisionTreeRegressor(max_depth=15).fit(X_tr, y_tr)
rf_final  = RandomForestRegressor(max_depth=15).fit(X_tr, y_tr)

res = pd.DataFrame({
    "Algorithm": ["ANN", "XGB", "RF", "DT"],
    "R2": [
        r2_score(y_te, model.predict(X_te, verbose=0)),
        r2_score(y_te, xgb_final.predict(X_te)),
        r2_score(y_te, rf_final.predict(X_te)),
        r2_score(y_te, dt_final.predict(X_te)),
    ],
}).sort_values("R2", ascending=False)
res.to_csv("r2test.csv", index=False)
print(res)


# ============================================================
# 6. Fast NumPy forward pass  (same math as model.predict)
# ============================================================
# Extract trained Dense weights/biases in layer order.
_layers = [l for l in model.layers if l.get_weights()]
Ws = [l.get_weights()[0] for l in _layers]
bs = [l.get_weights()[1] for l in _layers]

def ann_np(Xs):
    """Xs: (batch, 5) MinMax-scaled inputs -> (batch, 7) scaled outputs."""
    a = Xs
    for W, b in zip(Ws[:-1], bs[:-1]):
        a = np.maximum(0.0, a @ W + b)     # ReLU hidden layers
    return a @ Ws[-1] + bs[-1]             # linear output

# sanity check: NumPy path matches Keras (should print ~1e-6 or smaller)
_chk = np.max(np.abs(ann_np(X_te) - model.predict(X_te, verbose=0)))
print("max |ann_np - keras| =", _chk)


# ============================================================
# 7. GA optimization  (Scenario 1 objective, unchanged)
# ============================================================
LB = [500, 1, 0.15, 0.15, 0.0]     # T, P, Fw, Fc, Fo
UB = [1000, 29, 1.0, 1.0, 0.7]

def objective(P):
    """Vectorized Scenario-1 objective (minimized). P: (pop, 5) physical units."""
    preds = ann_np(scalerx.transform(P))
    FCH4, FH2O, FCO2, FCO, FH2, FCARBON, Q = scalery.inverse_transform(preds).T
    FCARBON = np.clip(FCARBON, 0, None)
    E_CO2 = FCO2 - P[:, 3]                        # net CO2 emission
    return -(1 - FCH4) - FH2 + FCARBON + E_CO2 + np.abs(Q) / 10.0

set_run_mode(objective, "vectorization")
ga = GA(func=objective, n_dim=5, size_pop=50, max_iter=1000,
        prob_mut=0.001, lb=LB, ub=UB, precision=1e-7)
best_x, best_y = ga.run()
print("best x:", best_x, "\nbest y:", float(np.ravel(best_y)[0]))


# ============================================================
# 8. GA SENSITIVITY TEST  ->  evidence for reviewer comment 1.1
#    Sweep population x mutation x seed; report objective,
#    seed-spread, and generations-to-converge.
# ============================================================
POPS   = [20, 50, 100, 200]
MUTS   = [0.001, 0.01, 0.1]
SEEDS  = [0, 1, 2, 3, 4]
MAX_IT = 300
TOL    = 1e-3

def gen_to_converge(hist, final, tol=TOL):
    hist = np.asarray(hist).ravel()
    target = abs(final) * tol
    for g, v in enumerate(hist):
        if abs(v - final) <= target:
            return g + 1
    return len(hist)

rows = []
for pop in POPS:
    for pm in MUTS:
        for sd in SEEDS:
            np.random.seed(sd)
            g = GA(func=objective, n_dim=5, size_pop=pop, max_iter=MAX_IT,
                   prob_mut=pm, lb=LB, ub=UB, precision=1e-7)
            _, by = g.run()
            by = float(np.ravel(by)[0])
            gc = gen_to_converge(g.generation_best_Y, by)
            rows.append((pop, pm, sd, by, gc))
            print(f"pop={pop:>3} mut={pm:<5} seed={sd}  best={by:.6f}  gen={gc}")

raw = pd.DataFrame(rows, columns=["pop", "prob_mut", "seed",
                                  "best_obj", "gen_converge"])
raw.to_csv("ga_sensitivity_raw.csv", index=False)

summary = (raw.groupby(["pop", "prob_mut"])
              .agg(best_mean=("best_obj", "mean"),
                   best_std =("best_obj", "std"),
                   gen_mean =("gen_converge", "mean"))
              .reset_index())
summary.to_csv("ga_sensitivity_summary.csv", index=False)
print("\n=== GA sensitivity summary ===")
print(summary.to_string(index=False))