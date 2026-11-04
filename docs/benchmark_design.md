# Benchmark design — proving correctness, then stress-testing reasoning

**Two jobs, in order.** This benchmark has to do two things, and the first is prerequisite to the
second:

1. **Prove the oracle is correct.** The CP-SAT solver *and* the independent `check_plan_iter2` must be
   shown to produce the *right* SAT/UNSAT verdict and *valid, degree-completing* plans — against
   something other than each other. Every ground-truth label the LLM evaluation uses is only as
   trustworthy as this proof. (Part A.)
2. **Stress-test the two LLM pipelines** against that trusted ground truth, over a corpus that is both
   *representative* of a real advising caseload and *binding* enough to separate the pipelines.
   (Part B.)

Companion docs: `docs/evaluation_plan.md` (pipelines/metrics for job 2), `docs/solver_constraints.md`
(the formal semantics I2.1–I2.17 being validated).

**Why this reframing matters.** Today the repo has solver↔checker *parity* tests (every solver plan
passes the checker). That is **circular**: it proves the two components *agree*, not that they are
*right*. A rule both encode wrongly — as the dissertation rule was until D29 — passes every parity
test while poisoning the ground truth. Part A is the answer to "who checks the checker?"

---

# PART A — Proving the oracle is correct (the validator benchmark)

Goal: independent evidence that `build_and_solve_iter2` and `check_plan_iter2` implement the degree
rules *correctly*, not merely consistently. Six layers, cheapest/strongest first.

## A1. Checker soundness — one targeted mutation per constraint
The checker's job is to *reject invalid plans*. Prove it actually enforces **each** rule by taking a
known-valid plan and introducing exactly **one** violation, then asserting the checker flags **that**
rule (and names it). One mutation per constraint — this is the core "who checks the checker" evidence.

| Constraint | Mutation injected | Checker must flag |
|---|---|---|
| I2.1 offered-term | move a module into a term it isn't offered | offering violation |
| prereq (tree) | place a module in/ before its prereq's semester | prerequisite violation |
| I2.3 preclusion | include two mutually-precluded modules | preclusion violation |
| bridging | drop MA1301 for a `needs_math_bridging` student before the math chain | bridging violation |
| §7 unit cap | push a semester above its (per-sem) cap | overload |
| I2.5 focus | keep only 2 focus primaries | focus-area shortfall |
| I2.6 L4000 depth | drop below 12u at level ≥4000 | depth shortfall |
| I2.7 B&D 32u | leave the B&D bucket short | B&D shortfall |
| I2.8 industrial (D29) | zero internship for an *ineligible* student; and separately, two internships | missing / padded industrial |
| I2.9 CP cap | exceed 12u of CP-coded modules | CP-cap violation |
| 160u total | finish at 156u | total-units shortfall |
| I2.13 C&E split | put the two GEN halves in non-contiguous semesters | service-learning split violation |
| I2.15 per-sem cap (C1) | schedule a module in a cap-0 (exchange) term | blocked-term violation |
| I2.16 CS-count (C2) | exceed N computing modules in a semester | CS-count violation |
| I2.17 FYP/UROP (C3) | want_fyp but CP4101 absent; want_urop + FYP (CP-cap) | gate / infeasible-combo |

**Each mutation is one test.** A constraint with no mutation test is an *ungraded grader* — the single
biggest silent risk, since the checker is what scores the LLMs. (The repo already has *some* negatives;
A1 makes it a complete, one-per-rule matrix.)

## A2. Checker completeness — solver-plan parity + hand-valid plans
Soundness (A1) proves the checker rejects bad plans; completeness proves it doesn't reject *good* ones.
Two sources: (i) the existing invariant *every solver plan passes the checker* (keep, it's a
completeness signal), and (ii) ~6 **hand-authored valid plans** for diverse profiles that a human
confirms satisfy every rule — the checker must accept all of them. If the solver and checker share a
too-strict bug, (i) can't catch it but (ii) can.

## A3. Metamorphic properties — correctness without knowing the answer
Relations that must hold for *any* instance regardless of the specific verdict. They need no
ground-truth label, so they are cheap and catch asymmetry/monotonicity bugs that spot-checks miss.
Run each over a random batch of instances; any violation is a solver or checker bug.

