---
description: Writes and runs spec-driven pytest suites for a specific FinCheck feature. Pass the spec name as an argument e.g. /test-feature 05-dashboard-backend
allowed-tools: Bash(pytest)
---

Run the full testing pipeline for the feature specified in $ARGUMENTS.

If no argument is provided, stop immediately and say:
"Please provide a spec name. Usage: `/test-feature <spec-name>` e.g. `/test-feature 05-dashboard-backend`"

If `.claude/specs/$ARGUMENTS.md` (or `specs/$ARGUMENTS.md`) does not exist, stop immediately and say:
"Spec file not found for $ARGUMENTS. Please check the spec name and try again."

---

## Step 1: Write Tests

Invoke the **fincheck-qa-agent** (Test Writer) subagent with the following context:

- **Spec file to base tests on**: `.claude/specs/$ARGUMENTS.md` (or `specs/$ARGUMENTS.md`)
- **Source files to read for structure**: `tests/conftest.py` (for existing fixtures), `app.py`, and the `database/` directory.
- **Output test file to create**: `tests/test_$ARGUMENTS.py` (format the filename to standard python snake_case, e.g., `test_dashboard_backend.py`).
- **Instruction**: Write tests based strictly on what the spec says the feature SHOULD do. Do NOT derive test logic from reading the implementation. Ensure your suite explicitly covers:
  - Happy paths & Empty States
  - HTMX reactivity (asserting partial HTML responses and `HX-` headers)
  - Auth guards & user data isolation
  - `Decimal` type discipline and `ZoneInfo("Asia/Kolkata")` timezone constraints.

Wait for `fincheck-qa-agent` to fully complete and confirm the test file has been written before proceeding to Step 2.

---

## Step 2: Run Tests

Once the test writer has finished, invoke the **fincheck-test-runner** subagent with the following context:

- **Test file to execute**: The exact file created in Step 1.
- **Spec file for context**: `.claude/specs/$ARGUMENTS.md` (or `specs/$ARGUMENTS.md`)
- **Run command**: `pytest <path_to_new_test_file> -v --tb=short`
- **Instruction**: Run ONLY the newly created test file. Do NOT run the full test suite. 
- **Analysis constraints**: Analyze any failures by cross-referencing the test code, the spec, and the source files. Focus ONLY on the top 2-3 root causes if there is a cascade of failures. Flag any architectural violations (e.g., float casting, raw SQL f-strings, missing HTMX logic).

---

## Handoff Rules

- Do NOT start Step 2 until Step 1 is fully complete and the file is saved to disk.
- Do NOT attempt to fix or modify any application code yourself, regardless of what the test results show. Your job is reporting.
- Do NOT run any tests beyond the specific feature test file.
- If `fincheck-qa-agent` reports it could not write the test file (e.g., missing dependencies or missing spec), stop and report the reason — do NOT proceed to Step 2.

---

## Final Output

After both subagents complete, produce a combined summary formatted exactly like this:

### 🧪 Testing Pipeline Report — `$ARGUMENTS`

**Step 1 — Tests Written**
*Provide a concise bulleted list of the tests that were generated, with a 5-10 word description of which spec requirement each validates.*

**Step 2 — Test Results**
*Mirror the `fincheck-test-runner`'s structured report (Summary table, Root Causes for failures, and Architecture Flags).*

**Verdict**
*Must be one of:*
- ✅ **Ready for code review** — All tests pass and align with FinCheck architecture.
- ❌ **Needs fixes** — List the specific files and lines the developer needs to fix based on the runner's analysis.