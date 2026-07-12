# regen_fig5.py -> combined Fig 5: (a) XGBoost 5x5, (b) ANN 4x4
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

import matplotlib.pyplot as plt
plt.rcParams.update({"font.family":"Arial","font.weight":"bold",
                     "axes.labelweight":"bold","axes.titleweight":"bold",
                     "text.color":"black","axes.labelcolor":"black",
                     "xtick.color":"black","ytick.color":"black"})
n = 1.5

# ---- (a) XGBoost ----
xg = pd.read_csv("cv_xgb.csv")          # learning_rate, n_estimators, R2
lrs = [0.1, 0.25, 0.5, 0.75, 1.0]
ns  = [10, 25, 50, 75, 100]
gxg = xg.pivot(index="learning_rate", columns="n_estimators", values="R2").reindex(index=lrs, columns=ns)

# ---- (b) ANN ----
an = pd.read_csv("cv_ann.csv")          # hidden_layers, nodes, R2
layers = [2, 3, 4, 5]
nodes  = [16, 32, 64, 128]
gan = an.pivot(index="hidden_layers", columns="nodes", values="R2").reindex(index=layers, columns=nodes)

fig, axes = plt.subplots(1, 2, figsize=(15, 6), dpi=300)

# panel a
ax = axes[0]
im = ax.imshow(gxg.values, cmap="Blues", aspect="auto", origin="lower", vmin=0.98, vmax=1.0)
ax.set_xticks(range(len(ns)));  ax.set_xticklabels(ns)
ax.set_yticks(range(len(lrs))); ax.set_yticklabels(lrs)
ax.set_xlabel("Number of Estimators", fontsize=17*n)
ax.set_ylabel("Learning Rate", fontsize=17*n)
ax.set_title("(a) XGBoost", fontsize=18*n)
for i in range(len(lrs)):
    for j in range(len(ns)):
        ax.text(j, i, f"{gxg.values[i,j]:.3f}", ha="center", va="center", fontsize=10*n)

# panel b
ax = axes[1]
im2 = ax.imshow(gan.values, cmap="Blues", aspect="auto", origin="lower", vmin=0.96, vmax=1.0)
ax.set_xticks(range(len(nodes)));  ax.set_xticklabels(nodes)
ax.set_yticks(range(len(layers))); ax.set_yticklabels(layers)
ax.set_xlabel("Nodes per Layer", fontsize=17*n)
ax.set_ylabel("Hidden Layers", fontsize=17*n)
ax.set_title("(b) ANN", fontsize=18*n)
for i in range(len(layers)):
    for j in range(len(nodes)):
        ax.text(j, i, f"{gan.values[i,j]:.3f}", ha="center", va="center", fontsize=10*n)

for ax in axes:
    ax.tick_params(axis="both", which="major", labelsize=15*n, width=3)
    for s in ax.spines.values(): s.set_linewidth(3)

fig.colorbar(im,  ax=axes[0], fraction=0.046, pad=0.04).set_label("R\u00b2", size=15*n)
fig.colorbar(im2, ax=axes[1], fraction=0.046, pad=0.04).set_label("R\u00b2", size=15*n)
fig.tight_layout()
fig.savefig("Figure5_combined.png", dpi=300, bbox_inches="tight")
plt.show()

print("XGB grid:\n", gxg.round(4))
print("\nANN grid:\n", gan.round(4))