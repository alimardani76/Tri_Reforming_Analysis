# regen_fig4_overlay.py -> DT and RF on ONE axis (answers 4.4 honestly)
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.pyplot as plt
plt.rcParams.update({"font.family":"Arial","font.weight":"bold",
                     "axes.labelweight":"bold","axes.titleweight":"bold",
                     "text.color":"black","axes.labelcolor":"black",
                     "xtick.color":"black","ytick.color":"black"})
dt = pd.read_csv("cv_dt.csv")   # max_depth, R2
rf = pd.read_csv("cv_rf.csv")   # max_depth, R2

n = 1.5

fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
ax.plot(dt["max_depth"], dt["R2"], linewidth=2*n, marker="o", markersize=7*n, label="Decision Tree")
ax.plot(rf["max_depth"], rf["R2"], linewidth=2*n, marker="s", markersize=7*n,
        markerfacecolor="none", label="Random Forest")
ax.set_xlabel("Max Depth", fontsize=18*n)
ax.set_ylabel("R\u00b2 score", fontsize=18*n)
ax.set_ylim(0.25, 1.05)
ax.set_xticks(range(0, 16, 5))
ax.tick_params(axis="both", which="major", labelsize=16*n, width=4)
for s in ax.spines.values():
    s.set_linewidth(4)
ax.legend(fontsize=15*n, frameon=False)
fig.tight_layout()
fig.savefig("Figure4_overlay.png", dpi=300, bbox_inches="tight")
plt.show()
print(f"DT @15 = {dt['R2'].iloc[-1]:.4f} | RF @15 = {rf['R2'].iloc[-1]:.4f}")