"""Company-wide presence information without exposing leave documents."""

import frappe
from frappe import _
from frappe.utils import cint, getdate, today


ALLOWED_ROLES = {"Employee", "HR User", "HR Manager", "System Manager"}
HR_ROLES = {"HR User", "HR Manager", "System Manager"}


def _deny(message="Not permitted"):
	frappe.throw(_(message), frappe.PermissionError)


def _get_company():
	user = frappe.session.user
	if user == "Guest":
		_deny()
	roles = set(frappe.get_roles(user))
	if not roles.intersection(ALLOWED_ROLES):
		_deny()
	if frappe.db.get_value("User", user, "user_type") != "System User":
		_deny()

	# This lookup intentionally bypasses Employee row permissions only for the
	# current user's own active employment. Client filters cannot widen scope.
	companies = {
		row.company
		for row in frappe.get_all(
			"Employee", filters={"user_id": user, "status": "Active"}, fields=["company"]
		)
		if row.company
	}
	default = frappe.defaults.get_user_default("Company")
	if companies:
		if default in companies:
			return default
		if len(companies) == 1:
			return next(iter(companies))
		_deny("Set a default Company matching your active Employee record.")

	# HR / administrators without an Employee record still need an explicitly
	# selected, readable company. Never accept an arbitrary company from the UI.
	if roles.intersection(HR_ROLES) and default:
		if frappe.get_list("Company", filters={"name": default}, fields=["name"], page_length=1):
			return default
	_deny("An active Employee record or an authorized HR default Company is required.")


def _is_half_day(leave, date):
	if not cint(leave.half_day):
		return False
	if leave.half_day_date:
		return getdate(leave.half_day_date) == date
	return getdate(leave.from_date) == getdate(leave.to_date) == date


def _get_employees(company, date):
	# Permission bypass is limited to this fixed, company-scoped projection.
	# Do not add leave type, reason, document names, or arbitrary query options.
	leaves = frappe.get_all(
		"Leave Application",
		filters={
			"company": company,
			"docstatus": 1,
			"status": "Approved",
			"from_date": ["<=", date],
			"to_date": [">=", date],
		},
		fields=["employee", "half_day", "half_day_date", "from_date", "to_date"],
	)
	by_employee = {}
	for leave in leaves:
		by_employee.setdefault(leave.employee, []).append(leave)
	if not by_employee:
		return []
	employees = frappe.get_all(
		"Employee",
		filters={"company": company, "status": "Active", "name": ["in", list(by_employee)]},
		fields=["name", "employee_name", "department"],
	)
	rows = []
	for employee in employees:
		applications = by_employee[employee.name]
		# Multiple approved half-day requests cover a full day. For a multi-day
		# request, only its actual half_day_date is shown as a half day.
		half_day = len(applications) == 1 and _is_half_day(applications[0], date)
		rows.append({
			"employee_name": employee.employee_name,
			"department": employee.department or "",
			"half_day": bool(half_day),
		})
	return sorted(rows, key=lambda row: (row["employee_name"].casefold(), row["department"].casefold()))


@frappe.whitelist()
def get_today_leaves():
	company = _get_company()
	date = getdate(today())
	return {"company": company, "date": str(date), "employees": _get_employees(company, date)}


@frappe.whitelist()
def get_card(filters=None):
	# Custom Number Cards send filters, but none are trusted or used here.
	data = get_today_leaves()
	return {
		"value": len(data["employees"]),
		"fieldtype": "Int",
		"route": ["company-leave-today"],
	}
