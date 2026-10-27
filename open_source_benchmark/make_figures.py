"""Regenerate figures entirely from this run's manifest and predictions."""
from pathlib import Path
import argparse

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def make_figures(out):
    out = Path(out)
    raw = pd.read_csv(out / "predictions.csv")
    raw = raw[(raw.status == "ok") & (raw.cohort == "grid")]
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(1, 3, figsize=(12, 4), constrained_layout=True)
    for ax, key, label in zip(axes, ["FH2", "FCO", "FCARBON"], ["H2", "CO", "Graphite C"]):
        for engine, group in raw.groupby("engine"):
            ax.scatter(group["aspen_"+key], group["pred_"+key], s=24,
                       marker="o" if engine == "scipy" else "+", alpha=.65, label=engine)
        maximum = raw[["aspen_"+key, "pred_"+key]].max().max()*1.05
        ax.plot([0, maximum], [0, maximum], color="0.4", linewidth=1)
        ax.set(xlabel="Aspen SRK [mol/mol inlet CH4]", ylabel="Ideal-gas + graphite [mol/mol inlet CH4]",
               title=label, xlim=(-.03, maximum), ylim=(-.03, maximum))
    axes[0].legend()
    fig.suptitle(f"Seven-species equilibrium: {raw.case_id.nunique()} selected grid cases (regime-balanced sample)")
    fig.savefig(out / "parity.png", dpi=180)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), constrained_layout=True)
    sweep = raw[raw.group.str.contains("co2_sweep")]
    for temperature, group in sweep.groupby("T"):
        scipy = group[group.engine == "scipy"].sort_values("Fc")
        line, = axes[0].plot(scipy.Fc, scipy.aspen_FCARBON, "o-", label=f"{temperature:g} C Aspen SRK")
        axes[0].plot(scipy.Fc, scipy.pred_FCARBON, "x--", color=line.get_color(), label=f"{temperature:g} C SciPy")
        ct = group[group.engine == "cantera"].sort_values("Fc")
        if len(ct):
            axes[0].scatter(ct.Fc, ct.pred_FCARBON, marker="+", s=55, color=line.get_color())
    axes[0].set(xlabel="Inlet CO2/CH4 [mol/mol]", ylabel="Graphite [mol/mol inlet CH4]",
                title="P=1 bar, H2O/CH4=0.2, O2/CH4=0")
    axes[0].legend(fontsize=8)
    pressure = raw[raw.group.str.contains("pressure_sweep")]
    scipy = pressure[pressure.engine == "scipy"].sort_values("P")
    axes[1].plot(scipy.P, scipy.aspen_FCARBON, "o-", label="Aspen SRK")
    axes[1].plot(scipy.P, scipy.pred_FCARBON, "x--", label="SciPy ideal gas")
    ct = pressure[pressure.engine == "cantera"].sort_values("P")
    if len(ct):
        axes[1].plot(ct.P, ct.pred_FCARBON, "+", label="Cantera ideal gas")
    axes[1].set(xlabel="Pressure [bar]", ylabel="Graphite [mol/mol inlet CH4]",
                title="800 C, H2O/CH4=0.2, CO2/CH4=0.6, O2/CH4=0.1")
    axes[1].legend(fontsize=8)
    fig.suptitle("Controlled sweeps: actual source-grid rows; graphite allowed in every calculation\nCantera + markers overlap SciPy where they agree")
    fig.savefig(out / "carbon_sweeps.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "results")
    make_figures(parser.parse_args().out)
