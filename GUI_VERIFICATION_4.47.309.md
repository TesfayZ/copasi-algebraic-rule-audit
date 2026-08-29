# GUI verification on COPASI 4.47.309 (manual, Desktop UI)

The scripted audit in this repository (`driver_v2.py`,
`verify_compartment_defect.py`, `verify_warning_channel.py`, etc.) was run
against COPASI 4.46.300, the latest version with published Python
bindings (`python-copasi` on PyPI tops out at 4.46.300 as of August
2026). COPASI 4.47 (Build 309), released August 13, 2026, has no Python
bindings published yet, so it could not be driven through the existing
scripted harness. The checks below were instead performed by hand in the
4.47.309 Desktop GUI, to confirm the corpus findings still hold on the
current stable release and to extend a few checks the scripted audit
could not attempt via the API alone.

No claim below rests on inspecting COPASI's 4.47.309 source code:
GitHub's tagged releases for `copasi/COPASI` still show 4.46 (Build 300)
as latest as of this writing, so no exact source snapshot for 4.47.309 is
publicly available.

Cases referenced below are from `results/target_cases_106.json` and
`results/copasi_detailed.jsonl`.

---

## Bug 1 (compartment default of 1) — reproduced manually, on the current release

Case 00547 (AlgebraicRule fixes compartment `C` to 2.5): the GUI's
Compartments panel shows Initial Volume = **1**, not 2.5, with no warning
and no visual indication anything is wrong. Simulation Type shows
`fixed`, the same category an ordinary undeclared constant would carry —
consistent with `verify_warning_channel.py`'s finding that
`CModelEntity.Status` has no member for "governed by an algebraic
constraint."

Control case 00675 (explicit constant = 9.8, not a rule): the same field
correctly shows **9.8**, confirming the defect is specific to
rule-governed entities and not a general compartment-import issue.

**Extended to a second entity type.** Case 00777 (AlgebraicRule fixes
global quantity `k2` to 2.5): the GUI's Global Quantities panel shows
Initial Value = **1**, not 2.5 — the identical wrong default, on a
parameter rather than a compartment. Blank Initial/transient Expression
fields, `Type: fixed`, same symptom pattern as the compartment case. This
case's downstream trajectory error is the corpus's largest, at
`max_rel_err` ≈ 1807× (see `copasi_detailed.jsonl`). Two different entity
types defaulting to the identical numeric value of 1, with identical
symptoms, is stronger evidence for one shared underlying code path than
either case alone.

**Direct visual confirmation the rule has no footprint in COPASI's
internal math.** On case 00547, Model > Mathematical > Differential
Equations shows COPASI's actual internal system: three ODEs (X0, X1, T),
each using the compartment's volume (`V_C`) as a plain constant
multiplier. No equation for `C` appears anywhere in this view. This
matches the entity-level finding (wrong default, no expression stored)
but is a different, independent form of evidence: it shows the rule is
absent from the model's *computed math*, not just mis-resolved on one
entity's stored value.

## Bug 2 (species silently dropped) — root cause extended to a species-level case

Case 00039 (AlgebraicRule: `S1 + S2 = k1`; `S2` recorded as `MISSING` in
`copasi_detailed.jsonl`). The GUI's Species panel shows `S2` as
`Type: reactions` — not `fixed`, because S2 happens to participate in a
reaction — with blank Initial/transient Expression, same as the
compartment and parameter cases above. This confirms Bug 2 shares Bug 1's
underlying mechanism (no representational status for an
algebraically-governed quantity), manifesting through a different
fallback label depending on whether the entity also participates in the
reaction network (`fixed` when isolated, as with a compartment;
`reactions` when it's also a reactant/product, as here).

Also confirmed: `S1`, the rule's *other* symbol and not itself the rule's
direct target, is independently wrong (`max_rel_err` ≈ 3.5,
GROSS_MISMATCH) because its dynamics are coupled to S2 through the
ignored constraint. This is a second, real-world instance of the
"silent omission corrupts a downstream, uninvolved-looking quantity"
pattern that `build_algebraic2.py` demonstrates by hand.

## Warning channel — GUI checked directly, same result as the API

COPASI's own documentation (Support/User_Manual/Error_Messages/SBML,
message "SBML (3)") states that COPASI warns when algebraic rules are
ignored on import. Checked at import time, with the message dialog open
and not dismissed, for cases 00547, 00675, 00039, and 00777: **no warning
dialog appeared in any case**, in the 4.47.309 Desktop GUI. This matches
`verify_warning_channel.py`'s finding for the Python API
(`CCopasiMessage` queue empty at every checkpoint) and extends it to the
GUI specifically, which the original API-only check could not address.
The gap is now a discrepancy between COPASI's own documented behavior and
what both interfaces actually do, not merely an absence of a warning in
one interface.

## "Reduce Model" setting — checked, and the reason it doesn't help is now understood

Toggling "Integrate Reduced Model" in the Time Course task (Deterministic
(LSODA) method) on case 00547 leaves compartment `C`'s value unchanged
(still 1, still wrong) in either state.

Running the Stoichiometric Analysis > Mass Conservation task on the same
model finds exactly one moiety: `X1 + T + X0 = 1` — a conservation
relation derived purely from reaction stoichiometry. Compartment `C` does
not appear in it. Reduce-model / moiety analysis operates entirely within
the reaction network's stoichiometry matrix; an AlgebraicRule-governed
compartment sits structurally outside that analysis. There was never a
mechanism by which this setting could affect it — the null result is
therefore a structural finding, not just an observed non-effect.

## Still not tested

- **Non-deterministic (stochastic/hybrid) task types.** The 4.47.309
  Time Course task exposes 9 methods total (2 deterministic, 3
  stochastic, 3 hybrid, 1 SDE). Only Deterministic (LSODA) was used
  above, matching the scripted audit. Whether the defect manifests
  identically under the other 7 is untouched.
- **Case 01377** (dynamically time-varying compartment): not re-examined
  manually; remains genuinely unresolved, as in the scripted audit.
- **Segfault root cause** (cases 00983, 01142): requires a debug build to
  trace; unreachable by both the scripted API approach and manual GUI
  inspection used here.

## Version note

All checks above were performed on COPASI 4.47.309 (Desktop), released
August 13, 2026 — the current latest stable release as of this writing.
The scripted, corpus-wide audit (106 cases) remains on 4.46.300, the
latest version with published Python bindings. If `python-copasi`
publishes 4.47.x bindings, re-running `driver_v2.py --detailed` against
them would extend this from spot-checks on 4 cases to the full corpus.
