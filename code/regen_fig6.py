# regen_fig6.py -> ANN parity plots (a) test (b) train, bold Arial
import numpy as np, pandas as pd, matplotlib.pyplot as plt
from sklearn.preprocessing import MinMaxScaler
from sklearn.model_selection import train_test_split
import tensorflow as tf
from tensorflow.keras import Sequential
from tensorflow.keras.layers import Dense, Input
from tensorflow.keras.callbacks import EarlyStopping

RNG=42; np.random.seed(RNG); tf.random.set_seed(RNG)
plt.rcParams.update({"font.family":"Arial","font.weight":"bold",
                     "axes.labelweight":"bold","axes.titleweight":"bold",
                     "text.color":"black","axes.labelcolor":"black",
                     "xtick.color":"black","ytick.color":"black"})
N_IN=5
data=pd.read_csv("added2.csv").sample(frac=1,random_state=RNG)
N_OUT=data.shape[1]-N_IN
sc=MinMaxScaler(); df=pd.DataFrame(sc.fit_transform(data),columns=data.columns)
Xtr,Xte,ytr,yte=train_test_split(df.iloc[:,:N_IN].to_numpy(),df.iloc[:,N_IN:].to_numpy(),
                                 test_size=0.2,random_state=RNG)
m=Sequential([Input(shape=(N_IN,)),Dense(128,activation="relu"),Dense(128,activation="relu"),
              Dense(128,activation="relu"),Dense(128,activation="relu"),Dense(N_OUT)])
m.compile(optimizer=tf.keras.optimizers.Adam(1e-3),loss="mse")
m.fit(Xtr,ytr,epochs=100,batch_size=32,validation_split=0.2,verbose=0,
      callbacks=[EarlyStopping(monitor="val_loss",patience=10,restore_best_weights=True)])

ptr=m.predict(Xtr,verbose=0); pte=m.predict(Xte,verbose=0)
fig,axes=plt.subplots(1,2,figsize=(13,6),dpi=300)
for ax,(yt,yp,title) in zip(axes,[(yte,pte,"(a) Test set"),(ytr,ptr,"(b) Training set")]):
    ax.scatter(yt.ravel(),yp.ravel(),s=6,alpha=0.25,color="#3b6fb0",edgecolors="none")
    ax.plot([0,1],[0,1],"k--",lw=2)
    ax.set_xlabel("Actual (scaled)",fontsize=18,fontweight="bold")
    ax.set_ylabel("Predicted (scaled)",fontsize=18,fontweight="bold")
    ax.set_title(title,fontsize=18,fontweight="bold")
    ax.set_xlim(0,1); ax.set_ylim(0,1)
    ax.tick_params(labelsize=14,width=2)
    for lb in ax.get_xticklabels()+ax.get_yticklabels(): lb.set_fontweight("bold")
    for s in ax.spines.values(): s.set_linewidth(2)
fig.tight_layout()
fig.savefig("Figure6_regen.png",dpi=300,bbox_inches="tight")
plt.show()