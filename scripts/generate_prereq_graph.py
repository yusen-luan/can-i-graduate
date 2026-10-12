from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
MODULES_FILE = ROOT / "data" / "modules.yaml"
OUTPUT_FILE = ROOT / "docs" / "prerequisite_graph.md"

PILLARS = [
    ("math_bridging", "Math bridging"),
    ("english_bridging", "English bridging"),
    ("cs_foundation", "CS foundation"),
    ("math_statistics", "Mathematics & statistics"),
    ("university_level_requirements", "University-level requirements"),
    ("computing_ethics", "Computing ethics"),
    ("interdisciplinary_cross_disciplinary", "Interdisciplinary / cross-disciplinary"),
]

def load_modules():
    with MODULES_FILE.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def cond_label(condition):
    field = condition.get("field", "condition")
    if "equals" in condition:
        return f"{field}={str(condition['equals']).lower()}"
    vals = ",".join(map(str, condition.get("in", [])))
    return f"{field} in [{vals}]"

def generate(modules):
    lines = [
        "# Iteration 1 prerequisite graph",
        "",
        "Generated from `data/modules.yaml`.",
        "",
        "- Solid arrow: ordinary prerequisite",
        "- Dashed arrow: conditional / bridging prerequisite",
        "- Dotted bidirectional edge: corequisite",
        "- Generic GE/ID/CD nodes are placeholders, not specific real modules",
        "",
        "```mermaid",
        "flowchart LR",
    ]

    grouped = {}
    for code, info in modules.items():
        grouped.setdefault(info.get("pillar", "other"), []).append(code)

    for pillar_id, title in PILLARS:
        codes = grouped.get(pillar_id, [])
        if not codes:
            continue
        lines.append(f'    subgraph {pillar_id}["{title}"]')
        for code in codes:
            kind = modules[code].get("kind")
            shape_l, shape_r = ('["', '"]')
            if kind == "bridging":
                shape_l, shape_r = '(["', '"])'
            elif kind == "generic_placeholder":
                shape_l, shape_r = '{{"', '"}}'
            lines.append(f"        {code}{shape_l}{code}{shape_r}")
        lines.append("    end")

    # Ordinary prereqs
    for target, info in modules.items():
        for p in info.get("prerequisites", {}).get("all_of", []):
            lines.append(f"    {p} --> {target}")

    # Conditional prereqs, including OR-groups.
    cond_idx = 0
    for target, info in modules.items():
        for rule in info.get("prerequisites", {}).get("conditional", []):
            label = cond_label(rule.get("when", {}))
            all_of = rule.get("all_of", [])
            one_of = rule.get("one_of", [])

            for p in all_of:
                lines.append(f'    {p} -. "{label}" .-> {target}')

            if one_of:
                cond_idx += 1
                gid = f"COND_{cond_idx}"
                choice_label = " OR ".join(one_of)
                lines.append(f'    {gid}{{"{choice_label}"}}')
                for p in one_of:
                    lines.append(f'    {p} -. "one of" .-> {gid}')
                lines.append(f'    {gid} -. "{label}" .-> {target}')

    # Scheduling bundle: separate modules, atomic same-semester placement.
    lines.append('    CS2101 == "8-unit bundle / same semester" ==> CS2103T')

    # Legacy corequisites, if any are added later.
    for target, info in modules.items():
        for coreq in info.get("corequisites", []):
            c = coreq["module"]
            lines.append(f'    {c} <-. "coreq" .-> {target}')

    lines.append("```")
    lines.append("")
    lines.append("## Current conditional pathways")
    lines.append("")
    lines.append("- Math bridging: if `needs_math_bridging=true`, satisfy MA1301 or MA1301X before MA1521, MA1522, and CS1231S.")
    lines.append("- English baseline: `english_path=direct_es2660` adds no English bridge.")
    lines.append("- English path `es1103_required`: ES1103 must be satisfied before ES2660.")
    lines.append("- English path `es1000_then_es1103`: ES1000 -> ES1103 -> ES2660.")
    lines.append("")
    return "\n".join(lines)

if __name__ == "__main__":
    modules = load_modules()
    OUTPUT_FILE.write_text(generate(modules), encoding="utf-8")
    print(f"Generated {OUTPUT_FILE}")
