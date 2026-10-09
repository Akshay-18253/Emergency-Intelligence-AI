## Summary of Changes
Provide a brief summary of what this pull request introduces, fixes, or refactors.

## Motivation & Context
- Why is this change required? What issue or milestone does it address?
- Relevant issue number: Closes #`<issue_number>` (if applicable)

## Engineering Discipline Checklist
Before requesting review, please confirm all requirements are met:

- [ ] **Zero Runtime Dependencies:** No external third-party dependencies have been added to `src/emergency_intelligence/` (Python standard library only).
- [ ] **Strict Typing:** All new functions, parameters, and return types are fully type-annotated (`typing`).
- [ ] **Comprehensive Tests:** New unit tests have been added in `tests/` covering new features and edge cases.
- [ ] **Coverage Gate:** `pytest` passes with $\ge 90\%$ code coverage across all branches (current target: $\ge 95\%$).
- [ ] **Pre-Flight Sanity:** Ran `python scripts/check.py` with zero errors.
- [ ] **Deterministic Tests:** Tests run offline with no external network requests or unseeded randomness.
- [ ] **Demonstration Tested:** Verified that all scripts in `examples/` run without errors or crashes.
- [ ] **Documentation Updated:** Updated `docs/` and `README.md` if public API or architecture changed.

## Verification Output
Paste the output summary of running `python scripts/check.py` or `pytest`:

```text
<paste terminal test output here>
```
