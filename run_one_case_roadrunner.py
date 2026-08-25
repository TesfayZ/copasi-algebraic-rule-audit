"""
run_one_case_roadrunner.py

Runs one SBML Test Suite case through libRoadRunner and scores the result
against the same reference trajectory used for the COPASI harness
(run_one_case_v2.py), so the two simulators' outcomes are
directly comparable. In practice every case in the 106-case corpus is
rejected at model-load time before a trajectory ever exists to score;
the comparison logic below exists for the small number of cases outside
that corpus where libRoadRunner does load and run (see driver_roadrunner.py
and the paper's "Building the corpus, correctly" for how this asymmetry
was used as an independent, structurally-blind check on corpus
membership).

Usage:
    python3 run_one_case_roadrunner.py <case_id>

Prints one line of JSON to stdout describing the outcome.
"""
import sys, os, csv, json
import numpy as np
import libsbml

SBML_TEST_SUITE = os.environ.get(
    "SBML_TEST_SUITE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "sbml-test-suite"),
)
BASE = os.path.join(SBML_TEST_SUITE, "cases", "semantic")


def parse_settings(path):
    d = {}
    for line in open(path):
        if ":" in line:
            k, v = line.split(":", 1)
            d[k.strip()] = v.strip()
    return d


def load_official_results(path):
    with open(path) as f:
        r = csv.reader(f)
        header = next(r)
        rows = [[float(x) for x in row] for row in r]
    return header, np.array(rows)


def species_compartment_map(sbml_path):
    doc = libsbml.readSBML(sbml_path)
    model = doc.getModel()
    m = {}
    comp_const = {}
    comp_size = {}
    for i in range(model.getNumCompartments()):
        c = model.getCompartment(i)
        comp_const[c.getId()] = c.getConstant()
        comp_size[c.getId()] = c.getSize() if c.isSetSize() else None
    for i in range(model.getNumSpecies()):
        s = model.getSpecies(i)
        m[s.getId()] = s.getCompartment()
    return m, comp_const, comp_size


def main():
    cid = sys.argv[1]
    cdir = f"{BASE}/{cid}/"
    settings_path = f"{cdir}{cid}-settings.txt"
    results_path = f"{cdir}{cid}-results.csv"
    sbml_path = f"{cdir}{cid}-sbml-l3v1.xml"

    settings = parse_settings(settings_path)
    header, official = load_official_results(results_path)
    variables = [v.strip() for v in settings.get("variables", "").split(",") if v.strip()]
    amount_vars = set(v.strip() for v in settings.get("amount", "").split(",") if v.strip())
    sp_compartment, comp_const, comp_size = species_compartment_map(sbml_path)

    import roadrunner
    roadrunner.Logger.setLevel(roadrunner.Logger.LOG_CRITICAL)

    try:
        rr = roadrunner.RoadRunner(sbml_path)
    except RuntimeError as e:
        msg = str(e)
        # This is the outcome for every one of the 106 corpus cases: an
        # explicit, named exception at load time, before any trajectory
        # is produced. See run_one_case_roadrunner's module docstring
        # and the paper's "Cross-simulator control" for why this
        # distinguishes an algebraic-rule rejection from any other
        # load-time failure.
        if "algebraic" in msg.lower():
            print(json.dumps({"cid": cid, "status": "LOAD_REJECTED_ALGEBRAIC", "msg": msg}))
        else:
            print(json.dumps({"cid": cid, "status": "LOAD_REJECTED_OTHER", "msg": msg}))
        return
    except Exception as e:
        print(json.dumps({"cid": cid, "status": "LOAD_REJECTED_OTHER", "msg": f"{type(e).__name__}: {e}"}))
        return

    start = float(settings["start"])
    duration = float(settings["duration"])
    steps = int(settings["steps"])

    try:
        rr.setIntegrator("cvode")
        sel_ids = ["time"] + variables
        rr.timeCourseSelections = sel_ids
        data = rr.simulate(start, duration, steps + 1)
    except Exception as e:
        print(json.dumps({"cid": cid, "status": "RUN_FAILED", "msg": f"{type(e).__name__}: {e}"}))
        return

    colnames = list(data.colnames)

    # roadrunner names a concentration selection with surrounding
    # brackets ("[S1]") and an amount or parameter selection bare
    # ("S1"); check both forms so the column lookup does not depend on
    # which one a given case happens to resolve to.
    def find_col(v):
        candidates = [v, f"[{v}]", f"'{v}'"]
        for c in candidates:
            if c in colnames:
                return colnames.index(c)
        return None

    time_idx = find_col("time")
    if time_idx is None:
        time_idx = 0

    missing = [v for v in variables if find_col(v) is None]
    if missing:
        print(json.dumps({"cid": cid, "status": "MISSING_VARS", "missing": missing, "have_cols": colnames}))
        return

    off_t = official[:, header.index("time")]
    sim_t = np.array(data[:, time_idx])
    max_rel_err = 0.0
    worst_var = None
    unit_warning = []
    for v in variables:
        iv_off = header.index(v)
        iv_sim = find_col(v)
        sim_col = np.array(data[:, iv_sim])
        sim_interp = np.interp(off_t, sim_t, sim_col)
        off_vals = official[:, iv_off]
        denom = np.maximum(np.abs(off_vals), 1e-12)

        # Applied only for parity with the COPASI harness's unit
        # handling on the rare case that does reach this point; see
        # run_one_case_v2.py's module docstring for the
        # amount-vs-concentration rationale.
        factor = 1.0
        if v in amount_vars and v in sp_compartment:
            comp = sp_compartment[v]
            if comp_const.get(comp, True) and comp_size.get(comp) is not None:
                factor = comp_size[comp]
            else:
                unit_warning.append(f"{v}: non-constant compartment '{comp}', amount conversion unverified")

        rel_err = np.max(np.abs(sim_interp * factor - off_vals) / denom)
        if rel_err > max_rel_err:
            max_rel_err = rel_err
            worst_var = v

    if max_rel_err < 1e-3:
        status = "PASS"
    elif max_rel_err < 5e-2:
        status = "NUMERICAL_DRIFT"
    else:
        status = "GROSS_MISMATCH"

    out = {"cid": cid, "status": status, "max_rel_err": max_rel_err, "worst_var": worst_var}
    if unit_warning:
        out["status"] = "UNVERIFIED_UNITS"
        out["unit_warning"] = unit_warning
        out["nominal_status_ignoring_units"] = status
        out["nominal_max_rel_err"] = max_rel_err
    print(json.dumps(out))


if __name__ == "__main__":
    main()