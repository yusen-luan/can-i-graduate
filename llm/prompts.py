"""Pipeline A (LLM-direct) prompt: the static degree rules + module catalog, the
output schema, and parsing of the model's answer back into a checker plan.

The system prompt is RENDERED from the same loaded data the checker grades
against (load_iter2), so the LLM and the oracle see one universe; it contains no
instance-specific text, so it is a stable, cacheable prefix. The per-instance
user turn is just the instance's `nl_prompt` (never `formal` / `ground_truth`).

`rename` (code -> code) is the hook for the label-obfuscation ablation
(evaluation_plan.md §6.1); identity by default.
"""
import json
import re

# --- output contract ----------------------------------------------------------
PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "feasible": {"type": "boolean"},
        "plan": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "semester": {"type": "integer"},
                    "modules": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["semester", "modules"],
                "additionalProperties": False,
            },
        },
        "reason": {"type": "string"},
    },
    "required": ["feasible", "plan", "reason"],
    "additionalProperties": False,
}

UE_TOKEN = "UE"   # what the model writes for one generic unrestricted elective

PILLAR_TAG = {
    "breadth_depth": "B&D",
    "industrial_experience": "B&D, industrial experience",
    "university_level_requirements": "ULR / general education",
    "interdisciplinary_cross_disciplinary": "ID/CD",
    "cs_foundation": "CS foundation",
    "math_statistics": "math/statistics",
    "computing_ethics": "computing ethics",
    "math_bridging": "math bridging",
    "english_bridging": "English bridging",
    "unrestricted_electives": "unrestricted elective",
}


def _tree(t, R):
    """Prerequisite tree -> compact boolean text: AND / OR with parentheses."""
    if t is None:
        return ""
    if isinstance(t, str):
        return R(t)
    if "all_of" in t:
        parts, op = t["all_of"], " AND "
    else:
        parts, op = t.get("one_of", []), " OR "
    s = op.join(_tree(c, R) for c in parts)
    return f"({s})" if len(parts) > 1 else s


def _terms(ts):
    names = {1: "Sem 1", 2: "Sem 2", 3: "Special Term 3", 4: "Special Term 4"}
    return ", ".join(names[t] for t in sorted(ts))


def catalog_lines(modules, program, R):
    idcd = set(program["requirement_groups"]["interdisciplinary_cross_disciplinary"]["candidates"])
    bd = program["breadth_depth"]
    ind = {m for o in bd["industrial_experience"]["options"] for m in o["set"]}
    out = []
    for code in sorted(modules):
        m = modules[code]
        if m.get("kind") == "generic_placeholder":
            continue          # UEs are described once, as the UE token
        tag = PILLAR_TAG.get(m.get("pillar"), m.get("pillar", ""))
        if m.get("pillar") == "industrial_experience" and code not in ind:
            # FYP/UROP share the data pillar but are NOT internship-option modules
            # (the checker's "extra industrial module" rule uses the option sets)
            tag = "B&D, CP-coded project (not an industrial-experience option)"
        if code in idcd:
            tag += f" ({m['category']})"
        elif m.get("pillar") == "interdisciplinary_cross_disciplinary":
            tag = "not an ID/CD candidate; counts toward total units only"
        pre = _tree((m.get("prerequisites") or {}).get("tree"), R)
        out.append(f"{R(code)} | {m['title']} | {m['units']} MC | level {m['level']} | "
                   f"offered: {_terms(m.get('offered_terms', [1, 2]))} | {tag}"
                   + (f" | prereq: {pre}" if pre else ""))
    return out


