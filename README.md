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

## License

MIT
