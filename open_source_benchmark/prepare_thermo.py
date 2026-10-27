"""Export open thermochemistry from the pinned Cantera distribution; no equilibria."""
import hashlib
import importlib.metadata
import json
from pathlib import Path

import cantera as ct

HERE = Path(__file__).resolve().parent


def main():
    if ct.__version__ != "3.1.0":
        raise RuntimeError("Thermo export requires Cantera 3.1.0")
    source = Path(ct.__file__).parent / "data"
    records = {}
    for filename, names in [("gri30.yaml", ["CH4", "H2O", "CO2", "O2", "CO", "H2"]),
                            ("graphite.yaml", ["C(gr)"])]:
        for species in ct.Species.list_from_file(str(source / filename)):
            if species.name in names:
                c = species.thermo.coeffs
                records[species.name] = {
                    "midpoint_K": float(c[0]), "high": c[1:8].tolist(),
                    "low": c[8:15].tolist(), "min_K": species.thermo.min_temp,
                    "max_K": species.thermo.max_temp,
                    "reference_pressure_Pa": species.thermo.reference_pressure,
                    "source": filename,
                }
    payload = {"cantera_version": ct.__version__, "species": records,
               "source_sha256": {f: hashlib.sha256((source / f).read_bytes()).hexdigest()
                                  for f in ["gri30.yaml", "graphite.yaml"]},
               "graphite_molar_volume_m3_per_mol": 0.012011 / 2160.0}
    (HERE / "thermo.json").write_text(json.dumps(payload, indent=2) + "\n")
    distribution = importlib.metadata.distribution("cantera")
    license_path = next(p for p in distribution.files if str(p).endswith("licenses/License.txt"))
    (HERE / "CANTERA_LICENSE.txt").write_bytes(distribution.locate_file(license_path).read_bytes())


if __name__ == "__main__":
    main()
