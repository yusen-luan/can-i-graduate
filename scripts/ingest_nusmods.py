"""Snapshot canonical BComp(CS) modules from the NUSMods API for a given AY.

Pulls module facts (units, offered terms, prerequisite tree, preclusion text)
for the curated set of codes a canonical CS plan can draw on, transforms them
into our module schema, and writes a versioned snapshot plus a validation
report that flags codes NUSMods does not have (the faculty pages are sometimes
stale). Degree *rules* are NOT here -- they are hand-curated in program_cs.yaml.

    python scripts/ingest_nusmods.py                 # default AY 2026-2027
    python scripts/ingest_nusmods.py --ay 2026-2027

Networked: reads https://api.nusmods.com/v2/<AY>/modules/<CODE>.json
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.nusmods.com/v2"

# --- Curated canonical seed ------------------------------------------------
# The union of: Common-Curriculum fixed choices, CS Foundation, Math&Science,
# bridging, every CS Focus-Area PRIMARY, team-project and industrial/CP codes.
# Grad (CS5xxx) electives are intentionally out of an undergrad planning domain.
SEED = {
    # Common curriculum fixed / ethics / english bridging
    "CS1101S", "ES2660", "GEA1000", "IS1108", "ES1000", "ES1103",
    # CS Foundation
    "CS1231S", "CS2030S", "CS2040S", "CS2100", "CS2101", "CS2103T",
    "CS2106", "CS2109S", "CS3230",
    # Math & Sciences + math bridging
    "MA1521", "MA1522", "ST2334", "MA1301", "MA1301X",
    # Focus-area primaries (AY source: comp.nus.edu.sg/programmes/ug/focus)
    "CS3231", "CS3236", "CS4231", "CS4232", "CS4234", "CS4330", "CS4430",
    "CS3243", "CS3244", "CS3263", "CS3264", "CS3268", "CS4243", "CS4244",
    "CS4246", "CS4248", "CS4262", "CS4263",
    "CS3241", "CS3242", "CS3247", "CS4247", "CS4350",
    "CS2107", "CS3235", "CS4236", "CS4230", "CS4238", "CS4239",
    "CS2102", "CS3223", "CS4221", "CS4224", "CS4225",
    "CS2111", "CS3240", "CS3249", "CS4249", "CS4353",
    "CS2108", "CS3245", "CS4242", "CS4347",
    "CS2105", "CS3103", "CS4222", "CS4226",
    "CS3210", "CS3211", "CS4223", "CS4310",
    "CS2104", "CS4212", "CS4215",
    "CS3213", "CS3217", "CS3219", "CS3227", "CS3282", "CS4211", "CS4218",
    # Team project
    "CS3203", "CS3216", "CS3281",
    # Industrial experience + CP-coded project / FYP
    "CP3880", "CP3200", "CP3202", "CP3107", "CP3110", "CP4101",
    "ETP3201L", "ETP3205", "IS4010", "CP3106", "CP3209", "CP4106",
    # ULR pick-list sample (real codes, verified; full lists in data/ge_pillars.yaml)
    "GEC1015", "GEC1030", "GEC1020",                 # Cultures & Connections (GEC%)
    "GESS1001", "GESS1020", "GESS1025",              # Singapore Studies (GESS%)
    "GEN2000", "GEN2001", "GEN2003", "GEN2004",      # Communities & Engagement (single-sem)
    # ID sample (Appendix B) and CD sample (Appendix C); full lists in data/id_cd.yaml
    "DTK1234", "IE2141", "IS1128", "HSI1000", "HSH1000",
    "DAO2703", "SC1101E", "GE2103", "CDE2300", "EL1101E",
}

# Codes whose pillar/category we tag explicitly (NUSMods has no degree-role data).
ULR_GE_PREFIXES = ("GEC", "GES", "GESS", "GEX", "GEA", "GEI", "GEN")
ID_CODES = {"DTK1234", "IE2141", "IS1128", "IS2218", "IS2238", "HSH1000",
            "HSS1000", "HSA1000", "HSI1000", "CDE2501", "EG2501", "EG1311", "PF1101A"}
CD_CODES = {"DAO2703", "SC1101E", "GE2103", "CDE2300", "EL1101E", "PE2101P",
            "MNO1706X", "ACC1701", "XD3103"}

# Preclusion groups are hand-curated: NUSMods ships preclusions as free text,
# which is unreliable to parse. We store the real NUSMods preclusion string on
# each module for provenance, but the solver uses these canonical groups.
PRECLUSION_GROUPS = {
    "intro_programming": ["CS1101S", "CS1010", "CS1010S", "CS1010X", "CS1010E",
                          "CS1010J", "CS1010A", "CS1010HS"],
    "data_structures": ["CS2040S", "CS1020", "CS1020E", "CS2010", "CS2020",
                        "CS2040", "CS2040C", "CS2040DE", "CS2040HS"],
    "discrete_math": ["CS1231S", "CS1231", "MA1100", "MA1100T"],
}


def level_of(code: str) -> int:
    """First digit-block of a module code -> level band (e.g. CS2103T -> 2000)."""
    m = re.search(r"(\d)", code)
    return int(m.group(1)) * 1000 if m else 0


def fetch(code: str, ay: str):
    url = f"{API}/{ay}/modules/{code}.json"
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def write_module_list(ay: str, out_dir: Path) -> int:
    """Every module code NUSMods lists for the AY -> module_list.json {code: title}.
    Not part of the planning universe: it lets the evaluator tell a real NUS
    module we don't model from a hallucinated / discontinued code."""
    with urllib.request.urlopen(f"{API}/{ay}/moduleList.json", timeout=60) as r:
        listing = {m["moduleCode"]: m["title"] for m in json.load(r)}
    (out_dir / "module_list.json").write_text(
        json.dumps(dict(sorted(listing.items())), indent=0, ensure_ascii=False), encoding="utf-8")
    return len(listing)


