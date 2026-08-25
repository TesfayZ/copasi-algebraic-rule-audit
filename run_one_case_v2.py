"""
run_one_case_v2.py

Runs one SBML Test Suite case through COPASI's Python bindings and scores
the result against the suite's own published reference trajectory. Called
once per case, in its own subprocess, by driver_v2.py -- COPASI
segfaults on two inputs in this corpus (see paper, "Cross-simulator
control"), and an in-process batch run would lose every remaining result
when that happens.

Four corrections are built into this version of the harness, relative to
an initial version that used simpler matching logic; all four are
described in full, with their quantified effect on the corpus-wide
result, in the paper's Results section, "Harness self-audit":

  - Variables are matched against COPASI's canonical SBML identifier
    (CTimeSeries.getSBMLId), not its display title. The two differ for
    non-species quantities: a parameter k4 is titled "Values[k4]" and a
    compartment comp is titled "Compartments[comp]", while species are
    titled unprefixed. Matching on the display title therefore
    misclassifies a present, correctly-computed parameter as a "silent
    omission" purely because of a naming convention.

  - Variables the test suite's settings file marks as amount-based are
    converted from COPASI's native concentration output using the
    species' compartment size, resolved the same way COPASI itself
    resolves it internally -- not the physically correct target of an
    AlgebraicRule -- since the question this harness answers is what
    COPASI actually reports, not what a fully conformant simulator
    would report. For a compartment whose size is fixed by an
    AlgebraicRule rather than declared as an ordinary constant, no
    static multiplicative factor is safe to apply (see the paper's
    "Root cause" section for why the two disagree); such cases are
    flagged as UNVERIFIED_UNITS and are not counted as a numeric
    match or mismatch until resolved by the internal-state
    investigation in verify_compartment_defect.py.

  - Per-variable scoring no longer stops at the first missing variable.
    A case's overall status still reports MISSING_VARS as soon as any
    requested variable is absent from COPASI's output -- that remains
    the right question for "did COPASI fully answer this test case."
    But every present variable in that case is now still scored and
    recorded in the emitted `variable_results` field, rather than left
    uncomputed. Earlier versions returned immediately on the first
    missing variable, which meant a case's other requested variables
    were absorbed into that single MISSING_VARS verdict even when they
    were present and numerically correct. secondary_analysis.py's
    target-type stratification depends on this per-variable detail; see
    README.md, "Known issues" for the size of the effect this had on
    the previously reported stratification table.

  - The reference-results header is matched case-insensitively for the
    time column ("time" vs "Time"). A handful of cases in the test
    suite (01567, 01575-01579) capitalize this column, which previously
    raised an uncaught exception -- masked in practice because those
    cases always hit the missing-variable return before reaching the
    time-column lookup. Removing that early return exposed it.

Usage:
    python3 run_one_case_v2.py <case_id>

Prints one line of JSON to stdout describing the outcome.
"""
import sys, os, csv, json, math
import numpy as np
import COPASI
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


