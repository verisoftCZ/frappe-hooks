"""Synthetic unit tests: never queue real mail or write to a site."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe

from verisoft_hr import celebration_digest as digest


class TestEvents(unittest.TestCase):
	def test_birthday_omits_age_and_original_date(self):
		result = digest.collect_events([
			{"employee_name": "Test", "date_of_birth": "1990-10-30"},
		], "2026-10-30")
		self.assertEqual(result, {"birthdays": [{"employee_name": "Test"}], "anniversaries": []})

	def test_both_events_and_completed_years(self):
		result = digest.collect_events([
			{"employee_name": "Test", "date_of_birth": "1990-10-30", "date_of_joining": "2021-10-30"},
		], "2026-10-30")
		self.assertEqual(len(result["birthdays"]), 1)
		self.assertEqual(result["anniversaries"], [{"employee_name": "Test", "years": 5}])

	def test_no_zero_year_future_or_wrong_day_events(self):
		rows = [{"employee_name": "Test", "date_of_joining": date} for date in (
			None, "2026-10-30", "2027-10-30", "2020-10-29", "2020-11-30",
		)]
		self.assertEqual(digest.collect_events(rows, "2026-10-30"), {"birthdays": [], "anniversaries": []})

	def test_leap_day_matches_only_actual_leap_day(self):
		rows = [{"employee_name": "Test", "date_of_birth": "2000-02-29"}]
		self.assertFalse(digest.collect_events(rows, "2026-02-28")["birthdays"])
		self.assertFalse(digest.collect_events(rows, "2026-03-01")["birthdays"])
		self.assertEqual(len(digest.collect_events(rows, "2028-02-29")["birthdays"]), 1)

	def test_html_escapes_employee_and_company(self):
		message = digest.render_message({
			"date": "2026-10-30", "company": "<Company>",
			"birthdays": [{"employee_name": "<script>"}],
			"anniversaries": [{"employee_name": "A&B", "years": 5}],
		})
		self.assertIn("&lt;script&gt;", message)
		self.assertIn("&lt;Company&gt;", message)
		self.assertIn("A&amp;B — 5 let", message)
		self.assertNotIn("<script>", message)

	def test_address_rejects_lists_display_names_and_header_injection(self):
		for value in (None, "", "invalid", "a@example.test,b@example.test", "HR <a@example.test>",
			"a@example.test\r\nBcc:b@example.test", "a@example.test;b@example.test"):
			with self.subTest(value=value), self.assertRaises(ValueError):
				digest._address(value)
		self.assertEqual(digest._address(" hr@example.test "), "hr@example.test")


class TestQueue(unittest.TestCase):
	def setUp(self):
		self.settings = {"enabled": True, "company": "Test Company", "recipient": "hr@example.test"}
		self.db = Mock()
		self.db.exists.return_value = False
		self.log = Mock(name="log")
		self.log.name = "daily-log"
		self.doc = Mock()
		self.doc.insert.return_value = self.log
		self.mail = Mock(return_value=SimpleNamespace(name="test-queue"))
		self.data = {"date": "2026-10-30", "company": "Test Company",
			"birthdays": [{"employee_name": "Test"}], "anniversaries": []}
		self.account = Mock(return_value=object())
		for target, name, value in (
			(frappe, "conf", {"hr_celebration_digest": self.settings}),
			(frappe, "db", self.db), (frappe, "get_doc", Mock(return_value=self.doc)),
			(frappe, "sendmail", self.mail), (digest, "preview", Mock(return_value=self.data)),
			(digest.EmailAccount, "find_outgoing", self.account),
		):
			patcher = patch.object(target, name, value, create=True)
			patcher.start()
			self.addCleanup(patcher.stop)

	def test_disabled_is_noop_without_reading_employees(self):
		self.settings["enabled"] = False
		self.assertEqual(digest.queue_daily_digest()["status"], "disabled")
		digest.preview.assert_not_called()
		self.mail.assert_not_called()

	def test_empty_day_does_not_create_queue_or_log(self):
		self.data["birthdays"] = []
		self.assertEqual(digest.queue_daily_digest()["status"], "empty")
		self.doc.insert.assert_not_called()
		self.mail.assert_not_called()

	def test_existing_log_prevents_requeue_even_when_queue_deleted(self):
		self.db.exists.return_value = True
		self.assertEqual(digest.queue_daily_digest()["status"], "already_queued")
		self.mail.assert_not_called()

	def test_concurrent_unique_insert_prevents_second_queue(self):
		self.doc.insert.side_effect = frappe.DuplicateEntryError
		self.assertEqual(digest.queue_daily_digest()["status"], "already_queued")
		self.mail.assert_not_called()

	def test_missing_sender_fails_before_log(self):
		self.account.return_value = None
		with self.assertRaises(frappe.OutgoingEmailError):
			digest.queue_daily_digest()
		self.doc.insert.assert_not_called()

	def test_one_combined_deferred_email_and_log_without_commit(self):
		self.data["anniversaries"] = [{"employee_name": "Another", "years": 2}]
		self.assertEqual(digest.queue_daily_digest()["status"], "queued")
		self.mail.assert_called_once()
		kwargs = self.mail.call_args.kwargs
		self.assertEqual(kwargs["recipients"], ["hr@example.test"])
		self.assertTrue(kwargs["delayed"])
		self.assertFalse(kwargs["now"])
		self.assertIn("Narozeniny", kwargs["message"])
		self.assertIn("Pracovní výročí", kwargs["message"])
		self.log.db_set.assert_called_once_with("email_queue", "test-queue", update_modified=False)
		self.db.commit.assert_not_called()

	def test_queue_failure_propagates_for_transaction_rollback(self):
		self.mail.side_effect = RuntimeError("queue unavailable")
		with self.assertRaises(RuntimeError):
			digest.queue_daily_digest()
		self.log.db_set.assert_not_called()
		self.db.commit.assert_not_called()

	def test_missing_queue_result_fails_for_rollback(self):
		self.mail.return_value = []
		with self.assertRaises(RuntimeError):
			digest.queue_daily_digest()
		self.log.db_set.assert_not_called()


class TestPreview(unittest.TestCase):
	def test_preview_enforces_company_and_active_status_without_writes(self):
		with patch.object(frappe, "db", Mock(), create=True) as db, patch.object(
			frappe, "get_all", return_value=[], create=True
		) as get_all:
			db.exists.return_value = True
			self.assertEqual(digest.preview("Company A", "2026-10-30")["birthdays"], [])
			self.assertEqual(get_all.call_args.kwargs["filters"], {"company": "Company A", "status": "Active"})
			db.commit.assert_not_called()

	def test_missing_company_fails_closed(self):
		with self.assertRaises(ValueError):
			digest.preview(None)
