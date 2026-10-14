# Project brief (digest of `misc/` course handouts)

Source: `misc/Project.pdf` and `misc/CS3263-Project-Guidelines 2627.docx` (CS3263, AY2026/27 Sem 1).
`misc/ResponsibleAI.pptx` contains the course's Responsible AI notes, which we need for the report's RAI section.
This file rarely changes. Edit it only if the course updates the brief.

## Assignment in one paragraph

Pick an AI sub-problem within a theme ("AI assistant for X" / "AI for good") that can be formulated as
a course problem type (constraint satisfaction, logical reasoning, planning, probabilistic reasoning,
sequential decision making). Formulate it so that a tool can solve it. Construct **many problem instances
described in natural language**. Then compare these two approaches:
1. **LLM-direct:** a frontier model solves the NL instance by reasoning on its own.
2. **LLM-as-translator:** the model turns the NL instance into a formal spec, and a solver solves it.

Use evidence (which instances each approach solves, and how well) to discuss pros and cons. Also discuss
practical variations (availability of a solver or data, input types) and whether non-course tools (LP/ILP, classifiers) would be
better. **Recognising the limitations of the tools is explicitly graded.**

## Our instantiation

- Theme: AI assistant for education → NUS CS degree / module planner.
- Formulation: a CSP over `x[module, semester]` (see `docs/solver_constraints.md`).
- Iterations add real-world complexity step by step, so that LLM-direct vs solver can be compared as difficulty grows.

## Deliverables & dates

| Item | Date | Notes |
|---|---|---|
| Group formation | Fri 18 Sep 2026 | done |
| Proposal (1 page) | Mon 28 Sep 2026 | ungraded, but required to receive a grade |
| Presentation | Week of 9 Nov 2026 | 15 min + 5 min Q&A, possibly a recorded video |
| **Report** | **Fri 13 Nov 2026** | ≤ 10 pages, single column, ≥ 11pt, 1-inch margins (title/refs/appendix excluded) |

The project is worth 25% of the course grade, based on the report and presentation.

## Grading criteria (what to optimise for)

- **Problem understanding:** motivation, problem definition, innovativeness, **responsible AI**.
- **Technical depth:** relevance, accuracy of the knowledge applied, level of achievement.
- **Methodology & results:** formulation as a course-style computational problem, prior work,
  implementation, and **analysis & insights**. The handout says this is "where projects stand out".
  Possible analyses: state-space size / worst-case cost, ablations, justification of LLM-direct vs tool,
  realism of the instance assumptions, failure cases and how to handle them.
- **Effort:** contributions of each member must be stated clearly (marks are deducted otherwise).
- **Report:** relevance, organisation, writing, strict 10-page limit.

## Rules to remember

- Disclose which parts were done with LLM assistance (this is not penalised, but it must be honest).
- Cite all sources. Do not paraphrase documentation.
- An LLM budget can be claimed (≤ $100, one receipt per claim, the group leader submits). SoC also hosts open-weight models
  (https://dochub.comp.nus.edu.sg/cf/guides/soclaas/start), which could be an extra comparison point.
