"""Native media and verified task reuse: synthetic files, no provider calls."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace
import wave

from PIL import Image

from crun import results
from crun.client import CRUNError


class ResultReuseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.root = Path(self.temporary.name)
        self.assets = self.root / "assets"
        self.assets.mkdir()
        self.environment = patch.dict(os.environ, {
            "CRUN_NEXT_CONFIG_DIR": str(self.root / "config"),
            "CRUN_API_KEY": "synthetic-account-a-not-a-real-key",
        })
        self.environment.start()
        self.output = patch.object(results, "_output_directory", return_value=self.assets)
        self.output.start()
        self.network = patch("requests.sessions.Session.request", side_effect=AssertionError("No network"))
        self.network.start()

    def tearDown(self):
        self.network.stop()
        self.output.stop()
        self.environment.stop()
        self.temporary.cleanup()

    def fixture_asset(self):
        temporary = self.assets / "source.png"
        Image.new("RGBA", (3, 2), (20, 40, 60, 0)).save(temporary)
        digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
        final = self.assets / f"crun-{digest}.png"
        temporary.replace(final)
        return final

    def stub_receipt(self, client):
        client.return_value.get_task.return_value = {
            "task_id": "fixture_task", "status": "success", "credits": 3.5,
            "result": {"media_urls": ["https://cdn.example.com/image.png?token=PRIVATE_SIGNED_URL"]},
        }

    def seed_cache(self):
        path = self.fixture_asset()
        with patch.object(results, "CRUNClient") as client, patch.object(results, "download_to_output", return_value=path), patch.object(results, "_decoded", return_value=("native", "mask")):
            self.stub_receipt(client)
            return results.load_result_details("fixture_task", kind="image")

    def test_completed_asset_reuses_native_media_without_provider_or_signed_url(self):
        first = self.seed_cache()
        self.assertEqual(first["actual_credits"], 3.5)
        self.assertEqual(first["task_id"], "fixture_task")
        index = results._index_path()
        content = index.read_text(encoding="utf-8")
        self.assertNotIn("PRIVATE_SIGNED_URL", content)
        self.assertNotIn("synthetic-account-a", content)
        with patch.object(results, "CRUNClient", side_effect=AssertionError("Reuse must stay local")), patch.object(results, "download_to_output", side_effect=AssertionError("No download")), patch.object(results, "_decoded", return_value=("reloaded native", "reloaded mask")):
            reused = results.load_result_details("fixture_task", kind="image")
        self.assertEqual(reused, {"media": "reloaded native", "mask": "reloaded mask", "url": "", "actual_credits": 3.5,
                                  "task_id": "fixture_task", "local_path": first["local_path"]})

    def test_account_change_cannot_reuse_previous_accounts_task(self):
        self.seed_cache()
        first_index = results._index_path()
        with patch.dict(os.environ, {"CRUN_API_KEY": "synthetic-account-b-not-a-real-key"}), patch.object(results, "CRUNClient", side_effect=CRUNError("Account task unavailable")) as client:
            self.assertNotEqual(first_index, results._index_path())
            with self.assertRaisesRegex(CRUNError, "fixture_task"):
                results.load_result_details("fixture_task", kind="image")
            client.assert_called_once()

    def test_changed_asset_is_not_trusted_as_completed_result(self):
        first = self.seed_cache()
        path = Path(first["local_path"])
        raw = bytearray(path.read_bytes())
        raw[-1] ^= 1
        path.write_bytes(raw)
        with patch.object(results, "CRUNClient", side_effect=CRUNError("Remote lookup attempted")) as client:
            with self.assertRaisesRegex(CRUNError, "fixture_task"):
                results.load_result_details("fixture_task", kind="image")
        client.assert_called_once()

    def test_tampered_index_cannot_load_outside_output_directory(self):
        self.seed_cache()
        index = results._index_path()
        data = json.loads(index.read_text(encoding="utf-8"))
        entry = next(iter(data["entries"].values()))
        entry["file_name"] = "../private.png"
        index.write_text(json.dumps(data), encoding="utf-8")
        with patch.object(results, "CRUNClient", side_effect=CRUNError("Remote lookup attempted")) as client, patch.object(results, "_decoded", side_effect=AssertionError("Do not decode tampered index")):
            with self.assertRaisesRegex(CRUNError, "fixture_task"):
                results.load_result_details("fixture_task", kind="image")
        client.assert_called_once()

    def test_result_kind_and_index_do_not_collide_with_cached_image(self):
        self.seed_cache()
        for arguments in ({"kind": "video"}, {"kind": "image", "result_index": 1}):
            with self.subTest(arguments=arguments), patch.object(results, "CRUNClient", side_effect=CRUNError("Remote lookup attempted")) as client:
                with self.assertRaisesRegex(CRUNError, "fixture_task"):
                    results.load_result_details("fixture_task", **arguments)
                client.assert_called_once()

    def test_cached_result_still_validates_retrieval_controls(self):
        self.seed_cache()
        for arguments in ({"timeout_seconds": -1}, {"poll_interval": 0}, {"result_index": True}):
            with self.subTest(arguments=arguments), patch.object(results, "CRUNClient", side_effect=AssertionError("No provider")):
                with self.assertRaises(ValueError):
                    results.load_result_details("fixture_task", kind="image", **arguments)

    def test_native_audio_recovery_contract_and_legacy_tuple_positions(self):
        path = self.assets / "fixture.wav"
        with patch.object(results, "CRUNClient") as client, patch.object(results, "download_to_output", return_value=path) as download, patch.object(results, "audio_from_file", return_value={"waveform": "native", "sample_rate": 8000}):
            self.stub_receipt(client)
            details = results.load_result_details("fixture_task", kind="audio")
            legacy = results.load_result("fixture_task", kind="audio")
        self.assertIsNone(details["mask"])
        self.assertEqual(details["media"]["sample_rate"], 8000)
        self.assertEqual(legacy[2:], (3.5, "fixture_task"))
        self.assertEqual(download.call_args.kwargs["kind"], "audio")

    def test_new_audio_result_node_keeps_old_image_video_output_positions(self):
        import result_nodes
        self.assertEqual(result_nodes.CRUNGetImageResult.RETURN_NAMES, ("image", "url", "actual_credits", "task_id"))
        self.assertEqual(result_nodes.CRUNGetVideoResult.RETURN_NAMES, ("video", "url", "actual_credits", "task_id"))
        audio = result_nodes.CRUNGetAudioResult
        self.assertEqual(audio.RETURN_TYPES[0], "AUDIO")
        self.assertEqual(audio.INPUT_TYPES()["required"]["task_id"][0], "STRING")
        self.assertEqual(audio.INPUT_TYPES()["required"]["task_id"][1]["default"], "")
        with patch.object(result_nodes, "load_result", side_effect=AssertionError("No submission or lookup")):
            blocked = audio().load("")
        self.assertEqual(blocked["result"][1:], ("", -1.0, ""))


@unittest.skipUnless(importlib.util.find_spec("torch"), "Host-provided PyTorch is absent outside ComfyUI")
class NativeDecoderTests(unittest.TestCase):
    def test_transparent_png_returns_comfy_inverted_alpha_mask(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "transparent.png"
            image = Image.new("RGBA", (2, 1))
            image.putdata([(255, 0, 0, 0), (0, 255, 0, 255)])
            image.save(path)
            pixels, mask = results.image_with_mask_from_file(path)
        self.assertEqual(tuple(pixels.shape), (1, 1, 2, 3))
        self.assertEqual(tuple(mask.shape), (1, 1, 2))
        self.assertEqual(mask.tolist(), [[[1.0, 0.0]]])
        self.assertEqual(pixels[0, 0, 0].tolist(), [1.0, 0.0, 0.0])

    def test_opaque_image_mask_is_zero_and_matches_image_dimensions(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "opaque.png"
            Image.new("RGB", (3, 2), (10, 20, 30)).save(path)
            pixels, mask = results.image_with_mask_from_file(path)
        self.assertEqual(tuple(mask.shape), (1, 2, 3))
        self.assertEqual(float(mask.sum()), 0)

    @unittest.skipUnless(importlib.util.find_spec("av"), "Host-provided PyAV is absent outside ComfyUI")
    def test_synthetic_pcm_wav_decodes_to_normalized_native_audio(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "synthetic.wav"
            samples = [32767, -32768, 0, 16384] * 20
            with wave.open(str(path), "wb") as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(8000)
                stream.writeframes(struct.pack("<" + "h" * len(samples), *samples))
            with patch("requests.sessions.Session.request", side_effect=AssertionError("No provider")):
                decoded = results.audio_from_file(path)
            self.assertEqual(decoded["sample_rate"], 8000)
            self.assertEqual(tuple(decoded["waveform"].shape), (1, 1, 80))
            self.assertAlmostEqual(float(decoded["waveform"][0, 0, 1]), -1.0)
            self.assertAlmostEqual(float(decoded["waveform"][0, 0, 3]), 0.5)
            with patch.object(results, "MAX_AUDIO_DECODED_BYTES", 16):
                with self.assertRaisesRegex(CRUNError, "limits"):
                    results.audio_from_file(path)
            class Cancelled(Exception):
                pass
            module = SimpleNamespace(InterruptProcessingException=Cancelled)
            with patch.dict(sys.modules, {"comfy.model_management": module}), patch.object(results, "_interrupt", side_effect=Cancelled):
                with self.assertRaises(Cancelled):
                    results.audio_from_file(path)


if __name__ == "__main__":
    unittest.main()