def render_system_prompt(modules, program, focus_areas, preclusions, rename=None):
    R = rename or (lambda c: c)
    L = lambda codes: ", ".join(R(c) for c in codes)  # noqa: E731
    rg = program["requirement_groups"]
    ulr = rg["university_level_requirements"]
    idcd = rg["interdisciplinary_cross_disciplinary"]
    bd = program["breadth_depth"]
    ind_opts = bd["industrial_experience"]["options"]
    ind_mods = sorted({m for o in ind_opts for m in o["set"]})
    n_ue = len(program["unrestricted_electives"]["candidates"])
    fr = focus_areas["rule"]
    cap_ceiling = program["max_overload_units"]
    bundle = next(iter(program["scheduling_bundles"].values()))["modules"]

    ulr_lines = "\n".join(f"  - {name.replace('_', ' ')}: at least {g['modules_required']} of "
                          f"{L(g['satisfied_by'])}" for name, g in ulr.items())
    ind_lines = "\n".join(f"  - option: {' + '.join(R(m) for m in o['set'])}" for o in ind_opts)
    focus_lines = "\n".join(f"  - {a}: {L(spec['primaries'])}"
                            for a, spec in focus_areas["areas"].items())
    precl_lines = "\n".join(f"  - {g}: {L(ms)}" for g, ms in preclusions["groups"].items())
    sl_lines = "\n".join(f"  - {R(x)} (Sem 1 half, carries the credit) then {R(y)} "
                         f"(0 MC continuation)" for x, y in program["service_learning_pairs"])

    return f"""You are an academic planning assistant for the NUS Bachelor of Computing (Computer Science), AY2026/27 cohort. A student describes their situation and request in natural language. Decide whether a plan that satisfies EVERY rule below and every request of the student exists within the semesters they allow. If it exists, give one concrete semester-by-semester plan.

Use only the rules and the module catalog below; they are the complete and authoritative model for this task (they may differ from the real NUS rules you remember).

# 1. Planning model
- The plan has semesters numbered 1..T, where T is the number of semesters the student wants to graduate within. Never use a semester number outside 1..T.
- By default plan semester s is NUS Semester 1 when s is odd and NUS Semester 2 when s is even.
- If the student designates some plan semesters as Special Terms, the remaining (regular) semesters alternate Sem 1, Sem 2, Sem 1, ... in order starting with Sem 1, skipping the special slots. A special slot that follows a Sem 2 is Special Term 3; one that follows a Special Term 3 is Special Term 4.
- A module may only be placed in a semester whose term is listed in its "offered" terms.
- Each module is taken at most once. Never schedule a module the student has already completed or been exempted from.
- Prerequisites: every prerequisite of a module must be satisfied by a module completed/exempted before planning or scheduled in a STRICTLY EARLIER semester (not the same one). Unless the student says otherwise, assume A-level H2 Mathematics (so {L(['MA1301', 'MA1301X'])} count as satisfied as prerequisites and are not taken) and direct English placement (so {L(['ES1000', 'ES1103'])} count as satisfied and are not taken). A student without H2 Mathematics, or with an English bridging requirement, must schedule those bridging modules like any other.
- Unit load: the units in a semester may not exceed the student's per-semester cap (or a semester-specific cap they give; "taking a semester off" means nothing at all may be placed in it), and never exceed {cap_ceiling} MC. Industrial-experience modules ({L(ind_mods)}) do NOT count toward a semester's unit load (they run over the vacation), but they still occupy a semester, must respect its offered terms, and cannot be placed in a semester taken off.
- {L(bundle)} must be taken together in the same semester.
- Year-long service learning: if you take one of these, its continuation must be in the immediately following plan semester:
{sl_lines}
- Preclusions: at most one module of each group below may be held (completed or scheduled; exempted modules do not count):
{precl_lines}

# 2. Graduation requirements (counting completed + exempted + scheduled modules)
- At least {program['total_units_required']} MC in total.
- Required modules: {L(program['required_modules'])}.
- University-level requirements (each list: take at least the stated number):
{ulr_lines}
- Interdisciplinary / cross-disciplinary (ID/CD): exactly {idcd['total_modules_required']} modules from {L(idcd['candidates'])}, with at least {idcd['min_id_modules']} ID and at most {idcd['max_cd_modules']} CD (category shown in the catalog).
- Focus area: the requested area (any one area if none is requested) needs at least {fr['courses_per_area']} of its primaries, with at least {fr['min_level4000_in_area']} at level 4000 or above:
{focus_lines}
- Level 4000: at least {bd['level4000']['min_units']} MC of modules at level 4000 or above.
- Breadth & Depth: at least {bd['min_units']} MC of modules tagged "B&D" in the catalog (this includes industrial experience).
- Industrial experience: complete exactly ONE of the options below in full, and take no industrial-experience module outside that option. If the student names an option, it must be that one. Exception: a student whose GPA qualifies for the final-year project may instead take {R(bd['fyp']['code'])} in place of the internship.
{ind_lines}
- CP-coded cap: {L(bd['cp_coded']['codes'])} together may total at most {bd['cp_coded']['max_units']} MC.
- {R(bd['fyp']['code'])} (final-year project) may only be taken by a student whose GPA qualifies for it; assume a student does NOT qualify unless they say so. UROP research means at least one of {L(bd['urop']['codes'])}; assume a student is eligible for UROP unless they say otherwise.
- Unrestricted electives: any remaining units may be filled with generic 4 MC unrestricted electives. Write each one as the code "{UE_TOKEN}" (offered in Sem 1 and Sem 2, level 1000, no prerequisites). At most {n_ue} generic electives exist in total, including any the student has already completed.

# 3. Student requests
Every request the student states is a hard constraint, in addition to the rules above. For example: a focus area to specialise in; a particular internship option; doing the final-year project or a UROP; per-semester or semester-specific unit caps; semesters taken off or used as Special Terms; a maximum number of CS/IFS/CP-coded modules in any one semester (industrial-experience modules excluded); a minimum unit load in every semester they are enrolled in (a semester with nothing scheduled is not enrolled); no empty semesters between enrolled ones; two modules not in the same semester; modules that must be taken, avoided, or finished by a given semester.

# 4. Answer format
Return JSON with:
- "feasible": true if a plan satisfying everything exists within the allowed semesters, else false.
- "plan": if feasible, one entry per plan semester 1..T, {{"semester": s, "modules": [codes]}} (an empty list for a semester with nothing scheduled); list only modules still to be taken. If infeasible, an empty list.
- "reason": one or two sentences; if infeasible, name the rule or request that makes it impossible.

# 5. Module catalog
Format: code | title | units | level | offered terms | requirement tag | prerequisites (AND / OR).
{chr(10).join(catalog_lines(modules, program, R))}
"""


