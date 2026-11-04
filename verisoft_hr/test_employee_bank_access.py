"""Synthetic tests for document-specific Employee bank permissions."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe

from verisoft_hr import employee_bank_access as bank_access
from verisoft_hr.employee_bank_access import EmployeeBankAccessMixin


class BaseEmployee:
	def get_permlevel_access(self, permission_type="write"):
		return list(self.base_levels.get(permission_type, []))

	def is_new(self):
		return self.new

	def onload(self):
		self.parent_loaded = True

	def set_onload(self, key, value):
		self.onload_data[key] = value


class Employee(EmployeeBankAccessMixin, BaseEmployee):
	pass


class TestEmployeeBankAccess(unittest.TestCase):
	def setUp(self):
		self.employee = Employee()
		self.employee.name = "SYNTHETIC-EMPLOYEE"
		self.employee.user_id = "spoofed@example.test"
		self.employee.new = False
		self.employee.onload_data = {}
		self.employee.base_levels = {"read": [0], "write": []}
		self.session = SimpleNamespace(user="employee@example.test")
		self.roles = Mock(return_value=["Employee"])
		self.db = Mock()
		self.db.get_value.return_value = self.session.user
		for name, value in {"session": self.session, "get_roles": self.roles, "db": self.db}.items():
			patcher = patch.object(frappe, name, value)
			patcher.start()
			self.addCleanup(patcher.stop)

	def test_self_can_read_only_bank_level(self):
		self.assertEqual(self.employee.get_permlevel_access("read"), [0, 2])
		self.assertEqual(self.employee.get_permlevel_access("write"), [])

	def test_self_cannot_gain_salary_level_one(self):
		self.assertNotIn(1, self.employee.get_permlevel_access("read"))

	def test_manager_cannot_read_other_employee(self):
		self.db.get_value.return_value = "subordinate@example.test"
		self.assertEqual(self.employee.get_permlevel_access("read"), [0])

	def test_forged_user_id_does_not_grant_access(self):
		self.employee.user_id = self.session.user
		self.db.get_value.return_value = "subordinate@example.test"
		self.assertNotIn(2, self.employee.get_permlevel_access("read"))

	def test_creator_is_not_employee_identity(self):
		self.employee.owner = self.session.user
		self.db.get_value.return_value = None
		self.assertNotIn(2, self.employee.get_permlevel_access("read"))

	def test_new_document_cannot_claim_self_access(self):
		self.employee.new = True
		self.assertNotIn(2, self.employee.get_permlevel_access("read"))
		self.db.get_value.assert_not_called()

	def test_guest_denied(self):
		self.session.user = "Guest"
		self.assertNotIn(2, self.employee.get_permlevel_access("read"))

	def test_unrelated_role_denied_even_if_linked(self):
		self.roles.return_value = ["Website Manager"]
		self.assertNotIn(2, self.employee.get_permlevel_access("read"))

	def test_manager_with_other_level_two_role_is_denied(self):
		self.employee.base_levels = {"read": [0, 1, 2], "write": [0, 2]}
		self.roles.return_value = ["Employee", "Jednatel"]
		self.db.get_value.return_value = "subordinate@example.test"
		self.assertEqual(self.employee.get_permlevel_access("read"), [0, 1])
		self.assertEqual(self.employee.get_permlevel_access("write"), [0])

	def test_hr_manager_retains_hr_user_permissions(self):
		self.roles.return_value = ["Employee", "HR User"]
		self.employee.base_levels = {"read": [0, 1, 2], "write": [0, 1, 2]}
		self.db.get_value.return_value = "subordinate@example.test"
		self.assertEqual(self.employee.get_permlevel_access("read"), [0, 1, 2])
		self.assertEqual(self.employee.get_permlevel_access("write"), [0, 1, 2])

	def test_administrator_preserves_framework_behavior(self):
		self.session.user = "Administrator"
		self.employee.base_levels = {"read": [0, 1, 2]}
		self.assertEqual(self.employee.get_permlevel_access("read"), [0, 1, 2])

	def test_onload_preserves_parent_and_returns_read_only_flag(self):
		self.employee.onload()
		self.assertTrue(self.employee.parent_loaded)
		self.assertEqual(self.employee.onload_data["verisoft_bank_access"], {"read": 1, "write": 0})

	def test_onload_does_not_include_bank_values(self):
		self.db.get_value.return_value = "subordinate@example.test"
		self.employee.onload()
		self.assertEqual(self.employee.onload_data, {"verisoft_bank_access": {"read": 0, "write": 0}})


class TestBankAccessSetupGuards(unittest.TestCase):
	def assert_setup_refused_before_writes(self, meta):
		with (
			patch.object(frappe, "get_meta", return_value=meta),
			patch.object(bank_access, "make_property_setter") as setter,
			patch.object(bank_access, "add_permission") as grant,
		):
			with self.assertRaises(frappe.ValidationError):
				bank_access.setup_bank_access()
			setter.assert_not_called()
			grant.assert_not_called()

	def meta(self, *, fields=None, permissions=None):
		return SimpleNamespace(
			get_field=lambda name: SimpleNamespace(permlevel=1),
			fields=fields or [], permissions=permissions or [],
		)

	def test_unrelated_level_two_field_stops_setup(self):
		self.assert_setup_refused_before_writes(self.meta(fields=[
			SimpleNamespace(fieldname="ctc", permlevel=2),
		]))

	def test_other_role_on_level_two_stops_setup(self):
		self.assert_setup_refused_before_writes(self.meta(permissions=[
			SimpleNamespace(role="Employee", permlevel=2, if_owner=0),
		]))

	def test_document_owner_rule_does_not_identify_employee(self):
		self.assert_setup_refused_before_writes(self.meta(permissions=[
			SimpleNamespace(role="HR User", permlevel=2, if_owner=1),
		]))

	def test_missing_upstream_field_stops_setup(self):
		meta = self.meta()
		meta.get_field = lambda name: None
		self.assert_setup_refused_before_writes(meta)
