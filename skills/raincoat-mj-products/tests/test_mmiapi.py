"""Response parsing and the guest-session trap, with no network access."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import mmiapi  # noqa: E402


class LoggedInTests(unittest.TestCase):
    def test_guest_payload_from_the_platform(self):
        # Real /api/user response for an anonymous visitor: status ok, usertype logged_out.
        guest = {
            "username": None,
            "nick": None,
            "usertype": "logged_out",
            "all_site": "no_uni",
        }
        self.assertFalse(mmiapi.is_logged_in(guest))

    def test_real_user(self):
        self.assertTrue(mmiapi.is_logged_in({"username": "a@b.com", "usertype": "vip"}))
        self.assertTrue(mmiapi.is_logged_in({"nick": "小明", "usertype": "normal"}))

    def test_empty_and_none(self):
        self.assertFalse(mmiapi.is_logged_in(None))
        self.assertFalse(mmiapi.is_logged_in({}))


class ExtractTests(unittest.TestCase):
    def test_result_data_shape(self):
        payload = {"status": "ok", "result": {"data": [{"id": 1}], "total": 42}}
        rows, total = mmiapi.extract_rows(payload)
        self.assertEqual(rows, [{"id": 1}])
        self.assertEqual(total, 42)

    def test_datatables_flat_shape(self):
        payload = {"aaData": [{"id": 1}, {"id": 2}], "iTotalRecords": 2}
        rows, total = mmiapi.extract_rows(payload)
        self.assertEqual(len(rows), 2)
        self.assertEqual(total, 2)

    def test_bare_list(self):
        rows, total = mmiapi.extract_rows([{"id": 1}])
        self.assertEqual(rows, [{"id": 1}])
        self.assertIsNone(total)

    def test_nested_one_level(self):
        payload = {"result": {"items": {"list": [{"id": 9}]}}}
        rows, _ = mmiapi.extract_rows(payload)
        self.assertEqual(rows, [{"id": 9}])

    def test_empty_result_is_not_silently_ok(self):
        with self.assertRaises(mmiapi.SchemaChanged):
            mmiapi.extract_rows({"status": "ok", "result": {}})


class ErrorTests(unittest.TestCase):
    def test_mapping(self):
        self.assertIsInstance(
            mmiapi.error_to_exception({"error_code": -401, "error_msg": "未登录"}),
            mmiapi.AuthRequired,
        )
        self.assertIsInstance(
            mmiapi.error_to_exception({"error_code": -403}), mmiapi.Forbidden
        )
        self.assertIsInstance(
            mmiapi.error_to_exception({"error_code": -404}), mmiapi.NotFound
        )
        self.assertIsInstance(
            mmiapi.error_to_exception({"error_code": 3, "error_msg": "Unkown platform id"}),
            mmiapi.PlatformUnsupported,
        )

    def test_chinese_message_from_nested_dict(self):
        exc = mmiapi.error_to_exception(
            {"error_code": -401, "error_msg": {"msg": "您尚未登录", "msg_en": "not logged in"}}
        )
        self.assertIn("您尚未登录", str(exc))


if __name__ == "__main__":
    unittest.main()