# --- parsing the answer -----------------------------------------------------------
def parse_response(text):
    """Model JSON -> {"feasible", "plan" {sem: [codes]}, "reason"} or raise ValueError."""
    d = json.loads(text)
    if not isinstance(d.get("feasible"), bool):
        raise ValueError("missing boolean 'feasible'")
    plan = {}
    for e in d.get("plan") or []:
        s = int(e["semester"])
        plan.setdefault(s, [])
        plan[s] += [str(m).strip().upper() for m in e.get("modules", []) if str(m).strip()]
    return {"feasible": d["feasible"], "plan": plan, "reason": str(d.get("reason", ""))}


_UE_RE = re.compile(r"^(UE|UE_GENERIC(_\d+)?)$")


def bind_electives(plan, student, ue_codes):
    """Bind each generic elective the model wrote ("UE", or any UE_GENERIC_n) to a
    placeholder id the student has not already used. Placeholders are
    interchangeable, and the NL prompt only says "N electives completed", so the
    model cannot know which ids those were. Beyond the available ids an
    unknown code is emitted, which the checker rejects (as it would the solver)."""
    used = {c for c in ue_codes if (student.get("completed", {}) or {}).get(c)
            or (student.get("exempted", {}) or {}).get(c)}
    free = iter([c for c in ue_codes if c not in used])
    out, extra = {}, 0
    for s in sorted(plan):
        out[s] = []
        for m in plan[s]:
            if _UE_RE.match(m):
                nxt = next(free, None)
                if nxt is None:
                    extra += 1
                    nxt = f"UE_GENERIC_EXTRA_{extra}"
                out[s].append(nxt)
            else:
                out[s].append(m)
    return out
