"""Synthetic unit tests: never queue real mail or write to a site."""

import json
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


class TestQueue(unittest.TestCase):
	def setUp(self):
		self.settings = {"enabled": True, "company": "Test Company"}
		self.db = Mock()
		self.db.exists.return_value = False
		self.log = Mock(name="log")
		self.log.name = "daily-log"
		self.doc = Mock()
		self.doc.insert.return_value = self.log
		self.mail = Mock()
		self.mail.side_effect = [SimpleNamespace(name="queue-1"), SimpleNamespace(name="queue-2")]
		self.db.get_value.side_effect = lambda doctype, user, field: user
		def get_doc(data):
			self.assertEqual(data["doctype"], digest.LOG_DOCTYPE, "No in-app notifications may be created")
			return self.doc
		self.data = {"date": "2026-10-30", "company": "Test Company",
			"birthdays": [{"employee_name": "Test"}], "anniversaries": []}
		for target, name, value in (
			(frappe, "conf", {"hr_celebration_digest": self.settings}),
			(frappe, "db", self.db), (frappe, "get_doc", get_doc),
			(frappe, "session", SimpleNamespace(user="Administrator")),
			(frappe, "sendmail", self.mail), (digest, "preview", Mock(return_value=self.data)),
			(digest, "_get_hr_users", Mock(return_value=["hr1@example.test", "hr2@example.test"])),
			(digest.EmailAccount, "find_outgoing", Mock(return_value=object())),
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

	def test_existing_log_prevents_repeated_emails(self):
		self.db.exists.return_value = True
		self.assertEqual(digest.queue_daily_digest()["status"], "already_queued")
		self.mail.assert_not_called()

	def test_concurrent_unique_insert_prevents_second_queue(self):
		self.doc.insert.side_effect = frappe.DuplicateEntryError
		self.assertEqual(digest.queue_daily_digest()["status"], "already_queued")
		self.mail.assert_not_called()

	def test_missing_outgoing_account_fails_before_writes(self):
		digest.EmailAccount.find_outgoing.return_value = None
		with self.assertRaises(frappe.OutgoingEmailError):
			digest.queue_daily_digest()
		self.doc.insert.assert_not_called()
		self.mail.assert_not_called()

	def test_separate_combined_email_per_hr_user_without_commit(self):
		self.data["anniversaries"] = [{"employee_name": "Another", "years": 2}]
		self.assertEqual(digest.queue_daily_digest()["status"], "queued")
		calls = [call.kwargs for call in self.mail.call_args_list]
		self.assertEqual([row["recipients"] for row in calls], [["hr1@example.test"], ["hr2@example.test"]])
		for row in calls:
			self.assertIn("Narozeniny", row["message"])
			self.assertIn("Pracovní výročí", row["message"])
			self.assertTrue(row["delayed"])
			self.assertFalse(row["now"])
			self.assertNotIn("cc", row)
			self.assertNotIn("bcc", row)
			self.assertEqual(row["sender"], "")
		self.log.db_set.assert_called_once_with({"emails_queued": 2, "email_queue_ids": json.dumps(["queue-1", "queue-2"])}, update_modified=False)
		self.db.commit.assert_not_called()

	def test_second_queue_failure_propagates_for_full_transaction_rollback(self):
		self.mail.side_effect = [SimpleNamespace(name="first-queue"), RuntimeError("insert unavailable")]
		with self.assertRaises(RuntimeError):
			digest.queue_daily_digest()
		self.log.db_set.assert_not_called()
		self.db.commit.assert_not_called()

	def test_no_hr_users_creates_no_log(self):
		digest._get_hr_users.return_value = []
		self.assertEqual(digest.queue_daily_digest()["status"], "no_recipients")
		self.doc.insert.assert_not_called()
		self.mail.assert_not_called()

	def test_per_recipient_permissions_filter_content(self):
		restricted = {**self.data, "birthdays": []}
		digest.preview.side_effect = [self.data, self.data, restricted]
		self.assertEqual(digest.queue_daily_digest()["recipients"], 1)
		self.mail.assert_called_once()
		self.assertEqual(self.mail.call_args.kwargs["recipients"], ["hr1@example.test"])
		self.assertEqual(digest.preview.call_args.kwargs, {"user": "hr2@example.test"})
		self.assertNotIn("Another", self.mail.call_args.kwargs["message"])

	def test_no_visible_events_creates_no_log(self):
		digest.preview.side_effect = [self.data, {**self.data, "birthdays": []}, {**self.data, "birthdays": []}]
		self.assertEqual(digest.queue_daily_digest()["status"], "no_recipients")
		self.doc.insert.assert_not_called()
		self.mail.assert_not_called()

	def test_legacy_recipient_is_ignored_and_explicit_sender_is_used(self):
		self.settings.update({"recipient": "old@example.test", "sender": "sender@example.test"})
		self.assertEqual(digest.queue_daily_digest()["status"], "queued")
		digest.EmailAccount.find_outgoing.assert_called_once_with(match_by_email="sender@example.test")
		for call in self.mail.call_args_list:
			self.assertEqual(call.kwargs["sender"], "sender@example.test")
			self.assertNotIn("old@example.test", call.kwargs["recipients"])

	def test_missing_queue_result_fails_for_rollback(self):
		self.mail.side_effect = None
		self.mail.return_value = []
		with self.assertRaises(RuntimeError):
			digest.queue_daily_digest()
		self.log.db_set.assert_not_called()
		self.db.commit.assert_not_called()

	def test_invalid_recipient_fails_before_any_writes(self):
		self.db.get_value.side_effect = None
		self.db.get_value.return_value = "bad@example.test,other@example.test"
		with self.assertRaises(ValueError):
			digest.queue_daily_digest()
		self.doc.insert.assert_not_called()
		self.mail.assert_not_called()

	def test_recipient_uses_user_email_instead_of_user_id(self):
		self.db.get_value.side_effect = lambda doctype, user, field: "delivery-" + user
		digest.queue_daily_digest()
		self.assertEqual(self.mail.call_args.kwargs["recipients"], ["delivery-hr2@example.test"])

	def test_different_visible_events_produce_different_messages(self):
		first = {**self.data, "birthdays": [{"employee_name": "Visible A"}]}
		second = {**self.data, "birthdays": [{"employee_name": "Visible B"}]}
		digest.preview.side_effect = [self.data, first, second]
		digest.queue_daily_digest()
		messages = [call.kwargs["message"] for call in self.mail.call_args_list]
		self.assertIn("Visible A", messages[0])
		self.assertNotIn("Visible B", messages[0])
		self.assertIn("Visible B", messages[1])
		self.assertNotIn("Visible A", messages[1])


class TestRecipients(unittest.TestCase):
	def test_administrator_is_excluded_even_with_hr_role_and_all_permissions(self):
		with patch.object(frappe, "get_all", side_effect=[
			["Administrator", "hr@example.test"], ["Administrator", "hr@example.test"]
		], create=True), patch.object(frappe, "has_permission", autospec=True, return_value=True) as permission:
			self.assertEqual(digest._get_hr_users("Company A"), ["hr@example.test"])
			self.assertTrue(all(call.kwargs["user"] != "Administrator" for call in permission.call_args_list))

	def test_explicit_role_enabled_desk_users_and_permissions(self):
		with patch.object(frappe, "get_all", create=True) as query, patch.object(
			frappe, "has_permission", autospec=True
		) as permission:
			query.side_effect = [["a", "b", "a"], ["a", "b", "a"]]
			permission.side_effect = lambda doctype, *args, **kwargs: kwargs["user"] == "a"
			self.assertEqual(digest._get_hr_users("Company A"), ["a"])
			self.assertEqual(query.call_args_list[0].kwargs["filters"], {
				"role": "HR User", "parenttype": "User", "parentfield": "roles",
			})
			self.assertEqual(query.call_args_list[1].kwargs["filters"]["enabled"], 1)
			self.assertEqual(query.call_args_list[1].kwargs["filters"]["user_type"], "System User")

	def test_no_role_assignments_returns_no_users(self):
		with patch.object(frappe, "get_all", return_value=[], create=True) as query:
			self.assertEqual(digest._get_hr_users("Company A"), [])
			query.assert_called_once()

	def test_app_and_email_notification_preferences_do_not_gate_digest(self):
		from frappe.desk.doctype.notification_settings import notification_settings as settings

		with patch.object(frappe, "get_all", side_effect=[["a"], ["a"]], create=True), patch.object(
			settings, "is_notifications_enabled", side_effect=AssertionError("Must ignore app preferences")
		), patch.object(settings, "is_email_notifications_enabled", side_effect=AssertionError("Must ignore alert email preferences")), patch.object(
			frappe, "has_permission", autospec=True, return_value=True
		):
			self.assertEqual(digest._get_hr_users("Company A"), ["a"])

	def test_address_accepts_only_single_plain_mailbox(self):
		for value in (None, "", "invalid", "a@example.test,b@example.test", "Name <a@example.test>",
			"a@example.test\r\nBcc:b@example.test", "a@example.test;b@example.test"):
			with self.subTest(value=value), self.assertRaises(ValueError):
				digest._address(value)
		self.assertEqual(digest._address(" hr@example.test "), "hr@example.test")


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

	def test_user_preview_uses_permission_checked_query_without_page_limit(self):
		with patch.object(frappe, "db", Mock(), create=True) as db, patch.object(
			frappe, "get_list", return_value=[], create=True
		) as get_list, patch.object(frappe, "get_all", create=True) as get_all:
			db.exists.return_value = True
			digest.preview("Company A", "2026-10-30", user="hr@example.test")
			self.assertEqual(get_list.call_args.kwargs["user"], "hr@example.test")
			self.assertEqual(get_list.call_args.kwargs["limit_page_length"], 0)
			self.assertNotIn("ignore_permissions", get_list.call_args.kwargs)
			get_all.assert_not_called()
