"""CanIGraduate — NUS Computer Science degree planner (frontend).

Thin Streamlit UI over src/solver.py + src/checker.py (+ src/plan_quality.py).
The CSP is the single source of truth; every plan shown is re-validated by the
independent checker and scored by the plan-quality evaluator.

v2 design (docs/ui_ux_plan.md §8): student-first, minimal copy. A dropdown picks
the student; one hero STUDENT CARD is the summary; the verdict is a row of STAT
TILES; the plan grid marks heavier / lighter semesters; the workload editor takes
any number of blocked / light / heavy semesters.
"""
import copy
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from model import (load_iter2, load_scenario, load_yaml, term_of,  # noqa: E402
                   per_semester_cap, pre_satisfied)
from solver import build_and_solve_iter2, explain_infeasible_iter2  # noqa: E402
from checker import check_plan_iter2  # noqa: E402

st.set_page_config(page_title="CanIGraduate", layout="wide",
                   initial_sidebar_state="expanded")

# ── category palette (colour is ALWAYS paired with a text label) ─────────────
PILLAR_BAR = {
    "cs_foundation": "#6699cc", "math_statistics": "#4bb3b3",
    "university_level_requirements": "#b077c2", "computing_ethics": "#e4696c",
    "interdisciplinary_cross_disciplinary": "#f99157", "breadth_depth": "#5bb85b",
    "industrial_experience": "#c47a4a", "service_learning": "#c47a4a",
    "unrestricted_electives": "#e8b43a", "math_bridging": "#aeb4bb",
    "english_bridging": "#aeb4bb",
}
PILLAR_LABEL = {
    "cs_foundation": "CS Core", "math_statistics": "Maths & Science",
    "university_level_requirements": "Univ. Curriculum", "computing_ethics": "Ethics",
    "interdisciplinary_cross_disciplinary": "Interdisciplinary", "breadth_depth": "Breadth & Depth",
    "industrial_experience": "Internship / FYP", "service_learning": "Service Learning",
    "unrestricted_electives": "Unrestricted", "math_bridging": "Bridging",
    "english_bridging": "Bridging",
}
LEGEND = [("Univ. Curriculum", "#b077c2"), ("CS Core", "#6699cc"),
          ("Maths & Science", "#4bb3b3"), ("Breadth & Depth", "#5bb85b"),
          ("Internship / FYP", "#c47a4a"), ("Interdisciplinary", "#f99157"),
          ("Ethics", "#e4696c"), ("Unrestricted", "#e8b43a")]

ENGLISH_LABELS = {"direct_es2660": "Direct (ES2660)",
                  "es1103_required": "ES1103 then ES2660",
                  "es1000_then_es1103": "ES1000 → ES1103 → ES2660"}
FOCUS_LABELS = {
    "any": "Flexible", "algorithms_theory": "Algorithms & Theory",
    "artificial_intelligence": "Artificial Intelligence",
    "computer_graphics_games": "Computer Graphics & Games",
    "computer_security": "Computer Security", "database_systems": "Database Systems",
    "hci": "Human–Computer Interaction", "multimedia_ir": "Multimedia IR",
    "networking_distributed": "Networking & Distributed",
    "parallel_computing": "Parallel Computing", "programming_languages": "Programming Languages",
    "software_engineering": "Software Engineering",
}
IND_DESC = {
    "CP3880": "6-month internship (CP3880, ATAP)", "IS4010": "6-month internship (IS4010, IIP)",
    "ETP3201L": "6-month innovation internship (ETP3201L)",
    "CP3200": "Two 3-month internships (CP3200 + CP3202)",
    "CP3107": "Two 3-month community internships (CP3107 + CP3110)",
    "ETP3205": "3-month innovation internship (ETP3205)",
}
PILLAR_NAME = {"digital_literacy": "Digital Literacy", "critique_and_expression": "Critique & Expression",
               "cultures_and_connections": "Cultures & Connections", "data_literacy": "Data Literacy",
               "singapore_studies": "Singapore Studies", "communities_and_engagement": "Communities & Engagement"}
TERM_LABEL = {1: "Term 1", 2: "Term 2", 3: "Special Term", 4: "Special Term"}

