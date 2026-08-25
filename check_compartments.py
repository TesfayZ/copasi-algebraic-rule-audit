"""
check_compartments.py

Scans the structurally-verified 106-case corpus (results/target_cases_106.json)
for compartment declarations that make unit handling nontrivial: a
non-unit size, a non-constant compartment, or more than one compartment
in the same model. This scan is what identified the eight
algebraic-rule-governed compartment cases examined directly in the
paper's "Root cause, directly verified" section -- cases where an
amount-vs-concentration conversion cannot be done with a single blanket
factor and instead requires resolving what value COPASI's own internal
state actually uses (see verify_compartment_defect.py).

Usage:
    python3 check_compartments.py
"""
import json
import os

import libsbml

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS_PATH = os.path.join(HERE, "results", "target_cases_106.json")

SBML_TEST_SUITE = os.environ.get("SBML_TEST_SUITE", os.path.join(HERE, "sbml-test-suite"))
BASE = os.path.join(SBML_TEST_SUITE, "cases", "semantic")


def main():
    with open(CORPUS_PATH) as f:
        target_cases = json.load(f)

    non_unit_compartment_cases = []
    variable_compartment_cases = []
    multi_compartment_cases = []

    for cid in target_cases:
        sbml_path = f"{BASE}/{cid}/{cid}-sbml-l3v1.xml"
        doc = libsbml.readSBML(sbml_path)
        model = doc.getModel()
        comps = model.getListOfCompartments()
        sizes = {}
        for i in range(comps.size()):
            comp = comps.get(i)
            sizes[comp.getId()] = (comp.getSize() if comp.isSetSize() else None, comp.getConstant())
        if comps.size() > 1:
            multi_compartment_cases.append((cid, sizes))
        for cidname, (size, const) in sizes.items():
            if size is not None and abs(size - 1.0) > 1e-9:
                non_unit_compartment_cases.append((cid, cidname, size))
            if not const:
                variable_compartment_cases.append((cid, cidname))

    print(f"Total cases checked: {len(target_cases)}")
    print(f"Cases with >1 compartment: {len(multi_compartment_cases)}")
    print(f"Cases with a compartment size != 1: {len(non_unit_compartment_cases)}")
    print(f"Cases with a non-constant compartment: {len(variable_compartment_cases)}")
    print()
    print("Non-unit-size cases:", non_unit_compartment_cases)
    print("Variable-compartment cases:", variable_compartment_cases)
    print("Multi-compartment cases:", [c[0] for c in multi_compartment_cases])


if __name__ == "__main__":
    main()
