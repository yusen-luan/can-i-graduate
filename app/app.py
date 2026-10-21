"""CanIGraduate — NUS Computer Science degree planner (frontend).

Thin Streamlit UI over src/solver.py + src/checker.py. The CSP is the single
source of truth; every plan shown is re-validated by the independent checker.
Visual language follows NUSMods: brand coral #ff5138 and the "eighties" base16
timetable palette.

    pip install -r requirements.txt
    streamlit run app/app.py
"""
import copy
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from model import load_iter2, load_scenario  # noqa: E402
from solver import build_and_solve_iter2, explain_infeasible_iter2  # noqa: E402
from checker import check_plan_iter2  # noqa: E402

# NUSMods "eighties" base16 palette, mapped to requirement categories. Dark text.
PILLAR_BG = {
    "cs_foundation": "#6699cc", "math_statistics": "#66cccc",
    "university_level_requirements": "#cc99cc", "computing_ethics": "#f2777a",
    "interdisciplinary_cross_disciplinary": "#f99157", "breadth_depth": "#99cc99",
    "industrial_experience": "#d27b53", "service_learning": "#d27b53",
    "unrestricted_electives": "#ffcc66", "math_bridging": "#cccccc",
    "english_bridging": "#cccccc",
}
LEGEND = [("Univ. Curriculum", "#cc99cc"), ("CS Foundation", "#6699cc"),
          ("Maths & Science", "#66cccc"), ("Breadth & Depth", "#99cc99"),
          ("Internship", "#d27b53"), ("Interdisc./CD", "#f99157"),
          ("Ethics", "#f2777a"), ("Unrestricted", "#ffcc66")]

ENGLISH_LABELS = {
    "direct_es2660": "Direct — take ES2660 straight away",
    "es1103_required": "Needs ES1103 first, then ES2660",
    "es1000_then_es1103": "Needs ES1000, then ES1103, then ES2660",
}
FOCUS_LABELS = {
    "any": "Any focus area", "algorithms_theory": "Algorithms & Theory",
    "artificial_intelligence": "Artificial Intelligence",
    "computer_graphics_games": "Computer Graphics & Games",
    "computer_security": "Computer Security", "database_systems": "Database Systems",
    "hci": "Human–Computer Interaction", "multimedia_ir": "Multimedia Information Retrieval",
    "networking_distributed": "Networking & Distributed Systems",
    "parallel_computing": "Parallel Computing", "programming_languages": "Programming Languages",
    "software_engineering": "Software Engineering",
}
IND_DESC = {
    "CP3880": "6-month internship (CP3880 Advanced Technology Attachment)",
    "IS4010": "6-month internship (IS4010 Industry Internship Programme)",
    "ETP3201L": "6-month innovation & enterprise internship (ETP3201L)",
    "CP3200": "Two 3-month internships (CP3200 + CP3202)",
    "CP3107": "Two 3-month community internships (CP3107 + CP3110, CVWO)",
    "ETP3205": "3-month innovation & enterprise internship (ETP3205)",
}
PILLAR_NAME = {
    "digital_literacy": "Digital Literacy", "critique_and_expression": "Critique & Expression",
    "cultures_and_connections": "Cultures & Connections", "data_literacy": "Data Literacy",
    "singapore_studies": "Singapore Studies", "communities_and_engagement": "Communities & Engagement",
}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"], [class*="st-"] { font-family:'Inter',system-ui,sans-serif; }
#MainMenu, header[data-testid="stHeader"], footer { display:none; }
.block-container { padding:1.2rem 2rem 3rem; max-width:1180px; }