CSS = """
<style>
:root{
  --s1:4px; --s2:8px; --s3:12px; --s4:16px; --s5:24px;
  --fz-xs:11px; --fz-sm:12px; --fz-md:13px; --fz-lg:15px; --fz-xl:19px; --fz-2xl:26px;
  --n0:#fff; --n50:#f7f8fa; --n100:#eef0f2; --n200:#e2e5e9; --n300:#d4d8dd;
  --n400:#9aa0a7; --n600:#5c636c; --n800:#2a2d31; --n900:#17191c;
  --accent:#ff5138; --ok:#1a7a46; --ok-bg:#edf6ef; --no:#c0392b; --no-bg:#fbeeee;
  --font: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
.stApp{ font-family:var(--font); background:var(--n50); color:var(--n800); }
#MainMenu, footer{ display:none; }
.block-container{ padding:var(--s4) var(--s5) var(--s5); max-width:1280px; }

section[data-testid="stSidebar"]{ background:var(--n0); border-right:1px solid var(--n200); width:328px !important; }
section[data-testid="stSidebar"] .block-container{ padding:var(--s4) var(--s3); }
.brand{ font-size:var(--fz-lg); font-weight:700; color:var(--n900); letter-spacing:-.01em; margin:0; }
.brand b{ color:var(--accent); }
.brand-sub{ font-size:var(--fz-xs); color:var(--n400); margin:2px 0 var(--s3); }
.side-h{ font-size:var(--fz-xs); letter-spacing:.07em; text-transform:uppercase; color:var(--n400);
  font-weight:700; margin:var(--s3) 0 var(--s1); }

/* hero student card */
.hero{ display:flex; gap:var(--s4); background:var(--n0); border:1px solid var(--n200);
  border-radius:8px; padding:var(--s4) var(--s5); margin-bottom:var(--s4); }
.mono{ width:46px; height:46px; border-radius:9px; background:var(--accent); color:#fff;
  display:flex; align-items:center; justify-content:center; font-weight:700; font-size:var(--fz-lg);
  flex-shrink:0; letter-spacing:-.02em; }
.hero .body{ flex:1; }
.hero .nm{ font-size:var(--fz-xl); font-weight:700; color:var(--n900); letter-spacing:-.01em; }
.hero .ds{ font-size:var(--fz-sm); color:var(--n600); margin:2px 0 var(--s3); line-height:1.45; }
.attrs{ display:grid; grid-template-columns:repeat(3,1fr); gap:var(--s4); }
.attr .ah{ font-size:var(--fz-xs); text-transform:uppercase; letter-spacing:.05em; color:var(--n400);
  font-weight:700; margin-bottom:3px; }
.attr .av{ font-size:var(--fz-sm); color:var(--n800); line-height:1.6; }

/* verdict stat tiles */
.tiles{ display:flex; gap:var(--s3); margin-bottom:var(--s4); }
.tile{ flex:1; background:var(--n0); border:1px solid var(--n200); border-radius:6px; padding:10px 16px; }
.tile .n{ font-size:var(--fz-2xl); font-weight:700; color:var(--n900); letter-spacing:-.02em; line-height:1.1; }
.tile .l{ font-size:var(--fz-xs); color:var(--n400); text-transform:uppercase; letter-spacing:.05em; margin-top:2px; }
.tile.ok{ border-left:3px solid var(--ok); } .tile.ok .n{ color:var(--ok); }
.tile.no{ border-left:3px solid var(--no); } .tile.no .n{ color:var(--no); font-size:var(--fz-xl); }
.subline{ font-size:var(--fz-xs); color:var(--n600); margin:-8px 0 var(--s4) 2px; }
.subline.no{ color:var(--no); margin-top:0; }

.sect{ font-size:var(--fz-xs); letter-spacing:.06em; text-transform:uppercase; color:var(--n400);
  font-weight:700; margin:var(--s3) 0 var(--s2); }
.legend{ display:flex; flex-wrap:wrap; gap:4px var(--s4); margin:0 0 var(--s3); }
.legend span{ font-size:var(--fz-xs); color:var(--n600); display:inline-flex; align-items:center; }
.legend i{ width:9px; height:9px; border-radius:2px; display:inline-block; margin-right:5px; }

/* plan grid */
.year{ margin-bottom:var(--s2); }
.year-h{ font-size:var(--fz-sm); font-weight:700; color:var(--n800); margin:10px 0 6px; }
.row{ display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:var(--s3); }
.row.three{ grid-template-columns:repeat(3, minmax(0,1fr)); }
.sem{ background:var(--n0); border:1px solid var(--n200); border-radius:6px; overflow:hidden;
  display:flex; flex-direction:column; min-height:64px; }
.sem-h{ display:flex; justify-content:space-between; align-items:center; padding:7px 10px;
  background:var(--n50); border-bottom:1px solid var(--n100); }
.sem-h b{ font-size:var(--fz-sm); color:var(--n800); font-weight:700; }
.sem-h .mc{ font-size:var(--fz-xs); color:var(--n400); font-weight:600; }
.sem-h .tag2{ font-size:10px; font-weight:700; padding:1px 6px; border-radius:3px; margin-left:6px;
  text-transform:uppercase; letter-spacing:.03em; }
.tag2.heavy{ background:var(--accent); color:#fff; } .tag2.light{ background:var(--n100); color:var(--n600); }
.loadbar{ height:3px; background:var(--n100); } .loadbar i{ display:block; height:100%; background:var(--accent); }
.sem-b{ padding:7px; display:flex; flex-direction:column; gap:5px; flex:1; }
.cell{ border-radius:4px; padding:5px 8px; border-left:3px solid; background:var(--n50); }
.cell .c{ font-weight:700; font-size:var(--fz-sm); color:var(--n900); }
.cell .t{ font-size:var(--fz-xs); color:var(--n600); line-height:1.3; }
.cell .meta{ font-size:var(--fz-xs); color:var(--n400); margin-top:1px; }
.empty{ color:var(--n300); font-size:var(--fz-sm); padding:8px 6px; text-align:center; }

/* requirement tracker */
.card{ background:var(--n0); border:1px solid var(--n200); border-radius:6px; padding:4px var(--s4) var(--s2); }
.req{ padding:7px 0; border-bottom:1px solid var(--n100); }
.req-top{ display:flex; justify-content:space-between; align-items:center; gap:var(--s2); }
.req .nm{ font-size:var(--fz-sm); color:var(--n800); font-weight:600; }
.req .dt{ font-size:var(--fz-xs); color:var(--n400); margin-top:1px; }
.bar{ height:4px; background:var(--n100); border-radius:2px; overflow:hidden; margin-top:5px; }
.bar i{ display:block; height:100%; background:var(--accent); } .bar i.done{ background:var(--ok); }
.tag{ font-size:var(--fz-xs); font-weight:700; padding:1px 8px; border-radius:4px; white-space:nowrap; }
.tag.met{ background:var(--ok-bg); color:var(--ok); } .tag.no{ background:var(--no-bg); color:var(--no); }
.flags{ font-size:var(--fz-xs); color:var(--n600); margin-top:var(--s2); }
.flags li{ margin:1px 0; }
</style>
"""


