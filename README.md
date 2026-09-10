# COPASI SBML Algebraic-Rule Audit

This repository accompanies the paper [Silent Loss of SBML Algebraic Constraints in COPASI](https://doi.org/10.5281/zenodo.22651187). It contains the full audit pipeline: corpus selection,
per-case simulation harnesses for both simulators under test, root-cause
verification scripts, and every result file the manuscript reports.

**Result, across the 106 official SBML Test Suite cases that
genuinely exercise algebraic rules** (see "Building the corpus,
correctly" below, since one commonly-cited count of 107 includes a case
that does not actually contain one): under trajectory-level comparison,
COPASI 4.46.300 matches the published reference trajectory in 7 cases
(6.6%), silently omits the algebraically-determined quantity in 81
(76.4%), reports a present-but-wrong value in 16 (15.1%), and segfaults
on 2 (1.9%), all on SBML input the test suite itself certifies as valid.
Fifteen of the 16 present-but-wrong cases are wrong by 22% to 765%
relative error; the sixteenth, case 00777, is wrong by roughly 1,807x
(180,705%), consistent with COPASI silently keeping a rule-fixed
parameter at its unset default while the reference trajectory decays on
the parameter's true, faster time constant. Several of the 7
trajectory-level matches occur despite a demonstrably incorrect internal
resolution of the underlying constraint; trajectory-level agreement and
constraint-level conformance are not the same claim. These counts are in
`results/final_results_106.csv`, cross-checked against the raw,
unresolved harness output in `results/copasi_regenerated.csv` (1 of the
16 "present but wrong" plus 7 of the 7 "matches" start out as
`UNVERIFIED_UNITS` there: the compartment-rule family resolved by hand
via `verify_compartment_defect.py`, see "Root cause" below).

**Stratified by target type** (419 individual variable requests across
the 106 cases; see `secondary_analysis.py` and
`results/target_breakdown.csv`): species dominate the request count
(300 of 419), but the earlier stratification table in this repository
overstated how often each type was silently omitted, because of a bug
described in "Self-audited results" below. With that bug fixed:

| Target type | Match | Numerical drift | Wrong | Silent omission | Crash |
|---|---|---|---|---|---|
| Species     | 112 | 21 | 102 | 64  | 1 |
| Compartment |   0 |  0 |   0 |  9  | 0 |
| Parameter   |  12 |  2 |  10 | 72  | 7 |
| Reaction    |   0 |  0 |   0 |  2  | 0 |
| Other/alias |   0 |  0 |   0 |  5  | 0 |
| **Total**   | **124** | **23** | **112** | **152** | **8** |

Species are still the most frequent target and still the most often
omitted (64 of 300 species requests), but the previously reported figure
of 228 counted a large number of species that were present in COPASI's
output the whole time, simply because they shared a test case with some
other, genuinely missing variable. See "Self-audited results" for how
this was found and fixed.

**Cross-simulator control:** the identical 106 cases run through
libRoadRunner (and, redundantly, Tellurium, which wraps it) are rejected
at model-load time in 106/106 cases with an explicit, named exception
identifying the unsupported algebraic rule. Zero silent degradations,
zero wrong values, zero crashes. `results/roadrunner_results_106.csv`
shows all 106 rows as `LOAD_REJECTED_ALGEBRAIC`.

**Structural mechanism, directly verified** (not inferred from output):
COPASI's internal `CModelEntity.Status` enumeration, used for every
rule-governable quantity, has no member representing "governed by an
algebraic constraint" (only `FIXED`, `ASSIGNMENT`, `REACTIONS`, `ODE`,
`TIME`). A compartment whose size is fixed by an algebraic rule falls
through to plain `FIXED`, defaulting to exactly 1 regardless of the
rule's declared target. This is confirmed by querying the simulator's
internal compartment object and status enum directly, not by comparing
output. `verify_compartment_defect.py` now runs this check against all
eight algebraic-rule-governed compartment cases in the corpus, not a
subset: the six cases whose declared target happens to be 1 read back
1.0 (consistent with either correct resolution or a lucky coincidence
with the default, and unable by themselves to distinguish the two), and
the two cases with a non-unit target (2.5 and 0.75) both read back
exactly 1.0, isolating the defect. A control case with the same non-unit
size declared as an ordinary constant (not via a rule) is read
correctly. The `CCopasiMessage` warning queue documented in COPASI's own
founding paper is empty at every pipeline checkpoint probed, under every
configuration the Python bindings expose. The missing status member is
directly verified; the exact C++ call site responsible for the specific
numeric default of 1 was not traced (that would require a debug build)
and is reported as the best-supported explanation available from the
Python-visible API, not as source-level proof of causation.

