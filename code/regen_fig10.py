# regen_fig10.py -> 5x3 contour grid, matches original smoothing/scaling
# Fix: consistent units (no x100), per-panel colorbars, cubic smoothing.
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.interpolate import griddata

plt.rcParams.update({
    "font.family": "Arial",
    "font.weight": "bold",
    "axes.labelweight": "bold",
    "axes.titleweight": "bold",
    "mathtext.default": "bf",
})
BASE = 1.35

data = pd.read_csv("added2.csv")
Ts = [500, 600, 700, 800, 900, 1000]
ratio_grid = {"Fw": [0,.1,.2,.3,.4,.5,.6,.7,.8,.9,1.0],
              "Fc": [0,.1,.2,.3,.4,.5,.6,.7,.8,.9,1.0],
              "Fo": [0,.1,.2,.3,.4,.5,.6,.7]}

def metric_block(sub, name):
    if name == "XCH4": return (1 - sub["FCH4"]).mean()
    if name == "YCO":  return sub["FCO"].mean()
    if name == "YH2":  return sub["FH2"].mean()
    if name == "ECO2": return (sub["FCO2"] - sub["Fc"]).mean()
    if name == "Coke": return sub["FCARBON"].mean()

metrics = [
    ("XCH4", r"$X_{CH_4}$ (–)"),
    ("YCO",  r"$Y_{CO}$ (mol mol$^{-1}$)"),
    ("YH2",  r"$Y_{H_2}$ (mol mol$^{-1}$)"),
    ("ECO2", r"$E_{CO_2}$ (mol mol$^{-1}$)"),
    ("Coke", r"Coke (mol mol$^{-1}$)"),
]
planes = ["Fw", "Fc", "Fo"]
plane_title  = {"Fw": r"$F_w$–$T$", "Fc": r"$F_c$–$T$", "Fo": r"$F_o$–$T$"}
plane_ylabel = {"Fw": r"$F_w$", "Fc": r"$F_c$", "Fo": r"$F_o$"}

nrow, ncol = len(metrics), len(planes)
fig, axes = plt.subplots(nrow, ncol, figsize=(18, 22), dpi=300)
fig.subplots_adjust(hspace=0.5, wspace=0.55, top=0.96, bottom=0.05)

for ri, (mname, clabel) in enumerate(metrics):
    for ci, pl in enumerate(planes):
        ax = axes[ri, ci]
        rs = ratio_grid[pl]
        # collect scattered points (T, ratio, value)
        Tpts, Rpts, Vpts = [], [], []
        for t in Ts:
            bt = data[data["T"] == t]
            for r in rs:
                sub = bt[np.isclose(bt[pl], r)]
                if len(sub):
                    Tpts.append(t); Rpts.append(r)
                    Vpts.append(metric_block(sub, mname))
        Tpts, Rpts, Vpts = map(np.array, (Tpts, Rpts, Vpts))

        # cubic-interpolate onto a fine grid -> smooth contours (like plotly)
        Tg, Rg = np.meshgrid(np.linspace(min(Ts), max(Ts), 300),
                             np.linspace(min(rs), max(rs), 300))
        Zg = griddata((Tpts, Rpts), Vpts, (Tg, Rg), method="cubic")

        cf = ax.contourf(Tg, Rg, Zg, levels=20, cmap="viridis")
        ax.contour(Tg, Rg, Zg, levels=12, colors="k", linewidths=0.5, alpha=0.4)

        ax.set_xlabel("T (\u00b0C)", fontsize=15*BASE, fontweight="bold")
        ax.set_ylabel(plane_ylabel[pl], fontsize=16*BASE, fontweight="bold")
        ax.tick_params(labelsize=12*BASE, width=1.6)
        for lbl in ax.get_xticklabels() + ax.get_yticklabels():
            lbl.set_fontweight("bold")
        for s in ax.spines.values():
            s.set_linewidth(1.6)
        if ri == 0:
            ax.set_title(plane_title[pl], fontsize=18*BASE, pad=12, fontweight="bold")

        # per-panel colorbar (restores original look)
        cbar = fig.colorbar(cf, ax=ax, fraction=0.046, pad=0.03)
        cbar.set_label(clabel, size=12*BASE, weight="bold")
        cbar.ax.tick_params(labelsize=10*BASE)
        for t in cbar.ax.get_yticklabels():
            t.set_fontweight("bold")

fig.savefig("Figure10_regen.png", dpi=300, bbox_inches="tight")
plt.show()
print("saved Figure10_regen.png")