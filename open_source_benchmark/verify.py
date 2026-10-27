"""Run the benchmark and full test suite, preserving exact execution evidence."""
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def main():
    result_dir = HERE / "results"
    result_dir.mkdir(exist_ok=True)
    commands = [
        ([sys.executable, "open_source_benchmark/run_benchmark.py", "--cantera"], "execution.txt"),
        ([sys.executable, "-m", "pytest", "open_source_benchmark/tests", "-v",
          "--junitxml=open_source_benchmark/results/pytest.xml"], "tests.txt"),
    ]
    evidence = []
    for command, filename in commands:
        start = perf_counter()
        completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        output = ("Command arguments: " + json.dumps(command) + "\n" +
                  completed.stdout + completed.stderr + f"\nExit code: {completed.returncode}\n")
        (result_dir / filename).write_text(output, encoding="utf-8")
        print(output, end="")
        evidence.append(dict(command=command, exit_code=completed.returncode,
                             elapsed_wall_s=perf_counter()-start))
        if completed.returncode:
            return completed.returncode
    suites = ET.parse(result_dir / "pytest.xml").getroot()
    counts = {key: sum(int(suite.get(key, 0)) for suite in suites.iter("testsuite"))
              for key in ["tests", "failures", "errors", "skipped"]}
    (result_dir / "verification.json").write_text(json.dumps(dict(commands=evidence, pytest=counts), indent=2)+"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
