"""Read bank details on one's own Employee document, without exposing subordinates.

Level 2 is reserved for these four fields. Metadata/list/export permissions remain
HR-only; the document controller adds read access for the linked employee only.
"""

import frappe
from frappe.core.doctype.doctype.doctype import validate_permissions_for_doctype
from frappe.custom.doctype.property_setter.property_setter import make_property_setter
from frappe.permissions import add_permission

BANK_PERMLEVEL = 2
BANK_FIELDS = ("salary_mode", "bank_name", "bank_ac_no", "iban")


class EmployeeBankAccessMixin:
	def get_permlevel_access(self, permission_type="write"):
		levels = list(super().get_permlevel_access(permission_type))
		if frappe.session.user == "Administrator" or "HR User" in frappe.get_roles():
			return levels

		# No other role (including a line manager) gets this level on other records.
		levels = [level for level in levels if level != BANK_PERMLEVEL]
		if permission_type == "read" and self._is_linked_employee():
			levels.append(BANK_PERMLEVEL)
		return levels

	def _is_linked_employee(self):
		user = frappe.session.user
		if user == "Guest" or "Employee" not in frappe.get_roles() or self.is_new():
			return False
		# Never trust user_id supplied on an unsaved/in-memory document or its owner.
		return frappe.db.get_value("Employee", self.name, "user_id") == user

	def onload(self):
		parent_onload = getattr(super(), "onload", None)
		if parent_onload:
			parent_onload()
		self.set_onload("verisoft_bank_access", {
			"read": int(BANK_PERMLEVEL in self.get_permlevel_access("read")),
			"write": int(BANK_PERMLEVEL in self.get_permlevel_access("write")),
		})


def setup_bank_access():
	"""Idempotent after-install/migrate configuration; preserve unrelated permissions.

	Refuse a site already using level 2 for something else instead of silently
	granting access to unrelated data. This function does not commit transactions.
	"""
	meta = frappe.get_meta("Employee")
	for field in BANK_FIELDS:
		if not meta.get_field(field):
			raise frappe.ValidationError(f"Employee bank access: missing field {field}")
	if any(df.permlevel == BANK_PERMLEVEL and df.fieldname not in BANK_FIELDS for df in meta.fields):
		raise frappe.ValidationError("Employee bank access: permission level 2 is already used by other fields")
	for perm in meta.permissions:
		if perm.permlevel == BANK_PERMLEVEL and (perm.role != "HR User" or perm.if_owner):
			raise frappe.ValidationError("Employee bank access: conflicting permission at level 2")

	for field in BANK_FIELDS:
		if meta.get_field(field).permlevel != BANK_PERMLEVEL:
			make_property_setter("Employee", field, "permlevel", BANK_PERMLEVEL, "Int")

	filters = {"parent": "Employee", "role": "HR User", "permlevel": BANK_PERMLEVEL, "if_owner": 0}
	name = frappe.db.get_value("Custom DocPerm", filters, "name")
	if not name:
		# add_permission copies the existing DocPerm set if no Custom DocPerm exist.
		add_permission("Employee", "HR User", BANK_PERMLEVEL)
		name = frappe.db.get_value("Custom DocPerm", filters, "name")
	permission = frappe.get_doc("Custom DocPerm", name)
	if not permission.read or not permission.write:
		permission.update({"read": 1, "write": 1})
		permission.save(ignore_permissions=True)
	validate_permissions_for_doctype("Employee")
	frappe.clear_cache(doctype="Employee")
