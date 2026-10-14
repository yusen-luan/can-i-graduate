---
name: checkpoint
description: Sync the project's context docs (docs/status.md, docs/decisions.md, docs/history.md, CLAUDE.md) after finishing a task or iteration, and enforce their size budgets so future sessions load accurate, non-bloated context. Use when the user says "checkpoint", "wrap up", "update status", "close the iteration", or after completing a meaningful task.
---

# Checkpoint: sync project context without bloat

Goal: a fresh session that reads only `CLAUDE.md` (and its `@docs/status.md` import) understands the project and its
current state accurately. Each piece of information lives in exactly one place.

## 1. Gather what changed
- `git status`, `git diff --stat`, and `git log --oneline -10`. Also look at what was done in this conversation.
- Optional argument: `iteration-end` means the current iteration is finished (see step 4).

## 2. Route each fact to its home (never duplicate)
| Kind of fact | Home |
|---|---|
| Task finished, next step, blocker, open question | `docs/status.md` |
| Modelling/design choice and its reason | `docs/decisions.md` (new `Dn` entry, ≤ 3 lines) |
| Formal constraint semantics | `docs/solver_constraints.md` |
| New/removed simplification | `docs/status.md` "Active simplifications" + program YAML `assumptions` |
| New command, directory, file role, or convention | `CLAUDE.md` (repo map / commands / conventions) |
| Human-facing usage docs | `README.md` |

If a fact is already recorded somewhere, link to it rather than restating it.

## 3. Update `docs/status.md`
- Bump `_Last updated:` to today's date.
- Move finished items into "Done" as **one line per task**. Do not narrate how they were done; git has that.
- Rewrite "Next" and "Open issues" so they reflect reality. Delete resolved items. Don't strike them through.

## 4. If the iteration ended (`iteration-end`)
- Append ≤ 8 lines to `docs/history.md`: goal, what the model gained, key numbers/results, simplifications lifted.
- Reset `docs/status.md` for the next iteration: new goal, empty Done, and carry over only the simplifications that remain active.

## 5. Enforce budgets (hard limits)
- `CLAUDE.md` ≤ 100 lines, `docs/status.md` ≤ 60 lines. Check with `wc -l`.
- If a file is over its limit, compress it: merge Done lines, move detail into a topic doc under `docs/`, or
  move history out. Never just truncate information that a future session needs.
- `CLAUDE.md` should change rarely. Only touch it when something stable changed (structure, commands, conventions, research framing).

## 6. Consistency check
- Paths and commands referenced in `CLAUDE.md` still exist (`ls` / `python src/model.py`).
- `docs/solver_constraints.md`, the YAML data and `README.md` don't contradict each other. If they do, add an
  "Open issues" line in status rather than silently fixing semantics.

## 7. Report
Tell the user in a few lines what changed in which file. Do not commit unless the user asks.
