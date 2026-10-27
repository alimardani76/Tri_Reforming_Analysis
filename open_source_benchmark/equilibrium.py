"""Convex Gibbs minimization via element-potential KKT equations.

Gas amounts are represented logarithmically. Graphite is a pure separate phase.
The internal active-set check permits its amount to vanish only if stable.
No Cantera equilibrium calls are used by this solver.
"""
import json
import warnings
from pathlib import Path
from time import perf_counter

import numpy as np
from scipy.optimize import least_squares
from scipy.special import logsumexp, xlogy

SPECIES = ["CH4", "H2O", "CO2", "O2", "CO", "H2", "C(gr)"]
FLOW_KEYS = ["FCH4", "FH2O", "FCO2", "FO2", "FCO", "FH2", "FCARBON"]
# Rows C,H,O; columns in SPECIES order.
A = np.array([[1, 0, 1, 0, 1, 0, 1],
              [4, 2, 0, 0, 0, 2, 0],
              [0, 1, 2, 2, 1, 0, 0]], dtype=float)
THERMO = json.loads((Path(__file__).parent / "thermo.json").read_text())
P0 = 101325.0
R = 8.31446261815324  # J mol-1 K-1


def conditions(T, P):
    tk, pa = float(T) + 273.15, float(P) * 100000.0
    if not np.isfinite([tk, pa]).all() or tk <= 0 or pa <= 0:
        raise ValueError("Require finite positive absolute T and P")
    return tk, pa


def feed(Fw, Fc, Fo):
    if not np.isfinite([Fw, Fc, Fo]).all() or min(Fw, Fc, Fo) < 0:
        raise ValueError("Require finite nonnegative feed ratios")
    return np.array([1., Fw, Fc, Fo, 0., 0., 0.])


def standard_g_rt(tk, pa=P0):
    values = []
    for name in SPECIES:
        d = THERMO["species"][name]
        if not d["min_K"] <= tk <= d["max_K"]:
            raise ValueError(f"Temperature outside thermo range for {name}")
        a = d["low"] if tk <= d["midpoint_K"] else d["high"]
        h = a[0] + a[1]*tk/2 + a[2]*tk**2/3 + a[3]*tk**3/4 + a[4]*tk**4/5 + a[5]/tk
        s = a[0]*np.log(tk) + a[1]*tk + a[2]*tk**2/2 + a[3]*tk**3/3 + a[4]*tk**4/4 + a[6]
        values.append(h-s)
    values[-1] += THERMO["graphite_molar_volume_m3_per_mol"] * (pa-P0)/(R*tk)
    return np.array(values)


def gibbs_rt(n, tk, pa):
    """Total G/(RT), on the one-mol inlet CH4 basis; x log x -> 0 at zero."""
    n = np.asarray(n)
    if (n < 0).any() or n[:6].sum() <= 0:
        return np.inf
    return float(n @ standard_g_rt(tk, pa) + xlogy(n[:6], n[:6]/n[:6].sum()*pa/P0).sum())


def validate(n, b, atol=1e-8):
    n = np.asarray(n)
    residual = float(np.max(np.abs(A @ n-b)))
    if not np.isfinite(n).all() or n.min() < 0 or residual > atol:
        raise RuntimeError(f"Invalid equilibrium: minimum={n.min()}, atom residual={residual}")
    if n[0] > 1+atol or n[5] > b[1]/2+atol:
        raise RuntimeError("Methane or hydrogen bound violated")
    return residual


def solve(T, P, Fw, Fc, Fo):
    started = perf_counter()
    tk, pa = conditions(T, P)
    incoming = feed(Fw, Fc, Fo)
    b = A @ incoming
    elements = b > 0
    # Species containing a structurally absent element cannot exist.
    allowed = ~np.any(A[~elements, :6] > 0, axis=0)
    ag = A[elements, :6][:, allowed]
    ac = A[elements, 6]
    g = standard_g_rt(tk, pa)
    gg = g[:6][allowed]
    scale = b[elements]
    m = len(scale)
    initial_lam = np.linalg.lstsq(ag.T, gg + np.log(pa/P0) - 2, rcond=None)[0]
    initial = np.r_[initial_lam, np.log(incoming.sum())]

    def branch(active, start):
        def residual(z):
            logy = ag.T @ z[:m] - gg - np.log(pa/P0)
            logn = z[m] + logy
            # Bounded iterates avoid overflows without changing accepted roots.
            ng = np.exp(np.clip(logn, -700, 300))
            nc = z[-1]*b[0] if active else 0.
            eq = list((ag @ ng + ac*nc-scale)/scale)
            eq.append(logsumexp(logy))
            if active:
                eq.append(g[-1] - ac @ z[:m])
            return np.array(eq)
        z0 = np.r_[start[:m+1], 0.1] if active else start[:m+1]
        result = least_squares(residual, z0, xtol=1e-13, ftol=1e-13,
                               gtol=1e-13, max_nfev=1500)
        if not result.success or np.max(np.abs(residual(result.x))) > 1e-9:
            raise RuntimeError(f"KKT solve failed: {result.message}")
        z = result.x
        n = np.zeros(7)
        n[:6][allowed] = np.exp(z[m] + ag.T @ z[:m] - gg - np.log(pa/P0))
        n[6] = z[-1]*b[0] if active else 0.
        affinity = float(g[-1] - ac @ z[:m])
        return n, affinity, z, result.nfev

    n, affinity, z, evaluations = branch(True, initial)
    active = n[6] >= 0
    if not active:
        n, affinity, z, count = branch(False, z)
        evaluations += count
    atom = validate(n, b)
    if (active and abs(affinity) > 1e-8) or (not active and affinity < -1e-8):
        raise RuntimeError("Graphite complementarity failed")
    return n, {"atom_max_abs": atom, "carbon_affinity_RT": affinity,
               "carbon_active": bool(active), "nfev": evaluations,
               "gibbs_RT": gibbs_rt(n, tk, pa), "elapsed_s": perf_counter()-started}


def solve_cantera(T, P, Fw, Fc, Fo):
    """Fresh six-species ideal gas + graphite, VCS TP equilibrium."""
    import cantera as ct
    started = perf_counter()
    tk, pa = conditions(T, P)
    incoming = feed(Fw, Fc, Fo)
    all_species = {s.name: s for s in ct.Species.list_from_file("gri30.yaml")}
    gas = ct.Solution(thermo="ideal-gas", species=[all_species[s] for s in SPECIES[:6]])
    carbon = ct.Solution("graphite.yaml")
    def fresh_mixture():
        gas.TPX = tk, pa, incoming[:6]
        carbon.TP = tk, pa
        mix = ct.Mixture([(gas, float(incoming[:6].sum())), (carbon, 0.)])
        mix.T, mix.P = tk, pa
        return mix
    mixture = fresh_mixture()
    method, attempts = "vcs", 1
    try:
        mixture.equilibrate("TP", solver="vcs", rtol=1e-9, max_steps=5000, log_level=0)
    except ct.CanteraError as error:
        warnings.warn(f"VCS attempt failed; retrying fresh feed with Gibbs: {error}", RuntimeWarning)
        mixture = fresh_mixture()
        method, attempts = "gibbs-fallback", 2
        mixture.equilibrate("TP", solver="gibbs", rtol=1e-9, max_steps=5000, log_level=0)
    n = mixture.species_moles
    atom = validate(n, A @ incoming)
    return n, {"atom_max_abs": atom, "gibbs_RT": gibbs_rt(n, tk, pa),
               "cantera_method": method, "attempts": attempts,
               "elapsed_s": perf_counter()-started}
