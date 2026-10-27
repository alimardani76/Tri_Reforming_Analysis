import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cases import INPUTS, read_grid, select_cases
from reporting import summarize

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parent


def test_sampling_determinism_strata_and_source_traceability():
    grid = read_grid(ROOT / "data/added2.csv")
    optima = pd.read_csv(ROOT / "results/revision_r2/aspen_results.csv")
    first, strata = select_cases(grid, optima)
    second, other = select_cases(grid.sample(frac=1, random_state=74), optima)
    pd.testing.assert_frame_equal(first, second)
    assert strata == other
    committed = pd.read_csv(HERE / "results/case_manifest.csv", float_precision="round_trip")
    pd.testing.assert_frame_equal(first, committed, check_dtype=False)
    assert len(strata) == 12 and all(s["selected_N"] == 5 for s in strata)
    assert not first.case_id.duplicated().any()
    sampled = first[first.source == "data/added2.csv"]
    for key in INPUTS:
        assert sampled[key].min() == grid[key].min()
        assert sampled[key].max() == grid[key].max()
    assert (sampled.FCARBON == 0).any() and (sampled.FCARBON > 1e-6).any()
    for row in sampled.to_dict("records"):
        index = row["source_row"]-2
        for key in INPUTS+["FCH4", "FH2O", "FCO2", "FCO", "FH2", "FCARBON"]:
            assert row[key] == grid.loc[index, key]
    assert sum(first.group == "published_optima") == 5
    assert sum(first.group.str.contains("co2_sweep")) == 18
    assert sum(first.group.str.contains("pressure_sweep")) == 8


def test_reference_files_unchanged_from_recorded_hashes():
    summary = json.loads((HERE / "results/summary.json").read_text())
    for name, expected in summary["source_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == expected
    for name, expected in summary["implementation_sha256"].items():
        assert hashlib.sha256((HERE / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == expected


def test_metrics_independently_recomputed_from_raw_rows():
    raw = pd.read_csv(HERE / "results/predictions.csv")
    metrics = pd.read_csv(HERE / "results/metrics.csv")
    for row in metrics.to_dict("records"):
        group = raw[(raw.engine == row["engine"]) & (raw.cohort == row["cohort"]) & (raw.status == "ok")]
        assert row["N"] == len(group)
        error = group["pred_"+row["output"]].to_numpy()-group["aspen_"+row["output"]].to_numpy()
        assert row["MAE"] == pytest.approx(sum(abs(error))/len(error), abs=1e-14)
        assert row["RMSE"] == pytest.approx(np.linalg.norm(error)/np.sqrt(len(error)), abs=1e-14)
        assert row["max_abs_error"] == pytest.approx(max(abs(error)), abs=1e-14)
    for prefix in ["pred_", "aspen_"]:
        good = raw[raw.status == "ok"]
        np.testing.assert_allclose(good[prefix+"X_CH4"], 1-good[prefix+"FCH4"], atol=1e-14)
        np.testing.assert_allclose(good[prefix+"E_CO2"], good[prefix+"FCO2"]-good.Fc, atol=1e-14)


def test_confusion_recomputed_and_failed_cases_excluded():
    raw = pd.read_csv(HERE / "results/predictions.csv")
    confusion = pd.read_csv(HERE / "results/carbon_confusion.csv")
    for row in confusion.to_dict("records"):
        good = raw[(raw.engine == row["engine"]) & (raw.cohort == row["cohort"]) & (raw.status == "ok")]
        counts = dict(TP=0, TN=0, FP=0, FN=0)
        for record in good.to_dict("records"):
            actual = record["aspen_FCARBON"] > row["threshold"]
            predicted = record["pred_FCARBON"] > row["threshold"]
            counts[("T" if actual == predicted else "F")+("P" if predicted else "N")] += 1
        assert all(row[k] == v for k, v in counts.items())
        assert sum(counts.values()) == row["N"]
    # Inject a failure with deliberately absurd numeric output to test exclusion.
    failed = raw.iloc[[0]].copy()
    failed["status"] = "failed"
    failed["pred_FH2"] = 1e9
    original, _, _ = summarize(raw)
    changed, _, runtime = summarize(pd.concat([raw, failed], ignore_index=True))
    pd.testing.assert_frame_equal(original, changed)
    assert sum(r["failed_N"] for r in runtime) == int((raw.status != "ok").sum())+1


def test_execution_counts_and_fallback_records():
    raw = pd.read_csv(HERE / "results/predictions.csv")
    summary = json.loads((HERE / "results/summary.json").read_text())
    for item in summary["runtime"]:
        group = raw[(raw.engine == item["engine"]) & (raw.cohort == item["cohort"])]
        assert item["attempted_N"] == len(group)
        assert item["evaluated_N"] == sum(group.status == "ok")
        assert item["failed_N"] == sum(group.status != "ok")
    if "cantera_method" in raw:
        fallback = raw[raw.cantera_method == "gibbs-fallback"]
        assert len(fallback) == summary["cantera_fallback_N"]
        assert all(fallback.attempts == 2)
        logs = json.loads((HERE / "results/warnings.json").read_text())
        assert all(any(item["case_id"] == case_id and "VCS attempt failed" in item["message"] for item in logs) for case_id in fallback.case_id)
