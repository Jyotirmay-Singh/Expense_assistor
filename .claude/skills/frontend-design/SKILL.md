---
name: spendly-ui-designer
description: Designs and generates modern, production-ready UI for Spendly, a personal expense tracker built (repo - https://github.com/Jyotirmay-Singh/Expense_assistor). Produces clean fintech-style pages and components - cards, forms, tables, dashboards, modals, charts - with consistent spacing, soft shadows, rounded corners, Lucide icons, and lightweight interactivity via HTMX, Alpine.js, and Chart.js. Use this skill whenever the user asks to design, build, create, redesign, improve, or style any Spendly page, screen, section, or component - including phrasings like "design the X page", "create UI for X", "build a component for X", "make the X look better", "redesign X", "add a chart to X", "make X interactive", or any request about Spendly's frontend, layout, CSS, charts, or visual polish - even when Spendly isn't named explicitly if the conversation context is clearly about it.
metadata:
  disable-model-invocation: true
---

# Spendly UI Designer

You are designing frontend UI for **Spendly**, a personal expense tracker. Spendly is a Flask app with server-rendered Jinja2 templates, vanilla CSS, and lightweight interactivity layered on top. The goal of this skill is to help you generate UI that feels like it belongs in a polished, modern fintech product - not generic bootstrap-era output, and not a React/Tailwind rewrite that doesn't match the stack.

## What Spendly's stack looks like

- **Backend:** Flask (`app.py`), SQLite or similar (`database/`)
- **Templates:** Jinja2 in `templates/` (e.g. `base.html`, `dashboard.html`, `add_expense.html`)
- **Styles:** vanilla CSS in `static/css/` - no Tailwind, no CSS-in-JS, no preprocessors assumed
- **Icons:** Lucide, loaded via CDN, used as `<i data-lucide="icon-name">` and initialized with `lucide.createIcons()`
- **Interactivity (the modern part):** three small, framework-free libraries, each with a clear job:
  - **HTMX** — server-driven updates (form submits, live search, inline edit, delete, pagination) by swapping HTML fragments returned from Flask. No custom JS, no JSON plumbing.
  - **Alpine.js** — purely client-side UI state (open/close a modal, toggle a dropdown, switch tabs, dismiss a toast). The modern replacement for the old "sprinkle of vanilla JS."
  - **Chart.js** — dashboard visualizations (category donut, spend-over-time line, income-vs-expense bars).

This trio is the idiomatic 2026 way to make a server-rendered Flask app feel interactive *without* adopting a SPA framework. It keeps the app's center of gravity in Python and HTML, which is exactly where Spendly wants it.

**Do not introduce React, Vue, Svelte, Tailwind, shadcn, Bootstrap, or styled-components** unless the user explicitly asks for a migration. HTMX/Alpine/Chart.js are additive sprinkles, not a framework swap.

## When to reach for which tool (read this before writing JS)

The most common mistake is using the wrong layer - e.g. hand-rolling a `fetch()` when HTMX would do it in one attribute, or spinning up an HTMX round-trip for something that never needed the server. Use this split:

| You want to... | Use | Why |
|---|---|---|
| Submit a form / add/edit/delete a record and update the page | **HTMX** | The server already knows how to render the row/card. Return the fragment, swap it in. |
| Live-search a transaction list as the user types | **HTMX** (`hx-trigger="keyup changed delay:300ms"`) | Filtering needs the database; let Flask do it and return `<tr>`s. |
| Load more / paginate / infinite scroll | **HTMX** | Server renders the next page of fragments. |
| Open/close a modal, dropdown, or accordion | **Alpine.js** (`x-data`, `x-show`) | Pure UI state. No server, no round-trip. |
| Switch tabs, toggle a "show details" panel, password visibility | **Alpine.js** | Same - client-only state. |
| Show/auto-dismiss a toast or flash message | **Alpine.js** (`x-init` + `setTimeout`) | Ephemeral UI. |
| Draw a chart from data passed by the route | **Chart.js** | Canvas-based, themed to the Spendly palette. |
| A one-off tiny DOM tweak with no state | plain vanilla JS | Don't pull in a library for `el.classList.toggle()`. |

Rule of thumb: **HTMX owns server state, Alpine owns client state, Chart.js owns data viz.** If a feature touches the database, it's HTMX. If it's just showing/hiding/animating something already on the page, it's Alpine.

For concrete, copy-ready recipes, read the reference file for the tool you're using:
- `references/htmx-patterns.md` — live search, inline edit, delete-with-confirm, form submit + swap, infinite scroll, plus the Flask side (detecting `HX-Request`, rendering partials)
- `references/alpinejs-patterns.md` — modal, dropdown, tabs, toast, multi-step form, click-outside
- `references/chartjs-patterns.md` — category donut, spend-trend line, income-vs-expense bar, and how to theme charts to Spendly's colors

Don't dump the whole reference into your answer - pull the one pattern you need and adapt it.

## Loading the libraries in base.html

Pin versions for stability (don't ship `@latest` to production - it can change under you). These are the current stable majors; bump the patch as needed:

```html
{# templates/base.html - inside <head> #}

{# Alpine.js - MUST have defer. Owns client-side UI state. #}
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.15.12/dist/cdn.min.js"></script>

{# Lucide icons - pinned, not @latest #}
<script src="https://unpkg.com/lucide@1.16.0"></script>

{# Chart.js - only on pages that actually render a chart (e.g. dashboard). #}
{# Load WITHOUT defer so `Chart` is defined before your init script runs. #}
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
```

```html
{# templates/base.html - just before </body> #}

{# HTMX - owns server-driven updates. #}
<script src="https://unpkg.com/htmx.org@2.0.9"></script>

{# Initialize Lucide after the DOM exists, and again after any HTMX swap #}
<script>
  lucide.createIcons();
  document.body.addEventListener('htmx:afterSwap', () => lucide.createIcons());
</script>
```

Two gotchas worth knowing:
- **Alpine needs `defer`.** Without it Alpine initializes before the DOM is ready and `x-data` silently does nothing.
- **Don't put Chart.js behind `defer` in the same block that defers Alpine** - if your chart init script runs before a deferred Chart.js finishes loading, you'll get `Chart is not defined`. Load Chart.js eagerly (no `defer`) on chart pages, then init in a script that runs after it.
- **Re-init Lucide after HTMX swaps.** When HTMX replaces part of the DOM, any new `<i data-lucide>` tags need `lucide.createIcons()` to run again - hence the `htmx:afterSwap` listener above.

## Before you design: check what already exists

If the user's project files are available (e.g. they've shared the repo, uploaded files, or you're inside the codebase), open `base.html`, the main CSS file, and one or two existing templates before generating anything new. The goal is *consistency* - Spendly should feel like one coherent product, not a collage.

Specifically, look for and reuse:

- **Color tokens** (CSS custom properties like `--color-primary`, `--color-bg`, `--color-surface`, etc.)
- **Spacing scale** (if there's a `--space-1`, `--space-2` pattern, use it)
- **Font family and type scale**
- **Existing component classes** - `.card`, `.btn`, `.input`, `.badge`, `.table`, etc.
- **The base layout** - sidebar? topbar? container width? Follow it.
- **Which libraries are already loaded** - check `base.html` for existing HTMX/Alpine/Chart.js/Lucide tags so you don't double-load them or load a conflicting version.

If you can't see the existing files and the request is non-trivial, ask the user to share a screenshot or paste a relevant template before you generate. One screenshot of the existing dashboard saves three rounds of revision.

## The Spendly design language

When you have no existing reference to follow, default to this. It's a clean, fintech-leaning aesthetic - close in spirit to Linear, Notion, or modern banking apps.

**Palette (defaults, override to match existing):**
- Background: very light neutral (`#F7F8FA` or near-white)
- Surface (cards): white (`#FFFFFF`) with a soft border (`#E5E7EB`) and/or tiny shadow
- Text: near-black for primary (`#111827`), muted gray for secondary (`#6B7280`)
- Primary accent: a single confident color - indigo/violet (`#6366F1`), emerald (`#10B981`), or similar. Pick one and stick with it.
- Semantic: green for income/positive (`#10B981`), red for expense/negative (`#EF4444`), amber for warnings (`#F59E0B`)

Define these as CSS custom properties so charts and components can share them (Chart.js can read them via `getComputedStyle` - see the chart reference).

**Spacing:** 8px grid. Use multiples of 4px or 8px for padding, gap, margin. Don't use arbitrary values like 13px or 27px.

**Radius:** `8px` for inputs and small elements, `12px` for cards, `16px` for modals. Pills/badges can be fully rounded.

**Shadows:** subtle only. A card shadow like `0 1px 2px rgba(0,0,0,0.04), 0 1px 3px rgba(0,0,0,0.06)` is the ceiling. No glows, no heavy drop shadows.

**Typography:** system font stack is fine (`-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`) or Inter if the project uses it. Type scale: 12 / 14 / 16 / 20 / 24 / 32. Font weights: 400 body, 500 medium, 600 semibold for headings. Numbers (amounts) should use tabular figures: `font-variant-numeric: tabular-nums`.

**Layout patterns:**
- Card-based composition - group related info in surfaces, don't sprawl
- Generous whitespace - tight layouts read as cluttered in finance apps
- Left-aligned content with clear hierarchy; centered layouts only for empty states and auth
- Tables: zebra stripes optional, but always have row hover, right-align numeric columns
- Forms: label above input, helper text below, error state in red with icon

## Icons: Lucide

Pinned load is shown in the base.html section above (use `@1.16.0`, not `@latest`). In templates, use:

```html
<i data-lucide="wallet"></i>
<i data-lucide="trending-up"></i>
<i data-lucide="plus"></i>
```

Call `lucide.createIcons()` after the DOM is ready **and after any dynamic DOM insert** - including HTMX swaps (the `htmx:afterSwap` listener in base.html handles this). If you build an Alpine component that injects icon markup conditionally, call `lucide.createIcons()` in its `x-init` too.

Size icons via CSS with `width`/`height` on the resulting `<svg>`, or wrap in a sized span. Prefer 16px inline with text, 20px for buttons, 24px for section headers.

Pick icons that carry meaning. A few Spendly-appropriate defaults:
- Expense/spend: `arrow-down-right`, `shopping-bag`, `credit-card`
- Income: `arrow-up-right`, `wallet`, `trending-up`
- Budget: `target`, `pie-chart`
- Category: `tag`, `folder`
- Add/new: `plus`, `plus-circle`
- Settings: `settings`, `sliders-horizontal`
- Date/time: `calendar`, `clock`
- Search: `search`, Filter: `filter`

One icon per button, one per section heading, one per table row action - that's usually the right density.

## Output structure

When fulfilling a design request, structure your response like this:

### 1. Short UI plan (2-5 bullets)
Name the key sections of the page/component and any notable UX decisions, **including which interactivity layer each piece uses** so the wiring is obvious. Keep it tight. Example: "Dashboard has 4 summary cards on top, a category donut (Chart.js), and a recent-transactions table with live search (HTMX, swaps `<tr>`s from `/transactions/search`). The 'add expense' button opens a modal (Alpine) whose form posts via HTMX and prepends the new row."

### 2. The code
- **Template file(s)** - full Jinja2 with `{% extends "base.html" %}` and a `{% block content %}` unless building `base.html` itself. Use Jinja control flow with sensible placeholder variable names the user can wire to their Flask route. When a feature uses HTMX, also show the **partial template** it swaps in (e.g. `templates/partials/_transaction_row.html`) and a one-line sketch of the Flask route that returns it.
- **CSS** - either a new file (e.g. `static/css/dashboard.css`) or additions to an existing stylesheet. Scope with a page/component class prefix (`.dashboard-...`, `.tx-table-...`) so styles don't leak.
- **JS** (only if needed) - for Alpine, prefer inline `x-data`/`x-show` attributes over separate files. For Chart.js, a small init script. Keep it readable; no frameworks.

Put each file in its own fenced code block with a clear header comment or path annotation like `{# templates/dashboard.html #}` or `/* static/css/dashboard.css */`.

### 3. Integration note (1-3 lines)
How to wire it up - which Flask route renders it, what variables/JSON the template expects, and any HTMX route that returns a partial. Call out if the route needs to branch on `request.headers.get("HX-Request")` to return a fragment vs. a full page. New Python dependency is almost always none (HTMX/Alpine/Chart.js are all client-side CDN scripts); mention only the optional `jinja-partials` / `htmx-flask` helpers if they'd genuinely simplify things.

## What to avoid

- **Generic/dated looks** - no `<h1>Welcome to My App</h1>` with default browser styles, no sharp-cornered bordered boxes, no 2012-era bootstrap cards.
- **Reaching for a framework** - no React/Vue/Tailwind/Bootstrap. The HTMX/Alpine/Chart.js trio covers the interactivity Spendly needs.
- **Wrong-layer interactivity** - don't hand-write `fetch()` + DOM manipulation when HTMX does it declaratively; don't make a server round-trip (HTMX) for something that's pure client state (Alpine). See the "when to reach for which" table.
- **Over-charting** - one or two charts per dashboard, max. A donut and a trend line tell the story; five charts is noise. Always label axes and use the semantic palette (red = expense, green = income).
- **Forgetting to re-init after swaps** - new Lucide icons / charts inside an HTMX-swapped fragment won't render unless you re-run their init. Account for it.
- **Code dumps without structure** - always separate template, partial, CSS, and JS into labeled blocks.
- **Over-styling** - solid color over gradient, border over shadow when it'll do. Restraint reads as quality.
- **Inconsistent spacing** - if you used 16px for card padding once, use 16px next time. No 14px here, 18px there.
- **Random color accents** - one primary accent, semantic colors for meaning, everything else neutral.
- **Mobile afterthought** - stack cards vertically and make tables horizontally scrollable below ~768px. Charts should set `responsive: true, maintainAspectRatio: false` and live in a sized container.

## Handling ambiguity

If the user asks for something under-specified ("design the reports page"), make reasonable assumptions and *state them up front* in the UI plan - one line each, no long preamble. For example: "Assuming reports page shows: monthly spend trend (line chart), top categories (donut), and a downloadable CSV. Let me know if you want different widgets."

Don't pepper the user with clarifying questions for things you can reasonably decide. Do ask when the answer genuinely changes the output - e.g. "Is this a standalone page or a modal on top of the dashboard?" or "Should the search filter live (HTMX) or just on submit?"

## A worked example of the right vibe

**Request:** "Design the add expense form"

**UI plan:**
- Modal dialog (not a full page) - users add expenses inline from the dashboard. Open/close state is **Alpine** (`x-data="{ open: false }"`), so no server round-trip just to show the form.
- Fields: amount (large, prominent, currency-prefixed, `tabular-nums`), category (pill selector), date (defaults to today), note (optional)
- Submit posts via **HTMX** (`hx-post="/expenses"`) and the route returns the new transaction row partial, which HTMX **prepends** to the table (`hx-target="#tx-rows" hx-swap="afterbegin"`). On success the modal closes via an `HX-Trigger` event Alpine listens for.
- Primary action "Add expense" anchors bottom-right; cancel is a subtle text button.

**Template:** `templates/partials/add_expense_modal.html` - included via `{% include %}`. Alpine wraps the overlay; the `<form>` carries the `hx-post`/`hx-target`. Reuses existing `.input`, `.btn-primary`, `.modal` classes.

**Partial:** `templates/partials/_transaction_row.html` - the single `<tr>` the route renders and HTMX swaps in. Reused by both the initial table render (`{% for tx in transactions %}{% include %}{% endfor %}`) and the add route, so there's one source of truth for a row.

**CSS:** additions to `static/css/components.css` for the pill selector; reuses existing `.modal` overlay styles.

**JS:** none beyond the inline Alpine attributes - HTMX handles the submit declaratively.

That's the shape - concrete, consistent with the stack, visually restrained, immediately usable, and interactive without a single line of framework code. For the exact attribute syntax, pull the relevant pattern from the reference files.