## Self-audited results

During the original single-simulator study, two errors were found and
corrected in the comparison harness (a display-title vs.
canonical-SBML-ID matching bug, and an amount-vs-concentration handling
gap). Extending the audit to a second simulator surfaced a third,
independent error: the original 107-case corpus was selected by
searching each case's plain-text model description for the literal
string "AlgebraicRule", which produces one false positive (case 01000,
whose description merely *mentions* AlgebraicRule while describing what
the model does *not* contain) and would have produced seven false
negatives had SBML's hierarchical Model Composition (`comp`) package not
been separately resolved (seven cases carry their AlgebraicRule inside a
submodel definition rather than the top-level model). The corrected
corpus is 106 cases, independently cross-checked by libRoadRunner's own
load-time judgment, which converges on the same 106 cases. These three
corrections, and their quantified effect on the final numbers, are
documented in full in the paper's Results section ("Building the corpus,
correctly" and "Harness self-audit") and in `tobefiled.md`.

A fourth, smaller issue was found later, in the scoring code rather than
the numbers: `run_one_case_v2.py` computed the amount-vs-concentration
conversion factor twice, once for the primary relative-error check and
once for the native-tolerance sensitivity check, with the
native-tolerance copy silently dropping the conversion. Checked against
the per-case output, this never changed a classification for this
corpus: the only cases where the factor is not 1 are the eight
compartment-rule cases, and for all eight the compartment is
non-constant, so the factor fell back to its 1.0 default in both copies
of the code, not just the buggy one. The two computations are now
unified into a single per-variable `factors` dict so the two checks
cannot diverge on a future or different corpus.

A fifth issue, found while re-checking the per-variable stratification
table above, did change published numbers and is what the paper now
calls Error 4. `run_one_case_v2.py` classified an entire case as
`MISSING_VARS` as soon as any one requested variable was absent, and
returned immediately, before scoring any of the case's other requested
variables. `secondary_analysis.py` then applied that single case-level
verdict to every variable the case had requested, including variables
that were present and had never actually been checked. For a case
requesting three variables, one of which is missing, the previous
pipeline recorded all three as silent omissions rather than one omission
and two variables of unknown status. Quantified against this corpus: of
the 336 variable-requests inside cases carrying an overall `MISSING_VARS`
status, only 152 were ever actually missing; the remaining 184 (164
species, 20 parameters) were present the whole time and simply never
individually scored. Rerunning them: 90 species and 12 parameters were
exact matches, 71 species and 8 parameters were themselves independently
wrong, and 3 species were within the numerical-drift band. A parallel
effect existed on the wrong-value side: `GROSS_MISMATCH` cases had their
single worst-variable verdict applied to every requested variable in the
case, so a case with four requested variables and one badly wrong one
recorded all four as wrong, even when the other three were exact matches
or within drift.

The fix, now in `run_one_case_v2.py`, scores every present variable
regardless of whether other requested variables in the same case are
missing, and emits a `variable_results` field recording each variable's
own status. The case-level status (used for the 7/81/16/2 headline
figures and for `results/final_results_106.csv`) is unchanged by this
fix, and reproduces identically: it still answers "did COPASI fully and
correctly answer this test case," and a missing or badly wrong variable
still fails the whole case on that question. `secondary_analysis.py` was
rewritten to read `variable_results` per case (from
`results/copasi_detailed.jsonl`, produced by `driver_v2.py --detailed`)
instead of broadcasting the case-level status, with one deliberate
exception: the eight hand-resolved `UNVERIFIED_UNITS` compartment cases
still use their hand-resolved case-level status uniformly, because a
single compartment conversion factor genuinely does apply identically to
every variable in those cases. This is not the same shortcut being
fixed; there, a case-level status was applied to variables it had no
bearing on, here, it correctly does.

## Repository layout

