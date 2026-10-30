# Verisoft HR

Customizations for Frappe HRMS: employee data change requests, leave approval workflows, and an organization-chart API override.

## Development

This repository contains the custom app only. Frappe, ERPNext, and HRMS are managed by a separate bench environment. Python >=3.14 is declared in `pyproject.toml`.

Check JSON syntax and expected fixture record names with Node.js:

```sh
node scripts/check-fixtures.cjs
```

Formatting and lint hooks are configured in `.pre-commit-config.yaml`:

```sh
pre-commit install
pre-commit run --all-files
```

Integration tests require a disposable test site with the required apps installed:

```sh
bench --site <test-site> run-tests --app verisoft_hr
```

The existing DocType test is a scaffold without assertions; it does not establish business-rule coverage.

## Installation

From a prepared bench, install this app on the intended site:

```sh
bench get-app https://github.com/verisoftCZ/frappe-hooks --branch main
bench --site <site> install-app verisoft_hr
```

Some workflow and permission configuration may also exist in the site database. Review the app hooks and fixture filters before exporting configuration.

## Company-wide leave overview

The custom Number Card `Company Employees on Leave Today` opens the Desk page
`company-leave-today`. Both show unique active employees with approved, submitted
leave covering today in the authorized company, without exposing leave types,
reasons, private employee fields, or links to leave documents.

System Users with Employee, HR User, HR Manager, or System Manager roles may use
the overview. Employees are scoped to their active employment company. HR users
without an active Employee record need a readable default Company. Multiple
active employment companies require a matching default Company.

After installing the updated app and migrating the target site, select this
Number Card in the workspace editor. The app does not overwrite existing
workspace layouts or change Employee / Leave Application document permissions.

## License

MIT
