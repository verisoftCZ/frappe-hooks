"""Daily HR-only digest. Configuration lives in site_config, never in fixtures.

No whitelisted methods: previews and scheduling are operator-only operations.
Queue insertion and the unique daily log share the scheduler's transaction.
"""

import hashlib
from html import escape

import frappe
from frappe.email.doctype.email_account.email_account import EmailAccount
from frappe.utils import getdate, validate_email_address

LOG_DOCTYPE = "HR Celebration Digest Log"


def collect_events(employees, on_date):
	"""Return names and completed service years only; omit original dates and ages."""
	on_date = getdate(on_date)
	birthdays, anniversaries = [], []
	for employee in employees:
		for field, target in (("date_of_birth", birthdays), ("date_of_joining", anniversaries)):
			value = employee.get(field)
			if not value:
				continue
			date = getdate(value)
			if (date.month, date.day) != (on_date.month, on_date.day) or date.year >= on_date.year:
				continue
			item = {"employee_name": employee["employee_name"]}
			if field == "date_of_joining":
				item["years"] = on_date.year - date.year
			target.append(item)
	return {"birthdays": birthdays, "anniversaries": anniversaries}


def preview(company, on_date=None):
	"""Read-only CLI preview; does not queue mail or write a log."""
	if not company or not frappe.db.exists("Company", company):
		raise ValueError("Configure an existing company for the HR celebration digest")
	on_date = getdate(on_date)
	employees = frappe.get_all(
		"Employee",
		filters={"status": "Active", "company": company},
		fields=["employee_name", "date_of_birth", "date_of_joining"],
		order_by="employee_name asc, name asc",
	)
	return {"date": on_date.isoformat(), "company": company, **collect_events(employees, on_date)}


def render_message(digest):
	date = getdate(digest["date"]).strftime("%d.%m.%Y")
	parts = [f"<p>Přehled pro {escape(digest['company'])} na {date}.</p>"]
	if digest["birthdays"]:
		parts.append("<h3>Narozeniny</h3><ul>")
		parts.extend(f"<li>{escape(row['employee_name'])}</li>" for row in digest["birthdays"])
		parts.append("</ul>")
	if digest["anniversaries"]:
		parts.append("<h3>Pracovní výročí</h3><ul>")
		for row in digest["anniversaries"]:
			years = row["years"]
			unit = "rok" if years == 1 else "roky" if years in (2, 3, 4) else "let"
			parts.append(f"<li>{escape(row['employee_name'])} — {years} {unit}</li>")
		parts.append("</ul>")
	return "".join(parts)


def queue_daily_digest():
	"""Scheduler entry point. Disabled until explicitly configured for this site.

	A unique log per date/company prevents concurrent or repeated queueing, even
	if Email Queue is later purged. Failed deliveries are retried in Email Queue.
	Do not commit here: the scheduler commits queue and log together or rolls back.
	"""
	settings = frappe.conf.get("hr_celebration_digest") or {}
	if settings.get("enabled") not in (True, 1):
		return {"status": "disabled"}
	recipient = _address(settings.get("recipient"))
	sender = settings.get("sender") or None
	if sender:
		sender = _address(sender)
	digest = preview(settings.get("company"))
	if not (digest["birthdays"] or digest["anniversaries"]):
		return {"status": "empty"}
	key = _log_name(digest)
	if frappe.db.exists(LOG_DOCTYPE, key):
		return {"status": "already_queued"}
	if not EmailAccount.find_outgoing(match_by_email=sender):
		raise frappe.OutgoingEmailError("Configure an enabled outgoing Email Account for the HR digest")

	# The primary key is the concurrency guard. Do not add recipient to this key:
	# changing a mailbox must not send a second digest for the same company/day.
	try:
		log = frappe.get_doc({
			"doctype": LOG_DOCTYPE,
			"digest_date": digest["date"],
			"company": digest["company"],
		}).insert(ignore_permissions=True, set_name=key)
	except frappe.DuplicateEntryError:
		return {"status": "already_queued"}

	queue = frappe.sendmail(
		recipients=[recipient],
		sender=sender or "",
		subject=f"Narozeniny a pracovní výročí — {getdate(digest['date']).strftime('%d.%m.%Y')}",
		message=render_message(digest),
		delayed=True,
		now=False,
		reference_doctype=LOG_DOCTYPE,
		reference_name=log.name,
		add_unsubscribe_link=0,
	)
	if not queue or not queue.name:
		raise RuntimeError("HR digest was not added to Email Queue; roll back this transaction")
	log.db_set("email_queue", queue.name, update_modified=False)
	return {"status": "queued", "log": log.name}


def _address(value):
	# Exactly one plain mailbox; disallow display names and recipient lists.
	if not isinstance(value, str) or any(char in value for char in ",;<>\r\n"):
		raise ValueError("Configure a single plain email address for the HR digest")
	value = value.strip()
	if not validate_email_address(value):
		raise ValueError("Invalid HR digest email address")
	return value


def _log_name(digest):
	company_hash = hashlib.sha256(digest["company"].encode()).hexdigest()[:20]
	return f"{digest['date']}-{company_hash}"
