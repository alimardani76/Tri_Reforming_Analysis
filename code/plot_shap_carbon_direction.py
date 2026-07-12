# plot_shap_carbon_direction.py -> response-letter figure for Comment 4.7
import numpy as np
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "Times New Roman"

# feature, mean|SHAP|, corr(feature, SHAP)  -- from shap_carbon_direction.py
data = [
    ("T",            0.1052, -0.908),
    (r"$F_w$ (steam)", 0.0782, -0.941),
    (r"$F_o$ (O$_2$)", 0.0755, -0.930),
    (r"$F_c$ (CO$_2$)",0.0343, +0.699),
    ("P",            0.0111, +0.383),
]

# signed importance = magnitude * sign(direction)
labels  = [d[0] for d in data]
signed  = [np.sign(d[2]) * d[1] for d in data]
corrs   = [d[2] for d in data]

# sort by magnitude, largest on top
order = np.argsort([abs(s) for s in signed])          # ascending
labels = [labels[i] for i in order]
signed = [signed[i] for i in order]
corrs  = [corrs[i]  for i in order]

colors = ["#c0392b" if s > 0 else "#2c6fbb" for s in signed]  # red promoter, blue sink

fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
y = np.arange(len(labels))
ax.barh(y, signed, color=colors, edgecolor="black", linewidth=1.2)

# annotate each bar with its correlation
for yi, (s, c) in enumerate(zip(signed, corrs)):
    off = 0.004 if s > 0 else -0.004
    ha  = "left" if s > 0 else "right"
    ax.text(s + off, yi, f"r={c:+.2f}", va="center", ha=ha, fontsize=13)

ax.axvline(0, color="black", linewidth=1.5)
ax.set_yticks(y)
ax.set_yticklabels(labels, fontsize=15)
ax.set_xlabel("Signed importance  (mean|SHAP| $\\times$ sign of effect)", fontsize=14)
ax.set_title("Directional effect of each input on carbon formation (SHAP)", fontsize=14)



xmax = max(abs(min(signed)), abs(max(signed))) * 1.35
ax.set_xlim(-xmax, xmax)
for sp in ["top", "right"]:
    ax.spines[sp].set_visible(False)
for sp in ["left", "bottom"]:
    ax.spines[sp].set_linewidth(1.5)
ax.tick_params(width=1.5, labelsize=12)

fig.tight_layout()
fig.savefig("shap_carbon_direction_plot.png", dpi=300, bbox_inches="tight")
plt.show()