@st.cache_data
def load():
    modules, program, student, focus, precl = load_iter2()
    scen = load_scenario(ROOT / "data" / "scenario_iter2.yaml")
    return modules, program, student, focus, precl, scen


@st.cache_data
def load_profiles():
    return load_yaml(ROOT / "data" / "profiles" / "benchmark_profiles.yaml")


def focus_label(k):
    return FOCUS_LABELS.get(k, k.replace("_", " ").title())


def slot_term(slot, term_layout):
    return term_layout[slot - 1] if term_layout else term_of(slot)


def monogram(label):
    words = [w for w in label.replace("—", " ").replace("/", " ").split() if w[:1].isalnum()]
    return (words[0][0] + (words[1][0] if len(words) > 1 else "")).upper() if words else "?"


def seed_from_profile(profile):
    """Write a benchmark profile's student+scenario into widget session_state.
    Reads the FULL per_semester_cap dict so any number of blocked/light/heavy
    semesters round-trips (v2 §8.4b)."""
    stu, sc = profile["student"], profile["scenario"]
    prefs = sc.get("preferences", {}) or {}
    gcap = int(sc["max_units_per_semester"])
    psc = {int(k): v for k, v in (prefs.get("per_semester_cap", {}) or {}).items()}
    blocked = [s for s, u in psc.items() if u == 0]
    light = [(s, u) for s, u in psc.items() if 0 < u < gcap]
    heavy = [(s, u) for s, u in psc.items() if u > gcap]
    layout = sc.get("term_layout")
    specials = [i + 1 for i, t in enumerate(layout) if t in (3, 4)] if layout else []
    ss = st.session_state
    ss["completed"] = list(stu.get("completed", {}) or {})
    ss["exempted"] = list(stu.get("exempted", {}) or {})
    ss["has_h2"] = bool(stu.get("has_h2_math", True))
    ss["english"] = stu.get("conditions", {}).get("english_path", "direct_es2660")
    ss["elig_fyp"] = bool(stu.get("eligible_fyp", False))
    ss["elig_urop"] = bool(stu.get("eligible_urop", True))
    ss["T"] = int(sc["target_semesters"])
    ss["cap"] = gcap
    ss["area"] = sc.get("focus_area", "any")
    ss["ind"] = sc.get("industrial_option", "any")
    ss["want_fyp"] = bool(sc.get("want_fyp", False))
    ss["want_urop"] = bool(sc.get("want_urop", False))
    ss["blocked"] = blocked
    ss["light_sems"] = [s for s, _ in light]
    ss["light_cap"] = light[0][1] if light else 12
    ss["heavy_sems"] = [s for s, _ in heavy]
    ss["heavy_cap"] = heavy[0][1] if heavy else 26
    # sensible default: cap Computing modules at 3/sem unless the profile sets its own
    ss["maxcs"] = int(prefs.get("max_cs_modules_per_sem", 0)) or 3
    ss["specials"] = specials


