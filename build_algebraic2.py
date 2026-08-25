"""
build_algebraic2.py

Builds and simulates a minimal, hand-constructed SBML model demonstrating
the practical consequence of the dominant failure mode (silent omission
of an algebraically-determined species): the paper's "Consequence of the
dominant fault, demonstrated directly" section and its Table 2.

Model: two independent reactions in a single well-mixed compartment.
  - A -> B, ordinary mass-action kinetics (rate k1*A). Unaffected by the
    defect; included as a within-model control showing the rest of the
    simulation behaves normally.
  - D -> P, rate k2*D, where D is not a reactant or product of any other
    reaction -- its value is determined *only* by the algebraic
    constraint T - A - B - D = 0 (a conserved-moiety / rapid-equilibrium
    pattern that is common in reduced kinetic models). Because COPASI
    has no representational status for "governed by an algebraic
    constraint" (see verify_warning_channel.py and the paper's "Root
    cause" section), D is silently held at its SBML-declared initial
    value of 0 for the entire simulation rather than resolved from the
    constraint, so reaction D -> P never fires, and P remains at exactly
    0.0 throughout even though the constraint fixes D at a constant,
    nonzero value (2.0, given Total=5.0 and A+B conserved at 3.0 by r1)
    -- with no error, warning, or otherwise implausible value anywhere
    in the visible output. Total is set to 5.0, not 3.0, specifically so
    that D's constraint-satisfying value (2.0) differs from COPASI's
    silently-substituted default (0): with Total=3.0, A(0)+B(0) already
    equals 3.0, so the correct D would itself be 0 and the demo would
    not distinguish COPASI's behavior from correct behavior.

Usage:
    python3 build_algebraic2.py

Writes results/algebraic2.xml, then runs it through COPASI
and prints the trajectory reproduced in the paper's Table 2.
"""
import os

import libsbml

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(HERE, "results")
MODEL_PATH = os.path.join(RESULTS_DIR, "algebraic2.xml")


def build_model():
    doc = libsbml.SBMLDocument(3, 1)
    model = doc.createModel("conservation_test2")

    comp = model.createCompartment()
    comp.setId("cell")
    comp.setConstant(True)
    comp.setSize(1.0)

    def make_species(sid, init, boundary=False, constant=False):
        s = model.createSpecies()
        s.setId(sid)
        s.setCompartment("cell")
        s.setInitialConcentration(init)
        s.setHasOnlySubstanceUnits(False)
        s.setBoundaryCondition(boundary)
        s.setConstant(constant)
        return s

    make_species("A", 3.0)
    make_species("B", 0.0)
    # D is marked boundaryCondition=True because its value is intended to
    # come entirely from the algebraic rule below, not from being a
    # reactant/product of a kinetic reaction; it is not otherwise
    # constant, since the rule is meant to update it over time.
    make_species("D", 0.0, boundary=True, constant=False)
    make_species("P", 0.0)

    for pid, val in [("Total", 5.0), ("k1", 0.2), ("k2", 0.5)]:
        p = model.createParameter()
        p.setId(pid)
        p.setConstant(True)
        p.setValue(val)

    r1 = model.createReaction()
    r1.setId("r1")
    r1.setReversible(False)
    sr = r1.createReactant()
    sr.setSpecies("A")
    sr.setStoichiometry(1)
    sr.setConstant(True)
    pr = r1.createProduct()
    pr.setSpecies("B")
    pr.setStoichiometry(1)
    pr.setConstant(True)
    r1.createKineticLaw().setMath(libsbml.parseL3Formula("k1*A"))

    r2 = model.createReaction()
    r2.setId("r2")
    r2.setReversible(False)
    sr2 = r2.createReactant()
    sr2.setSpecies("D")
    sr2.setStoichiometry(1)
    sr2.setConstant(True)
    pr2 = r2.createProduct()
    pr2.setSpecies("P")
    pr2.setStoichiometry(1)
    pr2.setConstant(True)
    r2.createKineticLaw().setMath(libsbml.parseL3Formula("k2*D"))  # D drives this reaction's kinetics

    alg = model.createAlgebraicRule()
    alg.setMath(libsbml.parseL3Formula("Total - A - B - D"))

    os.makedirs(RESULTS_DIR, exist_ok=True)
    libsbml.writeSBMLToFile(doc, MODEL_PATH)

    check_doc = libsbml.readSBML(MODEL_PATH)
    n_errors = check_doc.checkConsistency()
    print(f"wrote {MODEL_PATH} ({n_errors} libsbml consistency errors)")


def simulate_and_report():
    import COPASI

    dm = COPASI.CRootContainer.addDatamodel()
    dm.importSBML(MODEL_PATH)
    task = dm.getTask("Time-Course")
    task.setMethodType(COPASI.CTaskEnum.Method_deterministic)
    problem = task.getProblem()
    problem.setStepNumber(200)
    problem.setDuration(20.0)
    problem.setTimeSeriesRequested(True)
    task.initializeRaw(COPASI.CCopasiTask.OUTPUT_UI)
    task.processRaw(True)

    ts = task.getTimeSeries()
    n = ts.getRecordedSteps()
    nvar = ts.getNumVariables()
    sbml_ids = []
    for i in range(nvar):
        try:
            sbml_ids.append(ts.getSBMLId(i, dm))
        except Exception:
            sbml_ids.append(None)
    titles = [ts.getTitle(i) for i in range(nvar)]
    time_col = next(i for i, t in enumerate(titles) if t == "Time")
    col = {"A": sbml_ids.index("A"), "B": sbml_ids.index("B"), "P": sbml_ids.index("P")}

    rows = [(ts.getConcentrationData(s, time_col),
              ts.getConcentrationData(s, col["A"]),
              ts.getConcentrationData(s, col["B"]),
              ts.getConcentrationData(s, col["P"])) for s in range(n)]

    # Report the same time points shown in the paper's Table 2.
    targets = [0.0, 2.0, 5.0, 10.0, 15.0, 19.9]
    print()
    print(f"{'t':>6}{'A':>10}{'B':>10}{'P':>10}")
    for target_t in targets:
        closest = min(rows, key=lambda row: abs(row[0] - target_t))
        print(f"{closest[0]:6.1f}{closest[1]:10.4f}{closest[2]:10.4f}{closest[3]:10.4f}")
    print()
    print("D's correct, constraint-satisfying value is 2.0 throughout (Total - A - B,")
    print("with A+B conserved at 3.0 by r1). COPASI instead silently holds D at its")
    print("SBML-declared initial value of 0.0, so reaction D -> P (rate k2*D, which")
    print("should proceed at a constant rate of 1.0) never fires, and P remains at")
    print("exactly 0.0000 throughout.")


if __name__ == "__main__":
    build_model()
    try:
        simulate_and_report()
    except ImportError:
        print("COPASI Python bindings not importable here; algebraic2.xml was written, "
              "but the trajectory in the paper's Table 2 was not regenerated. "
              "Install python-copasi (see requirements.txt) and re-run to reproduce it.")