# UI/UX design plan — CanIGraduate frontend

**Author stance.** Written as a senior product designer doing a design review of `app/app.py`. The
app works, but it reads as *vibe-coded*: emoji used as iconography, a Google-font import, pill-and-card
soup, magic-number spacing, and a marketing-hero tone on what is actually a **dense planning tool**.
This doc (1) names the vibe-coded anti-patterns explicitly so we can reject them, (2) sets the design
principles and tokens, and (3) gives a concrete, line-level remediation plan referencing NUSMods as
the north star. NUSMods is the right reference because it solves the *same* problem — dense, scannable,
color-coded academic scheduling for the same university — and it is unmistakably a **tool**, not a
landing page.

---

## 1. The vibe-coded anti-pattern checklist (reject all of these)

A "vibe-coded" frontend optimizes for *first-glance dopamine*, not for the task. The tells, and
whether the current app commits them:

| # | Anti-pattern | In current `app/app.py`? |
|---|---|---|
| V1 | **Emoji as iconography** — 🎯🎓📚💼🧪🔬✈️🌙☀️⚖️🏅✅➖➕🗣️ carrying real meaning | **Yes** — `constraint_chips()` is built entirely from emoji (lines 244–281) |
| V2 | **Google-font import over the network** (Inter w/ 5 weights) — perf + offline fragility, and Inter is the single most overused "AI startup" font | **Yes** — `@import ...Inter:wght@400..800` (line 80) |
| V3 | **Pill-and-card soup** — every element wrapped in a bordered, rounded, shadowed card; `border-radius: 999px` chips everywhere | **Yes** — `.chip`, `.pill`, `.pcard`, `.card`, `.verdict` all rounded 12–999px |
| V4 | **Magic-number spacing** — `.68rem`, `.09em`, `1.1rem`, `-.02em` scattered with no scale | **Yes** — dozens of ad-hoc rem/em values, no token system |
| V5 | **Marketing-hero tone** — a big "Can I graduate?" headline + subtitle selling the tool to its own user | **Yes** — `.h1` "Can I graduate?" hero (lines 431–434) |
| V6 | **Color without a text label** — meaning encoded only in a hue (accessibility fail for ~8% of users) | Partial — plan cells rely on the color bar; a legend exists but cells have no category text |
| V7 | **Gradient/neon accents, glassmorphism, hover-transform animation** | No (good — keep it that way) |
| V8 | **Low information density on a data tool** — airy padding, oversized verdict box, one big column | **Yes** — the verdict is a large colored block; generous padding throughout |
| V9 | **Decorative inconsistency** — three chip color classes (`k`/`w`/`s`) that don't map to a documented taxonomy | **Yes** — chip classes are ad-hoc |
| V10 | **Redundant restating** — the same facts in the summary card chips *and* the requirement list | Partial |

**Rule:** every one of V1–V6, V8–V10 is a defect to be removed, not a style preference.

---

## 2. What NUSMods actually does (the reference, decoded)

Not "copy the look" — copy the *decisions*:

- **System font stack**, not a web font. Fast, native, invisible. (Fixes V2.)
- **High information density.** Tight, consistent padding; a timetable/planner shows a lot at once.
  The planner lists modules compactly with code + title + MC, color-coded by type. (Fixes V8.)
- **Restrained palette:** one brand accent (NUSMods red/orange ~`#ff5138`), a neutral gray ramp, and
  *muted, low-saturation* module-type colors chosen for contrast — not a rainbow. (Informs §3.)
- **Color + text, always.** Module type is shown by color *and* label; color is never the only signal.
  (Fixes V6.)
- **Minimal chrome.** Flat surfaces, hairline borders, almost no shadow, modest radius (~4–6px). A card
  is used only to group genuinely distinct regions — not around every list item. (Fixes V3.)
- **Functional, neutral copy.** Labels, not marketing. (Fixes V5.)
- **Icons are a consistent line-icon set** (or none) — never emoji. (Fixes V1.)

---

## 3. Design principles & tokens (the system to build against)

### 3.1 Principles
1. **Density over air.** This is an advising tool; the user wants to see the whole plan + whether each
   requirement is met, at once. Default to compact.
