"""All metrics are calculated from generated raw prediction/reference pairs."""
import numpy as np
import pandas as pd

OUTPUTS = ["FCH4", "FH2O", "FCO2", "FCO", "FH2", "FCARBON", "X_CH4", "Y_H2", "Y_CO", "E_CO2"]


def derived(row, prefix):
    return {prefix+"X_CH4": 1-row[prefix+"FCH4"], prefix+"Y_H2": row[prefix+"FH2"],
            prefix+"Y_CO": row[prefix+"FCO"], prefix+"E_CO2": row[prefix+"FCO2"]-row["Fc"]}


def summarize(raw):
    metrics, confusion, runtime = [], [], []
    for (engine, cohort), group in raw.groupby(["engine", "cohort"], sort=True):
        good = group[group.status == "ok"]
        runtime.append(dict(engine=engine, cohort=cohort, attempted_N=len(group), evaluated_N=len(good),
                            failed_N=int((group.status != "ok").sum()),
                            elapsed_s=float(group.elapsed_s.sum()),
                            median_case_s=float(good.elapsed_s.median()) if len(good) else None,
                            max_atom_residual=float(good.atom_max_abs.max()) if len(good) else None))
        if not len(good):
            continue
        for output in OUTPUTS:
            error = good["pred_"+output]-good["aspen_"+output]
            metrics.append(dict(engine=engine, cohort=cohort, output=output, N=len(good),
                                MAE=float(np.abs(error).mean()), RMSE=float(np.sqrt((error**2).mean())),
                                max_abs_error=float(np.abs(error).max())))
        for threshold in [0., 1e-8, 1e-6, 1e-4, 1e-3]:
            truth = good.aspen_FCARBON > threshold
            prediction = good.pred_FCARBON > threshold
            confusion.append(dict(engine=engine, cohort=cohort, threshold=threshold, N=len(good),
                                  TP=int((truth & prediction).sum()), TN=int((~truth & ~prediction).sum()),
                                  FP=int((~truth & prediction).sum()), FN=int((truth & ~prediction).sum())))
    return pd.DataFrame(metrics), pd.DataFrame(confusion), runtime


def pressure_metrics(raw):
    rows = []
    for (engine, pressure), group in raw[(raw.status == "ok") & (raw.cohort == "grid")].groupby(["engine", "P"]):
        for output in ["FH2", "FCARBON"]:
            error = group["pred_"+output]-group["aspen_"+output]
            rows.append(dict(engine=engine, P_bar=pressure, output=output, N=len(group),
                             MAE=float(abs(error).mean()), max_abs_error=float(abs(error).max())))
    return pd.DataFrame(rows)
