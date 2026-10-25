import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from crun import settings


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="crun-test-", dir=Path(__file__).resolve().parent)
        self.environment = patch.dict(os.environ, {"CRUN_NEXT_CONFIG_DIR": self.temporary.name, "CRUN_API_KEY": ""})
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.temporary.cleanup()

    def test_missing_config_read_does_not_create(self):
        self.assertEqual(settings.get_api_key(), "")
        self.assertFalse(settings.settings_path().exists())
        self.assertEqual(settings.public_status()["source"], "none")

    def test_save_get_and_clear(self):
        settings.save_api_key("test-placeholder-not-a-real-key")
        self.assertEqual(settings.get_api_key(), "test-placeholder-not-a-real-key")
        status = settings.public_status()
        self.assertTrue(status["configured"])
        self.assertEqual(status["source"], "saved")
        self.assertNotIn("test-placeholder-not-a-real-key", json.dumps(status))
        settings.clear_api_key()
        self.assertEqual(settings.get_api_key(), "")

    def test_environment_overrides_saved(self):
        settings.save_api_key("test-saved-key-placeholder")
        with patch.dict(os.environ, {"CRUN_API_KEY": "test-environment-placeholder"}):
            self.assertEqual(settings.get_api_key(), "test-environment-placeholder")
            self.assertEqual(settings.public_status()["source"], "environment")
            settings.clear_api_key()
            self.assertEqual(settings.get_api_key(), "test-environment-placeholder")

    def test_short_secret_not_exposed(self):
        with patch.dict(os.environ, {"CRUN_API_KEY": "abc"}):
            self.assertNotIn("abc", json.dumps(settings.public_status()))

    def test_invalid_key_rejected(self):
        for value in ["", " \n ", "test\nsecret", "x" * 8193, None]:
            with self.subTest(value=str(value)[:10]), self.assertRaises(settings.SettingsError):
                settings.save_api_key(value)
        self.assertFalse(settings.settings_path().exists())

    def test_corrupt_config_safe_status(self):
        settings.settings_path().write_text('{"api_key":"PRIVATE",broken', encoding="utf-8")
        with self.assertRaises(settings.SettingsError) as raised:
            settings.get_api_key()
        self.assertNotIn("PRIVATE", str(raised.exception))
        status = settings.public_status()
        self.assertFalse(status["configured"])
        self.assertNotIn("PRIVATE", json.dumps(status))

    def test_no_windows_plaintext_fallback(self):
        with patch.object(settings, "_IS_WINDOWS", True), patch.object(settings, "_dpapi", side_effect=settings.SettingsError("DPAPI unavailable")):
            with self.assertRaises(settings.SettingsError):
                settings.save_api_key("test-only-placeholder")
        self.assertFalse(settings.settings_path().exists())

    def test_atomic_replace_preserves_saved_on_failure(self):
        settings.save_api_key("test-old-key-placeholder")
        before = settings.settings_path().read_bytes()
        with patch.object(settings.os, "replace", side_effect=OSError("PRIVATE")):
            with self.assertRaises(settings.SettingsError) as raised:
                settings.save_api_key("test-new-key-placeholder")
        self.assertNotIn("PRIVATE", str(raised.exception))
        self.assertEqual(settings.settings_path().read_bytes(), before)
        self.assertEqual(list(Path(self.temporary.name).glob("*.tmp")), [])

    def test_connection_receipt_survives_module_reload_without_exposing_key(self):
        import importlib

        key = "test-persistent-key-placeholder"
        settings.save_api_key(key)
        original_credential = settings.settings_path().read_bytes()
        with patch.object(settings.time, "time", return_value=1234567890):
            settings.record_connection("connected", 0)
        importlib.reload(settings)
        status = settings.public_status()
        self.assertEqual(status["validation_state"], "connected")
        self.assertEqual(status["last_balance"], 0)
        self.assertEqual(status["checked_at"], 1234567890)
        self.assertNotIn(key, settings.status_path().read_text(encoding="utf-8"))
        self.assertNotIn("credential_fingerprint", status)
        self.assertEqual(settings.settings_path().read_bytes(), original_credential)

    def test_changed_key_invalidates_old_connection(self):
        settings.save_api_key("test-old-placeholder-key")
        settings.record_connection("connected", 120)
        settings.save_api_key("test-new-placeholder-key")
        status = settings.public_status()
        self.assertTrue(status["configured"])
        self.assertEqual(status["validation_state"], "saved")
        self.assertIsNone(status["last_balance"])
        self.assertEqual(status["checked_at"], 0)
        self.assertFalse(settings.status_path().exists())

    def test_same_key_keeps_connection_receipt(self):
        key = "test-same-placeholder-key"
        settings.save_api_key(key)
        settings.record_connection("connected", 120)
        settings.save_api_key(key)
        self.assertEqual(settings.public_status()["last_balance"], 120)

    def test_clear_key_also_clears_historical_balance(self):
        settings.save_api_key("test-placeholder-key")
        settings.record_connection("connected", 120)
        settings.clear_api_key()
        status = settings.public_status()
        self.assertFalse(settings.status_path().exists())
        self.assertEqual(status["validation_state"], "not_configured")
        self.assertIsNone(status["last_balance"])

    def test_environment_change_does_not_inherit_other_account_receipt(self):
        with patch.dict(os.environ, {"CRUN_API_KEY": "test-environment-placeholder-one"}):
            settings.record_connection("connected", 42)
        with patch.dict(os.environ, {"CRUN_API_KEY": "test-environment-placeholder-two"}):
            status = settings.public_status()
            self.assertEqual(status["validation_state"], "saved")
            self.assertIsNone(status["last_balance"])

    def test_failed_check_keeps_balance_timestamp_historical(self):
        settings.save_api_key("test-placeholder-key")
        with patch.object(settings.time, "time", return_value=1000):
            settings.record_connection("connected", 42)
        with patch.object(settings.time, "time", return_value=2000):
            settings.record_connection("unreachable")
        status = settings.public_status()
        self.assertEqual(status["validation_state"], "unreachable")
        self.assertEqual(status["last_balance"], 42)
        self.assertEqual(status["checked_at"], 2000)
        self.assertEqual(status["balance_checked_at"], 1000)

    def test_bad_connection_receipts_and_balances_are_safe(self):
        settings.save_api_key("test-placeholder-key")
        settings.status_path().write_text("not valid json", encoding="utf-8")
        self.assertEqual(settings.public_status()["validation_state"], "saved")
        for value in [False, -1, float("nan"), float("inf"), "42"]:
            with self.subTest(value=value), self.assertRaises(settings.SettingsError):
                settings.record_connection("connected", value)

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI integration")
    def test_windows_file_is_encrypted(self):
        value = "test-placeholder-not-a-real-key"
        settings.save_api_key(value)
        content = settings.settings_path().read_text(encoding="utf-8")
        self.assertNotIn(value, content)
        self.assertEqual(json.loads(content)["credential"]["format"], "dpapi")
        self.assertEqual(settings.get_api_key(), value)

    @unittest.skipUnless(os.name == "posix", "Unix permission integration")
    def test_unix_permissions(self):
        settings.save_api_key("test-placeholder-not-a-real-key")
        path = settings.settings_path()
        self.assertEqual(path.stat().st_mode & 0o077, 0)
        os.chmod(path, 0o644)
        with self.assertRaises(settings.SettingsError):
            settings.get_api_key()


if __name__ == "__main__":
    unittest.main()
