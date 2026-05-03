---
trigger: always_on
---

# Red-Green-Refactor Testing

You MUST follow strict Test-Driven Development (TDD) for all code changes that add or modify behavior. Do not write or modify implementation code before a failing test exists for it.

## The Cycle

For every unit of behavior, follow this loop and do not skip steps:

### 1. RED — Write a failing test first
- Write the smallest possible test that captures the next bit of desired behavior.
- Run the test and **confirm it fails**. Show the failing output before proceeding.
- The failure must be for the *right reason* (assertion failure or missing symbol the test is designed to drive out) — not an unrelated error like a typo, import error, or missing fixture. If it fails for the wrong reason, fix the test before moving on.
- If the test passes immediately, the test is wrong or the behavior already exists. Stop and reassess; do not proceed to step 2.

### 2. GREEN — Write the minimum code to pass
- Implement only enough production code to make the failing test pass. No extra features, no speculative abstractions, no unrelated cleanup.
- Run the test and **confirm it passes**. Also run the full existing test suite and confirm nothing else broke. Show the passing output before proceeding.
- If you find yourself wanting to add code not driven by a test, stop and write another failing test first (back to step 1).

### 3. REFACTOR — Improve the code with the safety net
- With all tests green, improve the design: rename, extract, deduplicate, simplify.
- Do not change behavior during refactor. No new tests should be needed.
- Run the full test suite after each meaningful refactor step and confirm it stays green.

## Hard Rules

- **Never** write production code without a failing test that requires it.
- **Never** modify a test and its corresponding production code in the same step. Tests and implementation change in separate, clearly-labeled steps.
- **Never** comment out, skip, weaken, or delete a test to get to green. If a test is wrong, fix it deliberately as a Red step and explain why.
- **Never** batch multiple behaviors into one Red step. One failing test at a time.
- **Always** show the actual test runner output (failing, then passing) at each transition. Do not paraphrase or claim a result without running the tests.

## Reporting Format

When working on a task, label your steps explicitly so I can follow the cycle:

    [RED] Adding test: <name> — expected to fail because <reason>
    <run output showing failure>

    [GREEN] Implementing: <minimal change>
    <run output showing pass + full suite pass>

    [REFACTOR] <what changed and why>
    <run output showing suite still green>

## When Tests Don't Apply

- Pure refactors of already-tested code: skip Red, but the existing suite must stay green throughout.
- Config, docs, and trivial formatting changes: no test required, state explicitly that the change is non-behavioral.
- Exploratory spikes: allowed, but the spike code must be deleted and rebuilt under TDD before being committed.