/* sidebar = NUSMods left panel */
[data-testid="stSidebar"] { background:#fafbfc; border-right:1px solid #e3e4e8; }
[data-testid="stSidebar"] .block-container { padding-top:1rem; }
.logo { font-size:1.4rem; font-weight:800; color:#ff5138; letter-spacing:-.02em; margin:0 0 2px; }
.logo-sub { font-size:.72rem; color:#99a0a7; margin-bottom:14px; }
.side-h { font-size:.7rem; letter-spacing:.08em; text-transform:uppercase; color:#99a0a7;
  font-weight:700; margin:14px 0 2px; }

/* verdict banner */
.verdict { border-radius:10px; padding:16px 20px; margin-bottom:8px; border:1px solid; }
.verdict.ok { background:#edf9f1; border-color:#c3e6cf; }
.verdict.no { background:#fdeeee; border-color:#f1c9c9; }
.verdict .t { font-size:1.22rem; font-weight:700; }
.verdict.ok .t { color:#1a7a46; } .verdict.no .t { color:#c0392b; }
.verdict .s { font-size:.9rem; color:#596069; margin-top:4px; }
.chk { font-size:.73rem; color:#9aa0a6; margin:2px 0 16px; }

/* timetable */
.pagetitle { font-size:.78rem; letter-spacing:.08em; text-transform:uppercase; color:#99a0a7;
  font-weight:700; margin:6px 0 8px; }
.sem { background:#fff; border:1px solid #e3e4e8; border-radius:10px; padding:9px 9px 5px; margin-bottom:12px; }
.sem-h { display:flex; justify-content:space-between; align-items:baseline; margin-bottom:6px; }
.sem-h b { font-size:.9rem; color:#1a1c1f; } .sem-h span { font-size:.72rem; color:#9aa0a6; }
.cell { border-radius:5px; padding:6px 9px; margin:5px 0; color:#2b2b2b; }
.cell .c { font-weight:700; font-size:.82rem; }
.cell .n { font-size:.69rem; opacity:.9; }
.cell .m { font-size:.64rem; opacity:.75; margin-top:1px; }
.empty { color:#b4b9bf; font-size:.76rem; padding:7px 4px; }
.legend { display:flex; flex-wrap:wrap; gap:8px 14px; margin:2px 0 14px; }
.legend span { font-size:.7rem; color:#6b7078; display:inline-flex; align-items:center; }
.legend i { width:11px; height:11px; border-radius:3px; display:inline-block; margin-right:5px; }

/* requirements */
.sec { font-size:.72rem; letter-spacing:.07em; text-transform:uppercase; color:#99a0a7;
  font-weight:700; margin:16px 0 2px; }
.req { display:flex; justify-content:space-between; align-items:center; gap:10px;
  padding:8px 2px; border-bottom:1px solid #eef0f2; }
.req .nm { font-size:.88rem; color:#1a1c1f; font-weight:500; }
.req .dt { font-size:.73rem; color:#99a0a7; margin-top:1px; }
.pill { font-size:.66rem; font-weight:700; padding:2px 10px; border-radius:999px; white-space:nowrap; }
.pill.met { background:#e3f6ec; color:#1a7a46; } .pill.no { background:#fdecec; color:#c0392b; }
</style>
"""


@st.cache_data
def load():
    modules, program, student, focus, precl = load_iter2()
    scen = load_scenario(ROOT / "data" / "scenario_iter2.yaml")
    return modules, program, student, focus, precl, scen


def focus_label(k):
    return FOCUS_LABELS.get(k, k.replace("_", " ").title())


def cell(code, modules):
    i = modules.get(code, {})
    return (f"<div class='cell' style='background:{PILLAR_BG.get(i.get('pillar'), '#cccccc')}'>"
            f"<div class='c'>{code}</div><div class='n'>{i.get('title','')[:34]}</div>"
            f"<div class='m'>{i.get('units','?')} MC</div></div>")


def semester_card(sem, mods, modules):
    u = sum(modules[m]["units"] for m in mods)
    body = "".join(cell(m, modules) for m in mods) or "<div class='empty'>No modules</div>"
    return (f"<div class='sem'><div class='sem-h'><b>Semester {sem}</b>"
            f"<span>{u} MC</span></div>{body}</div>")


def requirement_sections(plan, modules, program, focus, scenario):
    taken = {m for ms in plan.values() for m in ms}
    sat = lambda m: m in taken
    u = lambda pred: sum(modules[m]["units"] for m in taken if pred(m))
    bd, rg = program["breadth_depth"], program["requirement_groups"]

    uni = []
    for name, g in rg["university_level_requirements"].items():
        picked = [m for m in g["satisfied_by"] if sat(m)]
        uni.append((PILLAR_NAME.get(name, name.title()), ", ".join(picked) or "not chosen", len(picked) >= 1))
    uni.append(("Computing Ethics", "IS1108", sat("IS1108")))
    idc = rg["interdisciplinary_cross_disciplinary"]
    ids = [m for m in idc["candidates"] if sat(m) and modules[m].get("category") == "ID"]
    cds = [m for m in idc["candidates"] if sat(m) and modules[m].get("category") == "CD"]
    uni.append(("Interdisciplinary & Cross-disciplinary",
                f"{len(ids)} ID, {len(cds)} CD — {', '.join(ids + cds) or 'none'}",
                len(ids) + len(cds) == 3 and len(ids) >= 2 and len(cds) <= 1))

    found = [m for m in program["required_modules"] if modules[m]["pillar"] == "cs_foundation"]
    math = [m for m in program["required_modules"] if modules[m]["pillar"] == "math_statistics"]
    core = [("Computer Science Foundation", f"{sum(sat(m) for m in found)} of {len(found)} modules",
             all(sat(m) for m in found)),
            ("Mathematics & Sciences", ", ".join(math), all(sat(m) for m in math))]

    chosen = scenario.get("focus_area", "any")
    def area_ok(a):
        p = [m for m in focus["areas"][a]["primaries"] if m in modules and sat(m)]
        return (len(p) >= 3 and any(modules[m]["level"] >= 4000 for m in p)), p
    if chosen == "any":
        hits = [a for a in focus["areas"] if area_ok(a)[0]]
        frow = ("Focus area", ", ".join(focus_label(a) for a in hits) or "none satisfied", bool(hits))
    else:
        ok, p = area_ok(chosen)
        frow = (f"Focus — {focus_label(chosen)}", ", ".join(p) or "none taken", ok)
    l4 = u(lambda m: modules[m]["level"] >= 4000)
    bdu = u(lambda m: modules[m].get("pillar") in {"breadth_depth", "industrial_experience"})
    ind = [m for o in bd["industrial_experience"]["options"] for m in o["set"] if sat(m)]
    depth = [frow,
             ("Depth at level 4000+", f"{l4} MC (need 12)", l4 >= 12),
             ("Breadth & Depth total", f"{bdu} MC (need 32)", bdu >= bd["min_units"]),
             ("Industrial experience", ", ".join(ind) or "none", bool(ind))]

    total = u(lambda m: True)
    overall = [("Total units", f"{total} MC (need {program['total_units_required']})",
                total >= program["total_units_required"]),
               ("CP-coded project limit",
                f"{u(lambda m: m in bd['cp_coded']['codes'])} MC (max {bd['cp_coded']['max_units']})",
                u(lambda m: m in bd["cp_coded"]["codes"]) <= bd["cp_coded"]["max_units"])]
    return [("University Curriculum", uni), ("Computer Science Core", core),
            ("Breadth & Depth", depth), ("Overall", overall)]


st.set_page_config(page_title="CanIGraduate", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)
modules, program, student0, focus, precl, scen = load()
real_codes = sorted(c for c, i in modules.items() if i.get("kind") != "generic_placeholder")

with st.sidebar:
    st.markdown("<div class='logo'>CanIGraduate</div>"
                "<div class='logo-sub'>NUS Computer Science · AY2026/27</div>", unsafe_allow_html=True)
    st.markdown("<div class='side-h'>Student</div>", unsafe_allow_html=True)
    completed = st.multiselect("Already completed", real_codes, label_visibility="collapsed",
                               placeholder="Modules already completed")
    exempted = st.multiselect("Exempted", real_codes, label_visibility="collapsed",
                              placeholder="Modules exempted (adv. placement)")
    has_h2 = st.checkbox("Has A-level H2 Mathematics", value=True)
    english = st.selectbox("English placement", list(ENGLISH_LABELS),
                           format_func=lambda v: ENGLISH_LABELS[v])

    st.markdown("<div class='side-h'>Plan settings</div>", unsafe_allow_html=True)
    T = st.slider("Graduate within N semesters", 4, 12, int(scen["target_semesters"]))
    ceiling = int(program.get("max_overload_units", 28))
    cap = st.slider("Max units per semester", 12, ceiling, int(scen["max_units_per_semester"]))
    st.caption(f"Overload ceiling: {ceiling} MC per semester.")
    areas = ["any"] + list(focus["areas"])
    area = st.selectbox("Focus area", areas, index=areas.index(scen.get("focus_area", "any")),
                        format_func=focus_label)
    ivals = ["any"] + [o["set"][0] for o in program["breadth_depth"]["industrial_experience"]["options"]]
    iunits = {o["set"][0]: sum(modules[c]["units"] for c in o["set"])
              for o in program["breadth_depth"]["industrial_experience"]["options"]}
    ind = st.selectbox("Industrial experience", ivals,
                       format_func=lambda v: ("Any — let the planner choose" if v == "any"
                                              else f"{IND_DESC.get(v, v)} · {iunits[v]} MC"))

student = copy.deepcopy(student0)
student["completed"] = {m: True for m in completed}
student["exempted"] = {m: True for m in exempted}
student["conditions"] = {"needs_math_bridging": not has_h2, "english_path": english}
student["has_h2_math"] = has_h2
scenario = {**scen, "target_semesters": T, "max_units_per_semester": cap,
            "focus_area": area, "industrial_option": ind, "preferences": {}}

# Solve live on every change (no dead "click to run" state).
try:
    result = build_and_solve_iter2(modules, program, student, focus, precl, scenario)
except ValueError as e:
    st.error(str(e))
    st.stop()

if not result.feasible:
    reason = explain_infeasible_iter2({k: scenario[k] for k in
                ("target_semesters", "max_units_per_semester", "focus_area", "industrial_option")})
    st.markdown(f"<div class='verdict no'><div class='t'>No valid plan under these settings</div>"
                f"<div class='s'>{reason}</div></div>", unsafe_allow_html=True)
    st.stop()

violations = check_plan_iter2(result.plan, modules, program, student, focus, precl, scenario)
taken = [m for ms in result.plan.values() for m in ms]
used = max((s for s, ms in result.plan.items() if ms), default=0)
total = sum(modules[m]["units"] for m in taken)
st.markdown(
    f"<div class='verdict ok'><div class='t'>Yes — this degree can be completed</div>"
    f"<div class='s'>{used} semesters &nbsp;·&nbsp; {total} MC &nbsp;·&nbsp; focus: "
    f"{focus_label(area) if area != 'any' else 'flexible'}</div></div>", unsafe_allow_html=True)
st.markdown(f"<div class='chk'>{'Every requirement verified by the independent checker.' if not violations else 'CHECKER ISSUE: ' + '; '.join(violations)}</div>",
            unsafe_allow_html=True)

left, right = st.columns([3, 2], gap="large")
with left:
    st.markdown("<div class='pagetitle'>Study plan</div>", unsafe_allow_html=True)
    st.markdown("<div class='legend'>" + "".join(
        f"<span><i style='background:{c}'></i>{n}</span>" for n, c in LEGEND) + "</div>",
        unsafe_allow_html=True)
    sems = [(s, result.plan[s]) for s in sorted(result.plan)]
    ncol = 4 if len(sems) > 6 else 2
    cols = st.columns(ncol)
    for i, (sem, mods) in enumerate(sems):
        cols[i % ncol].markdown(semester_card(sem, mods, modules), unsafe_allow_html=True)
with right:
    st.markdown("<div class='pagetitle'>Requirements</div>", unsafe_allow_html=True)
    for section, rows in requirement_sections(result.plan, modules, program, focus, scenario):
        st.markdown(f"<div class='sec'>{section}</div>", unsafe_allow_html=True)
        for name, detail, met in rows:
            st.markdown(
                f"<div class='req'><div><div class='nm'>{name}</div><div class='dt'>{detail}</div></div>"
                f"<span class='pill {'met' if met else 'no'}'>{'Met' if met else 'Not met'}</span></div>",
                unsafe_allow_html=True)
