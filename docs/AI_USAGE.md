# AI Usage Disclosure

Required by the iWISE rules: every AI tool, how it was used, which components it influenced, and how the team verified the output.
Add a row every time an AI tool contributes to code, data, text or design. "Verified by" must be a team member who can explain the result.

| Date | Tool / model | Used by | Purpose | Components affected | Verification by the team | Verified by |
|---|---|---|---|---|---|---|
| 2026-10-21 | Claude Code (Claude Opus 5.5) | | Analysis of the 25 challenges and choice of Challenge 4 | Project direction | Team read the official challenge text and rules | |
| 2026-10-21 | Claude Code (Claude Opus 5.5) | | Project roadmap and phase plan | Planning | Team reviewed the timeline and scope | |
| 2026-10-21 | Claude Code (Claude Opus 5.5) | | Project scaffold, unified data schema and its unit tests | `src/truth_guardian/schema.py`, `tests/test_schema.py` | Ran `uv run pytest` (11 passed); team to walk through every validator | |

## Work done directly by the team

Fill in per member as the project progresses.

## Known limitations and risks of AI-generated parts

Fill in as they are found.
