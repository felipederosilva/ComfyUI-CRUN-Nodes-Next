import unittest
from unittest.mock import MagicMock, patch

import requests

from crun.client import API_BASE, CRUNClient, CRUNError


class Response:
    def __init__(self, body=None, status=200):
        self.body, self.status_code = body, status

    def json(self):
        if isinstance(self.body, Exception):
            raise self.body
        return self.body


class Session:
    def __init__(self, response):
        self.response, self.calls = response, []

    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class ClientTests(unittest.TestCase):
    def client(self, data=None, *, status=200, body=None):
        session = Session(Response(body if body is not None else {"code": 200, "data": data}, status))
        return CRUNClient("test-placeholder-not-a-real-key", session), session

    def test_balance_and_fixed_host_auth(self):
        client, session = self.client({"balance": 31.5})
        self.assertEqual(client.get_balance(), 31.5)
        args, kwargs = session.calls[0]
        self.assertEqual(args, ("GET", API_BASE + "/api/v1/client/account/balance"))
        self.assertEqual(kwargs["headers"]["x-api-key"], "test-placeholder-not-a-real-key")
        self.assertFalse(kwargs["allow_redirects"])
        self.assertEqual(kwargs["timeout"], (10, 60))

    def test_zero_balance(self):
        client, _ = self.client({"balance": 0})
        self.assertEqual(client.get_balance(), 0)

    def test_invalid_balances(self):
        for amount in [None, True, -1, "nan", "inf", "wrong"]:
            with self.subTest(amount=amount), self.assertRaises(CRUNError):
                self.client({"balance": amount})[0].get_balance()

    def test_missing_balance(self):
        with self.assertRaises(CRUNError):
            self.client({})[0].get_balance()

    def test_task_parameters(self):
        client, session = self.client({"task_id": "test_123", "status": "success", "credits": 2})
        self.assertEqual(client.get_task("test_123")["credits"], 2)
        self.assertEqual(session.calls[0][1]["params"], {"task_id": "test_123"})

    def test_task_id_validation_no_network(self):
        client, session = self.client({})
        for value in ["", "../secret", "task?key=foo", "task\nfoo", 12]:
            with self.subTest(value=value), self.assertRaises(CRUNError):
                client.get_task(value)
        self.assertEqual(session.calls, [])

    def test_effect_provider_paths(self):
        for provider in ["kling", "bytedance", "vidu"]:
            client, session = self.client({"templates": []})
            self.assertEqual(client.list_effects(provider), {"templates": []})
            self.assertTrue(session.calls[0][0][1].endswith(provider + "-templates"))

    def test_list_catalog_normalized(self):
        client, _ = self.client([{"key": "example"}])
        self.assertEqual(client.list_effects("kling")["total"], 1)

    def test_effects_reads_all_pages_and_rejects_repeated_pages(self):
        from unittest.mock import patch
        client, _ = self.client({})
        pages = [{"total": 2, "templates": [{"key": "a"}]}, {"total": 2, "templates": [{"key": "b"}]}]
        with patch.object(client, "_request", side_effect=pages) as request:
            self.assertEqual(len(client.list_effects("kling")["templates"]), 2)
            self.assertEqual(request.call_args_list[1].kwargs["params"]["page"], 2)
        with patch.object(client, "_request", return_value=pages[0]):
            with self.assertRaises(CRUNError):
                client.list_effects("kling")

    def test_invalid_provider_no_network(self):
        client, session = self.client({})
        with self.assertRaises(CRUNError):
            client.list_effects("https://external.invalid")
        self.assertEqual(session.calls, [])

    def test_estimate_is_not_generation(self):
        client, session = self.client({"credits": 4, "estimated": True})
        self.assertEqual(client.estimate_credits("example/model", {"prompt": "A fictional demo"}), {"credits": 4, "estimated": True})
        args, kwargs = session.calls[0]
        self.assertEqual(args[0], "POST")
        self.assertTrue(args[1].endswith("/estimate-credits"))
        self.assertEqual(kwargs["json"]["model"], "example/model")
        self.assertNotIn("callback_url", kwargs["json"])
        self.assertEqual(len(session.calls), 1)
        self.assertFalse(any(call[0][1].endswith("/CreateTask") for call in session.calls))

    def test_live_llm_inventory_uses_openai_shape_and_fixed_host(self):
        payload = {"object": "list", "data": [{"id": "test/chat"}]}
        client, session = self.client(body=payload)
        self.assertEqual(client.list_models(), payload)
        self.assertEqual(session.calls[0][0], ("GET", API_BASE + "/api/v1/models"))
        self.assertFalse(session.calls[0][1]["allow_redirects"])

    def test_submission_returns_id_once(self):
        client, session = self.client({"task_id": "fixture_task"})
        self.assertEqual(client.create_task("test/model", {"prompt": "Fictional"}), "fixture_task")
        self.assertEqual(len(session.calls), 1)
        self.assertTrue(session.calls[0][0][1].endswith("/CreateTask"))

    def test_native_upload_uses_fixed_ticket_and_credential_free_put(self):
        ticket = {"file_url": "https://cdn.example.com/temp/upload.png", "presigned_url": "https://store.example.com/bucket/upload.png?X-Amz-Signature=fixture"}
        client, api = self.client(ticket)
        storage = MagicMock()
        storage.__enter__.return_value = storage
        storage.request.return_value = Response(status=200)
        content = b"\x89PNG\r\n\x1a\nfixture"
        with patch("crun.client.requests.Session", return_value=storage):
            self.assertEqual(client.upload_bytes(content), ticket["file_url"])
        self.assertEqual(api.calls[0][0], ("GET", API_BASE + "/api/v1/client/files/upload-url"))
        self.assertEqual(api.calls[0][1]["params"], {"content_type": "image/png", "ext": ".png"})
        args, kwargs = storage.request.call_args
        self.assertEqual(args, ("PUT", ticket["presigned_url"]))
        self.assertEqual(kwargs["headers"], {"Content-Type": "image/png"})
        self.assertEqual(kwargs["data"], content)
        self.assertFalse(kwargs["allow_redirects"])
        self.assertFalse(storage.trust_env)
        self.assertEqual(storage.request.call_count, 1)

    def test_upload_rejects_private_urls_before_put_and_bad_bytes_before_ticket(self):
        client, api = self.client({"file_url": "https://cdn.example.com/file.png", "presigned_url": "https://127.0.0.1/private"})
        with patch("crun.client.requests.Session", side_effect=AssertionError("Do not PUT private URLs")):
            with self.assertRaises(CRUNError):
                client.upload_bytes(b"\x89PNG\r\n\x1a\nfixture")
        for content in (b"not a PNG", b"", "string"):
            with self.assertRaises(CRUNError):
                client.upload_bytes(content)
        self.assertEqual(len(api.calls), 1)

    def test_upload_error_is_sanitized_and_never_retried(self):
        ticket = {"file_url": "https://cdn.example.com/temp.png", "presigned_url": "https://store.example.com/temp.png?SECRET_SIGNATURE"}
        for outcome in (requests.Timeout("SECRET"), Response(status=302), Response(status=500)):
            client, api = self.client(ticket)
            storage = MagicMock()
            storage.__enter__.return_value = storage
            if isinstance(outcome, Exception):
                storage.request.side_effect = outcome
            else:
                storage.request.return_value = outcome
            with patch("crun.client.requests.Session", return_value=storage):
                with self.assertRaises(CRUNError) as raised:
                    client.upload_bytes(b"\x89PNG\r\n\x1a\nfixture")
            self.assertNotIn("SECRET", str(raised.exception))
            self.assertIn("No generation", str(raised.exception))
            self.assertEqual(storage.request.call_count, 1)

    def test_mp4_and_wav_use_the_same_credential_free_storage_contract(self):
        ticket = {"file_url": "https://cdn.example.com/media", "presigned_url": "https://store.example.com/upload"}
        for content, mime, extension in ((b"\x00\x00\x00\x18ftypisomfixture", "video/mp4", ".mp4"),
                                         (b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 32, "audio/wav", ".wav")):
            client, api = self.client(ticket)
            storage = MagicMock()
            storage.__enter__.return_value = storage
            storage.request.return_value = Response(status=200)
            with patch("crun.client.requests.Session", return_value=storage):
                self.assertEqual(client.upload_bytes(content, mime_type=mime, extension=extension), ticket["file_url"])
            self.assertEqual(api.calls[0][1]["params"], {"content_type": mime, "ext": extension})
            self.assertEqual(storage.request.call_args.kwargs["headers"], {"Content-Type": mime})
            self.assertFalse(storage.trust_env)
            self.assertEqual(storage.request.call_count, 1)
            with self.assertRaises(CRUNError):
                client.upload_bytes(content, mime_type="image/png", extension=".png")

    def test_ambiguous_submission_never_retries_or_suggests_resubmit(self):
        for response in [requests.Timeout("PRIVATE"), Response({}, 500), Response({}, 502), Response({"code": 500, "data": {}}), Response(ValueError("PRIVATE"))]:
            with self.subTest(response=type(response).__name__):
                session = Session(response)
                client = CRUNClient("test-key", session)
                with self.assertRaises(CRUNError) as raised:
                    client.create_task("test/model", {})
                self.assertIn("unknown", str(raised.exception))
                self.assertIn("Logs", str(raised.exception))
                self.assertNotIn("PRIVATE", str(raised.exception))
                self.assertEqual(len(session.calls), 1)

    def test_invalid_estimate(self):
        for data in [{"credits": 1}, {"credits": 1, "estimated": "yes"}, {"credits": -3, "estimated": False}]:
            with self.subTest(data=data), self.assertRaises(CRUNError):
                self.client(data)[0].estimate_credits("example", {})

    def test_invalid_estimate_inputs_no_network(self):
        client, session = self.client({})
        for model, inputs in [("", {}), ("example", []), ("example\n", {})]:
            with self.subTest(model=model), self.assertRaises(CRUNError):
                client.estimate_credits(model, inputs)
        self.assertEqual(session.calls, [])

    def test_provider_error_body_never_exposed(self):
        client, session = self.client(body={"code": 422, "message": "test-placeholder-not-a-real-key PRIVATE"})
        with self.assertRaises(CRUNError) as raised:
            client.get_balance()
        self.assertNotIn("PRIVATE", str(raised.exception))
        self.assertNotIn("test-placeholder", str(raised.exception))
        self.assertEqual(raised.exception.code, 422)
        self.assertEqual(len(session.calls), 1)

    def test_http_redirect_and_errors_not_retried(self):
        for status in [301, 401, 403, 429, 500]:
            client, session = self.client({}, status=status)
            with self.subTest(status=status), self.assertRaises(CRUNError):
                client.get_balance()
            self.assertEqual(len(session.calls), 1)

    def test_transport_errors_sanitized(self):
        for error in [requests.Timeout("PRIVATE_KEY"), requests.ConnectionError("PRIVATE_KEY")]:
            session = Session(error)
            client = CRUNClient("test-key", session)
            with self.assertRaises(CRUNError) as raised:
                client.get_balance()
            self.assertNotIn("PRIVATE_KEY", str(raised.exception))
            self.assertEqual(len(session.calls), 1)

    def test_invalid_json(self):
        client, _ = self.client(body=ValueError("PRIVATE"))
        with self.assertRaises(CRUNError) as raised:
            client.get_balance()
        self.assertNotIn("PRIVATE", str(raised.exception))

    def test_body_code_required(self):
        for body in [{"data": {}}, {"code": True, "data": {}}, [], {"code": 200}]:
            with self.subTest(body=body), self.assertRaises(CRUNError):
                self.client(body=body)[0].get_balance()

    def test_no_key_or_header_injection(self):
        for value in ["", "  ", "key\r\nInjected: x", None]:
            if value is None:
                continue
            with self.subTest(value=value), self.assertRaises(CRUNError):
                CRUNClient(value)


if __name__ == "__main__":
    unittest.main()
