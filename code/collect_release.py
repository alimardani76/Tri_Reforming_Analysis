# collect_release.py
# Run from inside the code/ folder. Gathers all .py scripts and .csv outputs
# into a timestamped release folder for the GitHub repo / submission.
import shutil
from pathlib import Path
from datetime import datetime

HERE = Path(__file__).resolve().parent          # the code/ folder
OUT  = HERE / f"release_{datetime.now():%Y%m%d}"
(OUT / "code").mkdir(parents=True, exist_ok=True)
(OUT / "data").mkdir(parents=True, exist_ok=True)
(OUT / "figures").mkdir(parents=True, exist_ok=True)

# ---- files we expect (scripts) ----
PY_FILES = [
    "train_and_opt.py",
    "permutation.py",
    "metrics_only.py",
    "carbon_strata.py",
    "validate_experimental.py",
    "noise_robustness.py",
    "shap_carbon_direction.py",
    "plot_shap_carbon_direction.py",
    "regen_fig1.py",
    "regen_fig4_overlay.py",
    "regen_fig5.py",
    "regen_fig6.py",
    "regen_fig9.py",
    "regen_fig10.py",
    "collect_release.py",
]

# ---- expected CSV outputs ----
CSV_FILES = [
    "cv_dt.csv", "cv_rf.csv", "cv_xgb.csv", "cv_ann.csv",
    "ga_sensitivity_raw.csv", "ga_sensitivity_summary.csv",
    "r2test.csv", "metrics_extra.csv",
    "perm_importance_carbon.csv", "carbon_strata.csv",
    "validation_songpan.csv", "noise_robustness.csv",
    "shap_carbon_direction.csv",
]

# ---- expected figure PNGs ----
FIG_FILES = [
    "Figure1_regen.png",
    "Figure4_overlay.png",
    "Figure5_combined.png",
    "Figure6_regen.png",
    "Figure8_carbon_importance.png",
    "Figure9_regen.png",
    "Figure10_regen.png",
    "shap_carbon_direction_plot.png",   # response-letter Fig R1
]

# ---- data ----
DATA_FILES = ["added2.csv"]

def grab(names, dest, label):
    found, missing = [], []
    for n in names:
        src = HERE / n
        if src.exists():
            shutil.copy2(src, dest / n)
            found.append(n)
        else:
            missing.append(n)
    print(f"\n[{label}]  copied {len(found)}/{len(names)}")
    for n in found:   print(f"   ok  : {n}")
    for n in missing: print(f"   MISS: {n}")
    return missing

print("="*60)
print(f"Collecting release into: {OUT.name}")
print("="*60)

miss = []
miss += grab(PY_FILES,  OUT / "code",    "PY  scripts")
miss += grab(CSV_FILES, OUT / "code",    "CSV outputs")   # csv next to code
miss += grab(DATA_FILES, OUT / "data",   "DATA")
miss += grab(FIG_FILES, OUT / "figures", "FIGURES")

# copy manuscript + bib if present one level up (Review/ root)
for extra in ["revised_trm.tex", "revised_trm.bib"]:
    for cand in [HERE / extra, HERE.parent / extra]:
        if cand.exists():
            shutil.copy2(cand, OUT / extra)
            print(f"\n[MANUSCRIPT]  ok  : {extra}")
            break

print("\n" + "="*60)
if miss:
    print(f"DONE with {len(miss)} missing item(s) — generate/rerun these then re-run:")
    for m in miss: print(f"   - {m}")
else:
    print("DONE — everything present. Release folder is complete.")
print(f"Location: {OUT}")
print("="*60)