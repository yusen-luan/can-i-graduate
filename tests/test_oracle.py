"""Oracle-correctness suite (benchmark_design.md Part A).

Proves the solver + independent checker are *correct*, not merely mutually
consistent (the existing parity tests only show they agree). Three layers:

  A1  checker SOUNDNESS  — one targeted mutation per constraint; the checker
                           must reject it and name the right rule. A constraint
                           with no mutation here is an ungraded grader.
  A3  METAMORPHIC props  — relations that must hold for ANY instance regardless
                           of the verdict (monotonicity / tightening direction);
                           need no ground-truth label, so they catch asymmetry
                           bugs spot-checks miss.
  A4  UNSAT MECHANISM    — every infeasible case must be infeasible for the
                           STATED reason: relax exactly that constraint and
                           confirm it flips SAT.

These complement (do not duplicate) the checker-negatives already in
test_iter2.py; together they form the complete one-per-rule matrix.
"""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from model import load_iter2, load_scenario  # noqa: E402
from solver import build_and_solve_iter2, explain_infeasible_iter2  # noqa: E402
from checker import check_plan_iter2  # noqa: E402

MODULES, PROGRAM, STUDENT, FOCUS, PRECL = load_iter2()
SCEN = load_scenario(Path(__file__).resolve().parents[1] / "data" / "scenario_iter2.yaml")
BD = PROGRAM["breadth_depth"]


def scenario(**over):
    s = copy.deepcopy(SCEN)
    s.update(over)
    return s


def solve(student=STUDENT, **over):
    return build_and_solve_iter2(MODULES, PROGRAM, student, FOCUS, PRECL, scenario(**over))


def check(plan, student=STUDENT, **over):
    return check_plan_iter2(plan, MODULES, PROGRAM, student, FOCUS, PRECL, scenario(**over))


def valid_plan():
    """A known-good plan (the default solver optimum) to mutate."""
    return copy.deepcopy(solve().plan)


def sem_of(plan):
    return {m: s for s, ms in plan.items() for m in ms}


def with_student(**flags):
    st = copy.deepcopy(STUDENT)
    for k, v in flags.items():
        if k in ("completed", "exempted", "conditions"):
            st[k] = {**st.get(k, {}), **v} if isinstance(v, dict) else v
        else:
            st[k] = v
    return st


def remove(plan, code):
    for s in plan:
        if code in plan[s]:
            plan[s].remove(code)
    return plan


# ======================================================================== #
# A1 — checker soundness: one mutation per constraint (not already in       #
#      test_iter2.py). Each asserts the checker flags THAT rule.            #
# ======================================================================== #

def test_A1_unknown_module():
    assert any("unknown module" in e for e in check({1: ["NOTACODE"]}))


def test_A1_duplicate_module():
    assert any("scheduled 2 times" in e for e in check({1: ["CS1101S"], 2: ["CS1101S"]}))


def test_A1_offering_term_locked():
    # CS2108 is Term-2-only (NUSMods AY26/27); placing it in a Term-1 plan slot is illegal.
    assert any("not offered" in e and "CS2108" in e for e in check({1: ["CS2108"]}))


def test_A1_preclusion_bite():
    # student already holds CS1010 (an intro-programming preclusion of CS1101S);
    # scheduling CS1101S makes two credit-bearing modules in the group.
    st = with_student(completed={"CS1010": True})
    assert any("preclusion" in e for e in check({1: ["CS1101S"]}, student=st))


def test_A1_bridging_prerequisite_enforced():
    # a needs_math_bridging student has NO bridging waiver, so MA1521 requires
    # MA1301/X earlier; omitting it is a prerequisite-tree violation.
    st = with_student(has_h2_math=False,
                      conditions={"needs_math_bridging": True, "english_path": "es1103_required"})
    assert any("MA1521" in e and "prerequisite tree" in e for e in check({1: ["MA1521"]}, student=st))


def test_A1_required_module_missing():
    plan = remove(valid_plan(), "CS2100")
    assert any("CS2100" in e and "required but not satisfied" in e for e in check(plan))


def test_A1_level4000_depth_shortfall():
    plan = valid_plan()
    for m in [c for c in sem_of(plan) if MODULES[c]["level"] >= 4000]:
        remove(plan, m)
    assert any("level-4000" in e for e in check(plan))


def test_A1_breadth_depth_shortfall():
    plan = valid_plan()
    for m in [c for c in sem_of(plan)
              if MODULES[c].get("pillar") in ("breadth_depth", "industrial_experience")]:
        remove(plan, m)
    assert any("breadth & depth" in e for e in check(plan))


