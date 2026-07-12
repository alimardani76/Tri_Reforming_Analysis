# regen_fig1.py -> histograms of the 7 outputs, 10 bins, bold Arial
import numpy as np, pandas as pd, matplotlib.pyplot as plt
from scipy.stats import skew

plt.rcParams.update({"font.family":"Arial","font.weight":"bold",
                     "axes.labelweight":"bold","axes.titleweight":"bold",
                     "text.color":"black","axes.labelcolor":"black",
                     "xtick.color":"black","ytick.color":"black"})
data = pd.read_csv("added2.csv")
cols = ["FH2O","FCO2","FCO","FH2","FCARBON","Q","FCH4"]
labels = [r"$F_{H_2O}$", r"$F_{CO_2}$", r"$F_{CO}$", r"$F_{H_2}$",
          r"$F_{Carbon}$", r"$Q$", r"$F_{CH_4}$"]

fig, axes = plt.subplots(2, 4, figsize=(20, 9), dpi=300)
axes = axes.ravel()
for ax, c, lab in zip(axes, cols, labels):
    ax.hist(data[c], bins=10, color="#3b6fb0", edgecolor="black", linewidth=1.2)
    ax.set_xlabel(lab, fontsize=20, fontweight="bold")
    ax.set_ylabel("Count", fontsize=18, fontweight="bold")
    ax.tick_params(labelsize=14, width=2)
    for lb in ax.get_xticklabels()+ax.get_yticklabels(): lb.set_fontweight("bold")
    for s in ax.spines.values(): s.set_linewidth(2)
    ax.text(0.95, 0.92, f"skew = {skew(data[c]):.2f}", transform=ax.transAxes,
            ha="right", va="top", fontsize=14, fontweight="bold",
            bbox=dict(boxstyle="round", fc="white", ec="black"))
axes[-1].axis("off")
fig.tight_layout()
fig.savefig("Figure1_regen.png", dpi=300, bbox_inches="tight")
plt.show()