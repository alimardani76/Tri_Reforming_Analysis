# noise_robustness.py -> ANN prediction degradation under input noise (5.3)
import numpy as np, pandas as pd
from sklearn.preprocessing import MinMaxScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_squared_error
import tensorflow as tf
from tensorflow.keras import Sequential
from tensorflow.keras.layers import Dense, Input
from tensorflow.keras.callbacks import EarlyStopping

RNG=42; np.random.seed(RNG); tf.random.set_seed(RNG)
N_IN=5
OUT=["FCH4","FH2O","FCO2","FCO","FH2","FCARBON","Q"]; C=OUT.index("FCARBON")

data=pd.read_csv("added2.csv").sample(frac=1,random_state=RNG)
scaler=MinMaxScaler(); df=pd.DataFrame(scaler.fit_transform(data),columns=data.columns)
Xtr,Xte,ytr,yte=train_test_split(df.iloc[:,:N_IN].to_numpy(),df.iloc[:,N_IN:].to_numpy(),
                                  test_size=0.2,random_state=RNG)
m=Sequential([Input(shape=(N_IN,)),Dense(128,activation="relu"),Dense(128,activation="relu"),
              Dense(128,activation="relu"),Dense(128,activation="relu"),Dense(len(OUT))])
m.compile(optimizer=tf.keras.optimizers.Adam(1e-3),loss="mse")
m.fit(Xtr,ytr,epochs=100,batch_size=32,validation_split=0.2,verbose=0,
      callbacks=[EarlyStopping(monitor="val_loss",patience=10,restore_best_weights=True)])

def carbon_metrics(Xin):
    p=m.predict(Xin,verbose=0)
    return (r2_score(yte[:,C],p[:,C]),
            np.sqrt(mean_squared_error(yte[:,C],p[:,C])))

rng=np.random.default_rng(0)
rows=[]
for sigma in [0.0,0.01,0.03,0.05,0.10]:
    r2s,rmses=[],[]
    reps = 1 if sigma==0 else 20
    for _ in range(reps):
        Xn = Xte*(1+rng.normal(0,sigma,Xte.shape))   # multiplicative Gaussian
        Xn = np.clip(Xn,0,1)                          # keep in scaled bounds
        r2,rmse=carbon_metrics(Xn)
        r2s.append(r2); rmses.append(rmse)
    rows.append((f"{int(sigma*100)}%",np.mean(r2s),np.mean(rmses)))
    print(f"sigma={int(sigma*100):>3}%  carbon R2={np.mean(r2s):.4f}  RMSE={np.mean(rmses):.4f}")

pd.DataFrame(rows,columns=["noise","carbon_R2","carbon_RMSE"]).to_csv("noise_robustness.csv",index=False)