def test_A1_cp_coded_cap_exceeded():
    # CP4101(12u) + another CP-coded module exceeds the 12u CP-coded cap.
    codes = BD["cp_coded"]["codes"]
    plan = {i + 1: [c] for i, c in enumerate(codes)}  # all CP-coded, each own sem
    assert any("cp-coded" in e for e in check(plan, student=with_student(eligible_fyp=True)))


def test_A1_total_units_shortfall():
    plan = valid_plan()
    # drop ~16 units of electives -> below the 160 floor
    for m in [c for c in sem_of(plan) if c.startswith("UE_GENERIC")][:4]:
        remove(plan, m)
    assert any("total units" in e for e in check(plan))


def test_A1_idcd_count_violation():
    plan = valid_plan()
    for m in [c for c in sem_of(plan) if MODULES[c].get("category") in ("ID", "CD")]:
        remove(plan, m)
    assert any("ID/CD" in e for e in check(plan))


def test_A1_urop_requires_eligibility():
    st = with_student(eligible_urop=False)
    assert any("eligible_urop" in e for e in check({1: ["CP3106"]}, student=st))


# ======================================================================== #
# A3 — metamorphic properties (no ground-truth label needed)               #
# ======================================================================== #

def _monotone(flags):
    """No True followed by a False (once feasible, stays feasible)."""
    return all(not (a and not b) for a, b in zip(flags, flags[1:]))


def test_A3_M1_horizon_monotonicity():
    # SAT(T) => SAT(T+1): more time can never make a plan infeasible. The sweep
    # must cross the boundary (UNSAT at 7, SAT at 8) so the property is exercised.
    feas = [solve(target_semesters=T).feasible for T in range(7, 12)]
    assert not feas[0] and feas[1], feas
    assert _monotone(feas), feas


def test_A3_M2_cap_monotonicity():
    # SAT(cap) => SAT(cap+2) up to the ceiling: more capacity never hurts. At
    # T=6 the sweep crosses the boundary (UNSAT at low caps, SAT at 28).
    feas = [solve(target_semesters=6, max_units_per_semester=c).feasible
            for c in range(20, 30, 2)]
    assert not feas[0] and feas[-1], feas
    assert _monotone(feas), feas


def test_A3_M3_credit_monotonicity():
    # completing a module the plan would schedule anyway cannot flip SAT->UNSAT.
    assert solve().feasible
    assert solve(student=with_student(completed={"CS1101S": True})).feasible


def test_A3_M3b_exemption_keeps_feasible():
    # an exemption satisfies the requirement AND its units count toward the
    # 160u total (D34), so exempting a module can never flip SAT->UNSAT.
    assert solve(student=with_student(exempted={"GEA1000": True})).feasible


def test_D34_exempted_units_count_toward_total():
    # exempting 4 MC (GEA1000) lets the plan schedule exactly 4 MC fewer.
    def scheduled(r):
        return sum(MODULES[m]["units"] for ms in r.plan.values() for m in ms)
    base = solve()
    exm = solve(student=with_student(exempted={"GEA1000": True}))
    assert scheduled(base) - scheduled(exm) == MODULES["GEA1000"]["units"]


def test_A3_M4_preference_monotonicity():
    # removing a per-instance preference can never flip SAT->UNSAT (D9).
    withpref = solve(target_semesters=10, preferences={"max_cs_modules_per_sem": 3})
    assert withpref.feasible          # precondition, so the property is exercised
    assert solve(target_semesters=10).feasible


def test_A3_M5_tightening_cannot_create_feasibility():
    # T=7/cap20 is infeasible; blocking a semester (a strictly tighter instance)
    # must NOT make it feasible.
    assert not solve(target_semesters=7).feasible
    assert not solve(target_semesters=7, preferences={"per_semester_cap": {1: 0}}).feasible


def test_A3_solver_plan_always_passes_checker_random_knobs():
    # parity as a metamorphic property across a spread of request knobs.
    for over in [dict(target_semesters=8), dict(target_semesters=10, max_units_per_semester=16),
                 dict(focus_area="computer_security", target_semesters=9),
                 dict(target_semesters=9, want_urop=True)]:
        r = build_and_solve_iter2(MODULES, PROGRAM, STUDENT, FOCUS, PRECL, scenario(**over))
        if r.feasible:
            assert check(r.plan, **over) == []


