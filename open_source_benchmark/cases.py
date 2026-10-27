"""Deterministic, deliberately regime-balanced sample (not population weighted)."""
import hashlib

import numpy as np
import pandas as pd

INPUTS = ["T", "P", "Fw", "Fc", "Fo"]
CARBON_THRESHOLD = 1e-6


def read_grid(path):
    grid = pd.read_csv(path, encoding="utf-8-sig")
    required = INPUTS + ["FCH4", "FH2O", "FCO2", "FCO", "FH2", "FCARBON", "Q"]
    if list(grid.columns) != required or len(grid) != 46464:
        raise ValueError("Unexpected source schema or row count")
    if not np.isfinite(grid.to_numpy()).all() or grid[INPUTS].duplicated().any():
        raise ValueError("Nonfinite values or duplicate operating points")
    if (grid[required[:-1]] < 0).any().any():
        raise ValueError("Negative inputs or species in source")
    return grid


def select_cases(grid, optima):
    work = grid.copy()
    work["temperature_band"] = (work["T"]-500)//200
    work["pressure_band"] = (work["P"] > 13).astype(int)
    work["carbon_regime"] = (work["FCARBON"] > CARBON_THRESHOLD).astype(int)
    work["rank"] = [hashlib.sha256(
        ("trm-v1:" + ",".join(format(v, ".12g") for v in row)).encode()
    ).hexdigest() for row in work[INPUTS].itertuples(index=False, name=None)]
    chosen = {}
    strata = []
    for key, group in work.groupby(["temperature_band", "pressure_band", "carbon_regime"], sort=True):
        ids = group.sort_values("rank").head(5).index
        for index in ids:
            chosen.setdefault(index, []).append("stratified")
        strata.append({"temperature_band": int(key[0]), "pressure_band": int(key[1]),
                       "carbon_positive": bool(key[2]), "population_N": len(group), "selected_N": len(ids)})
    for index, row in grid.iterrows():
        if (row["T"] in [600, 800, 1000] and row.P == 1 and row.Fw == .2
                and row.Fo == 0 and any(abs(row.Fc-v) < 1e-10 for v in [0, .2, .4, .6, .8, 1])):
            chosen.setdefault(index, []).append("co2_sweep")
        if row["T"] == 800 and row.Fw == .2 and row.Fc == .6 and row.Fo == .1:
            chosen.setdefault(index, []).append("pressure_sweep")
        if row["T"] in [500, 1000] and row.P == 1 and row.Fw == row.Fc == row.Fo == 0:
            chosen.setdefault(index, []).append("element_free")
    rows = []
    for index in sorted(chosen):
        row = grid.loc[index].to_dict()
        row.update(case_id=f"grid-{index:05d}", source="data/added2.csv",
                   source_row=int(index)+2, group=";".join(chosen[index]),
                   stratum=f"T{int(work.loc[index, 'temperature_band'])}-P{int(work.loc[index, 'pressure_band'])}-C{int(work.loc[index, 'carbon_regime'])}")
        rows.append(row)
    if optima.scenario.tolist() != [1, 2, 3, 4, 5]:
        raise ValueError("Unexpected optimum provenance")
    for index, row in optima.iterrows():
        record = {k: row[k] for k in INPUTS + ["FCH4", "FH2O", "FCO2", "FO2", "FCO", "FH2", "FCARBON"]}
        record.update(case_id=f"optimum-{int(row.scenario)}", source="results/revision_r2/aspen_results.csv",
                      source_row=int(index)+2, group="published_optima", stratum="off-grid")
        rows.append(record)
    return pd.DataFrame(rows).drop(columns="Q"), strata