```
tobefiled.md                   : responsible-disclosure writeup, ready
                                  to file against the COPASI tracker
requirements.txt               : pinned dependencies for full
                                  reproduction

build_corpus.py                : derives the corrected 106-case list
                                  from the SBML files directly, using
                                  structural verification rather than
                                  substring matching; writes
                                  results/target_cases_106.json
results/target_cases_106.json  : the verified, final 106-case list
                                  used throughout the paper and by
                                  every other script below

run_one_case_v2.py             : per-case COPASI harness (canonical-ID
                                  matching + unit handling). Computes,
                                  per case: a secondary classification
                                  against the test suite's own native
                                  absolute/relative tolerances
                                  (native_tolerance_status); an attempt
                                  to evaluate the algebraic rule's own
                                  residual directly from COPASI's output
                                  time series (algebraic_residual), which
                                  the paper reports is unobtainable in 98
                                  of 106 cases because a needed symbol is
                                  either an omitted requested variable or
                                  the rule's own governed quantity, never
                                  tracked as output at all (the remaining
                                  8 cases crashed or fell inside an
                                  uninspected comp-package submodel); and, per
                                  requested variable, its own match /
                                  numerical-drift / wrong / missing
                                  status (variable_results), used by
                                  secondary_analysis.py.
driver_v2.py                   : batch runner for the above, one
                                  subprocess per case; writes
                                  results/copasi_regenerated.csv and,
                                  with --detailed, results/copasi_detailed.jsonl
results/final_results.csv      : COPASI per-case verdicts, kept for
                                  transparency against the ORIGINAL,
                                  substring-matched 107-case list
                                  (includes the false-positive case
                                  01000)
results/final_results_106.csv  : COPASI per-case verdicts against the
                                  CORRECTED 106-case corpus; this is the
                                  table Table 1 in the paper reports.
                                  Includes hand-added notes
                                  cross-referencing the internal-state
                                  verification for the compartment-rule
                                  family, and a final_status column
                                  (driver_v2.py's own raw output uses
                                  status instead; secondary_analysis.py
                                  accepts either); re-running
                                  driver_v2.py reproduces the same
                                  status and error-magnitude
                                  classifications but not this file's
                                  annotation text.

secondary_analysis.py          : stratifies the 106-case results by
                                  the SBML type of each requested
                                  variable (species / compartment /
                                  parameter / reaction / other) and by
                                  each variable's own match / drift /
                                  wrong / omitted status, reproducing
                                  the paper's per-variable breakdown
                                  (419 total variable requests, Results
                                  "Stratification by target type");
                                  reads results/final_results_106.csv,
                                  results/copasi_detailed.jsonl, and
                                  results/target_cases_106.json, writes
                                  results/target_breakdown.csv. Requires
                                  copasi_detailed.jsonl to exist, i.e.
                                  driver_v2.py --detailed must be run
                                  first.
results/target_breakdown.csv   : output of the above; the source of
                                  the stratification table reproduced
                                  near the top of this README

run_one_case_roadrunner.py     : per-case libRoadRunner/Tellurium
                                  control harness
driver_roadrunner.py           : batch runner for the above; writes
                                  results/roadrunner_regenerated.csv
results/roadrunner_results_106.csv : libRoadRunner per-case verdicts,
                                  106-case corpus (paper's Table 2)

verify_compartment_defect.py   : queries COPASI's internal compartment
                                  value directly, against all eight
                                  algebraic-rule-governed compartment
                                  cases in the corpus; the key evidence
                                  for the numeric-default-of-1 claim
verify_warning_channel.py      : queries COPASI's CModelEntity.Status
                                  enum and CCopasiMessage queue
                                  directly for one representative case
                                  (00547); the key evidence that no
                                  status exists for an algebraically
                                  governed quantity, and no warning
                                  is raised

build_algebraic2.py            : minimal hand-built model showing the
                                  silent-omission failure propagating
                                  into a dead downstream reaction, then
                                  runs it through COPASI and reproduces
                                  the paper's Table (Consequence of the
                                  dominant fault, demonstrated
                                  directly)
check_compartments.py          : corpus-wide scan (over the corrected
                                  106-case list) identifying which
                                  cases have non-unit or non-constant
                                  compartments, i.e. which needed the
                                  deeper unit-handling investigation
```

## Path configuration

Every script that touches the SBML Test Suite resolves its location the
same way: the `SBML_TEST_SUITE` environment variable if set, otherwise a
directory named `sbml-test-suite` alongside the scripts. Set the
environment variable once rather than editing individual scripts if your
checkout lives elsewhere:

