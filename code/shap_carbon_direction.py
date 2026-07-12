# shap_carbon_direction.py -> sign/direction of each feed's effect on CARBON
# Verifies the 4.7 mechanism from the model itself.
import numpy as np
import pandas as pd
import shap
from sklearn.preprocessing import MinMaxScaler
from sklearn.model_selection import train_test_split
import tensorflow as tf
from tensorflow.keras import Sequential
from tensorflow.keras.layers import Dense, Input
from tensorflow.keras.callbacks import EarlyStopping

RNG = 42
np.random.seed(RNG); tf.random.set_seed(RNG)

N_IN = 5
FEATS = ["T", "P", "Fw", "Fc", "Fo"]
OUT   = ["FCH4","FH2O","FCO2","FCO","FH2","FCARBON","Q"]
CARBON = OUT.index("FCARBON")   # 5

data = pd.read_csv("added2.csv").sample(frac=1, random_state=RNG)
scaler = MinMaxScaler()
df = pd.DataFrame(scaler.fit_transform(data), columns=data.columns)
Xtr, Xte, ytr, yte = train_test_split(df.iloc[:, :N_IN].to_numpy(),
                                       df.iloc[:, N_IN:].to_numpy(),
                                       test_size=0.2, random_state=RNG)

# train the ANN
m = Sequential([Input(shape=(N_IN,)), Dense(128,activation="relu"),
                Dense(128,activation="relu"), Dense(128,activation="relu"),
                Dense(128,activation="relu"), Dense(len(OUT))])
m.compile(optimizer=tf.keras.optimizers.Adam(1e-3), loss="mse")
m.fit(Xtr, ytr, epochs=100, batch_size=32, validation_split=0.2, verbose=0,
      callbacks=[EarlyStopping(monitor="val_loss", patience=10, restore_best_weights=True)])

# SHAP for the CARBON output only. Use a small background + subset for speed.
bg = shap.sample(Xtr, 100, random_state=RNG)
Xs = Xte[:800]                      # subset of test set for SHAP
carbon_predict = lambda x: m.predict(x, verbose=0)[:, CARBON]
explainer = shap.Explainer(carbon_predict, bg)
sv = explainer(Xs)                  # SHAP values for carbon

shap_vals = sv.values               # (n_samples, 5)
feat_vals = Xs                       # (n_samples, 5), scaled 0-1

print("Feature | mean|SHAP| | corr(feat, SHAP) | direction")
print("-"*60)
rows=[]
for j, f in enumerate(FEATS):
    imp  = np.mean(np.abs(shap_vals[:, j]))
    corr = np.corrcoef(feat_vals[:, j], shap_vals[:, j])[0, 1]
    if corr < -0.2:   d = "SINK (higher -> less carbon)"
    elif corr > 0.2:  d = "PROMOTER (higher -> more carbon)"
    else:             d = "weak/mixed"
    rows.append((f, imp, corr, d))
    print(f"{f:>4} | {imp:.4f}     | {corr:+.3f}          | {d}")

pd.DataFrame(rows, columns=["feature","mean_abs_shap","corr","direction"]
             ).to_csv("shap_carbon_direction.csv", index=False)