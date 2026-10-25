import io
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from crun import media


class FakeClient:
    def __init__(self, key="fixture-key"):
        self._api_key = key
        self.calls = []

    def upload_bytes(self, data, **kwargs):
        self.calls.append((data, kwargs))
        return f"https://cdn.example.com/native-{len(self.calls)}.png"


class MediaTests(unittest.TestCase):
    def setUp(self):
        media._UPLOAD_CACHE.clear()

    def test_png_batch_preserves_order_pixels_dimensions_and_rounding(self):
        image = np.zeros((2, 3, 4, 3), dtype=np.float32)
        image[0, ..., 0] = 1
        image[1, ..., 1] = .5
        with patch("requests.sessions.Session.request", side_effect=AssertionError("Encoding must be offline")):
            images = media.image_batch_to_pngs(image)
        self.assertEqual(len(images), 2)
        with Image.open(io.BytesIO(images[0])) as first, Image.open(io.BytesIO(images[1])) as second:
            self.assertEqual(first.size, (4, 3))
            self.assertEqual(first.getpixel((0, 0)), (255, 0, 0))
            self.assertEqual(second.getpixel((0, 0)), (0, 128, 0))

    def test_grayscale_and_alpha_are_preserved(self):
        for channels, mode in ((1, "L"), (4, "RGBA")):
            image = np.ones((2, 2, channels), dtype=np.float32)
            encoded = media.image_batch_to_pngs(image)
            with Image.open(io.BytesIO(encoded[0])) as result:
                self.assertEqual(result.mode, mode)

    def test_invalid_shape_type_values_and_limits_are_rejected_locally(self):
        invalid = [np.zeros((1, 2, 2), dtype=np.uint8), np.zeros((0, 2, 2, 3), dtype=np.float32),
                   np.zeros((1, 2, 2, 2), dtype=np.float32), np.zeros((1, 2, 2, 3, 1), dtype=np.float32),
                   np.full((1, 2, 2, 3), np.nan), np.full((1, 2, 2, 3), np.inf),
                   np.full((1, 2, 2, 3), 1.1), np.full((1, 2, 2, 3), -.1)]
        for image in invalid:
            with self.subTest(shape=image.shape), self.assertRaises(ValueError):
                media.image_batch_to_pngs(image)
        image = np.zeros((2, 3, 4, 3), dtype=np.float32)
        for limits in ({"max_images": 1}, {"max_pixels": 5}, {"max_dimension": 2}, {"max_bytes": 10}):
            with self.subTest(limits=limits), self.assertRaises(ValueError):
                media.image_batch_to_pngs(image, **limits)

    def test_descriptions_are_json_safe_and_use_reserved_local_placeholders(self):
        image = np.zeros((2, 3, 4, 3), dtype=np.float32)
        first = media.describe_image_batch(image)
        second = media.describe_image_batch(image)
        self.assertEqual(first, second)
        self.assertEqual((first["count"], first["width"], first["height"], first["channels"]), (2, 4, 3, 3))
        self.assertEqual(len(first["sha256"][0]), 64)
        self.assertTrue(first["upload_required"])
        self.assertTrue(all(url.startswith("https://crun-next.invalid/local/") for url in first["placeholders"]))
        self.assertNotIn("tensor", str(first))

    def test_mask_stays_white_as_affected_and_is_never_resized(self):
        mask = np.asarray([[0, .5], [1, .25]], dtype=np.float32)
        images = media.mask_batch_to_images(mask)
        self.assertEqual(images.shape, (1, 2, 2, 1))
        self.assertEqual(float(images[0, 1, 0, 0]), 1)
        description = media.describe_mask_batch(mask)
        self.assertEqual(description["kind"], "comfy_mask")
        self.assertEqual(description["channels"], 1)
        self.assertIn("no inversion", description["mask_semantics"])

    def test_upload_needs_explicit_permission_and_whole_batch_validation(self):
        client = FakeClient()
        image = np.zeros((1, 2, 2, 3), dtype=np.float32)
        with self.assertRaises(ValueError):
            media.upload_images(client, image)
        bad = np.zeros((2, 2, 2, 3), dtype=np.float32)
        bad[1, 0, 0, 0] = np.nan
        with self.assertRaises(ValueError):
            media.upload_images(client, bad, allow_upload=True)
        self.assertEqual(client.calls, [])

    def test_successful_uploads_are_cached_by_content_and_credential(self):
        client = FakeClient()
        image = np.zeros((1, 2, 2, 3), dtype=np.float32)
        with patch.object(media.time, "monotonic", return_value=1000):
            first = media.upload_images(client, image, allow_upload=True)
            again = media.upload_images(FakeClient(), image, allow_upload=True)
            other = FakeClient("another-fixture-key")
            media.upload_images(other, image, allow_upload=True)
        self.assertEqual(first, again)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(len(other.calls), 1)
        self.assertNotIn("fixture-key", str(media._UPLOAD_CACHE))
        with patch.object(media.time, "monotonic", return_value=3000):
            media.upload_images(client, image, allow_upload=True)
        self.assertEqual(len(client.calls), 2)

    def test_real_comfy_tensor_encodes_when_torch_is_available(self):
        try:
            import torch
        except ImportError:
            self.skipTest("Host-provided PyTorch is absent outside ComfyUI")
        image = torch.ones((1, 2, 3, 3), dtype=torch.float32)
        self.assertEqual(media.describe_image_batch(image)["width"], 3)
        mask = torch.ones((1, 2, 3), dtype=torch.float32)
        self.assertEqual(media.mask_batch_to_images(mask).shape, (1, 2, 3, 1))


if __name__ == "__main__":
    unittest.main()