# ── rendering ────────────────────────────────────────────────────────────--
def hero_card(sel, profiles, student, scenario):
    sc, prefs = scenario, scenario.get("preferences", {}) or {}
    comp, exm = student.get("completed", {}), student.get("exempted", {})
    bg = []
    if comp:
        bg.append(f"{len(comp)} completed")
    if exm:
        bg.append(f"{len(exm)} exempted")
    if not comp and not exm:
        bg.append("Fresh start")
    bg.append("H2 Maths" if student.get("has_h2_math", True) else "Needs bridging")
    if student.get("eligible_fyp"):
        bg.append("FYP-eligible")

    goal = [f"{sc['target_semesters']} semesters", focus_label(sc.get("focus_area", "any"))]
    exp = []
    ind = sc.get("industrial_option", "any")
    exp.append("Any internship" if ind == "any" else ind)
    if sc.get("want_fyp"):
        exp.append("CP4101 FYP")
    if sc.get("want_urop"):
        exp.append("UROP")
    goal.append(", ".join(exp))

    cal = []
    psc = {int(k): v for k, v in (prefs.get("per_semester_cap", {}) or {}).items()}
    blk = [s for s, u in psc.items() if u == 0]
    lt = [s for s, u in psc.items() if 0 < u < sc["max_units_per_semester"]]
    hv = [s for s, u in psc.items() if u > sc["max_units_per_semester"]]
    if blk:
        cal.append("Blocked: " + ", ".join(f"sem {s}" for s in sorted(blk)))
    if lt:
        cal.append("Lighter: " + ", ".join(f"sem {s}" for s in sorted(lt)))
    if hv:
        cal.append("Heavier: " + ", ".join(f"sem {s}" for s in sorted(hv)))
    if sc.get("term_layout") and any(t in (3, 4) for t in sc["term_layout"]):
        sp = [i + 1 for i, t in enumerate(sc["term_layout"]) if t in (3, 4)]
        cal.append("Special Term: " + ", ".join(f"sem {s}" for s in sp))
    cal.append(f"≤ {sc['max_units_per_semester']} MC / sem")
    if not blk and not lt and not hv and not (sc.get("term_layout")):
        cal = ["Standard calendar"] + cal

    def col(title, lines):
        return (f"<div class='attr'><div class='ah'>{title}</div>"
                f"<div class='av'>{'<br>'.join(lines)}</div></div>")

    return (f"<div class='hero'><div class='mono'>{monogram(profiles[sel]['label'])}</div>"
            f"<div class='body'><div class='nm'>{profiles[sel]['label']}</div>"
            f"<div class='ds'>{profiles[sel]['description']}</div>"
            f"<div class='attrs'>{col('Background', bg)}{col('Goal', goal)}"
            f"{col('Calendar', cal)}</div></div></div>")


