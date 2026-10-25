import hashlib
import importlib.util
import io
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image

from crun import results
from crun.client import CRUNError


class ResultsTests(unittest.TestCase):
    def test_polling_queries_only_the_same_existing_id(self):
        client = MagicMock()
        client.get_task.side_effect = [{"task_id": "fixture_task", "status": state} for state in ("pending", "running", "success")]
        with patch.object(results.time, "sleep"):
            record = results.wait_for_task(client, "fixture_task", timeout_seconds=60)
        self.assertEqual(record["status"], "success")
        self.assertEqual([call.args for call in client.get_task.call_args_list], [("fixture_task",)] * 3)
        client.create_task.assert_not_called()
        client.upload_bytes.assert_not_called()

    def test_timeout_retains_id_and_does_not_replace_task(self):
        client = MagicMock()
        client.get_task.return_value = {"status": "pending"}
        with self.assertRaises(CRUNError) as raised:
            results.wait_for_task(client, "fixture_task", timeout_seconds=0)
        self.assertIn("fixture_task", str(raised.exception))
        self.assertIn("Get Result again", str(raised.exception))
        self.assertEqual(client.get_task.call_count, 1)
        client.create_task.assert_not_called()

    def test_failed_unknown_mismatched_and_transport_states_preserve_id(self):
        for response in ({"status": "failed"}, {"status": "unknown"}, {"task_id": "other_task", "status": "success"}, CRUNError("PRIVATE")):
            client = MagicMock()
            if isinstance(response, Exception):
                client.get_task.side_effect = response
            else:
                client.get_task.return_value = response
            with self.subTest(response=response), self.assertRaises(CRUNError) as raised:
                results.wait_for_task(client, "fixture_task")
            self.assertIn("fixture_task", str(raised.exception))
            self.assertNotIn("PRIVATE", str(raised.exception))
            client.create_task.assert_not_called()

    def test_load_result_decodes_native_media_and_preserves_actual_cost(self):
        marker = object()
        for kind, function in (("image", "image_from_file"), ("video", "video_from_file")):
            with patch.object(results, "CRUNClient") as client, patch.object(results, "download_to_output", return_value=Path("fixture.media")) as download, patch.object(results, function, return_value=marker):
                client.return_value.get_task.return_value = {"status": "success", "credits": 2.5, "result": {"media_urls": ["https://cdn.example.com/file"]}}
                result = results.load_result("fixture_task", kind=kind)
            self.assertEqual(result, (marker, "https://cdn.example.com/file", 2.5, "fixture_task"))
            self.assertEqual(download.call_args.kwargs, {"kind": kind})

    def test_missing_cost_is_unavailable_and_invalid_cost_is_not_zero(self):
        for value in (None, True, -1, "3", float("nan")):
            record = {"status": "success", "result": {"media_urls": ["https://cdn.example.com/file.png"]}}
            if value is not None:
                record["credits"] = value
            with patch.object(results, "CRUNClient") as client, patch.object(results, "download_to_output", return_value=Path("fixture.png")), patch.object(results, "image_from_file", return_value=object()):
                client.return_value.get_task.return_value = record
                if value is None:
                    self.assertEqual(results.load_result("fixture_task", kind="image")[2], -1)
                else:
                    with self.assertRaises(CRUNError):
                        results.load_result("fixture_task", kind="image")

    def test_missing_media_or_download_failure_does_not_lose_id(self):
        for result in (None, {}, {"media_urls": []}):
            with patch.object(results, "CRUNClient") as client:
                client.return_value.get_task.return_value = {"status": "success", "result": result}
                with self.assertRaises(CRUNError) as raised:
                    results.load_result("fixture_task", kind="image")
            self.assertIn("fixture_task", str(raised.exception))
        with patch.object(results, "CRUNClient") as client, patch.object(results, "download_to_output", side_effect=PermissionError("PRIVATE_PATH")):
            client.return_value.get_task.return_value = {"status": "success", "result": {"media_urls": ["https://cdn.example.com/file.png"]}}
            with self.assertRaises(CRUNError) as raised:
                results.load_result("fixture_task", kind="image")
        self.assertIn("fixture_task", str(raised.exception))
        self.assertNotIn("PRIVATE_PATH", str(raised.exception))

    def test_private_dns_and_local_urls_are_rejected_before_download(self):
        addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]
        with patch.object(results.socket, "getaddrinfo", return_value=addresses), patch.object(results.requests, "Session", side_effect=AssertionError("No request")):
            for url in ("https://cdn.example.com/file.png", "https://127.0.0.1/file", "https://crun-next.invalid/local/fake.png"):
                with self.assertRaises(CRUNError):
                    results.download_to_output(url, kind="image")

    def test_download_stream_is_bounded_credential_free_and_persisted_by_hash(self):
        content = b"fixture-media"
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            transport = MagicMock()
            transport.__enter__.return_value = transport
            response = transport.get.return_value.__enter__.return_value
            response.status_code = 200
            response.headers = {"Content-Length": str(len(content))}
            response.iter_content.return_value = [content]
            addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]
            with patch.object(results.socket, "getaddrinfo", return_value=addresses), patch.object(results.requests, "Session", return_value=transport), patch.object(results, "_output_directory", return_value=Path(directory)):
                path = results.download_to_output("https://cdn.example.com/file.mp4", kind="video")
            self.assertEqual(path.read_bytes(), content)
            self.assertIn(hashlib.sha256(content).hexdigest(), path.name)
            self.assertEqual(transport.get.call_args.kwargs["headers"], {"Accept": "video/*"})
            self.assertFalse(transport.get.call_args.kwargs["allow_redirects"])
            self.assertFalse(transport.trust_env)
            self.assertFalse(list(Path(directory).glob("*.part")))

    def test_oversize_stream_and_redirect_do_not_leave_partial_files(self):
        for status in (200, 302):
            with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
                transport = MagicMock()
                transport.__enter__.return_value = transport
                response = transport.get.return_value.__enter__.return_value
                response.status_code = status
                response.headers = {}
                response.iter_content.return_value = [b"more than four bytes"]
                with patch.object(results, "_public_download_url", return_value="https://cdn.example.com/file"), patch.object(results.requests, "Session", return_value=transport), patch.object(results, "_output_directory", return_value=Path(directory)), patch.object(results, "MAX_IMAGE_BYTES", 4):
                    with self.assertRaises(CRUNError):
                        results.download_to_output("https://cdn.example.com/file", kind="image")
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_real_png_decodes_to_native_image_when_torch_is_available(self):
        try:
            import torch
        except ImportError:
            self.skipTest("Host-provided PyTorch is absent outside ComfyUI")
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "fixture.png"
            Image.new("RGB", (3, 2), (255, 128, 0)).save(path)
            image = results.image_from_file(path)
        self.assertIsInstance(image, torch.Tensor)
        self.assertEqual(tuple(image.shape), (1, 2, 3, 3))
        self.assertEqual(float(image[0, 0, 0, 0]), 1)

    def test_result_nodes_expose_native_outputs_and_task_id_socket(self):
        import result_nodes
        for node, kind in ((result_nodes.CRUNGetImageResult, "IMAGE"), (result_nodes.CRUNGetVideoResult, "VIDEO")):
            self.assertEqual(node.RETURN_TYPES[0], kind)
            self.assertTrue(node.INPUT_TYPES()["required"]["task_id"][1]["forceInput"])
            with patch.object(result_nodes, "load_result", return_value=(object(), "https://cdn.example.com/file", -1, "fixture_task")) as load:
                output = node().load("fixture_task", timeout_seconds=0)
            self.assertEqual(output["result"][3], "fixture_task")
            self.assertEqual(load.call_args.kwargs["kind"], kind.lower())

    def test_empty_upstream_task_id_blocks_preview_without_network(self):
        import result_nodes
        for node in (result_nodes.CRUNGetImageResult, result_nodes.CRUNGetVideoResult):
            with patch.object(result_nodes, "load_result", side_effect=AssertionError("Prepare must not retrieve")):
                output = node().load("")
            self.assertEqual(output["result"][1:], ("", -1.0, ""))
            self.assertIn("prepare/estimate", output["ui"]["text"][0])


if __name__ == "__main__":
    unittest.main()
