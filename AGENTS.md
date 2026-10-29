# Project instructions

This repository contains a custom Frappe HRMS application. Keep changes small and reviewable, and prefer app hooks and fixtures over editing upstream applications.

- Inspect existing hooks, schemas, and fixtures before changing behavior.
- Preserve least-privilege access to Employee data and limit organization-chart API output to intended fields.
- Run `node scripts/check-fixtures.cjs` for JSON syntax and expected fixture record names.
- Python requirements and lint configuration are in `pyproject.toml` and `.pre-commit-config.yaml`.
- Integration tests require a configured Frappe bench and a disposable test site. The existing DocType test is a scaffold without assertions.
- Never commit credentials, private keys, employee data, or deployment configuration containing secrets.
- Do not push, deploy, migrate, or perform destructive operations without explicit operator authorization.
- For local workspaces, if `../AGENTS.md` exists, read it for additional operator instructions. Keep those local instructions and any sibling deployment notes outside this public repository.
