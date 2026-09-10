# To Be Filed: Verified Faults for Upstream Disclosure (v4, post cross-simulator audit)

Status: **FILED**. This is v4 of this document; the findings 
below are unchanged from filing. See "Filing history" at the end of 
this document for what happened after submission, on both channels used. 
v1's numbers predate the harness self-audit in the paper's Results section.
v2 reflected that correction only (7 pass / 82 silent omission / 16
present-but-wrong / 2 crash, out of 107 cases). v3 reflected a second,
independent correction found while extending the audit to a control
simulator: one of the original 107 cases (01000) does not contain an
AlgebraicRule at all and is dropped, giving a corrected denominator of
106. v4 corrects two further issues found while re-checking v3's own
numbers, neither of which changes the 106-case, case-level totals below:
the internal-state check behind Bug 1 now covers all eight
compartment-rule cases in the corpus rather than three of them, and the
relative-error range reported for Bug 3 now includes an outlier case
(00777) that the earlier range omitted. See the paper's "Building the
corpus, correctly" and "Harness self-audit" sections for the full
account, and `build_corpus.py` for the corrected selection script.

Every claim below is reproducible from the scripts in this repository,
run against the official SBML Test Suite
(https://github.com/sbmlteam/sbml-test-suite), scored against the
suite's own published reference results, and, for the root-cause claim
specifically, additionally verified by direct inspection of COPASI's
internal state (see `verify_compartment_defect.py` and
`verify_warning_channel.py`).

Environment: `python-copasi` 4.46.300, `libroadrunner` 2.10.0,
`tellurium` 2.2.13, `python-libsbml` 5.21.1 (all current PyPI releases
at audit time; see `requirements.txt`). COPASI accessed via
`COPASI.CRootContainer` / `CTimeSeries` Python bindings,
`CTaskEnum.Method_deterministic` time-course task. **Not tested via this
script-driven pipeline**: COPASI GUI, non-deterministic task types,
"Reduce Model" setting. The GUI and "Reduce Model" setting were
subsequently checked by hand, on the current COPASI release (4.47.309,
no Python bindings published for it at the time of this audit); see
`GUI_VERIFICATION_4.47.309.md` for what was and was not confirmed
this way. Non-deterministic task types remain untested by either
approach.

---

## Bug 1 (root cause, directly verified): no internal status exists for an algebraically-governed quantity, so rule-governed compartments silently default to a fixed value of 1

**What it is.**
For an SBML `AlgebraicRule` that determines a *compartment's* size
(e.g. `C - 2.5 = 0`), COPASI silently substitutes a default value of
exactly `1` for the compartment, regardless of the rule's declared
target, and does so with `importSBML() → True` and zero messages in the
`CCopasiMessage` queue.

**How it is detected -- directly, not inferred.**
Two independent internal-state checks, not a trajectory comparison.

(a) Query the compartment object's current value through COPASI's own
Python API (`model.getCompartments().get(i).getValue()`) after running
the model to completion. Run against all eight algebraic-rule-governed
compartment cases in the corpus (see `verify_compartment_defect.py`):
six declare a target of `1.0`, and two declare a non-unit target
(`2.5` and `0.75`). All eight return exactly `1.0` internally. The six
target-1 cases cannot by themselves distinguish correct resolution from
a lucky coincidence with the default; the two non-unit-target cases can,
and both confirm the defect. A control case with the *same* non-unit
size (`9.8`) declared as an ordinary constant, not via a rule, is read
correctly by COPASI, ruling out "cannot represent non-unit compartments"
as the explanation and isolating the defect to algebraic-rule resolution
specifically.

(b) Query `CModelEntity.Status` -- the enum COPASI uses internally for
every rule-governable quantity (species, compartments, global
parameters) -- directly through the Python bindings
(`verify_warning_channel.py`). It contains exactly five members:
`FIXED`, `ASSIGNMENT`, `REACTIONS`, `ODE`, `TIME`. There is no
`ALGEBRAIC` member anywhere in the released API surface. Querying the
affected compartment's status after import returns `0` (`FIXED`) --
the same status an ordinary, undeclared constant carries. This check was
run on one representative case (00547); it is a structural finding about
the object model itself, shared by every quantity of this type
regardless of case, not an inference from behavior, and is a plausible
(though not source-code-confirmed) explanation for why the substitution
is silent: there is no representational slot for "governed by an
algebraic constraint" that a warning could even be conditioned on.

**Warning-channel check, also directly verified.**
The `CCopasiMessage` queue was probed at three pipeline checkpoints
(after import, after task initialization, after task execution) under
both `CCopasiMessage.setIsGUI(True)` and `(False)` -- the one flag the
bindings expose for GUI-vs-script message handling, for case 00547. In
every configuration the queue is empty except for one unrelated message
(a missing-output-file notice from the task runner). This directly
addresses, and does not resolve in COPASI's favor, an apparent tension
with COPASI's own 2006 paper (Hoops et al., *Bioinformatics* 22(24),
2006), which states the user is warned when a model contains
unsupported SBML features, and with COPASI's own current documentation
(Support/User_Manual/Error_Messages/SBML, message "SBML (3)"), which
states the same thing more specifically for algebraic rules. **Update:**
the GUI-only warning path this section originally left open was
subsequently checked by hand, on the current COPASI release (4.47.309):
no warning dialog appears at import for this or three other cases
tested. See `GUI_VERIFICATION_4.47.309.md`.

