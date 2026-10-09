---
name: code-review-agent
description: Review changes in this Bible reader with an independent code-review agent. Use for requested code reviews or an independent review before a PR; routine implementation alone does not require this workflow.
---

# Code-review agent

Produce actionable findings against the requested change, grounded in the diff,
repository contracts, and observed behavior. This skill does not authorize merging,
publishing, or posting reviews to GitHub.

Establish the review scope from the user's request: a working-tree diff, commit
range, or PR. Read `AGENTS.md` and only the documents relevant to that scope.
Include untracked implementation files when reviewing local changes. Record the
base and head, or identify the working-tree snapshot, so findings are traceable.

When coordinating a review and agent delegation is available, spawn one independent reviewer with the
review scope, the user's requested behavior, and this skill's path. Ask it to
inspect the diff and surrounding code without editing files or posting reviews.
Read-only external access stays within the authorized review scope. Avoid supplying
the author's expected findings or conclusion. A delegated reviewer performs the
review directly, without spawning another reviewer. If delegation is unavailable,
review directly and disclose that limitation.

Focus the review on concrete failures introduced by the change. For this reader,
follow affected paths across project validation, saved settings, immutable job
snapshots, source fidelity, note identity, measurement, and final rendering.
Consult the relevant source/alignment/typesetting skill when that boundary is
affected. Layout findings need compiled PDF evidence when feasible; string checks
alone do not establish correct RTL positioning or page-local note placement.
Use attributable fixtures; the synthetic demo is not evidence of biblical content.

Run focused checks when they can resolve a suspected issue, using fresh ignored
output directories. Keep pre-existing issues and unavailable prerequisites
distinct from regressions. Do not invent findings to fill a quota or expand the
review into unrelated refactoring.

Report findings in severity order. Each finding should name a precise file and
line, the triggering input or action, the resulting failure, and supporting
evidence. Suggest a correction when useful. If there are no actionable findings,
say so and identify material gaps in verification. State which checks actually ran.

The implementing agent assesses findings against the user's intent, fixes supported
issues within the authorized task, and reruns affected checks. The reviewer remains
read-only; the implementing agent retains responsibility for edits and PR actions.