- **M1 Horizon monotonicity:** `SAT(T) ⇒ SAT(T+1)`. More time cannot make a plan infeasible.
- **M2 Cap monotonicity:** `SAT(cap) ⇒ SAT(cap+1)` (up to the overload ceiling).
- **M3 Credit monotonicity:** completing a module the student would have taken anyway cannot flip
  SAT→UNSAT. (Exemptions handled carefully — they waive the requirement but grant no units, so verify
  the 160u floor is still reachable via UE filler; this edge *is* a property worth asserting.)
- **M4 Preference monotonicity:** removing a per-instance preference cannot flip SAT→UNSAT (D9: baseline
  feasibility never depends on a preference).
- **M5 Tightening direction:** lowering cap, lowering T, or adding a forbid can only move SAT→UNSAT,
  never UNSAT→SAT.
- **M6 Checker-accepts-permutation:** reordering modules across semesters in a way that still respects
  every constraint stays valid — a sanity check that the checker isn't accidentally order-sensitive.

## A4. UNSAT mechanism verification — infeasible for the *stated* reason
An instance can be UNSAT for an **unintended** over-constraint and still get filed as testing, say,
"offering-lock." For every UNSAT case: relax **exactly** the hypothesized binding constraint and
confirm it flips to SAT. If it stays UNSAT, our stated reason is wrong. This gates every UNSAT instance
entering the corpus (and validates `explain_infeasible_iter2`'s diagnosis against the true cause).

## A5. External semantic validation — against the real rulebook
A1–A4 prove the code is *internally* correct and consistent; they cannot prove it matches **NUS's
actual degree rules** (that's the modeling-error class the dissertation bug belonged to). Mitigation:
hand-validate a **stratified sample of ~15–20 ground-truth labels** (plans + verdicts) against the CS
cohort 2026/27 page and, if reachable, an academic advisor. Report the agreement rate as an explicit
validity bound on the oracle ("semantics externally confirmed on N/M sampled instances"). This is the
honest ceiling on every downstream claim and must be in the report's threats-to-validity.

## A6. Differential cross-check on small instances (optional, strong)
For deliberately small sub-problems (few modules, short horizon), enumerate feasibility by a second,
independent means (brute force or an alternative encoding) and confirm it agrees with CP-SAT. Differs
from A2 in that the second solver shares *no code* with the primary one — the strongest guard against a
shared formulation bug.

**Part A exit criterion (gates freezing the oracle):** A1 matrix complete (one mutation per rule); A2
hand-valid plans accepted; A3 properties green on a random batch; A4 run on every UNSAT case; A5 sample
validated and its agreement rate recorded. Only then is the ground truth trustworthy enough to grade
LLMs against.

---

# PART B — The representative scenario corpus

## B1. The two input axes an advisor reasons over
Every advising conversation is `(who the student is) × (what they ask for)` — the PROFILE and REQUEST
layers (`evaluation_plan.md` §2.1–2.2).

**PROFILE (the "who"):** entry pathway (A-level H2-math · poly/no-H2-math · IB/international · mature);
standing (fresh · mid-degree · final-year · behind/retaking); advanced credit (none · AP · poly APC ·
transfer); non-canonical history (CS1010/CS2040C → preclusion bite); eligibility (FYP · UROP · neither).

**REQUEST (the "what"):** horizon (6/7/8/9–10 sem); workload (standard 20 · overload 26–28 · part-load
12–16 · chill sem · exchange cap-0); focus area (11); industrial (any · specific 6-mo · two 3-mo ·
dissertation-instead); research (none · FYP · UROP · FYP+UROP); calendar (canonical · special term ·
exchange · NOC); module prefs (pin/forbid/deadline · ≤N CS/sem · heavy-pair).

**Coverage rule:** every value appears ≥once; every REQUEST axis appears in **both a SAT and an UNSAT**
instance (an untested constraint is an ungraded grader — see A1).

## B2. Student archetype library (advisor's caseload)
✅ built in `data/profiles/benchmark_profiles.yaml`; ➕ to add. Each is the advising story that
generates its NL prompt. **"Faithful?"** flags whether the current model represents it *faithfully* or
only *approximately* given the active simplifications (canonical-only; generic UE/ULR-picklist/ID-CD).

| # | Archetype (advising story) | Key profile/request | Status | Faithful? |
|---|---|---|---|---|
| A0 | On-track fresh Y1 | default; T=8 cap20 | ✅ | yes |
| A1 | Poly / no H2 math | bridging + ES1103 | ✅ | yes |
| A2 | Transfer with APC | completed/exempted; T=7 | ✅ | yes |
| A3 | Early-grad overloader | T=7 cap26 | ✅ | yes |
| A4 | Exchange / SEP | cap-0 sem; T=9 | ✅ | yes |
| A5 | Part-load (work/health) | cap16 + chill; T=10 | ✅ | yes |
| A6 | Honours dissertation | eligible_fyp, want_fyp, special term | ✅ | yes |
| A7 | Internship + UROP | CP3880, want_urop | ✅ | yes |
| A8 | Infeasible 3-year | T=6 cap20 | ✅ | yes |
| A9 | Mid-degree check-in (Y2/Y3) | completed = foundation + GEs | ➕ | yes |
| A10 | Final-year audit ("am I done?") | completed ⊇ ~150u; small T | ➕ | yes |
| A11 | Behind / retaking | missing a blocking prereq; tight T | ➕ | yes |
| A12 | Preclusion bite | completed={CS1010}; CS1101S blocked | ➕ | yes |
| A13 | Over-credited (unit shortfall) | heavy exempted → UE-filler stress | ➕ | approx (generic UE) |
| A14 | Two short internships | industrial_option=CP3200 | ➕ | yes |
| A15 | FYP + UROP (the trap) | want_fyp ∧ want_urop → UNSAT | ➕ | yes |
| A16 | Deep-focus near-boundary | focus + L4000 + tight T (+pins) | ➕ | yes (pins need C4) |
| A18 | Leave of absence / deferred sem | one cap-0 sem, no exchange credit | ➕ | yes (≈ exchange) |
| A19 | Focus switch mid-degree | completed = another area's primaries | ➕ | yes |

> **A17 (NOC) dropped.** NOC needs C6, which is descoped (no iter4, no more features). NOC stays in
> the report only as a named *not-representable* limitation (§B3), not as a corpus instance.

## B3. Realism & representativeness — an honest assessment
**Are the scenarios realistic?** *Individually,* yes — A0–A19 are drawn from cases a CS advisor sees
every term, each expressible in the current schema. Two caveats a reviewer will (rightly) raise:

1. **The distribution is deliberately NOT representative.** A real CS cohort is dominated by on-track
   A-level students (≈ A0). This corpus is **stress-weighted** (≤40% trivial, front-loaded with traps
   and UNSAT) so the pipelines can diverge. That is correct for a stress test but means the *aggregate*
   accuracy is **not** a real-world accuracy. → Report **two** numbers: stress-corpus accuracy, and an
   **advising-realistic** accuracy re-weighted by a plausible caseload mix (estimate the mix from the
   dense-diagonal slice, B2 A0–A19 paired with natural requests).
2. **Realistic scenarios we deliberately do NOT represent** (state as limitations, not silently drop):
   **second major / minor** (extra requirement bucket) — common for NUS CS and the biggest realism gap;
   **NOC** (whole-semester overseas work-study); **S/U declaration** (no grade model); **graduate-level
   modules** (CS5xxx, not in universe); **module-specific timetable clashes** (out of scope by design).
   A13 is *approximate* (generic UE). These are out of scope (no iter4 / no further features); naming
   them is itself RAI evidence that we know where the model stops matching reality.

**Net:** realistic per-case, intentionally unrepresentative in aggregate (handled by dual reporting),
with a named set of not-yet-representable real cases. That is the defensible position.

## B4. Infeasibility taxonomy — graded UNSAT (each mechanism-verified per A4)
The interesting result is *at what subtlety each pipeline stops detecting infeasibility.* Four tiers:
- **T1 Arithmetic floor** (obvious): `T×cap < 160` (e.g. T=6/cap20 = `infeasible_3yr`). Pure division.
- **T2 Bin-packing residue** (subtle): capacity nominally enough but 4u granularity + single-sem
  offerings still UNSAT — *verified*: cap=27/T=6 (cap 162 ≥ 160) is UNSAT. The "divides fine, packs
  badly" trap.
- **T3 Chain-length** (graph reasoning, unit-independent): a prereq chain of length *k* needs ≥*k*
  ordered semesters; set T below the longest-chain floor → UNSAT for a *structural*, not arithmetic,
  reason.
- **T4 Policy interaction** (fine print): CP-cap `want_fyp ∧ want_urop` (CP4101's 12u fills the 12u cap;
  the off-cap internship exemption is the nuance); offering-window lock inside a cap-0 term; preclusion
  dead-end; over-exemption unit shortfall. **All T4 cases require A4 mechanism verification** before
  entering the corpus — they are the easiest to get UNSAT-for-the-wrong-reason.

## B5. Near-boundary SAT — where placement is forced
Hardest *valid* cases: minimum-horizon SAT (T at the measured floor, zero slack); offering-saturated
terms (no reorder freedom); low solution-count backbones (enumerate via CP-SAT callback); and
exemption-enabled early grad (SAT for a transfer, UNSAT for a fresh student on the same request —
tests whether the pipeline used the transcript). These maximize the chance an LLM-direct plan is
*almost* right but violates one constraint → feeds the checker-violation histogram.

## B6. Difficulty is measured, not asserted (construct corrected)
Measure per instance: **near-UNSAT margin** (smallest ΔT/Δunits flipping SAT→UNSAT), **solution count /
backbone**, **active binding-constraint count**. **Do NOT use CP-SAT solve-time as the LLM-difficulty
axis** — it measures solver, not reasoner, difficulty (an instance trivial for CP-SAT can be a
fine-print trap for an LLM). Keep solve-time only for the cost section. Treat "do solver-difficulty
signals predict LLM difficulty?" as a **result**, not an assumption, and plot accuracy against the
measured signals.

## B7. NL authoring (so we test reasoning, not parsing luck)
Generate NL *from* the formal instance for exact ground truth — **but** note the bias: verbalized specs
make *translation artificially easy* and understate the direct pipeline's real edge (tolerating messy
prose). Mitigate on a ~20-instance slice by authoring prose **student-first**, then deriving + solving
the gold spec. Rules: linguistic variety across 3 authors **counterbalanced across the difficulty
range** (avoid the author×difficulty confound); state some preferences implicitly; add distractor
detail; keep an **obfuscation variant** that renames codes **but preserves the full rule/prereq
structure in-context** (else the ablation confounds "lost memorization" with "lost parseable graph");
no ambiguity that changes ground truth.

## B8. Corpus composition (≈100 instances + the Part-A suite, ≤ $100)
| Slice | Count | Purpose |
|---|---|---|
| **Part A oracle suite** (A1 mutations + A2 hand-valid + A3 properties + A4 + A5 sample) | ~50 tests | prove the oracle before using it |
| Dense diagonal (A0–A19 × natural request) | ~20 | realistic caseload; feeds the re-weighted accuracy |
| C-tag sweep on 3 anchors (A0, A11, A7) | ~21 | within-profile accuracy-vs-difficulty curves |
| UNSAT tiers T1–T4 (≥3/tier, all A4-verified) | ~15 | graded infeasibility detection |
| Near-boundary SAT (B5) | ~12 | forced-placement validity stress |
| Interaction traps (A15, offering-lock, preclusion, over-exempt) | ~8 | headline LLM-direct failures |
| **Baselines** (always-SAT; canonical-4yr-plan; a non-frontier model) | ~3 runs | calibrate what the corpus balance makes guessable |
| Obfuscation mirror (structure-preserving, balanced 20-subset) | ~20 | memorization vs reasoning |
| **Balance + power check** | — | ≤40% trivial; every C-tag has SAT *and* UNSAT; ≥N per cell for any claimed heatmap comparison |

## B9. Build order
1. **Part A first** — mutation matrix (A1) + metamorphic props (A3) + hand-valid plans (A2); this is the
   checker-strengthening work and must precede freezing the oracle.
2. **C4 done** (pins/deadlines — enables A16 + crisp offering-lock). C6/NOC descoped.
3. Add profiles **A9–A19** (no A17/NOC); validate each to its declared `expect`; **A4-verify every UNSAT**.
4. **A5 external sample validation**; record agreement rate; then **freeze/tag the oracle**.
5. Generator → `{nl_prompt, formal, ground_truth, meta}`; obfuscation mirror; baselines; balance+power
   check; then run the LLM evaluation (`evaluation_plan.md`).