# ======================================================================== #
# A4 — UNSAT mechanism verification: infeasible for the STATED reason       #
#      (relax exactly that constraint -> must flip to SAT)                  #
# ======================================================================== #

def test_A4_T1_arithmetic_floor():
    # T=6/cap20 (120u capacity < 160) is UNSAT; the binding reason is capacity.
    assert not solve(target_semesters=6, max_units_per_semester=20).feasible
    # relax ONLY the cap -> flips SAT, confirming capacity (not some other rule) binds.
    assert solve(target_semesters=6, max_units_per_semester=28).feasible


def test_A4_T2_bin_packing_residue():
    # cap=27/T=6 gives 162u nominal capacity (>=160) yet is UNSAT: the residue is
    # 4-unit bin-packing under single-sem offerings, not raw arithmetic.
    assert not solve(target_semesters=6, max_units_per_semester=27).feasible
    # one more unit of headroom (the packing slack) flips it.
    assert solve(target_semesters=6, max_units_per_semester=28).feasible


def test_A4_T4_cp_cap_fyp_urop_conflict():
    # FYP (CP4101, 12u) + UROP is UNSAT because CP4101 alone fills the 12u CP cap.
    st = with_student(eligible_fyp=True)
    assert not build_and_solve_iter2(MODULES, PROGRAM, st, FOCUS, PRECL,
                                     scenario(want_fyp=True, want_urop=True,
                                              target_semesters=9)).feasible
    # relax ONLY the UROP request -> flips SAT, confirming the CP cap is the binding reason.
    assert build_and_solve_iter2(MODULES, PROGRAM, st, FOCUS, PRECL,
                                 scenario(want_fyp=True, want_urop=False,
                                          target_semesters=9)).feasible


# ======================================================================== #
# Regression guards (iter3 review): solver/checker parity on C4 codes,      #
# exact `used` semantics, and an explainer that probes the real instance.   #
# ======================================================================== #

def test_C4_unknown_module_code_is_rejected():
    # a typo must fail loudly, never silently drop the constraint (I2.18)
    for prefs in ({"require_modules": ["CS9999"]}, {"forbid_modules": ["CS9999"]},
                  {"deadline": {"CS9999": 3}}):
        with pytest.raises(ValueError, match="unknown module"):
            build_and_solve_iter2(MODULES, PROGRAM, STUDENT, FOCUS, PRECL,
                                  scenario(preferences=prefs))


def test_C4_pin_on_waived_bridge_is_satisfied_in_both():
    # an H2-Maths student is placement-waived from MA1301: pinning it (or giving it
    # a deadline) is trivially satisfied -- solver plan must pass the checker.
    for prefs in ({"require_modules": ["MA1301"]}, {"deadline": {"MA1301": 3}}):
        r = solve(preferences=prefs)
        assert r.feasible
        assert check(r.plan, preferences=prefs) == []


def test_no_empty_semesters_does_not_cap_heavy_semesters():
    # four 26 MC semesters make T=7 feasible; the plan has no gaps, so adding
    # no_empty_semesters (already satisfied) must not flip it to UNSAT.
    heavy = {3: 26, 4: 26, 5: 26, 6: 26}
    r = solve(target_semesters=7, preferences={"per_semester_cap": heavy})
    assert r.feasible
    prefs = {"per_semester_cap": heavy, "no_empty_semesters": True}
    r2 = solve(target_semesters=7, preferences=prefs)
    assert r2.feasible
    assert check(r2.plan, target_semesters=7, preferences=prefs) == []


def test_no_empty_semesters_is_actually_enforced():
    # a blocked middle semester forces a gap (1-3 | 5-10); without the gap only
    # 6 semesters (120 MC) remain -> UNSAT. A solver that let `used` float would
    # return a gapped plan here.
    prefs = {"per_semester_cap": {4: 0}, "no_empty_semesters": True}
    assert solve(target_semesters=10, preferences={"per_semester_cap": {4: 0}}).feasible
    assert not solve(target_semesters=10, preferences=prefs).feasible


def test_explainer_probes_the_given_instance():
    # FYP + UROP is UNSAT at any horizon (CP cap): the explainer must not claim
    # a longer horizon fixes it, and must name the request as the blocker.
    st =with_student(eligible_fyp=True)
    sc = scenario(want_fyp=True, want_urop=True, target_semesters=9)
    why = explain_infeasible_iter2(MODULES, PROGRAM, st, FOCUS, PRECL, sc)
    assert "target_semesters" not in why
    assert "UROP" in why or "final-year" in why
