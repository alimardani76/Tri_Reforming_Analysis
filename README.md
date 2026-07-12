# Explainable ML for Low-Emission Methane Tri-Reforming

Code, data, figures, and Aspen-automation utilities for the manuscript:

**"Explainable Machine Learning for Low-Emission Methane Tri-Reforming:
Carbon Formation, Hydrogen Production, and Operating-Window Optimization"**


Yaghoubi, Mansouri, Alimardani, Fazeli, Asgari.

---

## Overview

An Aspen Plus Gibbs free-energy-minimization model generates a 46,464-point
tri-reforming (TRM) equilibrium dataset. Decision-tree, random-forest, XGBoost,
and artificial-neural-network (ANN) surrogates are trained and compared; the ANN
is interrogated with permutation importance and SHAP, and embedded in a
genetic-algorithm multi-objective optimization. Every figure and table in the
paper is regenerated from committed code and data.

## Repository structure

    .
    ├── data/
    │   └── added2.csv                 # 46,464-point equilibrium dataset
    ├── code/
    │   ├── train_and_opt.py           # model training + GA + sensitivity
    │   ├── permutation.py             # carbon-specific permutation importance (Fig 8)
    │   ├── metrics_only.py            # RMSE / MAE table
    │   ├── carbon_strata.py           # regime-stratified carbon error
    │   ├── validate_experimental.py   # Aspen vs Song & Pan (2004) benchmark
    │   ├── noise_robustness.py        # input-noise degradation test
    │   ├── shap_carbon_direction.py   # SHAP sink/promoter direction check
    │   ├── regen_fig1.py ... regen_fig10.py   # figure regeneration
    │   └── plot_shap_carbon_direction.py      # response-letter figure
    ├── figures/                       # generated PNGs
    └── simulation/
        ├── TRM_automation_no_S1.apw   # clean Aspen model (no sensitivity block)
        ├── TRM_original_with_S1.apw   # original Aspen model (built-in sensitivity S-1)
        └── verify_clean_aspen.py      # Python-Aspen COM automation / verification

## Requirements

Python 3.9+ with:

    numpy pandas matplotlib scipy scikit-learn xgboost tensorflow shap scikit-opt

The Aspen-automation script additionally requires Windows, a licensed Aspen Plus
installation, and pywin32:

    pip install pywin32

## Reproducing the ML results

All ML scripts read `data/added2.csv` and use a fixed seed (42). From `code/`:

    python train_and_opt.py        # models, GA, sensitivity table, CV CSVs
    python metrics_only.py         # RMSE / MAE
    python permutation.py          # Fig 8 + carbon importances
    python carbon_strata.py        # stratified carbon error
    python noise_robustness.py     # noise degradation table
    python shap_carbon_direction.py
    python regen_fig1.py           # (and regen_fig4_overlay / 5 / 6 / 9 / 10)

---

## Aspen Plus automation (simulation/)

This folder contains the thermodynamic model that produced the dataset, plus a
Python driver that controls Aspen Plus programmatically through its COM
interface. This is useful for anyone wanting to regenerate the data, run new
operating points, or couple Aspen to a Python workflow without manual GUI use.

### Files

- **TRM_automation_no_S1.apw** — the clean model used for automation. The
  built-in Aspen sensitivity block (S-1) has been removed so that operating
  points are driven entirely from Python; this avoids conflicts between the
  external driver and Aspen's internal case table.
- **TRM_original_with_S1.apw** — the original model, retaining the internal
  sensitivity block S-1 (the full-factorial sweep over T, P, Fw, Fc, Fo used to
  build the 46,464-point dataset). Kept for provenance.
- **verify_clean_aspen.py** — the Python-Aspen COM driver / verifier.

### What verify_clean_aspen.py does

Using win32com, the script:

1. Launches Aspen headlessly (Apwn.Document, Visible = 0, SuppressDialogs = 1)
   and loads TRM_automation_no_S1.apw.
2. Writes inputs directly to the flowsheet tree — feed temperature and pressure,
   and the five operating variables (reactor T and P; inlet CH4, H2O, CO2, O2
   flows) — via explicit node paths such as \Data\Blocks\B1\Input\TEMP and
   \Data\Streams\1\Input\FLOW\MIXED\CO2.
3. Runs the RGibbs reactor (Reinit() then Engine.Run2()), polling
   Engine.IsRunning with a timeout.
4. Reads the outlet molar flows and reactor duty from the product-stream and
   block-output nodes, converting the heat duty from cal/s to kW
   (Q_kW = QCALC * 4.184 / 1000).
5. Cross-checks the Aspen result at several representative operating points
   against the corresponding rows of added2.csv, applying relative/absolute
   tolerances and printing a PASS/FAIL report per variable.

In short, it is a minimal, reusable template for driving Aspen Plus from Python:
set inputs -> solve -> read outputs -> validate against stored data. The same
input/output node map can be repurposed to generate new datasets or to embed
Aspen in a larger automated pipeline.

### Usage

    pip install pywin32
    python simulation/verify_clean_aspen.py

Edit the ROOT path near the top of the script so CLEAN_APW and DATA_CSV point to
your local simulation/ and data/ folders. A licensed Aspen Plus installation
registered for COM (Apwn.Document) is required.

Note: .apw files are Aspen Plus binaries and require Aspen Plus to open. They are
provided for reproducibility and for users who wish to extend the automation; the
ML pipeline itself runs entirely from data/added2.csv and does not need Aspen.

---

## Data

added2.csv columns:
`T, P, Fw, Fc, Fo, FCH4, FH2O, FCO2, FCO, FH2, FCARBON, Q`
(five inputs, then seven normalized outputs per mole of inlet CH4).
