"""
verify_warning_channel.py

Extends verify_compartment_defect.py with two further, directly-verified
observations that bear on *why* the substitution in that script is
silent rather than warned:

1. COPASI's CCopasiMessage queue -- the documented channel through
   which import-time and run-time warnings are surfaced to a script-
   driven caller -- is empty at every stage of the pipeline (import,
   task initialization, task execution) for a model whose only
   unsupported construct is an AlgebraicRule. This holds identically
   whether CCopasiMessage.setIsGUI(True) or (False) is set beforehand,
   which is the one flag COPASI's own bindings expose for
   distinguishing GUI-style from script-style message handling.

2. CModelEntity, the internal COPASI base class for every model
   quantity that can be governed by a rule (species, compartments,
   global parameters), exposes a fixed, closed status enum:
   FIXED, ASSIGNMENT, REACTIONS, ODE, TIME. There is no ALGEBRAIC
   member. This is a structural fact about the object model, not an
   inference from behavior: it means an algebraic-rule target has no
   status value available that would represent "governed by an
   algebraic constraint" even in principle, inside the currently
   released C++ API surface exposed to Python. The observed behavior
   (silent fall-through to Status_FIXED, i.e. an ordinary constant,
   defaulting numerically to 1) is consistent with this structural gap
   being the reason; the exact C++ call site that chooses the specific
   numeric default of 1 was not traced (it would require a debug build
   of COPASI, outside this study's scope), so we report the missing
   enum member as directly verified and the causal link to the numeric
   default as the best-supported explanation available from the
   Python-visible API, not as source-level proof of causation.

Usage:
    python3 verify_warning_channel.py
"""
import os

import COPASI

SBML_TEST_SUITE = os.environ.get(
    "SBML_TEST_SUITE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "sbml-test-suite"),
)
BASE = os.path.join(SBML_TEST_SUITE, "cases", "semantic")
PROBE_CASE = "00547"  # AlgebraicRule fixes compartment C to 2.5


def probe_message_queue(is_gui):
    COPASI.CCopasiMessage.clearDeque()
    COPASI.CCopasiMessage.setIsGUI(is_gui)
    dm = COPASI.CRootContainer.addDatamodel()
    ok = dm.importSBML(f"{BASE}/{PROBE_CASE}/{PROBE_CASE}-sbml-l3v1.xml")
    n_after_import = COPASI.CCopasiMessage.size()

    task = dm.getTask("Time-Course")
    task.setMethodType(COPASI.CTaskEnum.Method_deterministic)
    problem = task.getProblem()
    problem.setStepNumber(10)
    problem.setDuration(1.0)
    task.initializeRaw(COPASI.CCopasiTask.OUTPUT_UI)
    n_after_init = COPASI.CCopasiMessage.size()

    task.processRaw(True)
    n_after_run = COPASI.CCopasiMessage.size()
    all_text = COPASI.CCopasiMessage.getAllMessageText(True)

    return {
        "import_ok": ok,
        "messages_after_import": n_after_import,
        "messages_after_init": n_after_init,
        "messages_after_run": n_after_run,
        "message_text": all_text,
    }


def report_status_enum():
    members = [
        ("Status_FIXED", COPASI.CModelEntity.Status_FIXED),
        ("Status_ASSIGNMENT", COPASI.CModelEntity.Status_ASSIGNMENT),
        ("Status_REACTIONS", COPASI.CModelEntity.Status_REACTIONS),
        ("Status_ODE", COPASI.CModelEntity.Status_ODE),
        ("Status_TIME", COPASI.CModelEntity.Status_TIME),
        ("Status___SIZE", COPASI.CModelEntity.Status___SIZE),
    ]
    return members


def report_compartment_status(cid):
    dm = COPASI.CRootContainer.addDatamodel()
    dm.importSBML(f"{BASE}/{cid}/{cid}-sbml-l3v1.xml")
    model = dm.getModel()
    comps = model.getCompartments()
    out = []
    for i in range(comps.size()):
        c = comps.get(i)
        out.append((c.getObjectName(), c.getStatus(), c.getInitialValue()))
    return out


if __name__ == "__main__":
    print("=== 1. CCopasiMessage queue, case", PROBE_CASE, "(compartment C := 2.5 by AlgebraicRule) ===")
    for is_gui in (False, True):
        r = probe_message_queue(is_gui)
        print(f"  setIsGUI({is_gui}): import_ok={r['import_ok']}  "
              f"messages: after-import={r['messages_after_import']}  "
              f"after-init={r['messages_after_init']}  "
              f"after-run={r['messages_after_run']}")
        if r["message_text"].strip():
            print("    message text:", r["message_text"].strip())

    print()
    print("=== 2. CModelEntity.Status enum (complete, from the released Python bindings) ===")
    for name, val in report_status_enum():
        print(f"  {name} = {val}")
    print("  -> no ALGEBRAIC member exists; five concrete statuses plus a size sentinel.")

    print()
    print("=== 3. Compartment status after import, case", PROBE_CASE, "===")
    for name, status, value in report_compartment_status(PROBE_CASE):
        print(f"  compartment '{name}': status={status} (0=FIXED), initial value={value}")
        print("    -> imported as an ordinary FIXED constant, the only status available "
              "for a quantity COPASI cannot represent as governed by a rule of this kind.")
