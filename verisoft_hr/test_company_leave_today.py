"""Unit tests with synthetic data only; no site/database writes."""

import datetime
import unittest
from types import SimpleNamespace as Row
from unittest.mock import Mock, patch

import frappe

from verisoft_hr import company_leave_today as overview


class TestCompanyLeaveToday(unittest.TestCase):
	def setUp(self):
		self.db = Mock()
		self.db.get_value.return_value = "System User"
		self.defaults = Mock()
		self.defaults.get_user_default.return_value = "Company A"
		self.get_all = Mock(return_value=[Row(company="Company A")])
		self.get_list = Mock(return_value=[Row(name="Company A")])
		def throw(message, exception):
			raise exception(message)

		for name, value in {
			"session": Row(user="employee@example.test"),
			"db": self.db,
			"defaults": self.defaults,
			"get_roles": Mock(return_value=["Employee"]),
			"get_all": self.get_all,
			"get_list": self.get_list,
			"throw": throw,
		}.items():
			patcher = patch.object(frappe, name, value, create=True)
			patcher.start()
			self.addCleanup(patcher.stop)
		translation = patch.object(overview, "_", lambda text: text)
		translation.start()
		self.addCleanup(translation.stop)
		self.date = datetime.date(2026, 10, 30)

	def test_guest_cannot_read_company_or_leave_data(self):
		frappe.session.user = "Guest"
		with self.assertRaises(frappe.PermissionError):
			overview._get_company()
		self.get_all.assert_not_called()

	def test_unrelated_role_is_denied(self):
		frappe.get_roles.return_value = ["Website Manager"]
		with self.assertRaises(frappe.PermissionError):
			overview._get_company()
		self.get_all.assert_not_called()

	def test_website_user_with_employee_role_is_denied(self):
		self.db.get_value.return_value = "Website User"
		with self.assertRaises(frappe.PermissionError):
			overview._get_company()
		self.get_all.assert_not_called()

	def test_employee_cannot_widen_company_by_changing_default(self):
		self.defaults.get_user_default.return_value = "Company B"
		self.assertEqual(overview._get_company(), "Company A")
		self.get_all.assert_called_once_with(
			"Employee", filters={"user_id": "employee@example.test", "status": "Active"}, fields=["company"]
		)
		self.get_list.assert_not_called()

	def test_employee_without_active_employment_is_denied(self):
		self.get_all.return_value = []
		with self.assertRaises(frappe.PermissionError):
			overview._get_company()

	def test_multiple_employments_need_matching_default(self):
		self.get_all.return_value = [Row(company="Company A"), Row(company="Company B")]
		self.assertEqual(overview._get_company(), "Company A")
		self.defaults.get_user_default.return_value = "Company C"
		with self.assertRaises(frappe.PermissionError):
			overview._get_company()

	def test_hr_fallback_checks_company_permissions(self):
		frappe.get_roles.return_value = ["HR User"]
		self.get_all.return_value = []
		self.assertEqual(overview._get_company(), "Company A")
		self.get_list.assert_called_once_with(
			"Company", filters={"name": "Company A"}, fields=["name"], page_length=1
		)
		self.get_list.return_value = []
		with self.assertRaises(frappe.PermissionError):
			overview._get_company()

	def test_hr_without_default_is_denied(self):
		frappe.get_roles.return_value = ["HR Manager"]
		self.get_all.return_value = []
		self.defaults.get_user_default.return_value = None
		with self.assertRaises(frappe.PermissionError):
			overview._get_company()

	def leave(self, employee, half_day=0, half_day_date=None, **extra):
		return Row(employee=employee, half_day=half_day, half_day_date=half_day_date,
			from_date=self.date, to_date=self.date, **extra)

	def test_fixed_query_filters_and_minimal_output(self):
		self.get_all.side_effect = [
			[self.leave("E1", leave_type="Sensitive", description="Private", name="LEAVE-1")],
			[Row(name="E1", employee_name="Alice", department="Engineering", personal_email="private@example.test")],
		]
		rows = overview._get_employees("Company A", self.date)
		self.assertEqual(rows, [{"employee_name": "Alice", "department": "Engineering", "half_day": False}])
		leave_call, employee_call = self.get_all.call_args_list
		self.assertEqual(leave_call.kwargs["filters"], {
			"company": "Company A", "docstatus": 1, "status": "Approved",
			"from_date": ["<=", self.date], "to_date": [">=", self.date],
		})
		self.assertEqual(set(leave_call.kwargs["fields"]), {
			"employee", "half_day", "half_day_date", "from_date", "to_date",
		})
		self.assertEqual(employee_call.kwargs["filters"], {
			"company": "Company A", "status": "Active", "name": ["in", ["E1"]],
		})

	def test_duplicates_are_one_person_and_two_half_days_are_full(self):
		self.get_all.side_effect = [
			[self.leave("E1", 1, self.date), self.leave("E1", 1, self.date)],
			[Row(name="E1", employee_name="Alice", department=None)],
		]
		self.assertEqual(overview._get_employees("Company A", self.date), [
			{"employee_name": "Alice", "department": "", "half_day": False}
		])

	def test_half_day_only_on_its_actual_date(self):
		leave = self.leave("E1", 1, self.date,)
		self.assertTrue(overview._is_half_day(leave, self.date))
		self.assertFalse(overview._is_half_day(leave, self.date + datetime.timedelta(days=1)))
		leave.half_day = 0
		self.assertFalse(overview._is_half_day(leave, self.date))

	def test_no_approved_leaves_does_not_query_all_employees(self):
		self.get_all.return_value = []
		self.assertEqual(overview._get_employees("Company A", self.date), [])
		self.assertEqual(self.get_all.call_count, 1)

	def test_card_uses_same_data_and_ignores_forged_filters(self):
		with patch.object(overview, "get_today_leaves", return_value={"employees": [{}, {}]}):
			result = overview.get_card(filters={"company": "Company B", "status": "Rejected"})
		self.assertEqual(result, {"value": 2, "fieldtype": "Int", "route": ["company-leave-today"]})

	def test_endpoint_uses_server_today_and_authorized_company(self):
		with (
			patch.object(overview, "_get_company", return_value="Company A"),
			patch.object(overview, "today", return_value="2026-10-30"),
			patch.object(overview, "_get_employees", return_value=[]) as employees,
		):
			result = overview.get_today_leaves()
		employees.assert_called_once_with("Company A", self.date)
		self.assertEqual(result, {"company": "Company A", "date": "2026-10-30", "employees": []})
