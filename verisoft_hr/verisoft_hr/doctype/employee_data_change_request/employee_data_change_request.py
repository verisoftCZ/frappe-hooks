# Copyright (c) 2026, Verisoft s.r.o. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class EmployeeDataChangeRequest(Document):
	def get_permlevel_access(self, permission_type="write"):
		levels = list(super().get_permlevel_access(permission_type))
		roles = frappe.get_roles()
		if frappe.session.user == "Administrator" or {"HR User", "HR Manager"}.intersection(roles):
			return levels
		levels = [level for level in levels if level != 1]
		if permission_type not in ("read", "write") or "Employee" not in roles:
			return levels
		# Saved requests use their stored employee link, not a client-supplied value.
		employee = self.get("employee") if self.is_new() else frappe.db.get_value(
			self.doctype, self.name, "employee"
		)
		if employee and frappe.db.get_value("Employee", employee, "user_id") == frappe.session.user:
			levels.append(1)
		return levels

	def onload(self):
		self.set_onload("verisoft_request_bank_access", {
			"read": int(1 in self.get_permlevel_access("read")),
			"write": int(1 in self.get_permlevel_access("write")),
		})
