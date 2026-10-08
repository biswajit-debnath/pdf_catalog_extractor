# Project rules for coding agents

## Always research and plan before changing anything
For ANY change (new feature, bug fix, refactor, dependency change), even if the prompt says "just implement it":
1. Research first. Check current docs and versions of any library or API involved. Don't rely on memory.
2. Write a plan doc in `docs/` (e.g. `docs/partN-plan.md` or `docs/change-<topic>.md`) with: research findings, the work split into small segments (goal, approach, expected output, verification, size), edge cases handled and not handled, open questions.
3. Stop and wait for approval before writing implementation code. Only skip this if the user explicitly says "skip the plan" for that specific task.
4. Exception: trivial edits (typos, comments, formatting) need no plan.

## Implementation rules
- One segment at a time, in plan order. After each segment, run it on the sample data, show real output, and state pass/fail. Don't continue on failure.
- Add tests as you go. Keep the plan doc in sync with what was actually built.
- Keep it simple: plain functions and dicts or dataclasses, minimal dependencies, hand-editable JSON, no frameworks or clever abstractions.
- Deterministic code first; LLM calls only where a later part explicitly requires them.
- Never commit client PDFs, extracted images, output folders or API keys. Tests use only the synthetic fixtures in `tests/fixtures/`. Real sample PDFs stay local and gitignored.
- Every page ends in exactly one state: saved, saved with flags, review, or skipped with a reason. Nothing disappears silently.
