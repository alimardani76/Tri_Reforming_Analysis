# carbon_strata.py -> stratified carbon error (answers 2.1)
import numpy as np, pandas as pd
from sklearn.preprocessing import MinMaxScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error
import tensorflow as tf
from tensorflow.keras import Sequential
from tensorflow.keras.layers import Dense, Input
from tensorflow.keras.callbacks import EarlyStopping

RNG=42; np.random.seed(RNG); tf.random.set_seed(RNG)
N_IN=5
OUT=["FCH4","FH2O","FCO2","FCO","FH2","FCARBON","Q"]
C=OUT.index("FCARBON")

data=pd.read_csv("added2.csv").sample(frac=1,random_state=RNG)
scaler=MinMaxScaler(); df=pd.DataFrame(scaler.fit_transform(data),columns=data.columns)
Xtr,Xte,ytr,yte=train_test_split(df.iloc[:,:N_IN].to_numpy(),df.iloc[:,N_IN:].to_numpy(),
                                 test_size=0.2,random_state=RNG)

m=Sequential([Input(shape=(N_IN,)),Dense(128,activation="relu"),Dense(128,activation="relu"),
              Dense(128,activation="relu"),Dense(128,activation="relu"),Dense(len(OUT))])
m.compile(optimizer=tf.keras.optimizers.Adam(1e-3),loss="mse")
m.fit(Xtr,ytr,epochs=100,batch_size=32,validation_split=0.2,verbose=1,
      callbacks=[EarlyStopping(monitor="val_loss",patience=10,restore_best_weights=True)])

pred=m.predict(Xte,verbose=0)
# work in ORIGINAL carbon units (un-scale just the carbon column)
cmin=data.iloc[:,N_IN+C].min(); cmax=data.iloc[:,N_IN+C].max()
yt=yte[:,C]*(cmax-cmin)+cmin
yp=pred[:,C]*(cmax-cmin)+cmin

# bands (original units): zero, low-but-nonzero, high
low_hi=0.2   # transition-zone upper edge; adjust if you like
bands={"zero (=0)":       yt==0,
       f"low (0,{low_hi}]":(yt>0)&(yt<=low_hi),
       f"high (>{low_hi})": yt>low_hi}

rows=[]
for name,mask in bands.items():
    n=int(mask.sum())
    if n==0: continue
    rmse=np.sqrt(mean_squared_error(yt[mask],yp[mask]))
    mae=mean_absolute_error(yt[mask],yp[mask])
    rows.append((name,n,round(rmse,4),round(mae,4)))
tbl=pd.DataFrame(rows,columns=["Carbon band","N","RMSE","MAE"])
tbl.to_csv("carbon_strata.csv",index=False)
print(tbl.to_string(index=False))