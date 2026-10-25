"""Exercise the actual aiohttp bridge offline, including credential boundaries."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from crun import server


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.env = patch.dict(os.environ, {"CRUN_NEXT_CONFIG_DIR": self.directory.name, "CRUN_API_KEY": ""})
        self.env.start()
        app = web.Application()
        routes = web.RouteTableDef()
        server.register_routes(routes)
        server.register_routes(routes)
        app.add_routes(routes)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()
        response = await self.client.get("/crun-next/status")
        self.assertEqual(response.status, 200)
        self.nonce = (await response.json())["nonce"]

    async def asyncTearDown(self):
        await self.client.close()
        self.env.stop()
        self.directory.cleanup()

    def headers(self, **extra):
        return {"X-CRUN-Nonce": self.nonce, **extra}

    async def test_status_does_not_call_provider_or_create_credentials(self):
        with patch.object(server, "CRUNClient", side_effect=AssertionError("No remote requests")):
            response = await self.client.get("/crun-next/status")
            payload = await response.json()
        self.assertFalse(payload["configured"])
        self.assertNotIn("api_key", payload)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(list(Path(self.directory.name).iterdir()), [])

    async def test_save_status_clear_never_returns_secret(self):
        fake = "fake-crun-local-test-key-123456789"
        response = await self.client.post("/crun-next/credentials", json={"api_key": fake}, headers=self.headers())
        self.assertEqual(response.status, 200)
        self.assertNotIn(fake, await response.text())
        response = await self.client.get("/crun-next/status")
        body = await response.json()
        self.assertTrue(body["configured"])
        self.assertNotIn(fake, json.dumps(body))
        response = await self.client.post("/crun-next/credentials/clear", json={}, headers=self.headers())
        self.assertFalse((await response.json())["configured"])

    async def test_post_requires_nonce(self):
        response = await self.client.post("/crun-next/credentials", json={"api_key": "fake"})
        self.assertEqual(response.status, 403)

    async def test_cross_origin_and_rebinding_rejected(self):
        for headers in ({"Origin": "https://attacker.example"}, {"Host": "attacker.example"}):
            response = await self.client.post("/crun-next/connection", json={}, headers=self.headers(**headers))
            self.assertEqual(response.status, 403)

    async def test_bad_json_and_oversized_body(self):
        for body in ("[]", "broken", '{"api_key":"' + "x" * 70000 + '"}'):
            response = await self.client.post("/crun-next/credentials", data=body, headers=self.headers())
            self.assertEqual(response.status, 400)

    async def test_live_check_uses_mock_balance(self):
        with patch.object(server, "CRUNClient") as client:
            client.return_value.get_balance.return_value = 123.5
            response = await self.client.post("/crun-next/connection", json={}, headers=self.headers())
        self.assertEqual((await response.json())["balance"], 123.5)

    async def test_tools_are_local_and_available_in_nodes_menu(self):
        with patch.object(server, "CRUNClient", side_effect=AssertionError("No remote requests")):
            response = await self.client.get("/crun-next/tools", headers=self.headers())
            payload = await response.json()
        self.assertTrue(payload["tools"])
        self.assertTrue(all(tool["status"] == "node_available" for tool in payload["tools"]))
        self.assertTrue(all(tool["default_mode"] == "prepare" for tool in payload["tools"]))

    async def test_models_load_locally_without_provider_requests(self):
        with patch.object(server, "CRUNClient", side_effect=AssertionError("No remote requests")):
            response = await self.client.get("/crun-next/models", headers=self.headers())
            payload = await response.json()
        self.assertEqual(response.status, 200)
        self.assertGreaterEqual(payload["summary"]["entry_count"], 274)

    async def test_refresh_is_explicit_and_restart_is_reported(self):
        snapshot = {"entries": [], "summary": {"entry_count": 0}}
        with patch.object(server, "refresh_catalog", return_value=snapshot) as refresh:
            response = await self.client.post("/crun-next/models/refresh", json={}, headers=self.headers())
            payload = await response.json()
        refresh.assert_called_once()
        self.assertTrue(payload["restart_required"])

    async def test_effects_fetch_provider_specific_catalog(self):
        with patch.object(server, "CRUNClient") as client:
            client.return_value.list_effects.return_value = {"templates": [{"key": "test", "name": "Test", "credit": 5}]}
            response = await self.client.post("/crun-next/effects/catalog", json={"provider": "kling"}, headers=self.headers())
            payload = await response.json()
            client.return_value.list_effects.assert_called_once_with("kling")
        self.assertEqual(payload["cards"][0]["id"], "test")

    async def test_invalid_provider_never_reaches_client(self):
        with patch.object(server, "CRUNClient", side_effect=AssertionError("No remote requests")):
            response = await self.client.post("/crun-next/effects/catalog", json={"provider": "other"}, headers=self.headers())
        self.assertEqual(response.status, 400)

    async def test_unexpected_exception_is_sanitized(self):
        with patch.object(server, "CRUNClient", side_effect=RuntimeError("SECRET_DO_NOT_RETURN")):
            response = await self.client.post("/crun-next/connection", json={}, headers=self.headers())
        self.assertEqual(response.status, 500)
        self.assertNotIn("SECRET_DO_NOT_RETURN", await response.text())


class BoundaryTests(unittest.TestCase):
    def test_remote_peer_is_rejected(self):
        class Request:
            remote = "203.0.113.1"
            host = "127.0.0.1:8188"
            headers = {}
        with self.assertRaises(web.HTTPForbidden):
            server.check_local_request(Request(), nonce=False)


if __name__ == "__main__":
    unittest.main()
