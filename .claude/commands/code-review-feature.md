---
description: Runs parallel security and quality code review for a specific FinCheck feature. Pass the spec name as an argument e.g. /code-review-feature 05-dashboard-backend
allowed-tools: Bash(git diff), Bash(git diff --staged)
---

Run the full code review pipeline for the feature specified in $ARGUMENTS.

If no argument is provided, stop immediately and say:
"Please provide a spec name. Usage: `/code-review-feature <spec-name>` e.g. `/code-review-feature 05-dashboard-backend`"

If the spec file at `.claude/specs/$ARGUMENTS.md` (or `specs/$ARGUMENTS.md`) does not exist, stop immediately and say:
"Spec file not found for $ARGUMENTS. Please check the spec name and try again."

## Pre-flight Check

Before invoking any subagents, collect the diff of the recent work:
- Run `git diff` for unstaged changes.
- Run `git diff --staged` for staged changes.
- Combine both into a single diff string.

If both are empty, stop immediately and say:
"No changes detected. Implement the feature or stage/save your files before running the code review."

---

## Step 1: Parallel Review

Invoke both subagents simultaneously with the exact same context. Do not wait for one to finish before starting the other.

**fincheck-security-reviewer** receives:
- The combined git diff.
- Spec file for context: `.claude/specs/$ARGUMENTS.md`
- Source files to reference: `app.py`, `database/services.py`, and `database/schemas.py`.
- Instruction: Review only the changed code for security vulnerabilities (focusing on IDOR, HTMX XSS, and missing CSRF/Validation). Do not comment on quality, layout, or style.

**fincheck-quality-reviewer** receives:
- The combined git diff.
- Spec file for context: `.claude/specs/$ARGUMENTS.md`
- Source files to reference: `app.py`, `database/services.py`, `database/schemas.py`, and the `templates/` directory.
- Instruction: Review only the changed code for quality, algorithmic performance (N+1 queries), and strict adherence to the FinCheck stack (SQLAlchemy 2.0, Tailwind, Alpine, Decimal discipline). Do not comment on security concerns.

---

## Step 2: Unified Report

Once both subagents have completed, combine their findings into a single unified report. De-duplicate any overlapping findings — if both agents flagged the exact same line, merge them into one bullet point with both the security and quality perspectives noted.

Structure the combined report exactly as follows:

```markdown
## 🔍 Code Review Report — `$ARGUMENTS`

### 🛡️ Security Findings
[Insert fincheck-security-reviewer agent output here]

### 💎 Quality & Architecture Findings
[Insert fincheck-quality-reviewer agent output here]

---

### 📋 Combined Action Plan
*Ordered checklist of everything that needs to be fixed, prioritized by severity:*

1. **[CRITICAL]** [High security findings or N+1 Performance bugs]
2. **[CHANGES REQUESTED]** [Quality items that violate project architecture]
3. **[SUGGESTION]** [Medium/Low security findings or Python nits]
4. **[POLISH]** [Minor Tailwind/Jinja/PEP8 suggestions]

---

### ⚖️ Overall Verdict
**[Select ONE of the following]**
- ✅ **APPROVED** — Ready to commit. No blocking issues found.
- 🟡 **APPROVED WITH SUGGESTIONS** — Can commit, but consider addressing the [SUGGESTION] and [POLISH] items.
- ❌ **CHANGES REQUESTED** — Must fix before committing. See the [CRITICAL] and [CHANGES REQUESTED] items in the action plan above.