2. **One accent, earned.** The red/orange accent marks exactly one thing per view (the primary verdict
   / brand), nothing else competes.
3. **Color + label, never color alone.** Every category cell carries its code/name; color is a
   secondary cue aligned to a documented taxonomy.
4. **A real scale, no magic numbers.** All spacing/type pulls from the tokens below.
5. **Flat and quiet.** Hairline borders, ≤1 subtle shadow reserved for the single elevated surface,
   radius 6px standard / 4px on dense cells. No 999px pills except a genuine status tag.

### 3.2 Tokens (define once as CSS variables; replace every magic number)
```
/* spacing — 4px base scale */   --s1:4px --s2:8px --s3:12px --s4:16px --s5:24px --s6:32px
/* type scale */                 --t-xs:11px --t-sm:12px --t-md:13px --t-lg:15px --t-xl:19px --t-2xl:24px
/* weights (3 only) */           --w-reg:400 --w-med:500 --w-bold:700
/* neutral ramp */               --n0:#fff --n50:#f7f8fa --n100:#eef0f2 --n200:#e2e5e9
                                 --n400:#9aa0a7 --n600:#5c636c --n800:#2a2d31 --n900:#17191c
/* accent (brand/verdict only) */ --accent:#ff5138  --accent-weak:#fff1ee
/* semantic */                   --ok:#1a7a46 --ok-bg:#edf6ef  --no:#c0392b --no-bg:#fbeeee
/* font */  --font: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif
```
System font stack — **delete the Google-font `@import`.**

### 3.3 Category color taxonomy (muted, AA-contrast, documented)
Keep the pillar→color map but (a) lower saturation to NUSMods-muted levels, (b) verify each bar/bg
pair meets WCAG AA for the text on it, (c) ensure every plan cell renders **code + title + MC + pillar
name**, so color is redundant. The existing `PILLAR_BAR`/`PILLAR_BG` + `LEGEND` are the right *idea*;
they need the saturation + contrast pass and the in-cell label.

---

## 4. Component inventory (what the screen is made of)

| Component | Redesign note |
|---|---|
| **Left config rail** | Keep the profile picker + three expanders. Replace emoji section headers with plain labels + a single consistent icon set (or none). Group logically: *Student · Goal · Workload*. |
| **Profile summary** | Replace the emoji-chip wall with a compact **key-value strip** (label: value), grouped Student / Goal / Workload. Text-first; a small category dot is allowed, emoji are not. Drop facts already shown in the requirement tracker (fix V10). |
| **Verdict** | Demote from a large colored block to a **slim status bar**: one line — ✓/✗ glyph + "Can graduate in N semesters · 160 MC" + the checker line inline. Accent/semantic color as a left border, not a full fill. (Fixes V8.) |
| **Study plan grid** | Keep the year-grouped aligned columns (this part is already NUSMods-shaped). Tighten padding to the token scale; reduce radius to 6px; each cell = code (bold) + title + MC + a 3px category bar. Keep the legend but make it the single source of the color taxonomy. |
| **Requirement tracker** | Keep the met/not-met list but make it a **progress-oriented** panel: each bucket shows `X / Y MC` with a thin progress bar, not just a Met/Not-met pill. This is the highest-value view for an advisee and currently the weakest. |
| **Legend** | One row, muted swatches + labels; it defines the taxonomy used everywhere. |

---

## 5. Concrete remediation plan (mapped to `app/app.py`)

Ordered by impact-to-effort. Each is a discrete, testable change; the 3 AppTest smoke tests
(`tests/test_app.py`) must stay green throughout.

1. **Kill the web font (V2).** Remove the `@import` line; set `--font` to the system stack; apply via
   `.stApp`. *(1-line win, removes the biggest "AI-template" tell.)*
2. **Introduce tokens (V4).** Add the `:root` variables from §3.2; replace magic numbers in `CSS`
   progressively. Start with spacing + type on the plan grid and cards.
