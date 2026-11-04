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

## Employee data change requests

Requests support mobile number, personal email, date of birth, current address,
permanent address and bank account number. Changes are applied to Employee only
after workflow approval, once per request. Blank new values leave existing data
unchanged. The existing `current_address`/`new_address` request field names are
retained; the latter updates `Employee.current_address`.

The Client Script fixture loads permission-checked defaults through
`get_request_defaults`. Ordinary employees can load only their own defaults.
Current/new bank account fields on requests use a separate level 1: self access
is document-specific, and the existing HR User/HR Manager approver roles can
read/write them. Being a line manager, request reader or share recipient does
not expose someone else's bank fields. Static Employee list/export permissions
do not include those fields. Existing requests cannot be reassigned to oneself
by a non-HR editor. Deploy the schema, controller, Python hooks and Client Script
fixture together; no workflow transitions are changed.

Czech labels missing from upstream catalogs are provided in
`verisoft_hr/translations/cs.csv`, together with the request/DocType titles.
Source labels remain English. Site-level Translation records take precedence
over app translations; clear the translation/site cache after changing the file.

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
matched only in leap years. Empty days produce no email; missed past dates
are not replayed. Delivery follows scheduler and Email Queue availability.

Recipients are enabled System Users explicitly assigned the `HR User` role,
with read access to the configured Company and Employee.
Each user's content is further limited by their Employee list/field permissions.
An `HR Manager` or `System Manager` role alone does not qualify. The built-in
`Administrator` is always excluded, even if assigned HR User. Each recipient gets
a separate email to their User.email, containing only their permitted events.
Recipient addresses are not shared via To/CC/BCC. No Notification Log is created.
This scheduled business email is independent of users' in-app notification and
notification-email preferences. An enabled outgoing Email Account is required.

After deploying and migrating, configure the `hr_celebration_digest` object in
the private site configuration, using real values instead of these examples:

```json
{
  "hr_celebration_digest": {
    "enabled": false,
    "company": "Example Company",
    "sender": "notifications@example.com"
  }
}
```

Do not store site configuration in Git. The task is disabled when the object or
enabled flag is absent. The legacy fixed `recipient` key is ignored. The optional
`sender` selects an enabled outgoing account by address, with Frappe's standard
fallback to the default outgoing account. Without `sender`, a default outgoing
account must be available. Disable standard HRMS birthday/work anniversary
reminders separately if only this HR digest is wanted.

For a read-only operator preview restricted to one recipient's Employee
permissions (contains employee names), use:

```sh
bench --site <site> execute verisoft_hr.celebration_digest.preview --kwargs '{"company":"Example Company","user":"hr@example.com"}'
```

`HR Celebration Digest Log` is readable by HR Manager and System Manager. Its
unique date/company key prevents duplicate runs, including after Email Queue
cleanup. It stores the number and IDs of queued emails, without employee details.
Keep logs to preserve deduplication. Newly assigned HR users do not receive a
second run for an already completed day. All queues and the log share one
transaction; a queue creation failure must roll back the whole run. The log means
queued, not delivered; retry delivery failures through the original Email Queue
records. Missing or invalid email addresses for recipients with events fail the
run before any queue is created. No Employee permissions change, and the preview
is not exposed as an HTTP API.

## Mandatory employee trainings

`Employee mandatory trainings` belongs to the Verisoft HR module. Its existing
name, field names, `SKOL-.####` naming series and HR permissions are preserved.
Before migrating a site with the original custom DocType, back it up and compare
its definition with this version. Schema sync converts the same-named definition
to this app's standard DocType; employee training records remain site data.

Filtered fixtures carry the Report Builder `Školení – přehled platnosti` and
the two Notification rules `Školení – brzy končí platnost` and
`Školení – platnost skončila`. They retain their original behavior: in-app Alerts
to HR User, 30 days before expiry and on the expiry date, excluding renewed and
external-worker trainings. No additional scheduler hook or Server Script is used.
The report excludes renewed/external trainings and retains its site-specific
`Company Letterhead - Grey` reference; provision or configure that letterhead
separately when installing on another site. Letterhead content and training data
are not exported by this app.

## Employee bank details

`employee_bank_access.py` extends Employee through `extend_doctype_class`.
Salary Mode, Bank Name, Bank Account No and IBAN use a dedicated permission
level 2. An Employee can read these fields on their own saved profile, identified
by the stored `Employee.user_id`; being the document creator or a manager does
not grant access. This does not grant document access or employee write access.
HR User retains read/write access on all Employee documents allowed by their
normal document/User Permissions. Administrator retains framework access.
CTC and Salary Currency permissions are unchanged.

After-install/migrate setup applies only the four Property Setters and the HR
User level-2 permission, preserving other permission rows. It refuses a site
already using level 2 for unrelated fields or other roles. Deploy the controller,
hooks and form script together, then migrate with maintenance enabled. No UI
Server Script or manual fixture export is needed for this feature.

Ordinary Employee list queries, reports and exports do not gain bank fields,
even for their own row: self access is deliberately limited to document detail
APIs and its form. The form mirrors server-provided per-document flags without
granting static Employee permissions. Custom reports/endpoints/templates which
bypass Frappe's standard permission checks must enforce equivalent restrictions.

Before deployment, test own/subordinate/HR reads, writes, list/export restrictions
and repeat migrations on a disposable site. Reverting only the application image
leaves the level-2 metadata in the database; restore the previous four permlevels
and remove only the new HR User level-2 row as part of a reviewed rollback.

## License

MIT
