# Contributing (Dev Workflow)

## Normal Development

1. Write code (VS Code auto-format on save recommended).
2. `git add -A`
3. `git commit` (fast pre-commit: Black, isort, Ruff --fix, detect-secrets baseline)
   - If hooks keep re-formatting, run `make fmt` first, then commit
4. `git push` (CI runs strict lint + Bandit)

## Fixing Format Issues

- `make fmt`  # auto-fix everything
- `make lint` # verify checks (no auto-fix)
- `make security` # run Bandit locally (optional)

## Emergency

- `make commit-wip msg="debugging xyz"`   # skip slower checks
- `make commit-emergency msg="hotfix"`    # skip all checks (use sparingly)

## Detect-Secrets Baseline

**When to update the baseline:**
- After adding test files with dummy credentials
- After removing false positives
- When detect-secrets reports new legitimate test secrets
- Before releases to ensure baseline is current

**How to update:**
```bash
detect-secrets scan > .secrets.baseline
git diff .secrets.baseline  # Review changes carefully!
```

**Important:** Always review baseline changes before committing to ensure no real secrets are being whitelisted.