3. **De-emoji the chips (V1, V9).** Rewrite `constraint_chips()` → a `summary_strip()` of
   `label: value` rows under three documented groups (Student / Goal / Workload). Keep meaning, drop
   emoji. Update the `test_app` assertions that currently look for e.g. "Special Term" text (keep a
   plain-text "Special Term" label so the test still passes).
4. **Slim the verdict (V5, V8).** Replace the big `.verdict` block + hero with a one-line status bar +
   a neutral tool title ("CanIGraduate — NUS CS degree planner"). Keep the checker line inline.
5. **Flatten the card soup (V3).** Reduce radius to 6px (4px on cells); remove borders/shadows from
   list items (`.req`, `.chip`); keep a single bordered surface per region (plan, tracker).
6. **Label every cell (V6).** In `cell()`, add the pillar name; verify contrast on `PILLAR_BG`/`BAR`.
7. **Upgrade the requirement tracker.** Add `X / Y MC` + a thin progress bar per bucket in
   `requirement_sections()` rendering; this is the most useful advisee view.
8. **De-dup (V10).** Drop from the summary strip any fact the tracker already shows.

### Accessibility acceptance criteria (gate the redesign)
- All text ≥ WCAG **AA** contrast against its background (check every `PILLAR_BG` + text pair).
- No information conveyed by color alone (every category cell has a text label).
- Keyboard focus states visible on all controls (don't suppress Streamlit's defaults).
- Readable at 320px-narrow sidebar without horizontal scroll.

---

## 6. Explicit non-goals (so the redesign stays disciplined)
- **No timetable/clash view** — out of scope per `iter3_plan.md`; this is a degree planner, not NUSMods'
  timetable.
- **No dark mode, no theming toggle, no animation** — quiet and flat is the brief.
- **No new dependencies / no JS components** — stay within Streamlit + scoped CSS (the earlier
  `[class*="st-"]` CSS corruption bug is why: scope to `.stApp` and our own class names only).
- **No marketing surfaces** — no hero, no "AI-powered" badge, no onboarding modal.

---

## 6b. Status — reworked 2026-10-20 (verified)
Plan verified against the then-current `app/app.py` (web-font import line 80, 19 emoji, two `999px`
pills, the "Can I graduate?" hero all confirmed present), then remediated. After the rework:
web-font imports **0**, functional-UI emoji **0** (incl. ✓/✗ glyphs), `999px` pills **0**, marketing
hero **0**. Applied: system-font stack + `:root` design tokens (V2/V4); de-emojied **key-value
summary strip** grouped Student/Goal/Workload (V1/V9/V10); **slim status bar** with left-border accent
replacing the big coloured block + neutral "Degree plan" title (V5/V8); flat 6px/4px cards, hairline
borders, list items unboxed (V3); every plan cell now labels its **pillar** alongside colour (V6);
requirement tracker shows **X/Y progress bars** (upgrade); and the new **plan-reasonableness score +
advisor notes** surfaced from `src/plan_quality.py`. All 3 AppTest smoke tests green; full suite 173.

## 8. v2 redesign — student-first, minimal copy (2026-10-20)
v1 fixed the vibe-coded *style* but left two product problems: it is **too wordy** (explanatory
sentences nobody reads) and the **benchmark picker is primitive** (a radio list of internal names).
v2 makes the *student the hero object* and strips copy to near-zero.

### 8.1 Kill the filler copy (explicit removals)
- Page sub-title *"A constraint-solver planner for NUS Computer Science. Every plan is re-validated by
  an independent checker and scored for reasonableness."* → **delete**. The product shows this; it
  doesn't need to narrate it.
- Sidebar caption *"Pick a student, then fine-tune below…"* → **delete**.
- Verdict prose *"this degree can be completed — 10 semesters · 160 MC · focus: …"* → **replace** with
  stat tiles (8.3). Keep the literal phrase "can be completed" only as an aria/again-invisible anchor
  if tests need it, not as a sentence.
- Sub-line *"Plan reasonableness 94/100 · verified by the independent checker"* → **replace** with a
  reasonableness tile + a small `✓ Validated` pill (no sentence).
- The profile description paragraph moves *onto the card* as one short line, not a block.

