"""
driver_roadrunner.py

Batch-runs run_one_case_roadrunner.py over a corpus of case IDs, one
subprocess per case. By default this reproduces the paper's Table 2 (the
cross-simulator control): all 106 cases in the structurally-verified
corpus, rejected at load time.

The paper also reports a second, earlier use of this same per-case
script: running it against the original, substring-matched 107-case
list to independently cross-check corpus membership (Results, "Building
the corpus, correctly"). That run is what surfaced case 01000 as a
false positive -- libRoadRunner loads and simulates it without error,
the only case in either list for which that is true. To reproduce that
specific check rather than the main control result, pass a JSON file
containing the 107-case list via --corpus; the paper's build_corpus.py
docstring describes exactly how that superseded, substring-based list
was originally derived.

Output: results/roadrunner_regenerated.csv.
"""
import argparse
import csv
import json
import os
import subprocess
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CORPUS = os.path.join(HERE, "results", "target_cases_106.json")
CASE_SCRIPT = os.path.join(HERE, "run_one_case_roadrunner.py")
OUT_DIR = os.path.join(HERE, "results")
OUT_PATH = os.path.join(OUT_DIR, "roadrunner_regenerated.csv")

TIMEOUT_S = 30


def run_case(cid):
    try:
        p = subprocess.run(["python3", CASE_SCRIPT, cid], capture_output=True, text=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return {"cid": cid, "status": "TIMEOUT"}
    if p.returncode != 0:
        return {"cid": cid, "status": "CRASH", "returncode": p.returncode, "stderr": p.stderr[-800:]}
    line = p.stdout.strip().splitlines()[-1] if p.stdout.strip() else ""
    try:
        return json.loads(line)
    except Exception:
        return {"cid": cid, "status": "UNPARSEABLE_OUTPUT", "stdout": p.stdout[-500:], "stderr": p.stderr[-500:]}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", default=DEFAULT_CORPUS,
                     help="JSON file with a list of case IDs (default: results/target_cases_106.json)")
    args = ap.parse_args()

    with open(args.corpus) as f:
        target_cases = json.load(f)

    print(f"Running libRoadRunner control on {len(target_cases)} cases from {args.corpus}...")
    results = []
    for i, cid in enumerate(target_cases):
        results.append(run_case(cid))
        if (i + 1) % 20 == 0:
            print(f"  ...{i + 1}/{len(target_cases)} done")

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_PATH, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "status", "message"])
        for r in results:
            w.writerow([r["cid"], r.get("status", "UNKNOWN"), r.get("msg", "")])
    print(f"wrote {OUT_PATH}")

    counts = Counter(r.get("status", "UNKNOWN") for r in results)
    print()
    print(f"=== summary across {len(results)} cases ===")
    for k, v in counts.most_common():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
