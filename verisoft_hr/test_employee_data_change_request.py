"""Synthetic validation and application tests; no site writes or notifications."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe

from verisoft_hr import employee_data_change_request as requests


class Request(frappe._dict):
	def is_new(self):
		return self.get("is_new_record", True)

	def set(self, key, value):
		self[key] = value

	def db_set(self, key, value):
		self[key] = value


class TestEmployeeDataChangeRequest(unittest.TestCase):
	def setUp(self):
		self.user = "employee@example.test"
		self.roles = Mock(return_value=["Employee"])
		self.employee = Request(
			name="SYNTHETIC-EMPLOYEE", cell_number="OLD-PHONE", personal_email="old@example.test",
			date_of_birth="1990-01-01", current_address="OLD-CURRENT", permanent_address="OLD-PERMANENT",
			bank_ac_no="OLD-ACCOUNT", bank_name="UNCHANGED-BANK", salary_mode="Bank", iban="UNCHANGED-IBAN",
		)
		self.employee.save = Mock()
		self.employee.check_permission = Mock()
		self.employee.apply_fieldlevel_read_permissions = Mock()
		self.db = Mock()
		self.db.get_value.side_effect = lambda dt, filters, fields, **kw: (
			self.employee if dt == "Employee" and isinstance(fields, list)
			else self.employee.name
		)
		self.get_doc = Mock(return_value=self.employee)
		def throw(message, exc=frappe.ValidationError):
			raise exc(message)
		for name, value in {
			"session": SimpleNamespace(user=self.user), "get_roles": self.roles,
			"db": self.db, "get_doc": self.get_doc, "throw": throw,
		}.items():
			patcher = patch.object(frappe, name, value)
			patcher.start()
			self.addCleanup(patcher.stop)
		time = patch.object(frappe.utils, "now", return_value="2026-11-04 12:00:00")
		time.start()
		self.addCleanup(time.stop)
		self.request = Request(doctype="Employee Data Change Request", name="SYNTHETIC-REQUEST",
			employee=self.employee.name, workflow_state="Draft", changes_applied=0)

	def test_new_request_captures_both_addresses_and_bank_account(self):
		requests.validate_request(self.request)
		self.assertEqual(self.request.current_address, "OLD-CURRENT")
		self.assertEqual(self.request.current_permanent_address, "OLD-PERMANENT")
		self.assertEqual(self.request.current_bank_ac_no, "OLD-ACCOUNT")
		self.assertEqual(self.request.requested_by, self.user)

	def test_new_request_cannot_target_someone_else(self):
		self.request.employee = "OTHER-EMPLOYEE"
		requests.validate_request(self.request)
		self.assertEqual(self.request.employee, self.employee.name)

	def test_existing_other_employee_request_cannot_be_reassigned_to_self(self):
		self.request.is_new_record = False
		self.db.get_value.side_effect = lambda dt, *args, **kw: self.employee if dt == "Employee" else "OTHER-EMPLOYEE"
		with self.assertRaises(frappe.PermissionError):
			requests.validate_request(self.request)

	def test_hr_keeps_selected_employee(self):
		self.roles.return_value = ["HR User"]
		requests.validate_request(self.request)
		self.assertEqual(self.request.employee, self.employee.name)

	def test_hr_without_employee_is_rejected(self):
		self.roles.return_value = ["HR User"]
		self.request.employee = None
		with self.assertRaises(frappe.ValidationError):
			requests.validate_request(self.request)

	def test_missing_employee_is_rejected(self):
		self.db.get_value.side_effect = None
		self.db.get_value.return_value = None
		with self.assertRaises(frappe.ValidationError):
			requests.validate_request(self.request)

	def test_approved_request_updates_new_fields_and_preserves_other_bank_fields(self):
		self.request.update(workflow_state="Approved", new_bank_ac_no="NEW-ACCOUNT",
			new_address="NEW-CURRENT", new_permanent_address="NEW-PERMANENT")
		requests.apply_approved_changes(self.request)
		self.assertEqual(self.employee.bank_ac_no, "NEW-ACCOUNT")
		self.assertEqual(self.employee.current_address, "NEW-CURRENT")
		self.assertEqual(self.employee.permanent_address, "NEW-PERMANENT")
		self.assertEqual(self.employee.bank_name, "UNCHANGED-BANK")
		self.assertEqual(self.employee.iban, "UNCHANGED-IBAN")
		self.assertEqual(self.employee.salary_mode, "Bank")
		self.employee.save.assert_called_once_with(ignore_permissions=True)
		self.assertEqual(self.request.changes_applied, 1)

	def test_previous_change_fields_still_apply(self):
		self.request.update(workflow_state="Approved", new_mobile_number="NEW-PHONE",
			new_personal_email="new@example.test", new_date_of_birth="1991-01-01")
		requests.apply_approved_changes(self.request)
		self.assertEqual(self.employee.cell_number, "NEW-PHONE")
		self.assertEqual(self.employee.personal_email, "new@example.test")
		self.assertEqual(self.employee.date_of_birth, "1991-01-01")

	def test_blank_new_fields_leave_existing_values(self):
		self.request.workflow_state = "Approved"
		requests.apply_approved_changes(self.request)
		self.assertEqual(self.employee.bank_ac_no, "OLD-ACCOUNT")
		self.assertEqual(self.employee.permanent_address, "OLD-PERMANENT")

	def test_only_approved_requests_are_applied(self):
		for state in ("Draft", "Pending", "Rejected"):
			self.request.workflow_state = state
			requests.apply_approved_changes(self.request)
		self.employee.save.assert_not_called()

	def test_already_applied_request_is_not_repeated(self):
		self.request.update(workflow_state="Approved", changes_applied=1)
		requests.apply_approved_changes(self.request)
		self.employee.save.assert_not_called()

	def test_defaults_use_permission_checked_document(self):
		data = requests.get_request_defaults()
		self.employee.check_permission.assert_called_once_with("read")
		self.employee.apply_fieldlevel_read_permissions.assert_called_once()
		self.assertEqual(data["values"]["current_bank_ac_no"], "OLD-ACCOUNT")
		self.assertEqual(data["values"]["current_permanent_address"], "OLD-PERMANENT")

	def test_defaults_cannot_read_subordinates_even_if_their_employee_doc_is_readable(self):
		with self.assertRaises(frappe.PermissionError):
			requests.get_request_defaults("OTHER-EMPLOYEE")
		self.get_doc.assert_not_called()

	def test_guest_cannot_load_defaults(self):
		frappe.session.user = "Guest"
		with self.assertRaises(frappe.PermissionError):
			requests.get_request_defaults()

	def test_unrelated_role_cannot_load_defaults(self):
		self.roles.return_value = ["Website Manager"]
		with self.assertRaises(frappe.PermissionError):
			requests.get_request_defaults()
