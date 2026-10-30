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

## HR celebration digest

An optional combined birthday and work anniversary email runs daily at 07:00
in the site's System Settings time zone. It includes active employees of one
explicitly configured company. Birthdays omit age and original birth dates;
anniversaries show completed years of service (at least one). February 29 is
matched only in leap years. Empty days produce no email; missed past dates are
not replayed. Delivery follows scheduler and email queue availability.

After deploying and migrating, configure the `hr_celebration_digest` object in
the private site configuration, using real values instead of these examples:

```json
{
  "hr_celebration_digest": {
    "enabled": false,
    "company": "Example Company",
    "recipient": "hr@example.com",
    "sender": "notifications@example.com"
  }
}
```

The sender is optional if a default outgoing Email Account is enabled. An
explicit sender is resolved using Frappe's standard outgoing-account selection,
which can fall back to the default account. Enable only after checking that
selection and the recipient. Do not store site configuration in Git. The task
is disabled when the object or enabled flag is absent. Disable standard HRMS
birthday/work anniversary reminders separately if only the HR digest is wanted.

For a read-only operator preview (contains employee names), use:

```sh
bench --site <site> execute verisoft_hr.celebration_digest.preview --kwargs '{"company":"Example Company"}'
```

`HR Celebration Digest Log` is readable by HR Manager and System Manager. Its
unique date/company key prevents duplicate queueing across concurrent runs and
Email Queue cleanup. The queue ID is retained as text so mail cleanup does not
remove the deduplication record. Failed deliveries must be retried in Email
Queue; the log means queued, not delivered. Keep logs to preserve deduplication.
Queue and log creation share one transaction. No Employee permissions change,
and the preview is not exposed as an HTTP API.

## License

MIT
