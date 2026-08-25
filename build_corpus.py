"""
build_corpus.py

Selects the official SBML Test Suite semantic cases that genuinely contain
an AlgebraicRule, and ship an SBML L3V1 encoding, settings file, and
reference results table. Output: results/target_cases_106.json, the corpus used
by every other script in this repository.

This selection method supersedes the more direct one we started with
(grep for the literal string "AlgebraicRule" in each case's .m
description file), which returns 107 cases but contains one false
positive: case 01000's description merely *mentions* AlgebraicRule while
describing what the model does NOT contain ("It's a RoadRunner-friendly
model in that it only doesn't have bits that RoadRunner can't handle:
AlgebraicRules, CSymbolDelays, and FastReactions."). This is confirmed
two independent ways: (1) libsbml reports zero Rule elements of type
Algebraic anywhere in the model, including any comp-package submodel
definitions; (2) libRoadRunner, run against all 107 originally-selected
cases (see driver_roadrunner.py), loads and simulates case 01000 without
error while rejecting all other 106 with an explicit "Unable to support
algebraic rules" exception -- an independent, structurally-blind
cross-check that converges on the identical 106-case corpus.

Seven further cases in the original 107 (01142, 01174, 01350, 01359,
01368, 01377, 01386) use the SBML hierarchical Model Composition (comp)
package: their AlgebraicRule lives inside a <comp:ModelDefinition>
submodel referenced by the top-level model, not in the top-level model's
own <listOfRules>. A scan of Model.getNumRules() on the top-level model
alone misses these; this script also inspects every comp:ModelDefinition
attached via the document's 'comp' plugin. All seven are confirmed
genuine AlgebraicRule cases and are retained.

Net effect versus the substring-match selection: one case dropped
(01000), seven cases correctly retained that a naive scan would have
missed. Final corpus size: 106. Full narrative in the paper's Results
section, "Building the corpus, correctly."
"""
import glob
import json
import os

import libsbml

# The SBML Test Suite checkout location can be overridden with the
# SBML_TEST_SUITE environment variable; by default we look for a sibling
# directory named sbml-test-suite alongside this script (see README.md,
# "Reproducing the audit end to end").
SBML_TEST_SUITE = os.environ.get(
    "SBML_TEST_SUITE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "sbml-test-suite"),
)
BASE = os.path.join(SBML_TEST_SUITE, "cases", "semantic")


def has_algebraic_rule(model):
    return any(model.getRule(i).isAlgebraic() for i in range(model.getNumRules()))


def case_has_algebraic_rule(sbml_path):
    doc = libsbml.readSBML(sbml_path)
    model = doc.getModel()
    if model is None:
        return False
    if has_algebraic_rule(model):
        return True
    plugin = doc.getPlugin("comp")
    if plugin is not None:
        for i in range(plugin.getNumModelDefinitions()):
            if has_algebraic_rule(plugin.getModelDefinition(i)):
                return True
    return False


def main():
    dirs = sorted(glob.glob(f"{BASE}/*/"))
    if not dirs:
        raise SystemExit(
            f"No test-suite case directories found under {BASE}. "
            "Set SBML_TEST_SUITE to your checkout of "
            "github.com/sbmlteam/sbml-test-suite, or place it in a "
            "sibling directory of this script named sbml-test-suite."
        )
    cases = []
    for d in dirs:
        cid = os.path.basename(d.rstrip("/"))
        sbml = f"{d}{cid}-sbml-l3v1.xml"
        settings = f"{d}{cid}-settings.txt"
        results = f"{d}{cid}-results.csv"
        if not (os.path.exists(sbml) and os.path.exists(settings) and os.path.exists(results)):
            continue
        if case_has_algebraic_rule(sbml):
            cases.append(cid)
    cases.sort()
    print(f"{len(cases)} cases selected out of {len(dirs)} test-suite directories scanned")
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "target_cases_106.json")
    with open(out_path, "w") as f:
        json.dump(cases, f, indent=2)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
