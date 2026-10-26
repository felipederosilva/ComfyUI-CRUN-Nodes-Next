import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

import generated_nodes as generated
from crun import execution, media

ROOT = Path(__file__).resolve().parents[1]
ENTRIES = json.loads((ROOT / 'data/catalog.json').read_text(encoding='utf-8'))['entries']


def model(identifier):
    return next(entry for entry in ENTRIES if entry.get('model') == identifier)


class NativeNodeTests(unittest.TestCase):
    def setUp(self):
        self.image = np.zeros((1, 4, 6, 3), dtype=np.float32)

    def test_seedance_has_first_last_native_connections_and_offline_payload(self):
        node = generated.make_node(model('bytedance/seedance2-0-i2v'))
        self.assertEqual(node.INPUT_TYPES()['optional']['first_frame'][0], 'IMAGE')
        self.assertEqual(node.INPUT_TYPES()['optional']['last_frame'][0], 'IMAGE')
        with patch('requests.sessions.Session.request', side_effect=AssertionError('Offline')):
            output = node().execute(prompt='A fictional landscape', first_frame=self.image, last_frame=self.image + 1)
        result = json.loads(output['result'][0])
        self.assertEqual(result['mode'], 'prepare')
        self.assertEqual(len(result['payload']['input']['img_urls']), 2)
        self.assertNotEqual(*result['payload']['input']['img_urls'])
        self.assertEqual(result['errors'], [])
        self.assertTrue(all(info['upload_required'] for info in result['native_media']))

    def test_r2v_native_socket_is_not_overwritten_by_url_widget(self):
        node = generated.make_node(model('bytedance/seedance2-0-r2v'))
        definitions = {**node.INPUT_TYPES()['required'], **node.INPUT_TYPES()['optional']}
        self.assertEqual(definitions['reference_images'][0], 'IMAGE')
        self.assertEqual(definitions['reference_images_urls'][0], 'STRING')

    def test_array_alternatives_have_real_native_connections(self):
        for identifier, socket in [('flux-1-1-pro', 'image'), ('flux-kontext-max', 'image'), ('wan/2-5-preview-i2v', 'first_frame'), ('wan/2-6-i2v', 'first_frame')]:
            with self.subTest(model=identifier):
                node = generated.make_node(model(identifier))
                self.assertEqual(node.INPUT_TYPES()['optional'][socket][0], 'IMAGE')
                result = json.loads(node().execute(prompt='Fictional scene', **{socket: self.image})['result'][0])
                self.assertIsInstance(result['payload']['input']['img_urls'], list)
                self.assertEqual(len(result['payload']['input']['img_urls']), 1)

    def test_prepare_stays_offline_and_invalid_optional_cap_stops_before_request(self):
        node = generated.make_node(model('bytedance/seedance2-0-i2v'))()
        with patch.object(execution, 'CRUNClient', side_effect=AssertionError('No provider request')):
            result = json.loads(node.execute(prompt='A fictional landscape', first_frame=self.image)['result'][0])
            self.assertEqual(result['mode'], 'prepare')
            with self.assertRaisesRegex(ValueError, 'nonnegative'):
                node.execute(prompt='A fictional landscape', first_frame=self.image, crun_mode='generate', crun_max_credits=-1)

    def test_bad_model_inputs_stop_before_upload(self):
        node = generated.make_node(model('bytedance/seedance2-0-i2v'))()
        with patch.object(execution, 'CRUNClient', side_effect=AssertionError('No provider request')):
            with self.assertRaisesRegex(ValueError, 'Invalid model input'):
                node.execute(prompt='A fictional landscape', resolution='unsupported', first_frame=self.image, crun_mode='estimate', crun_allow_upload=True)

    def test_estimate_action_uploads_then_quotes_without_extra_switches_or_submission(self):
        node = generated.make_node(model('bytedance/seedance2-0-i2v'))()
        with patch.object(execution, 'CRUNClient') as client, patch.object(media, 'upload_pngs', return_value=['https://cdn.example.com/image.png']) as upload:
            client.return_value.estimate_credits.return_value = {'credits': 5, 'estimated': True}
            result = json.loads(node.execute(prompt='Fictional scene', first_frame=self.image, crun_mode='estimate')['result'][0])
            upload.assert_called_once()
            client.return_value.estimate_credits.assert_called_once_with('bytedance/seedance2-0-i2v', {'prompt': 'Fictional scene', 'img_urls': ['https://cdn.example.com/image.png']})
            client.return_value.create_task.assert_not_called()
        self.assertEqual(result['credit_state'], 'estimate')

    def test_ambiguous_sources_last_without_first_and_bad_counts_rejected(self):
        node = generated.make_node(model('bytedance/seedance2-0-i2v'))()
        for values in ({'last_frame': self.image}, {'first_frame': np.repeat(self.image, 2, axis=0)}, {'first_frame': self.image, 'img_urls': '["https://cdn.example.com/image.png"]'}):
            with self.subTest(keys=list(values)), self.assertRaises(ValueError):
                node.execute(prompt='Fictional scene', **values)

    def test_inpainting_has_mask_port_and_requires_matching_dimensions(self):
        node = generated.make_node(model('image-inpaint'))
        self.assertEqual(node.INPUT_TYPES()['optional']['mask'][0], 'MASK')
        with self.assertRaisesRegex(ValueError, 'dimensions'):
            node().execute(image=self.image, mask=np.zeros((1, 2, 2), dtype=np.float32))

    def test_fixed_two_image_effect_has_ordered_native_slots(self):
        entry = generated._effect_entry('bytedance', {'id': 'fixture', 'required_images': 2, 'raw': {}, 'credits': [{'resolution': '720p', 'credits': 3}]})
        ports = generated.make_node(entry).INPUT_TYPES()['optional']
        self.assertEqual(ports['image_1'][0], 'IMAGE')
        self.assertEqual(ports['image_2'][0], 'IMAGE')

    def test_draft_placeholders_cannot_be_copied_into_provider_requests(self):
        with patch.object(execution, 'CRUNClient', side_effect=AssertionError('No provider request')):
            with self.assertRaisesRegex(ValueError, 'placeholders'):
                execution.run_entry(model('bytedance/seedance2-0-i2v'), {'prompt': 'Test', 'img_urls': ['https://crun-next.invalid/local/draft.png']}, 'estimate')

    def test_motion_video_port_prepares_real_role_without_upload(self):
        class Video:
            def get_dimensions(self): return 720, 720
            def get_duration(self): return 5.0
            def get_frame_rate(self): return 24
            def save_to(self, path): Path(path).write_bytes(b'\x00\x00\x00\x18ftypisomfixture')
        node = generated.make_node(model('kling/v3-motion-control'))
        self.assertEqual(node.INPUT_TYPES()['optional']['motion_video'][0], 'VIDEO')
        with patch.object(execution, 'CRUNClient', side_effect=AssertionError('Prepare remains offline')):
            result = json.loads(node().execute(image=self.image, motion_video=Video(), character_orientation='image', mode='std')['result'][0])
        self.assertEqual(result['errors'], [])
        self.assertEqual(len(result['payload']['input']['video_urls']), 1)
        video = next(info for info in result['native_media'] if info['kind'] == 'video')
        self.assertEqual(video['duration'], 5)
        self.assertTrue(video['placeholders'][0].endswith('.mp4'))

    def test_seedance_numbered_audio_reference_is_native_and_gaps_fail_locally(self):
        node = generated.make_node(model('bytedance/seedance2-5-r2v'))
        optional = node.INPUT_TYPES()['optional']
        self.assertEqual(optional['reference_video_1'][0], 'VIDEO')
        self.assertEqual(optional['reference_video_10'][0], 'VIDEO')
        self.assertEqual(optional['reference_audio_1'][0], 'AUDIO')
        audio = {'sample_rate': 16000, 'waveform': np.zeros((1, 1, 16000), dtype=np.float32)}
        with patch.object(execution, 'CRUNClient', side_effect=AssertionError('No request')):
            result = json.loads(node().execute(prompt='Synthetic audio-led scene', reference_audio_1=audio)['result'][0])
            self.assertEqual(result['errors'], [])
            self.assertTrue(result['payload']['input']['reference_audios'][0].endswith('.wav'))
            with self.assertRaisesRegex(ValueError, 'gap'):
                node().execute(prompt='Synthetic', reference_audio_2=audio)

    def test_native_clip_upload_then_estimate_does_not_create_a_task(self):
        class Video:
            def get_dimensions(self): return 720, 720
            def get_duration(self): return 5.0
            def get_frame_rate(self): return 24
            def save_to(self, path): Path(path).write_bytes(b'\x00\x00\x00\x18ftypisomfixture')
        node = generated.make_node(model('kling/v3-motion-control'))
        with patch.object(execution, 'CRUNClient') as client, patch.object(media, 'upload_pngs', return_value=['https://cdn.example.com/character.png']), patch.object(media, 'upload_media_bytes', return_value=['https://cdn.example.com/motion.mp4']) as upload:
            client.return_value.estimate_credits.return_value = {'credits': 2, 'estimated': True}
            result = json.loads(node().execute(image=self.image, motion_video=Video(), character_orientation='image', mode='std', crun_mode='estimate')['result'][0])
        self.assertEqual(upload.call_args.kwargs['mime_type'], 'video/mp4')
        self.assertEqual(result['payload']['input']['video_urls'], ['https://cdn.example.com/motion.mp4'])
        client.return_value.create_task.assert_not_called()


if __name__ == '__main__':
    unittest.main()