**Why it is sometimes invisible in the output trajectory.**
Whether this substitution corrupts the reported trajectory depends on
the reaction network's kinetic order. For first-order kinetics
(`rate = C·k·[X]`, with `[X] = amount/C`), substituting amount for
concentration shows `C` cancels algebraically from the resulting
amount-based rate law -- a wrong internal `C` produces *no* detectable
error in reported amounts. For second-order kinetics
(`rate = k·[S1][S2]·C`), the same substitution leaves a factor of `C`
that does *not* cancel, and the reported trajectory is measurably wrong
(≈24% relative error observed, direction and rough magnitude consistent
with using `C=1` instead of the true `C=0.75`). **Practical consequence: some fraction of cases
that pass a trajectory-level comparison do so by algebraic coincidence
specific to first-order kinetics, not because the constraint was
actually resolved.**

**How it should be corrected.**
`importSBML()` or the time-course task setup should raise a visible
warning whenever an `AlgebraicRule` cannot be incorporated into a
compartment's simulated size, naming the compartment and its
rule-declared target versus the value actually used. The current
behavior -- silent substitution with a reported import success -- is
the defect; full symbolic resolution of arbitrary algebraic rules is a
larger, separate engineering question, and is not what this issue is
asking for.

**Impact if not corrected.**
Any model using an algebraic rule to fix a compartment's size (a
legitimate SBML pattern) will silently, and for a broad class of
reaction kinetics, be materially wrong, with the only currently
available detection mechanism being a direct internal-state query most
users have no reason to perform.

---

## Bug 2: algebraically-determined species silently dropped from output (81/106, dominant failure mode)

Mechanism unchanged from earlier versions of this document; the
denominator changed from 107 to 106 in v3 (see header) and the count
from 82 to 81 accordingly, purely because case 01000 -- which does not
contain an AlgebraicRule -- was removed from the corpus, not because
any COPASI behavior changed. See `run_one_case_v2.py` and
`results/final_results_106.csv` for the corrected, case-by-case list. Minimal
reproduction of the downstream consequence (a species-consuming
reaction silently never fires) unchanged: `build_algebraic2.py`.

Note for whoever files this: the case-level count above (81 of 106
cases have at least one omitted variable) is the right figure for a
per-case bug report. It should not be read as "81 cases have every
requested variable omitted." Re-checking each case's individually
present variables (v4; see "Harness corrections applied" below) found
that most cases carrying this status also had other, present variables,
some correct and some independently wrong. That distinction matters for
`results/target_breakdown.csv`, which reports it, but not for this
disclosure, which is about the omission mechanism itself.

**Update:** a species-level instance of this mechanism was subsequently
inspected directly in the COPASI GUI (case 00039; see
`GUI_VERIFICATION_4.47.309.md`), showing the same absence of any
stored expression for the omitted quantity that Bug 1 documented for a
compartment, and a downstream consequence on a second, coupled variable
in the same case.

---

## Bug 3: gross numerical mismatch, present but wrong (16/106)

Unchanged in substance from v2; one case (00575, a global parameter
`p2`) was corrected from silent omission to present-but-wrong (22%
relative error) due to our own harness's display-title-vs-identifier
matching bug, documented in the manuscript's "Harness self-audit"
section. Relative errors across the 16 cases range 22% to 765% in 15 of
them. The sixteenth, case 00777, is wrong by roughly 1,807x (180,705%
relative error): COPASI's reported trajectory for species `S1` decays
on an apparent time constant close to 1, while the reference decays on
the true, rule-fixed parameter value of 2.5, so the two trajectories
diverge geometrically and the gap is largest at the latest reported time
point, where the reference value is smallest. This is consistent with
the same silent-default mechanism as Bug 1 and Bug 2, applied here to a
rule-governed parameter rather than a compartment or species; it was not
separately root-caused via internal-state inspection the way Bug 1 was,
and is reported at the trajectory level only.

