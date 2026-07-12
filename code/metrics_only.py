# metrics_only.py  -> RMSE, MAE, R2 for all four models (1.3 + 5.2)
import numpy as np, pandas as pd
from sklearn.preprocessing import MinMaxScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.ensemble import RandomForestRegressor
from sklearn import tree
from xgboost import XGBRegressor
import tensorflow as tf
from tensorflow.keras import Sequential
from tensorflow.keras.layers import Dense, Input
from tensorflow.keras.callbacks import EarlyStopping

RNG = 42
np.random.seed(RNG); tf.random.set_seed(RNG)

N_IN = 5
data = pd.read_csv("added2.csv").sample(frac=1, random_state=RNG)
N_OUT = data.shape[1] - N_IN

scaler = MinMaxScaler()
df = pd.DataFrame(scaler.fit_transform(data), columns=data.columns)
X_tr, X_te, y_tr, y_te = train_test_split(
    df.iloc[:, :N_IN].to_numpy(), df.iloc[:, N_IN:].to_numpy(),
    test_size=0.20, random_state=RNG)

# --- ANN ---
m = Sequential([Input(shape=(N_IN,)), Dense(128, activation="relu"),
                Dense(128, activation="relu"), Dense(128, activation="relu"),
                Dense(128, activation="relu"), Dense(N_OUT)])
m.compile(optimizer=tf.keras.optimizers.Adam(1e-3), loss="mse")
m.fit(X_tr, y_tr, epochs=100, batch_size=32, validation_split=0.2, verbose=1,
      callbacks=[EarlyStopping(monitor="val_loss", patience=10,
                               restore_best_weights=True)])

# --- trees ---
xgb_final = XGBRegressor().fit(X_tr, y_tr)
dt_final  = tree.DecisionTreeRegressor(max_depth=15).fit(X_tr, y_tr)
rf_final  = RandomForestRegressor(max_depth=15).fit(X_tr, y_tr)

def met(yt, yp):
    return (r2_score(yt, yp),
            np.sqrt(mean_squared_error(yt, yp)),
            mean_absolute_error(yt, yp))

preds = {"ANN": m.predict(X_te, verbose=0),
         "XGBoost": xgb_final.predict(X_te),
         "RF": rf_final.predict(X_te),
         "DT": dt_final.predict(X_te)}
tbl = pd.DataFrame([(n, *met(y_te, p)) for n, p in preds.items()],
                   columns=["Model", "R2", "RMSE", "MAE"]).sort_values("R2", ascending=False)
tbl.to_csv("metrics_extra.csv", index=False)
print(tbl.to_string(index=False))