def cell(code, modules):
    i = modules.get(code, {})
    bar = PILLAR_BAR.get(i.get("pillar"), "#c3c8ce")
    plabel = PILLAR_LABEL.get(i.get("pillar"), "Module")
    return (f"<div class='cell' style='border-left-color:{bar}'>"
            f"<div class='c'>{code}</div><div class='t'>{i.get('title','')[:42]}</div>"
            f"<div class='meta'>{i.get('units','?')} MC · {plabel}</div></div>")


def sem_column(slot, mods, modules, term_layout, cap_s, industrial):
    load = sum(modules[m]["units"] for m in mods if m not in industrial)
    total = sum(modules[m]["units"] for m in mods)
    term = TERM_LABEL[slot_term(slot, term_layout)]
    tag = ""
    if load >= 24 or (cap_s and load > cap_s - 0 and cap_s > 20 and load >= cap_s):
        tag = "<span class='tag2 heavy'>Heavy</span>"
    elif 0 < load <= 12:
        tag = "<span class='tag2 light'>Light</span>"
    pct = min(100, int(load / 28 * 100))
    body = "".join(cell(m, modules) for m in mods) or "<div class='empty'>No modules</div>"
    return (f"<div class='sem'><div class='sem-h'><b>Semester {slot} · {term}</b>"
            f"<span class='mc'>{total} MC{tag}</span></div>"
            f"<div class='loadbar'><i style='width:{pct}%'></i></div>"
            f"<div class='sem-b'>{body}</div></div>")


def plan_grid_html(plan, modules, scenario, global_cap, industrial):
    tl = scenario.get("term_layout")
    slots = sorted(plan)
    html, year, prev_term, buckets = [], 1, 0, {}
    for s in slots:
        t = slot_term(s, tl)
        if t in (1, 2) and t <= prev_term:
            year += 1
        buckets.setdefault(year, []).append(s)
        prev_term = t if t in (1, 2) else prev_term
    for y, ss in buckets.items():
        cols = "".join(sem_column(s, plan[s], modules, tl,
                                  per_semester_cap(scenario, s, global_cap), industrial) for s in ss)
        klass = "row three" if len(ss) >= 3 else "row"
        html.append(f"<div class='year'><div class='year-h'>Year {y}</div>"
                    f"<div class='{klass}'>{cols}</div></div>")
    return "".join(html)


