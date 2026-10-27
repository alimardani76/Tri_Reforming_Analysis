import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.linalg import null_space

from equilibrium import (A, P0, R, SPECIES, THERMO, conditions, feed, gibbs_rt,
                         solve, standard_g_rt, validate)

HERE = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("case", [(500, 1, 0, 0, 0), (1000, 29, 0, 0, 0),
                                  (600, 1, .2, .6, 0), (800, 29, .2, .6, .1),
                                  (900, 1, 1, 1, .7), (500, 29, 1, 1, .7)])
def test_solved_balance_bounds_and_graphite_kkt(case):
    n, diagnostics = solve(*case)
    b = A @ feed(*case[2:])
    np.testing.assert_allclose(A @ n, b, atol=1e-9, rtol=0)
    assert np.all(n >= 0)
    assert 0 <= n[0] <= 1 + 1e-9
    assert n[5] <= 2+case[2]+1e-9
    assert n[6] <= b[0]+1e-9
    if n[6] > 0:
        assert abs(diagnostics["carbon_affinity_RT"]) < 1e-8
    else:
        assert diagnostics["carbon_affinity_RT"] >= -1e-8
    tk, pa = conditions(*case[:2])
    assert gibbs_rt(n, tk, pa) <= gibbs_rt(feed(*case[2:]), tk, pa)+1e-8


def test_graphite_enabled_and_absent_element_exact_zeros():
    n, _ = solve(500, 1, 0, 0, 0)
    assert n[6] > .1  # Not a numerical trace; graphite formation is feasible and selected.
    assert np.all(n[[1, 2, 3, 4]] == 0)
    n, d = solve(1000, 1, 1, 1, .7)
    assert n[6] == 0 and d["carbon_affinity_RT"] >= 0


def test_conversions_and_reference_pressure():
    assert conditions(0, 1) == (273.15, 100000.)
    assert conditions(726.85, 1.01325) == (1000., P0)
    assert {d["reference_pressure_Pa"] for d in THERMO["species"].values()} == {P0}
    n = np.array([.2, .3, .1, .01, .4, 1., .2])
    p1, p2, tk = P0, 29e5, 1000.
    expected = n[:6].sum()*np.log(p2/p1) + n[6]*THERMO["graphite_molar_volume_m3_per_mol"]*(p2-p1)/(R*tk)
    assert gibbs_rt(n, tk, p2)-gibbs_rt(n, tk, p1) == pytest.approx(expected, abs=1e-12)


@pytest.mark.parametrize("case", [(500, 0, 0, 0, 0), (-274, 1, 0, 0, 0),
                                  (500, 1, -.1, 0, 0), (500, float('nan'), 0, 0, 0),
                                  (5000, 1, 0, 0, 0)])
def test_bad_inputs_rejected(case):
    with pytest.raises(ValueError):
        solve(*case)


def test_validator_detects_invalid_outputs():
    b = A @ feed(.2, .6, .1)
    with pytest.raises(RuntimeError):
        validate(np.zeros(7), b)
    n = feed(.2, .6, .1)
    n[-1] = -1e-12
    with pytest.raises(RuntimeError):
        validate(n, b)


def test_feasible_perturbations_cannot_lower_gibbs():
    case = (600, 1, .2, .6, 0)
    n, _ = solve(*case)
    # O2 is a tiny equilibrium trace. Keep it fixed to probe useful feasible directions.
    selected = [0, 1, 2, 4, 5, 6]
    basis = null_space(A[:, selected])
    rng = np.random.default_rng(174)
    tk, pa = conditions(*case[:2])
    for _ in range(40):
        direction = basis @ rng.normal(size=basis.shape[1])
        step = .2 * np.min(n[selected][direction < 0]/(-direction[direction < 0]))
        trial = n.copy()
        trial[selected] += step*direction
        np.testing.assert_allclose(A @ trial, A @ n, atol=1e-12)
        assert gibbs_rt(trial, tk, pa) >= gibbs_rt(n, tk, pa)-1e-10


@pytest.mark.parametrize("tk", [773.15, 999.99, 1000., 1000.01, 1273.15])
def test_nasa_polynomials_and_solid_pressure_match_cantera(tk):
    ct = pytest.importorskip("cantera")
    available = {s.name: s for s in ct.Species.list_from_file("gri30.yaml")}
    gas = ct.Solution(thermo="ideal-gas", species=[available[name] for name in SPECIES[:6]])
    carbon = ct.Solution("graphite.yaml")
    gas.TP = tk, P0
    carbon.TP = tk, 29e5
    expected = np.r_[gas.standard_gibbs_RT, carbon.standard_gibbs_RT]
    actual = standard_g_rt(tk, 29e5)
    np.testing.assert_allclose(actual, expected, atol=2e-12, rtol=0)


def test_every_executed_prediction_is_balanced_and_nonnegative():
    raw = pd.read_csv(HERE / "results/predictions.csv")
    from equilibrium import FLOW_KEYS
    for row in raw[raw.status == "ok"].to_dict("records"):
        n = np.array([row["pred_"+k] for k in FLOW_KEYS])
        validate(n, A @ feed(row["Fw"], row["Fc"], row["Fo"]))


def test_executed_engine_agreement():
    raw = pd.read_csv(HERE / "results/predictions.csv")
    if "cantera" not in raw.engine.values:
        pytest.skip("Cantera not executed")
    from equilibrium import FLOW_KEYS
    for key in FLOW_KEYS:
        values = raw[raw.status == "ok"].pivot(index="case_id", columns="engine", values="pred_"+key).dropna()
        assert len(values) > 0
        np.testing.assert_allclose(values.scipy, values.cantera, atol=1e-7, rtol=0)
