"""
verify_compartment_defect.py

Directly verifies the paper's central mechanistic claim: for a compartment
whose size is determined by an SBML AlgebraicRule, COPASI silently
substitutes a default value of 1 regardless of the rule's declared target,
while an explicitly-declared (non-rule) compartment of the same non-unit
size is read correctly.

This does NOT infer the defect from output trajectories (which can be
confounded by algebraic cancellation in first-order kinetics, as discussed
at length in the paper). It queries COPASI's own internal CCompartment
object directly, after simulation, via the Python bindings.

Usage:
    python3 verify_compartment_defect.py

This is run against all eight cases in the corpus whose AlgebraicRule
fixes a compartment size (identified by check_compartments.py and cross-
referenced against results/copasi_regenerated.csv's UNVERIFIED_UNITS
rows), not a subset of them. Six declare a target of 1 -- which the
defect's default happens to coincide with, so these cases cannot by
themselves distinguish "COPASI resolved the rule" from "COPASI
defaulted to a constant of 1 and got lucky." The remaining two declare
non-unit targets (2.5 and 0.75) and are what isolates the defect: 00547
resolves to the wrong compartment value (and downstream trajectory
error under 5e-2, PASS at the trajectory level despite the wrong
internal state), while 00548's larger downstream error crosses the
trajectory-level GROSS_MISMATCH threshold as well.

Expected output (matches paper Results, "Root cause, directly verified"):
    00539  rule target=1.0   COPASI internal value=1.0   <- (coincides; not distinguishing)
    00540  rule target=1.0   COPASI internal value=1.0   <- (coincides; not distinguishing)
    00541  rule target=1.0   COPASI internal value=1.0   <- (coincides; not distinguishing)
    00542  rule target=1.0   COPASI internal value=1.0   <- (coincides; not distinguishing)
    00544  rule target=1.0   COPASI internal value=1.0   <- (coincides; not distinguishing)
    00545  rule target=1.0   COPASI internal value=1.0   <- (coincides; not distinguishing)
    00547  rule target=2.5   COPASI internal value=1.0   <- BUG
    00548  rule target=0.75  COPASI internal value=1.0   <- BUG
    00675  declared const=9.8 (NOT a rule)  COPASI internal value=9.8  <- CONTROL: correct
"""
import os

import COPASI

SBML_TEST_SUITE = os.environ.get(
    "SBML_TEST_SUITE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "sbml-test-suite"),
)
BASE = os.path.join(SBML_TEST_SUITE, "cases", "semantic")

CASES = [
    ("00539", 1.0, "AlgebraicRule target"),
    ("00540", 1.0, "AlgebraicRule target"),
    ("00541", 1.0, "AlgebraicRule target"),
    ("00542", 1.0, "AlgebraicRule target"),
    ("00544", 1.0, "AlgebraicRule target"),
    ("00545", 1.0, "AlgebraicRule target"),
    ("00547", 2.5, "AlgebraicRule target"),
    ("00548", 0.75, "AlgebraicRule target"),
    ("00675", 9.8, "Explicit constant (NOT a rule) -- control"),
]


def get_compartment_value_after_simulation(cid, steps=20, duration=10.0):
    dm = COPASI.CRootContainer.addDatamodel()
    dm.importSBML(f"{BASE}/{cid}/{cid}-sbml-l3v1.xml")
    task = dm.getTask("Time-Course")
    task.setMethodType(COPASI.CTaskEnum.Method_deterministic)
    problem = task.getProblem()
    problem.setStepNumber(steps)
    problem.setDuration(duration)
    problem.setTimeSeriesRequested(True)
    task.initializeRaw(COPASI.CCopasiTask.OUTPUT_UI)
    task.processRaw(True)
    model = dm.getModel()
    comps = model.getCompartments()
    values = {}
    for i in range(comps.size()):
        c = comps.get(i)
        values[c.getObjectName()] = c.getValue()
    return values


if __name__ == "__main__":
    print(f"{'case':<8}{'declared/target':<18}{'kind':<32}{'COPASI internal value'}")
    for cid, target, kind in CASES:
        vals = get_compartment_value_after_simulation(cid)
        for compname, val in vals.items():
            flag = ""
            if "AlgebraicRule" in kind and abs(val - target) > 1e-9:
                flag = "  <-- BUG: silently defaulted to 1, ignoring rule"
            elif "control" in kind and abs(val - target) < 1e-9:
                flag = "  <-- CONTROL: correctly read explicit non-unit size"
            print(f"{cid:<8}{target:<18}{kind:<32}{compname}={val}{flag}")