def requirement_sections(plan, modules, program, focus, scenario, student):
    # a requirement is satisfied by a module in the plan OR already held
    # (completed/exempted) — mirror the checker so the panel matches the verdict.
    taken = {m for ms in plan.values() for m in ms}
    done = [m for m in modules if pre_satisfied(m, student)]
    sat = lambda m: m in taken or pre_satisfied(m, student)
    u = lambda pred: (sum(modules[m]["units"] for m in taken if pred(m))
                      + sum(modules[m]["units"] for m in done if pred(m)))
    bd, rg = program["breadth_depth"], program["requirement_groups"]

    uni = []
    for name, g in rg["university_level_requirements"].items():
        picked = [m for m in g["satisfied_by"] if sat(m)]
        uni.append((PILLAR_NAME.get(name, name.title()), ", ".join(picked) or "not chosen",
                    len(picked) >= 1, None))
    uni.append(("Computing Ethics", "IS1108", sat("IS1108"), None))
    idc = rg["interdisciplinary_cross_disciplinary"]
    ids = [m for m in idc["candidates"] if sat(m) and modules[m].get("category") == "ID"]
    cds = [m for m in idc["candidates"] if sat(m) and modules[m].get("category") == "CD"]
    uni.append(("Interdisciplinary & Cross-disciplinary",
                f"{len(ids)} ID, {len(cds)} CD — {', '.join(ids + cds) or 'none'}",
                len(ids) + len(cds) == 3 and len(ids) >= 2 and len(cds) <= 1, (len(ids + cds), 3)))

    found = [m for m in program["required_modules"] if modules[m]["pillar"] == "cs_foundation"]
    math = [m for m in program["required_modules"] if modules[m]["pillar"] == "math_statistics"]
    core = [("Computer Science Foundation", f"{sum(sat(m) for m in found)} of {len(found)} modules",
             all(sat(m) for m in found), (sum(sat(m) for m in found), len(found))),
            ("Mathematics & Sciences", ", ".join(math), all(sat(m) for m in math),
             (sum(sat(m) for m in math), len(math)))]

    chosen = scenario.get("focus_area", "any")
    def area_ok(a):
        p = [m for m in focus["areas"][a]["primaries"] if m in modules and sat(m)]
        return (len(p) >= 3 and any(modules[m]["level"] >= 4000 for m in p)), p
    if chosen == "any":
        hits = [a for a in focus["areas"] if area_ok(a)[0]]
        frow = ("Focus area", ", ".join(focus_label(a) for a in hits) or "none satisfied", bool(hits), None)
    else:
        ok, p = area_ok(chosen)
        frow = (f"Focus — {focus_label(chosen)}", ", ".join(p) or "none taken", ok, (len(p), 3))
    l4 = u(lambda m: modules[m]["level"] >= 4000)
    bdu = u(lambda m: modules[m].get("pillar") in {"breadth_depth", "industrial_experience"})
    ind = [m for o in bd["industrial_experience"]["options"] for m in o["set"] if sat(m)]
    fyp_code = bd.get("fyp", {}).get("code")
    diss = bool(fyp_code and sat(fyp_code))
    ind_detail = (", ".join(ind) if ind else "") + (" + CP4101 dissertation" if diss else "")
    depth = [frow,
             ("Depth at level 4000+", f"{l4} MC (need 12)", l4 >= 12, (l4, 12)),
             ("Breadth & Depth total", f"{bdu} MC (need {bd['min_units']})", bdu >= bd["min_units"],
              (bdu, bd["min_units"])),
             ("Industrial experience", ind_detail or "none", bool(ind) or diss, None)]
    if scenario.get("want_fyp") or diss:
        depth.append(("Final-Year Project (CP4101)", "scheduled" if diss else "not scheduled", diss, None))
    urop = [m for m in bd.get("urop", {}).get("codes", []) if sat(m)]
    if scenario.get("want_urop") or urop:
        depth.append(("UROP research", ", ".join(urop) or "not scheduled", bool(urop), None))

    total = u(lambda m: True)
    overall = [("Total units", f"{total} MC (need {program['total_units_required']})",
                total >= program["total_units_required"], (total, program["total_units_required"])),
               ("CP-coded project limit",
                f"{u(lambda m: m in bd['cp_coded']['codes'])} MC (max {bd['cp_coded']['max_units']})",
                u(lambda m: m in bd["cp_coded"]["codes"]) <= bd["cp_coded"]["max_units"], None)]
    return [("University Curriculum", uni), ("Computer Science Core", core),
            ("Breadth & Depth", depth), ("Overall", overall)]


# ── app ──────────────────────────────────────────────────────────────────--
st.markdown(CSS, unsafe_allow_html=True)
modules, program, student0, focus, precl, scen = load()
profiles = load_profiles()
real_codes = sorted(c for c, i in modules.items() if i.get("kind") != "generic_placeholder")
ceiling = int(program.get("max_overload_units", 28))
sems12 = list(range(1, 13))
pnames = list(profiles)
INDUSTRIAL = {m for o in program["breadth_depth"]["industrial_experience"]["options"] for m in o["set"]}

