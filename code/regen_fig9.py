# regen_fig9.py -> ONE figure, panels (a) T-P, (b) T-Fc, (c) beeswarm
# Bold Arial black; carbon-specific SHAP. SLOW (~4 min).
import numpy as np, pandas as pd, matplotlib.pyplot as plt, shap
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
                     "xtick.color":"black","ytick.color":"black",
                     "axes.edgecolor":"black"})
N_IN=5; FEATS=["T","P","Fw","Fc","Fo"]
OUT=["FCH4","FH2O","FCO2","FCO","FH2","FCARBON","Q"]; C=OUT.index("FCARBON")

data=pd.read_csv("added2.csv").sample(frac=1,random_state=RNG)
sc=MinMaxScaler(); df=pd.DataFrame(sc.fit_transform(data),columns=data.columns)
Xtr,Xte,ytr,yte=train_test_split(df.iloc[:,:N_IN].to_numpy(),df.iloc[:,N_IN:].to_numpy(),
                                 test_size=0.2,random_state=RNG)
m=Sequential([Input(shape=(N_IN,)),Dense(128,activation="relu"),Dense(128,activation="relu"),
              Dense(128,activation="relu"),Dense(128,activation="relu"),Dense(len(OUT))])
m.compile(optimizer=tf.keras.optimizers.Adam(1e-3),loss="mse")
m.fit(Xtr,ytr,epochs=100,batch_size=32,validation_split=0.2,verbose=0,
      callbacks=[EarlyStopping(monitor="val_loss",patience=10,restore_best_weights=True)])

bg=shap.sample(Xtr,100,random_state=RNG)
carbon=lambda x:m.predict(x,verbose=0)[:,C]
expl=shap.Explainer(carbon,bg)
Xs=Xte[:800]; sv=expl(Xs); S=sv.values
Tphys=Xs[:,0]*(1000-500)+500
def phys(idx):
    lo,hi={1:(1,29),2:(0,1),3:(0,1),4:(0,0.7)}[idx]
    return Xs[:,idx]*(hi-lo)+lo

FS=22   # base font (bold)

fig=plt.figure(figsize=(22,6.5),dpi=300)
ax0=fig.add_subplot(1,3,1); ax1=fig.add_subplot(1,3,2); ax2=fig.add_subplot(1,3,3)

def scatter(ax, color_idx, clabel, title):
    sct=ax.scatter(Tphys, S[:,0], c=phys(color_idx), cmap="Blues",
                   s=110, edgecolors="black", linewidths=0.6, alpha=0.65)
    ax.set_xlabel("T (\u00b0C)", fontsize=FS, fontweight="bold", color="black")
    ax.set_ylabel("SHAP value for carbon", fontsize=FS, fontweight="bold", color="black")
    ax.set_title(title, fontsize=FS, fontweight="bold", color="black")
    ax.tick_params(labelsize=FS-6, width=3, colors="black")
    for lb in ax.get_xticklabels()+ax.get_yticklabels(): lb.set_fontweight("bold")
    for s in ax.spines.values(): s.set_linewidth(3); s.set_edgecolor("black")
    cb=fig.colorbar(sct, ax=ax)
    cb.set_label(clabel, size=FS-4, weight="bold", color="black")   # colour = interacting feature
    cb.ax.tick_params(labelsize=FS-8, colors="black")
    for lb in cb.ax.get_yticklabels(): lb.set_fontweight("bold")

scatter(ax0, 1, "P (bar)",  "(a) T–P interaction")
scatter(ax1, 3, r"$F_c$",   "(b) T–$F_c$ interaction")

# ---- (c) beeswarm into ax2 ----
plt.sca(ax2)
sv.feature_names=FEATS
shap.summary_plot(sv, features=Xs, feature_names=FEATS,
                  show=False, color_bar=True, plot_size=None)
ax2=plt.gca()
ax2.set_title("(c) SHAP summary", fontsize=FS, fontweight="bold", color="black")
ax2.set_xlabel("SHAP value for carbon", fontsize=FS, fontweight="bold", color="black")
# force EVERYTHING black + bold (summary_plot defaults to grey)
ax2.tick_params(labelsize=FS-6, width=3, colors="black")
for lb in ax2.get_xticklabels()+ax2.get_yticklabels():
    lb.set_fontweight("bold"); lb.set_color("black")
for s in ax2.spines.values(): s.set_linewidth(3); s.set_edgecolor("black")
ax2.xaxis.label.set_color("black"); ax2.yaxis.label.set_color("black")
# recolor the SHAP colorbar (last axis in fig) to black text
for cax in fig.axes:
    if cax.get_ylabel() in ("Feature value",):
        cax.tick_params(colors="black")
        cax.yaxis.label.set_color("black"); cax.yaxis.label.set_fontweight("bold")

fig.tight_layout()
fig.savefig("Figure9_regen.png", dpi=300, bbox_inches="tight")
plt.show()
print("saved Figure9_regen.png")