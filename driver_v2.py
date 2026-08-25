"""
driver_v2.py

Batch-runs run_one_case_v2.py over every case in the
structurally-verified, 106-case corpus (results/target_cases_106.json; see
build_corpus.py and the paper's "Building the corpus, correctly"). Each
case runs in its own subprocess with a fixed timeout, both to obtain a
signal-safe verdict per case and because two cases in this corpus
segfault the COPASI interpreter (00983, 01142) and would otherwise take
the rest of the batch down with them.

Output: results/copasi_regenerated.csv, one row per case with the status
this run produced. The repository also ships results/final_results_106.csv, a
curated version of this same table with added cross-reference notes
pointing PASS cases in the compartment-rule family to the internal-state
verification in verify_compartment_defect.py (see the paper's "Root
cause, directly verified" section); a fresh run of this driver reproduces
the same status and error-magnitude classifications but not that
annotation text, which was added by hand for readability.
"""
import csv
import argparse
import json
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS_PATH = os.path.join(HERE, "results", "target_cases_106.json")
CASE_SCRIPT = os.path.join(HERE, "run_one_case_v2.py")
OUT_DIR = os.path.join(HERE, "results")
OUT_PATH = os.path.join(OUT_DIR, "copasi_regenerated.csv")

TIMEOUT_S = 30


def run_case(cid):
    try:
        p = subprocess.run(["python3", CASE_SCRIPT, cid], capture_output=True, text=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return {"cid": cid, "status": "TIMEOUT"}
    if p.returncode != 0:
        # A nonzero return code with no parseable JSON on stdout is how a
        # segmentation fault in the COPASI interpreter surfaces here: the
        # subprocess is killed by a signal before it can print a result.
        return {"cid": cid, "status": "CRASH", "returncode": p.returncode, "stderr": p.stderr[-500:]}
    line = p.stdout.strip().splitlines()[-1] if p.stdout.strip() else ""
    try:
        return json.loads(line)
    except Exception:
        return {"cid": cid, "status": "UNPARSEABLE_OUTPUT", "stdout": p.stdout[-500:], "stderr": p.stderr[-500:]}


def summarize_note(r):
    status = r.get("status")
    if status == "MISSING_VARS":
        return f"missing: {r.get('missing')}"
    if status in ("GROSS_MISMATCH", "PASS", "NUMERICAL_DRIFT"):
        if "max_rel_err" in r:
            return f"max_rel_err={r['max_rel_err']}, worst_var={r.get('worst_var')}"
        return ""
    if status == "UNVERIFIED_UNITS":
        return "; ".join(r.get("unit_warning", []))
    if status == "CRASH":
        return f"returncode={r.get('returncode')}"
    return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--detailed", action="store_true",
                        help="also write raw JSON-lines results for secondary analyses")
    args = parser.parse_args()
    with open(CORPUS_PATH) as f:
        target_cases = json.load(f)

    print(f"Running COPASI audit on {len(target_cases)} cases (corrected, structurally-verified corpus)...")
    results = []
    for i, cid in enumerate(target_cases):
        results.append(run_case(cid))
        if (i + 1) % 20 == 0:
            print(f"  ...{i + 1}/{len(target_cases)} done")

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_PATH, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "status", "notes"])
        for r in results:
            w.writerow([r["cid"], r.get("status", "UNKNOWN"), summarize_note(r)])
    if args.detailed:
        detail_path = os.path.join(OUT_DIR, "copasi_detailed.jsonl")
        with open(detail_path, "w", encoding="utf-8") as f:
            for result in results:
                f.write(json.dumps(result, sort_keys=True) + "\n")
        print(f"wrote {detail_path}")
    print(f"wrote {OUT_PATH}")

    from collections import Counter
    counts = Counter(r.get("status", "UNKNOWN") for r in results)
    print()
    print(f"=== summary across {len(results)} cases ===")
    for k, v in counts.most_common():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()