with st.sidebar:
    st.markdown("<div class='brand'>Can<b>I</b>Graduate</div>"
                "<div class='brand-sub'>NUS Computer Science · AY2026/27</div>", unsafe_allow_html=True)
    st.markdown("<div class='side-h'>Student</div>", unsafe_allow_html=True)
    sel = st.selectbox("Student", pnames, key="profile_name",
                       format_func=lambda k: profiles[k]["label"], label_visibility="collapsed")

if st.session_state.get("_seeded") != sel:
    seed_from_profile(profiles[sel])
    st.session_state["_seeded"] = sel
    st.rerun()

with st.sidebar:
    with st.expander("Background", expanded=False):
        completed = st.multiselect("Completed modules", real_codes, key="completed")
        exempted = st.multiselect("Exempted (advanced placement)", real_codes, key="exempted")
        has_h2 = st.checkbox("Has A-level H2 Mathematics", key="has_h2")
        english = st.selectbox("English placement", list(ENGLISH_LABELS), key="english",
                               format_func=lambda v: ENGLISH_LABELS[v])
        elig_fyp = st.checkbox("Eligible for Final-Year Project", key="elig_fyp")
        elig_urop = st.checkbox("Eligible for UROP", key="elig_urop")

    with st.expander("Goal", expanded=True):
        T = st.slider("Graduate within N semesters", 4, 12, key="T")
        cap = st.slider("Normal units per semester", 12, ceiling, key="cap")
        areas = ["any"] + list(focus["areas"])
        area = st.selectbox("Focus area", areas, key="area", format_func=focus_label)
        ivals = ["any"] + [o["set"][0] for o in program["breadth_depth"]["industrial_experience"]["options"]]
        iunits = {o["set"][0]: sum(modules[c]["units"] for c in o["set"])
                  for o in program["breadth_depth"]["industrial_experience"]["options"]}
        ind = st.selectbox("Industrial experience", ivals, key="ind",
                           format_func=lambda v: ("Any — planner chooses" if v == "any"
                                                  else f"{IND_DESC.get(v, v)} · {iunits[v]} MC"))
        want_fyp = st.checkbox("Do a Final-Year Project (CP4101)", key="want_fyp")
        want_urop = st.checkbox("Do UROP research", key="want_urop")

    with st.expander("Workload & calendar", expanded=False):
        blocked = st.multiselect("Blocked semesters (leave of absence)", sems12, key="blocked",
                                 format_func=lambda v: f"Semester {v}")
        light_sems = st.multiselect("Lighter semesters", sems12, key="light_sems",
                                    format_func=lambda v: f"Semester {v}")
        light_cap = st.slider("…lighter cap (MC)", 4, 16, key="light_cap")
        heavy_sems = st.multiselect("Heavier / overload semesters", sems12, key="heavy_sems",
                                    format_func=lambda v: f"Semester {v}")
        heavy_cap = st.slider("…heavier cap (MC)", 20, ceiling, key="heavy_cap")
        maxcs = st.slider("Max CS modules per semester (0 = no limit)", 0, 6, key="maxcs")
        specials = st.multiselect("Special-Term semesters", sems12, key="specials",
                                  format_func=lambda v: f"Semester {v}")

# ── assemble student + scenario ─────────────────────────────────────────────
student = copy.deepcopy(student0)
student["completed"] = {m: True for m in completed}
student["exempted"] = {m: True for m in exempted}
student["conditions"] = {"needs_math_bridging": not has_h2, "english_path": english}
student["has_h2_math"] = has_h2
student["eligible_fyp"] = elig_fyp
student["eligible_urop"] = elig_urop

per_sem = {}
for s in light_sems:
    if s <= T:
        per_sem[s] = light_cap
for s in heavy_sems:
    if s <= T and heavy_cap > cap:
        per_sem[s] = heavy_cap
for s in blocked:                      # blocked wins over light/heavy
    if s <= T:
        per_sem[s] = 0
term_layout = None
active_specials = [s for s in specials if s <= T]
if active_specials:
    term_layout = [3 if s in active_specials else term_of(s) for s in range(1, T + 1)]

