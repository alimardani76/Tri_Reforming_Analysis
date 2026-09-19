# September 2026 R2 verification outputs

This directory preserves the compact numerical outputs used for the second-round
reviewer checks of the TRM manuscript.

- `ann_vs_aspen.csv`: ANN-versus-Aspen errors for all seven outputs at the five final ANN-selected operating points.
- `aspen_results.csv`: direct Aspen outputs and derived performance indicators for those five points.
- `elemental_balances.csv`: C/H/O closure diagnostics for the direct Aspen checks.
- `weight_sensitivity_best.csv`: ANN-selected optima for normalized one-at-a-time weight perturbations.
- `weight_sensitivity_summary.csv`: direct Aspen verification of the eleven normalized weight-sensitivity optima.
- `carbon_boundary_summary.csv`: held-out carbon/no-carbon confusion summary, including false-carbon-free rate and onset recall.

Interpret these CSVs together with the scripts in `code/revision_r2/` and
`simulation/`. Aspen atom-closure status is not a substitute for a
version-specific solver-status check.