def evaluate_algebraic_residuals(model, id_to_col, data, time_col):
    """Evaluate top-level AlgebraicRules where every symbol is exposed."""
    rules = [model.getRule(i) for i in range(model.getNumRules())
             if model.getRule(i).isAlgebraic()]
    if not rules:
        return {"evaluable": False, "reason": "no_top_level_algebraic_rule"}
    functions = {name: getattr(math, name) for name in
                 ("sin", "cos", "tan", "exp", "log", "sqrt", "floor", "ceil", "fabs")}
    maxima = []
    for rule in rules:
        formula = libsbml.formulaToL3String(rule.getMath()).replace("^", "**")
        try:
            vals = []
            for row in data:
                env = dict(functions)
                env.update({name: float(row[col]) for name, col in id_to_col.items()})
                env["time"] = float(row[time_col])
                vals.append(float(eval(formula, {"__builtins__": {}}, env)))
            maxima.append(max(abs(v) for v in vals))
        except (NameError, SyntaxError, TypeError, ValueError, OverflowError):
            return {"evaluable": False, "reason": "rule_symbols_not_exposed",
                    "formula": formula}
    maximum = max(maxima)
    scale = max(1.0, float(np.max(np.abs(data))))
    return {"evaluable": True, "rules": len(rules), "max_absolute": maximum,
            "max_normalized": maximum / scale, "satisfied": maximum <= 1e-8}


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
    sbml_model = libsbml.readSBML(sbml_path).getModel()

    COPASI.CCopasiMessage.clearDeque()
    dm = COPASI.CRootContainer.addDatamodel()
    ok = dm.importSBML(sbml_path)
    if not ok:
        print(json.dumps({"cid": cid, "status": "IMPORT_FAILED"}))
        return
    n_msgs = COPASI.CCopasiMessage.size()
    msgs = [COPASI.CCopasiMessage.getFirstMessage().getText() for _ in range(n_msgs)]

    task = dm.getTask("Time-Course")
    task.setMethodType(COPASI.CTaskEnum.Method_deterministic)
    problem = task.getProblem()
    problem.setStepNumber(int(settings["steps"]))
    problem.setDuration(float(settings["duration"]) - float(settings["start"]))
    problem.setOutputStartTime(float(settings["start"]))
    problem.setTimeSeriesRequested(True)
    task.initializeRaw(COPASI.CCopasiTask.OUTPUT_UI)
    ran = task.processRaw(True)
    if not ran:
        print(json.dumps({"cid": cid, "status": "RUN_RETURNED_FALSE", "msgs": msgs}))
        return

    ts = task.getTimeSeries()
    n = ts.getRecordedSteps()
    nvar = ts.getNumVariables()
    titles = [ts.getTitle(i) for i in range(nvar)]

    # Match on the canonical SBML identifier rather than the display
    # title -- see the module docstring for why the two are not
    # interchangeable for non-species quantities.
    sbml_ids = []
    for i in range(nvar):
        try:
            sbml_ids.append(ts.getSBMLId(i, dm))
        except Exception:
            sbml_ids.append(None)
    id_to_col = {sid: i for i, sid in enumerate(sbml_ids) if sid}
    data = np.array([[ts.getConcentrationData(s, c) for c in range(nvar)] for s in range(n)])

    time_col = None
    for i, t in enumerate(titles):
        if t == "Time":
            time_col = i
            break

    residual = evaluate_algebraic_residuals(sbml_model, id_to_col, data, time_col)
    missing = [v for v in variables if v not in id_to_col]
    present = [v for v in variables if v not in missing]

    # Case-level status still reports MISSING_VARS as soon as any requested
    # variable is absent -- this is the right question for "did COPASI fully
    # answer this test case" and is unchanged from prior versions of this
    # harness. What changes here: we no longer return before scoring the
    # variables that *are* present. A case with three requested variables,
    # one of which never appears in COPASI's output, still has the other
    # two computed and classified below, and that per-variable detail is
    # carried in `variable_results` for use by secondary_analysis.py.
    # Earlier versions of this harness returned immediately on `missing`,
    # which meant every present-and-correct variable in such a case was
    # invisible to any per-variable analysis -- silently absorbed into the
    # case's single MISSING_VARS verdict. See README.md, "Known issues".
    time_idx_lower = [h.lower() for h in header]
    off_t = official[:, time_idx_lower.index("time")]
    sim_t = data[:, time_col]
    max_rel_err = 0.0
    worst_var = None
    unit_warning = []
    # Amount/concentration factor per variable, computed once and reused
    # by both the primary relative-error check below and the native-
    # tolerance sensitivity check further down, so the two checks never
    # silently disagree purely from one of them forgetting the
    # conversion. See README.md, "Known issues / open items" for why
    # this used to be computed twice with two different (and, for
    # variables with a genuine non-unity constant compartment, briefly
    # inconsistent) code paths.
    factors = {}
    for v in present:
        factor = 1.0
        if v in amount_vars and v in sp_compartment:
            comp = sp_compartment[v]
            if comp_const.get(comp, True) and comp_size.get(comp) is not None:
                factor = comp_size[comp]
            else:
                # A non-constant compartment (or one with no directly
                # stored size, as in the comp-package case 01377) has no
                # static factor that can safely convert concentration to
                # amount here; flag rather than guess.
                unit_warning.append(f"{v}: non-constant compartment '{comp}', amount conversion unverified")
        factors[v] = factor

    # Per-variable results, computed for every present variable regardless
    # of whether other requested variables in this case are missing. This
    # is what secondary_analysis.py's target-type stratification actually
    # needs: a case-level status answers "did COPASI solve this test
    # case," but attributing every one of a case's requested variables to
    # that single case-level verdict overcounts whichever bucket the case
    # landed in. A variable that is present and numerically correct is a
    # match regardless of what else in the same case was missing or wrong.
    variable_results = {v: {"status": "MISSING"} for v in missing}
    for v in present:
        iv_off = header.index(v)
        iv_sim = id_to_col[v]
        sim_interp = np.interp(off_t, sim_t, data[:, iv_sim])
        off_vals = official[:, iv_off]
        denom = np.maximum(np.abs(off_vals), 1e-12)

        rel_err = np.max(np.abs(sim_interp * factors[v] - off_vals) / denom)
        if rel_err < 1e-3:
            v_status = "PASS"
        elif rel_err < 0.05:
            v_status = "NUMERICAL_DRIFT"
        else:
            v_status = "GROSS_MISMATCH"
        variable_results[v] = {"rel_err": rel_err, "status": v_status}
        if rel_err > max_rel_err:
            max_rel_err = rel_err
            worst_var = v

    if missing:
        status = "MISSING_VARS"
    elif max_rel_err < 1e-3:
        status = "PASS"
    elif max_rel_err < 0.05:
        status = "NUMERICAL_DRIFT"
    else:
        status = "GROSS_MISMATCH"

    # This is a secondary sensitivity criterion.  It never replaces the
    # pre-registered primary classifications above. Uses the same
    # per-variable `factors` as the primary check above, for the same
    # reason. Only meaningful when every requested variable is present;
    # a case with any missing variable can't be scored against its own
    # tolerances at all, so this stays NOT_APPLICABLE for such cases, as
    # it did before this fix.
    native_abs = float(settings.get("absolute", 0.0))
    native_rel = float(settings.get("relative", 0.0))
    if missing:
        native_tolerance_status = "NOT_APPLICABLE"
    else:
        native_ok = True
        for v in present:
            sim_interp = np.interp(off_t, sim_t, data[:, id_to_col[v]])
            off_vals = official[:, header.index(v)]
            if not np.all(np.abs(sim_interp * factors[v] - off_vals) <= native_abs + native_rel * np.abs(off_vals)):
                native_ok = False
                break
        native_tolerance_status = "PASS" if native_ok else "FAIL"

    out = {"cid": cid, "status": status, "max_rel_err": max_rel_err, "worst_var": worst_var, "msgs": msgs,
           "missing": missing, "variable_results": variable_results,
           "native_tolerance_status": native_tolerance_status,
           "native_absolute_tolerance": native_abs, "native_relative_tolerance": native_rel,
           "algebraic_residual": residual}
    # A missing variable is a stronger, case-level failure than an
    # unresolved unit-conversion factor on some other, present variable,
    # and takes priority for the case-level status -- this matches the
    # original harness's behavior, where the missing-variable return
    # happened before unit_warning was ever computed, so the two
    # conditions could never previously coincide. Removing that early
    # return (to let present variables still be scored) means both
    # conditions can now genuinely occur together, e.g. cases 00543 and
    # 00546, so the priority has to be made explicit rather than
    # implicit in control flow. Per-variable detail for the case is
    # still carried in `variable_results` either way.
    if unit_warning and not missing:
        out["status"] = "UNVERIFIED_UNITS"
        out["unit_warning"] = unit_warning
        out["nominal_status_ignoring_units"] = status
        out["nominal_max_rel_err"] = max_rel_err
    elif unit_warning:
        out["unit_warning"] = unit_warning
    print(json.dumps(out))


if __name__ == "__main__":
    main()