# sensible scheduling defaults (skipped automatically when already completed/exempted):
# intro programming is the very first module; quantitative reasoning sits in Year 1.
deadline = {"CS1101S": 1, "GEA1000": 2}
scenario = {"name": "app", "target_semesters": T, "max_units_per_semester": cap,
            "focus_area": area, "industrial_option": ind,
            "want_fyp": want_fyp, "want_urop": want_urop,
            "preferences": {"per_semester_cap": per_sem, "max_cs_modules_per_sem": maxcs,
                            "min_units_per_semester": 0, "no_empty_semesters": False,
                            "heavy_conflicts": [], "deadline": deadline}}
if term_layout:
    scenario["term_layout"] = term_layout

# ── hero card ────────────────────────────────────────────────────────────---
st.markdown(hero_card(sel, profiles, student, scenario), unsafe_allow_html=True)

# ── solve + verdict ──────────────────────────────────────────────────────---
try:
    result = build_and_solve_iter2(modules, program, student, focus, precl, scenario)
except ValueError as e:
    st.error(str(e))
    st.stop()

if not result.feasible:
    reason = explain_infeasible_iter2({k: scenario[k] for k in
                ("target_semesters", "max_units_per_semester", "focus_area", "industrial_option")})
    st.markdown("<div class='tiles'><div class='tile no'><div class='n'>No valid plan</div>"
                "<div class='l'>under these settings</div></div></div>"
                f"<div class='subline no'>{reason}</div>", unsafe_allow_html=True)
    st.stop()

violations = check_plan_iter2(result.plan, modules, program, student, focus, precl, scenario)
taken = [m for ms in result.plan.values() for m in ms]
held = taken + [m for m in modules if pre_satisfied(m, student)]   # include prior credit
used = max((s for s, ms in result.plan.items() if ms), default=0)
total = sum(modules[m]["units"] for m in held)
cs_count = sum(1 for m in held if m.startswith(("CS", "IFS", "CP")) and m not in INDUSTRIAL)
valid = not violations
st.markdown(
    "<div class='tiles'>"
    f"<div class='tile'><div class='n'>{used}</div><div class='l'>semesters</div></div>"
    f"<div class='tile'><div class='n'>{total}</div><div class='l'>MC total</div></div>"
    f"<div class='tile'><div class='n'>{cs_count}</div><div class='l'>CS modules</div></div>"
    f"<div class='tile {'ok' if valid else 'no'}'><div class='n'>{'Valid' if valid else 'Issue'}</div>"
    f"<div class='l'>checker</div></div></div>",
    unsafe_allow_html=True)
if not valid:
    st.markdown(f"<div class='subline no'>Checker: {'; '.join(violations)}</div>", unsafe_allow_html=True)

left, right = st.columns([3, 2], gap="large")
with left:
    st.markdown("<div class='sect'>Study plan</div>", unsafe_allow_html=True)
    st.markdown("<div class='legend'>" + "".join(
        f"<span><i style='background:{c}'></i>{n}</span>" for n, c in LEGEND) + "</div>",
        unsafe_allow_html=True)
    st.markdown(plan_grid_html(result.plan, modules, scenario, cap, INDUSTRIAL), unsafe_allow_html=True)
with right:
    st.markdown("<div class='sect'>Degree requirements</div>", unsafe_allow_html=True)
    rows_html = []
    for section, rows in requirement_sections(result.plan, modules, program, focus, scenario, student):
        rows_html.append(f"<div class='sect' style='margin-top:8px'>{section}</div>")
        for name, detail, met, prog in rows:
            bar = ""
            if prog:
                got, need = prog
                pct = min(100, int(100 * got / need)) if need else 100
                bar = f"<div class='bar'><i class='{'done' if met else ''}' style='width:{pct}%'></i></div>"
            rows_html.append(
                f"<div class='req'><div class='req-top'><div class='nm'>{name}</div>"
                f"<span class='tag {'met' if met else 'no'}'>{'Met' if met else 'Not met'}</span></div>"
                f"<div class='dt'>{detail}</div>{bar}</div>")
    st.markdown("<div class='card'>" + "".join(rows_html) + "</div>", unsafe_allow_html=True)