```bash
export SBML_TEST_SUITE=/path/to/your/sbml-test-suite
```

## Reproducing the audit end to end

```bash
pip install -r requirements.txt --break-system-packages
git clone --depth 1 https://github.com/sbmlteam/sbml-test-suite.git ./sbml-test-suite
# or: export SBML_TEST_SUITE=/path/to/existing/checkout

python3 build_corpus.py                # rebuilds results/target_cases_106.json (106 cases)
python3 driver_v2.py --detailed        # full COPASI audit -> results/copasi_regenerated.csv
                                        # and results/copasi_detailed.jsonl
python3 driver_roadrunner.py           # cross-simulator control -> results/roadrunner_regenerated.csv
python3 verify_compartment_defect.py   # root-cause verification, part 1 (value, all 8 cases)
python3 verify_warning_channel.py      # root-cause verification, part 2 (status enum + message queue)
python3 check_compartments.py          # corpus-wide compartment scan
python3 build_algebraic2.py            # minimal downstream-consequence demo
python3 secondary_analysis.py          # stratification by target type -> results/target_breakdown.csv
                                        # requires copasi_detailed.jsonl from the --detailed run above
```

`secondary_analysis.py` reads `results/final_results_106.csv` for the
hand-curated case-level status of the eight compartment-rule cases (see
"Self-audited results" above), and `results/copasi_detailed.jsonl` for
every other case's per-variable results. It does not fall back to
`results/copasi_regenerated.csv` alone, and raises a clear error rather
than failing silently if `copasi_detailed.jsonl` is missing.

Expect a few minutes wall-clock for the full sweep on one core; each case
runs in its own subprocess (COPASI segfaults on two inputs and would
otherwise take down the whole batch).

To reproduce the corpus-verification cross-check described in the
paper's "Building the corpus, correctly" (running libRoadRunner against
the original, substring-matched 107-case list to confirm that case 01000
is the only one it loads and simulates without error), build that list
using the substring method described in `build_corpus.py`'s docstring,
save it as a JSON array of case IDs, and pass it to
`driver_roadrunner.py --corpus <path>`.

## Status

Filed. All four bugs (and the corpus-construction note, Bug 5) were submitted to the COPASI project across two channels:

GitHub (copasi/COPASI repository): filed as issues #18 (Bug 4, segfault), #19 (Bug 1, root cause), and #20 (Bugs 2-3, silent omission and present-but-wrong values). The maintainers responded constructively on #18, confirming they would investigate the crash. On #19 the response was that COPASI does not support AlgebraicRule and users should be aware of that, without addressing the report's actual claim: that the documented import-time warning for this case does not appear to reach CCopasiMessage or the GUI, and that the substitution is undetectable from output alone. #20 received no response.

Shortly after filing, GitHub Issues were disabled on the copasi/COPASI repository and issues #18-#20 are no longer publicly accessible. The project's README was also updated to direct feedback and bug reports to the official Bugzilla tracker rather than GitHub. We don't know what prompted either change and aren't asserting a connection between the timing and our filing.

Bugzilla (the project's official tracker, tracker.copasi.org): filed as bugs #3348 (segfault), #3349 (root cause), #3350 (omission and wrong values), each referencing the corresponding GitHub issue for full detail. These remain accessible as of this writing.

A maintainer also opened an issue on this repository labeling it "invalid project," without responding to our reply addressing the distinction between "COPASI doesn't support AlgebraicRule" (true, and never disputed here) and "COPASI silently produces a plausible-looking wrong result when one is present, with no warning through any channel we could find" (the actual subject of this audit).

Full filing history, the original filing checklist, and the exact text submitted to each tracker are in tobefiled.md.

GUI_VERIFICATION_4.47.309.md documents a follow-up manual check, performed in the COPASI 4.47.309 Desktop GUI (the current stable release as of this writing; no Python bindings are published for it yet, so it could not be driven through the scripted pipeline above). It reproduces Bug 1 on a second entity type and confirms it visually in COPASI's own Differential Equations view, extends Bug 2's root cause to a species-level case, and checks two things the API-only pipeline could not: whether the GUI shows a warning the API doesn't, and whether the "Reduce Model" setting has any effect.
