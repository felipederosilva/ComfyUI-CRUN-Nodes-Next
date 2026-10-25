import unittest

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
        self.assertFalse(hasattr(client, "create_task"))

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
