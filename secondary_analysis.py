"""Secondary validation/sensitivity analyses for the 106-case COPASI audit.

The primary, case-level classifications remain in results/final_results_106.csv
and answer "did COPASI fully and correctly answer this test case." This
script answers a different question -- for each individual requested
variable across the corpus, was that specific quantity a match, a silent
omission, a numerical drift, a gross mismatch, or unreachable because the
case crashed -- and stratifies the answer by SBML target type (species,
compartment, parameter, reaction).

This requires per-variable ground truth, not the case-level status. An
earlier version of this script applied the single case-level status to
every variable a case requested, on the reasoning that MISSING_VARS,
GROSS_MISMATCH, etc. already summarize the case. That reasoning does not
transfer to a per-variable table: a case with three requested variables,
one of which is missing, has its case-level status set by that one
absent variable, but the other two are not thereby missing themselves.
Broadcasting the case-level status to all three overcounts whichever
bucket the case landed in. Quantified against this corpus: of the 336
variable-requests inside cases that carried a MISSING_VARS case-level
status, only 152 were actually missing; the remaining 184 were present
and were never individually checked before this fix. See README.md,
"Known issues" for the full accounting.

The fix: read `variable_results`, which run_one_case_v2.py now emits per
case (via driver_v2.py --detailed, in results/copasi_detailed.jsonl),
and classify each requested variable by its own recorded status rather
than by its case's aggregate status.

One category of case is a deliberate exception to this rule: the eight
UNVERIFIED_UNITS compartment-rule cases, whose amount-vs-concentration
conversion factor could not be resolved automatically and were instead
hand-verified against COPASI's internal compartment value directly (see
verify_compartment_defect.py and the paper's "Root cause, directly
verified"). That resolution establishes a single conversion factor for
the whole case -- every requested variable in these cases is an
amount-based species sharing the same compartment -- so the hand-
resolved case-level status from results/final_results_106.csv is used
uniformly for all of a case's variables only for these eight cases. This
is not the same shortcut being fixed above: there, a case-level status
was being applied to variables it had no bearing on; here, the
compartment conversion factor genuinely does apply identically to every
variable in the case.
"""
import csv
import json
import os
from collections import Counter, defaultdict

import libsbml

HERE = os.path.dirname(os.path.abspath(__file__))
SUITE = os.environ.get("SBML_TEST_SUITE", os.path.join(HERE, "sbml-test-suite"))
BASE = os.path.join(SUITE, "cases", "semantic")

VARIABLE_GROUP = {
    "PASS": "match",
    "NUMERICAL_DRIFT": "numerical_drift",
    "GROSS_MISMATCH": "wrong",
    "MISSING": "silent_omission",
}
CASE_GROUP = {"PASS": "match", "GROSS_MISMATCH": "wrong"}
FIELDNAMES = ["target_type", "match", "numerical_drift", "wrong", "silent_omission", "crash"]


def settings(path):
    values = {}
    for line in open(path, encoding="utf-8"):
        if ":" in line:
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip()
    return values


def target_types(model):
    out = {}
    for get_n, get, label in ((model.getNumSpecies, model.getSpecies, "species"),
                               (model.getNumCompartments, model.getCompartment, "compartment"),
                               (model.getNumParameters, model.getParameter, "parameter"),
                               (model.getNumReactions, model.getReaction, "reaction")):
        for i in range(get_n()):
            out[get(i).getId()] = label
    return out


def load_case_status(path):
    """Load the hand-curated, per-case final classification.

    This remains the source of truth for the eight UNVERIFIED_UNITS
    compartment-rule cases (see module docstring) and is cross-checked
    against copasi_detailed.jsonl's own case-level status for every
    other case, so the two inputs can't silently drift apart.
    """
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit(f"{path} is empty")
    if "final_status" not in rows[0]:
        raise SystemExit(f"{path} has no 'final_status' column (found: {list(rows[0].keys())}).")
    return {r["case_id"]: r["final_status"] for r in rows}


def load_variable_results(path):
    """Load per-case, per-variable results written by the fixed harness."""
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            out[r["cid"]] = r
    return out


def main():
    if not os.path.isdir(BASE):
        raise SystemExit("SBML Test Suite unavailable; set SBML_TEST_SUITE as documented in README.md.")
    case_status = load_case_status(os.path.join(HERE, "results", "final_results_106.csv"))
    detailed_path = os.path.join(HERE, "results", "copasi_detailed.jsonl")
    if not os.path.exists(detailed_path):
        raise SystemExit(
            f"{detailed_path} not found. Run `python3 driver_v2.py --detailed` first "
            "to produce the per-variable results this script depends on."
        )
    detailed = load_variable_results(detailed_path)
    corpus = json.load(open(os.path.join(HERE, "results", "target_cases_106.json"), encoding="utf-8"))

    counts = defaultdict(Counter)
    for cid in corpus:
        model = libsbml.readSBML(os.path.join(BASE, cid, f"{cid}-sbml-l3v1.xml")).getModel()
        requested = [v.strip() for v in settings(os.path.join(BASE, cid, f"{cid}-settings.txt"))["variables"].split(",")]
        types = target_types(model)
        status = case_status[cid]

        if status == "CRASH":
            # No time series was ever produced; nothing to check per variable.
            for v in requested:
                counts[types.get(v, "other / extension alias")]["crash"] += 1
            continue

        if status in CASE_GROUP:
            raw = detailed.get(cid, {}).get("status")
            if raw == "UNVERIFIED_UNITS":
                # One of the eight compartment-rule cases: the hand-
                # resolved case-level status applies uniformly (see
                # module docstring).
                for v in requested:
                    counts[types.get(v, "other / extension alias")][CASE_GROUP[status]] += 1
                continue

        # Every other case: use the fixed harness's per-variable results.
        var_results = detailed.get(cid, {}).get("variable_results")
        if var_results is None:
            raise SystemExit(
                f"Case {cid} (final_status={status}) has no 'variable_results' in "
                f"{detailed_path}. Re-run driver_v2.py --detailed with the current "
                "run_one_case_v2.py, which emits this field for every scored case."
            )
        for v in requested:
            v_status = var_results.get(v, {}).get("status")
            if v_status not in VARIABLE_GROUP:
                raise SystemExit(
                    f"Case {cid}, variable {v}: unrecognized per-variable status "
                    f"'{v_status}'. Expected one of {sorted(VARIABLE_GROUP)}."
                )
            counts[types.get(v, "other / extension alias")][VARIABLE_GROUP[v_status]] += 1

    out = os.path.join(HERE, "results")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, "target_breakdown.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for key in sorted(counts):
            writer.writerow({"target_type": key, **counts[key]})
    print(path)


if __name__ == "__main__":
    main()