---

## Bug 4: segmentation fault on valid SBML input (2/106)

Cases `00983` and `01142`. Both were re-confirmed present in the
corrected 106-case corpus. Case `01142` is additionally notable: it is
one of the seven cases whose AlgebraicRule lives inside an SBML
comp-package submodel definition (see Bug 5 below), and it is the one
case in the entire cross-simulator comparison where libRoadRunner's own
error message is imprecise (it names "algebraic rules" when the more
direct trigger is the model's use of the `delay` CSymbol, a second
unsupported construct) -- but libRoadRunner still fails safely with an
exception, while COPASI's process terminates. Root cause for the
segfaults still requires a debug build; out of scope for what could be
verified via the Python bindings alone.

---

## Bug 5 (corpus-construction finding, reported for completeness -- not a COPASI defect): one case in the original 107-case selection does not contain an AlgebraicRule at all

Case `01000`'s model description mentions "AlgebraicRule" only to say
the model deliberately excludes one ("a RoadRunner-friendly model...
doesn't have... AlgebraicRules, CSymbolDelays, and FastReactions").
Confirmed via `libsbml`: zero rules of type Algebraic. It was
originally included via a substring match on the description file and
is dropped from the corrected 106-case corpus. It is reported here,
not because it implicates a COPASI defect, but because it was
originally counted as a "silent omission" case (missing variables
`S4`, `k1`, `k2`, `kavo`) for reasons evidently unrelated to algebraic
rules -- most likely one of this "kitchen sink" model's several other
advanced SBML features (comp submodel replacement, conversion factors,
event priorities). Whoever files this may wish to investigate that
failure separately; we did not, since it is out of this study's scope.

---

## Cross-simulator control (supporting context for filing, not itself a bug report)

The identical 106-case corpus run through libRoadRunner 2.10.0 (and,
redundantly, Tellurium 2.2.13, which wraps it) is rejected at
model-load time in 106/106 cases with an explicit, named exception
(`RuntimeError: Unable to support algebraic rules. The formula
'<exact formula>' is not supported.`). Zero silent degradations, zero
wrong values, zero crashes. This is included in the filing not as a
demand that COPASI match libRoadRunner's feature set, but as evidence
that (a) this corpus is not intrinsically pathological -- another
mature, actively used SBML simulator handles every one of these 106
inputs safely -- and (b) a safe failure mode (reject with a named
error) is achievable in practice for this exact class of unsupported
input, which is what Bug 1's proposed remediation is asking COPASI to
do as well.

---

## Summary table (final, post cross-simulator audit)

| Bug | Cases (of 106) | Detectable without this audit | Verified how |
|---|---|---|---|
| 1. No status for algebraic quantities; compartment defaults to 1 | 8 total; defect confirmed in all 8, visible in trajectory for 1 | None via trajectory alone for 7/8 (algebraic cancellation) | Direct internal-state query (value, all 8 cases; status enum, 1 case) |
| 2. Species silently dropped | 81 (76.4%) | None -- no error, no warning | Output-column absence + manual model inspection |
| 3. Present but wrong | 16 (15.1%) | None -- output looks complete | Reference-trajectory comparison |
| 4. Segfault | 2 (1.9%) | Immediate -- process dies | Subprocess return code |
| **Matches reference** | **7 (6.6%)** | -- | -- |
| Cross-simulator control (libRoadRunner/Tellurium) | 106/106 rejected safely, explicit error | Immediate -- exception raised | Direct exception inspection |

Note: Bug 1's 8 cases are a subset already counted within the 7-pass /
16-mismatch totals above (7 of the 8 pass at trajectory level, 1 fails);
Bug 1 is reported separately because it is a *root-cause* finding about
**why**, verified independently of the trajectory-level pass/fail count.

---

## Harness corrections applied across all versions (for maintainer context)

Filed transparently because it is directly relevant to how much to
trust the numbers being reported.

1. **Display-title vs. canonical-ID matching (v2).** Initial harness
   matched requested variables against `CTimeSeries` display titles
   (`Values[k4]`, `Compartments[comp]` for non-species quantities)
   instead of canonical SBML identifiers (`CTimeSeries.getSBMLId`).
   Reclassified exactly 1/107 cases (00575) upon correction.
2. **Amount-vs-concentration handling (v2).** Initial harness compared
   raw concentration values in all cases; the majority of cases in this
   corpus request amount-based comparison. Resolved case-by-case rather
   than a blanket conversion factor, since a naive "multiply by
   declared target compartment size" correction is itself wrong when
   COPASI's own (buggy) internal state, not the physically correct
   value, determines what its raw output actually represents (see Bug
   1). One case (01377) with a dynamically time-varying compartment
   remains unresolved and is excluded from headline claims rather than
   guessed at.
3. **Corpus selection by substring match (v3).** The original
   case-selection method (grep the literal string "AlgebraicRule" in
   each case's description file) produces one false positive (01000,
   described in Bug 5) and would have produced seven false negatives
   had we not separately checked SBML comp-package submodel
   definitions (cases 01142, 01174, 01350, 01359, 01368, 01377, 01386,
   whose AlgebraicRule lives inside a `comp:ModelDefinition`, not the
   top-level model). Corrected via `build_corpus.py`, and independently
   cross-checked against libRoadRunner's own load-time judgment, which
   converges on the identical 106-case corpus.
4. **Per-variable stratification broadcast (v4).** The harness
   classified an entire case as `MISSING_VARS` on the first missing
   requested variable and returned before scoring the case's other
   requested variables. The per-variable breakdown script then applied
   that single case-level status to every variable the case had
   requested, including ones it had never checked. This does not affect
   the case-level totals reported throughout this document (7/81/16/2
   of 106), which were always based on the case-level status directly.
   It did affect `results/target_breakdown.csv`, the per-variable
   breakdown by SBML type: of 336 variable-requests inside
   `MISSING_VARS` cases, only 152 were actually missing, and the
   remaining 184 were present and had simply never been individually
   scored. Fixed in `run_one_case_v2.py`, which now scores every
   present variable regardless of what else in the case is missing.

Full narrative in the accompanying manuscript, Results section
"Harness self-audit" and "Building the corpus, correctly."

## Filing history

Filed on two channels, in this order.

GitHub (copasi/COPASI repository, github.com/copasi/COPASI/issues, which at filing time was open and listed as the repository's issue tracker): Bug 4 (segfault) as issue #18, Bug 1 (root cause) as issue #19, Bugs 2-3 (silent omission, present-but-wrong) as issue #20, in that order, each cross-referencing the others.

Maintainer response on #18: acknowledged the report and said they would look into why the crash occurs. No further update at time of writing.

Maintainer response on #19: that COPASI does not support AlgebraicRule and users should know this, closing with "what would you have liked to have happen instead." We replied pointing to the specific claim being tested, not disputed: verify_warning_channel.py checks CCopasiMessage.size() at three pipeline checkpoints on the exact case discussed (00547), under both setIsGUI(True) and (False), and finds it empty throughout; the 4.47.309 GUI shows no dialog either. The response did not dispute this finding and instead restated that COPASI does not support AlgebraicRule, which this report has never claimed otherwise and states explicitly in Bug 1's "how it should be corrected" section above.

#20 received no maintainer response.

Some time after filing, GitHub Issues were disabled on the copasi/COPASI repository. Issues #18, #19, and #20 are no longer publicly visible as a result. The repository's README was also updated to direct bug reports to the project's Bugzilla tracker (tracker.copasi.org) and mailing list rather than GitHub. We do not know what prompted either change and are not claiming a causal link to this filing; we note the sequence for the record.

Bugzilla (tracker.copasi.org, the tracker the project's README names as its designated channel): filed as bug #3348 (segfault, mirroring #18), bug #3349 (root cause, mirroring #19), and bug #3350 (omission and wrong values, mirroring #20), each linking back to its GitHub counterpart for full detail and attachments. All three remain accessible at tracker.copasi.org as of this writing.

Separately, a maintainer opened an issue on this repository (not the COPASI repository) stating the project is "invalid" on the grounds that COPASI does not support AlgebraicRule. We replied there pointing to the specific sections of this document and the specific scripts (verify_warning_channel.py, verify_compartment_defect.py, build_algebraic2.py) establishing that the report is about silent, undetectable behavior when an unsupported construct is present, not about the absence of support itself, and noting how libRoadRunner and Tellurium handle the identical input safely by contrast. No response followed as of writing this.