### 8.2 The STUDENT CARD (replaces the radio list + the key-value strip)
One elegant card is both the selector surface and the summary — consolidating two primitive widgets
into the hero object:
- **Monogram/accent** + **archetype title** (e.g. "Honours track — dissertation").
- **One human line** ("GPA-eligible, wants a dissertation instead of an internship, one exchange sem").
- **3 compact attribute columns** — *Background* (standing / entry path / credits), *Goal* (horizon /
  focus / experience), *Calendar* (exchange / special term / load) — each a 1–3 word value, no labels
  longer than the value. This is the old strip, redesigned as a card, with the wordiest rows dropped.
- The card is the thing you *switch* (8.4), so selection and summary are the same affordance.

### 8.3 Verdict as STAT TILES (replaces the wordy status line)
A dashboard-style KPI row — glanceable, no prose:
`[ 10 semesters ] [ 160 MC ] [ 15 CS modules ] [ Valid ]`.
Infeasible → one red tile `[ No valid plan ]` + a single short reason line (the one place a sentence
earns its place). **The plan-reasonableness score is NOT shown in the app** (user found the 0–100
number confusing; it stays an `eval/`-side research metric only — D32). Advisor notes removed too.

### 8.4 Switching students — THE fork (see the question for previews)
Three candidate affordances; pick one in the question below. All keep the fine-tune expanders for
power users, collapsed by default.

### 8.4b Per-semester load editor — multiple light AND heavy semesters
v1's single "exchange" + single "light" dropdowns are too limited. The model already stores an
arbitrary `per_semester_cap: {s: cap}` (I2.15), so the UI should expose it directly:
- A **compact per-semester load row** (one control per plan semester 1..T). Each semester picks a
  level: **Blocked (0)** · **Light (≤12)** · **Normal** (= the global cap) · **Heavy / overload**
  (above the global cap, up to the 28 MC ceiling). Any number of each is allowed.
- Mechanism: *Blocked* → `per_semester_cap[s]=0`; *Light* → a low value; *Heavy* → a value above the
  global cap; *Normal* → omit the key. This is a pure data mapping — no solver/checker change.
- Replaces both the `exchange` and `light` selectboxes with one honest editor (and keeps `seed_from_
  profile` working by reading the whole `per_semester_cap` dict instead of guessing one light + one
  exchange).

### 8.4c Indicate heavier / lighter semesters in the plan grid (output)
Each semester header gets a small **load indicator**: a thin bar (load ÷ effective cap) + a one-word
tag only when notable — **Heavy** (≥ ~24 MC or at an overload cap), **Light** (≤ ~12 MC), nothing for
normal. Colour follows the one-accent rule (heavy = accent, light = muted); never colour-only — the
tag text carries it. This reuses the data `plan_quality` already computes (it flags very heavy / very
light semesters), so input intent and output reality are shown in the same vocabulary.

### 8.5 Layout
`sidebar: brand + student selector (+ collapsed fine-tune)  |  main: student card → stat tiles →
(plan grid  |  requirements)`. Same grid/tracker as v1 (those work); the change is the card, the
tiles, and the copy diet.

### 8.6 Streamlit feasibility
Dropdown = `st.selectbox` (native, trivial). Card gallery = `st.columns` + one `st.button` per card
(works; keep ≤ a scrollable grid since there are ~19 profiles). Carousel = `st.button` ◀ ▶ over an
index in `session_state` (works; no true swipe — native Streamlit has no gesture, so "swipe" = prev/
next). Test contract preserved: keep widget keys (`profile_name`, `want_fyp`, `specials`, …) and the
strings the AppTest asserts ("can be completed", "No valid plan", "Special Term", "CP4101").

## 7. Definition of done
- Anti-pattern checklist §1: V1–V6, V8–V10 all resolved (web font gone, tokens in, emoji gone from
  functional UI, verdict slimmed, cards flattened, cells labelled, tracker shows progress, no dup).
- NUSMods decisions §2 all reflected (system font, density, restrained palette, color+label, minimal
  chrome, neutral copy).
- Accessibility criteria §5 met.
- `tests/test_app.py` (3 AppTest smoke tests) green; add assertions for the new plain-text labels so
  the de-emoji'd UI is regression-guarded.
