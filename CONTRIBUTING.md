# Contributing (Dev Workflow)

## Normal Development

1. Write code (VS Code auto-format on save recommended).
2. `git add -A`
3. `git commit` (fast pre-commit: Black, isort, Ruff --fix, detect-secrets baseline)
4. `git push` (CI runs strict lint + Bandit)

## Fixing Format Issues

- `make fmt`  # auto-fix everything
- `make lint` # verify checks (no auto-fix)
- `make security` # run Bandit locally (optional)

## Emergency

- `make commit-wip msg="debugging xyz"`   # skip slower checks
- `make commit-emergency msg="hotfix"`    # skip all checks (use sparingly)

## Detect-Secrets Baseline

- To update baseline: `detect-secrets scan > .secrets.baseline`
- Always review baseline changes before committing.