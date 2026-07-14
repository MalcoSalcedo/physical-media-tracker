# Development workflow

This is a solo hobby project, but it follows a normal team workflow anyway —
it keeps the commit history reviewable and the repo believable as portfolio
evidence of process.

- `main` is the protected, always-deployable branch. No direct commits once
  Phase 1 code lands — everything goes through a PR, even solo.
- Feature branches are named `feat/<short-description>` (e.g.
  `feat/catalog-api`). Fixes use `fix/<short-description>`.
- Open a PR against `main` for every change of substance; squash-merge once
  CI is green. Trivial doc-only tweaks can be pushed directly to `main`.
- Reference the relevant Phase/task from `task.md` or the GitHub Issue number
  in the PR description.