def to_tree(prereq_tree):
    """NUSMods and/or/leaf tree -> our all_of/one_of/leaf tree, grades stripped."""
    if prereq_tree is None:
        return None
    if isinstance(prereq_tree, str):
        return prereq_tree.split(":")[0]  # "CS2040S:D" -> "CS2040S"
    if isinstance(prereq_tree, dict):
        if "and" in prereq_tree:
            return {"all_of": [to_tree(c) for c in prereq_tree["and"]]}
        if "or" in prereq_tree:
            return {"one_of": [to_tree(c) for c in prereq_tree["or"]]}
        if "nOf" in prereq_tree:  # [n, [children]] -> approximate as one_of
            return {"one_of": [to_tree(c) for c in prereq_tree["nOf"][1]]}
    return None


def pillar_of(code: str) -> str:
    if code in {"MA1301", "MA1301X"}:
        return "math_bridging"
    if code in {"ES1000", "ES1103"}:
        return "english_bridging"
    if code in {"MA1521", "MA1522", "ST2334"}:
        return "math_statistics"
    if code == "IS1108":
        return "computing_ethics"
    if code in ID_CODES or code in CD_CODES:
        return "interdisciplinary_cross_disciplinary"
    # CS1101S is the Digital Literacy ULR module (its units count in the Common
    # Curriculum, not the 36u CS Foundation), so it is tagged ULR, not foundation.
    if code in {"ES2660", "GEA1000", "CS1101S"} or code.startswith(ULR_GE_PREFIXES):
        return "university_level_requirements"
    if code in {"CS1231S", "CS2030S", "CS2040S", "CS2100", "CS2101",
                "CS2103T", "CS2106", "CS2109S", "CS3230"}:
        return "cs_foundation"
    if code.startswith("CP") or code in {"ETP3201L", "ETP3205", "IS4010"}:
        return "industrial_experience"
    return "breadth_depth"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ay", default="2026-2027")
    ap.add_argument("--sleep", type=float, default=0.15)
    args = ap.parse_args(argv)

    out_dir = ROOT / "data" / f"snapshot_{args.ay}"
    out_dir.mkdir(parents=True, exist_ok=True)

    modules, raw, report = {}, {}, []
    for code in sorted(SEED):
        data = fetch(code, args.ay)
        time.sleep(args.sleep)
        if data is None:
            report.append(f"- **MISSING**: {code} not found in AY{args.ay}")
            continue
        raw[code] = data
        terms = sorted({s["semester"] for s in data.get("semesterData", [])})
        units = int(float(data["moduleCredit"]))
        tree = to_tree(data.get("prereqTree"))
        modules[code] = {
            "title": data.get("title", ""),
            "units": units,
            "level": level_of(code),
            "offered_terms": terms or [1, 2],
            "kind": "bridging" if pillar_of(code) in {"math_bridging", "english_bridging"} else "canonical",
            "pillar": pillar_of(code),
            "prerequisites": {"tree": tree, "conditional": []},
            "nusmods_preclusion": data.get("preclusion", ""),
        }
        if code in ID_CODES:
            modules[code]["category"] = "ID"
        elif code in CD_CODES:
            modules[code]["category"] = "CD"
        if units != 4:
            report.append(f"- units: {code} is {units}u (not 4u) in AY{args.ay}")
        if not terms:
            report.append(f"- terms: {code} has no semesterData; defaulted to [1,2]")
        elif terms not in ([1], [2], [1, 2]):
            report.append(f"- terms: {code} offered in special terms {terms}")

    # attach preclusion_group tags
    code_to_group = {c: g for g, cs in PRECLUSION_GROUPS.items() for c in cs}
    for code, info in modules.items():
        if code in code_to_group:
            info["preclusion_group"] = code_to_group[code]

    (out_dir / "modules.raw.json").write_text(
        json.dumps(raw, indent=2), encoding="utf-8")
    (out_dir / "modules.yaml").write_text(
        yaml.safe_dump(modules, sort_keys=True, allow_unicode=True), encoding="utf-8")
    (out_dir / "preclusions.yaml").write_text(
        yaml.safe_dump({"groups": PRECLUSION_GROUPS}, sort_keys=True), encoding="utf-8")
    n_listed = write_module_list(args.ay, out_dir)

    header = [
        f"# NUSMods ingestion report — AY{args.ay}",
        "",
        f"Fetched {len(SEED)} seed codes; {len(modules)} resolved, "
        f"{len(SEED) - len(modules)} missing. Full AY module list: {n_listed} codes "
        "(module_list.json, used only to classify out-of-model codes in evaluation).",
        "",
        "Anomalies vs the 'canonical 4u, offered both sems' assumption:",
        "",
    ]
    (out_dir / "validation_report.md").write_text(
        "\n".join(header + (report or ["- (none)"])) + "\n", encoding="utf-8")

    print(f"Wrote {len(modules)} modules to {out_dir}")
    print(f"Missing/anomalies: {len([r for r in report if 'MISSING' in r])} missing, "
          f"{len(report)} report lines. See validation_report.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
