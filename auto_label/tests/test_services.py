from types import SimpleNamespace
from unittest.mock import Mock, patch
import uuid

import requests
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings

from auto_label.providers import provider_by_id
from auto_label.models import AutoLabelModel
from auto_label.serializers import AutoLabelModelSerializer, inspect_ultralytics_model
from auto_label.services import (
    inference_confidence,
    prediction_bbox_data,
    prediction_polygon_data,
    request_predictions,
)
from auto_label.propagation import bbox_iou, crop_bbox, normalize_bbox, track_next_bbox
from auto_label.tasks import (
    DUPLICATE_IOU_THRESHOLD,
    _assign_track,
    _best_overlapping_annotation,
)


class AutoLabelGeometryTests(SimpleTestCase):
    def setUp(self):
        self.media = SimpleNamespace(width=200, height=100)

    def test_bbox_uses_center_xywh(self):
        data = prediction_bbox_data({
            'bbox': [100, 50, 40, 20],
            'bbox_format': 'xywh',
            'normalized': False,
        }, self.media)
        self.assertEqual(data, {'x': 80.0, 'y': 40.0, 'width': 40.0, 'height': 20.0})

    def test_polygon_flattens_normalized_points(self):
        data = prediction_polygon_data({
            'polygon': [[0.1, 0.2], [0.8, 0.2], [0.8, 0.9]],
            'normalized': True,
        }, self.media)
        self.assertEqual(data, {'points': [20.0, 20.0, 160.0, 20.0, 160.0, 90.0]})

    def test_invalid_polygon_is_skipped(self):
        self.assertIsNone(prediction_polygon_data({'points': [1, 2, 3, 4]}, self.media))

    def test_confidence_is_validated(self):
        self.assertEqual(inference_confidence(None), 0.45)
        with self.assertRaisesRegex(ValueError, 'between 0 and 1'):
            inference_confidence(-0.1)

    def test_yolo_world_declares_bbox_only(self):
        provider = provider_by_id('yolo_world')
        self.assertEqual(provider['capabilities'], ['bbox'])

    def test_sam3_declares_polygon_and_supported_model(self):
        provider = provider_by_id('sam3')
        self.assertEqual(provider['capabilities'], ['polygon'])
        self.assertEqual(provider['models'], ['facebook/sam3'])


class AutoLabelUploadContractTests(SimpleTestCase):
    def test_storage_is_configured_as_storage_instance(self):
        storage = AutoLabelModel._meta.get_field('model_file').storage
        self.assertTrue(callable(getattr(storage, 'save', None)))

    def test_upload_only_requires_project_and_file(self):
        fields = AutoLabelModelSerializer().fields
        for field_name in ('name', 'version', 'task_type', 'class_names'):
            self.assertFalse(fields[field_name].required)

    def test_temporary_flag_is_server_managed(self):
        self.assertTrue(AutoLabelModelSerializer().fields['is_temporary'].read_only)

    def test_model_upload_scans_task_and_ordered_class_names(self):
        yolo = Mock(return_value=SimpleNamespace(
            task='detect',
            names={2: 'person', 0: 'animal', 1: 'vehicle'},
        ))
        model_file = SimpleUploadedFile('person.pt', b'model-content')

        with patch.dict('sys.modules', {'ultralytics': SimpleNamespace(YOLO=yolo)}):
            metadata = inspect_ultralytics_model(model_file)

        self.assertEqual(metadata['task_type'], 'object_detection')
        self.assertEqual(metadata['capabilities'], ['bbox'])
        self.assertEqual(metadata['class_names'], ['animal', 'vehicle', 'person'])


class AutoLabelInferenceFallbackTests(SimpleTestCase):
    @override_settings(
        INFERENCE_API_URL='http://inference.invalid',
        INFERENCE_AGENT_TOKEN='',
        AUTO_LABEL_LOCAL_FALLBACK=False,
        AUTO_LABEL_INFERENCE_RETRIES=2,
        AUTO_LABEL_INFERENCE_RETRY_DELAY=0,
    )
    @patch('auto_label.services.requests.post')
    def test_transient_502_is_retried(self, post):
        failed = Mock(ok=False, status_code=502, text='temporary failure', reason='Bad Gateway')
        succeeded = Mock(ok=True)
        succeeded.json.return_value = {'predictions': [], 'summary': {}}
        post.side_effect = [failed, succeeded]

        result = request_predictions({'engine': {}, 'dataset': {}})

        self.assertEqual(result['predictions'], [])
        self.assertEqual(post.call_count, 2)

    @override_settings(
        INFERENCE_API_URL='http://inference.invalid',
        INFERENCE_AGENT_TOKEN='secret',
        AUTO_LABEL_LOCAL_FALLBACK=False,
    )
    @patch('auto_label.services.requests.post')
    def test_uses_unified_auto_label_endpoint(self, post):
        post.return_value.ok = True
        post.return_value.json.return_value = {'predictions': []}
        payload = {'engine': {'provider': 'sam3'}, 'dataset': {}}

        request_predictions(payload)

        post.assert_called_once_with(
            'http://inference.invalid/v1/auto-label/predict',
            json=payload,
            headers={'Authorization': 'Bearer secret'},
            timeout=120,
        )

    @override_settings(
        INFERENCE_API_URL='http://inference.invalid',
        INFERENCE_AGENT_TOKEN='secret',
        AUTO_LABEL_LOCAL_FALLBACK=False,
    )
    @patch('auto_label.services.requests.post')
    def test_uploaded_model_omits_legacy_fields_from_remote_contract(self, post):
        post.return_value.ok = True
        post.return_value.json.return_value = {'predictions': []}
        payload = {
            'engine': {
                'provider': 'uploaded_yolo',
                'model_id': 29,
                'name': 'custom-yolo',
                'checksum': 'abc123',
            },
            'model': {'registry_id': 29, 'checksum': 'abc123'},
            'dataset': {'id': 1, 'media_ids': [2]},
            'output_type': 'bbox',
            'confidence': 0.45,
        }

        request_predictions(payload)

        sent_payload = post.call_args.kwargs['json']
        self.assertNotIn('model', sent_payload)
        self.assertNotIn('checksum', sent_payload['engine'])
        self.assertEqual(sent_payload['engine']['model_id'], 29)

    @override_settings(
        INFERENCE_API_URL='http://inference.invalid',
        INFERENCE_AGENT_TOKEN='',
        AUTO_LABEL_LOCAL_FALLBACK=True,
    )
    @patch('auto_label.services._local_predictions')
    @patch('auto_label.services.requests.post')
    def test_connection_error_uses_local_fallback(self, post, local_predictions):
        post.side_effect = requests.ConnectionError('offline')
        local_predictions.return_value = {'predictions': [], 'summary': {'engine': 'local'}}
        payload = {'model': {}, 'dataset': {}}

        result = request_predictions(payload)

        self.assertEqual(result['summary']['engine'], 'local')
        local_predictions.assert_called_once_with(payload)


class ObjectPropagationTests(SimpleTestCase):
    def test_bbox_validation_and_iou(self):
        bbox = normalize_bbox(
            {'x': -5, 'y': 10, 'width': 30, 'height': 20},
            image_width=100,
            image_height=80,
        )
        self.assertEqual(bbox, {'x': 0.0, 'y': 10.0, 'width': 30.0, 'height': 20.0})
        self.assertAlmostEqual(bbox_iou(bbox, bbox), 1.0)

    def test_tracker_finds_shifted_template(self):
        import cv2
        import numpy as np

        rng = np.random.default_rng(7)
        patch = rng.integers(0, 255, size=(24, 30, 3), dtype=np.uint8)
        source = np.zeros((120, 160, 3), dtype=np.uint8)
        target = np.zeros_like(source)
        source[30:54, 40:70] = patch
        target[47:71, 66:96] = patch
        cv2.rectangle(source, (40, 30), (69, 53), (255, 255, 255), 1)
        cv2.rectangle(target, (66, 47), (95, 70), (255, 255, 255), 1)
        bbox = {'x': 40.0, 'y': 30.0, 'width': 30.0, 'height': 24.0}
        template = crop_bbox(source, bbox)

        result = track_next_bbox(target, bbox, template, template, 0.7)

        self.assertIsNotNone(result)
        tracked, confidence, _ = result
        self.assertGreaterEqual(confidence, 0.7)
        self.assertLess(abs(tracked['x'] - 66), 2)
        self.assertLess(abs(tracked['y'] - 47), 2)

    def test_existing_overlapping_annotation_is_linked_to_track(self):
        selected = SimpleNamespace(
            data={'x': 10, 'y': 10, 'width': 30, 'height': 40},
            track_id=None,
            save=Mock(),
        )
        other = SimpleNamespace(
            data={'x': 80, 'y': 80, 'width': 10, 'height': 10},
            track_id=None,
            save=Mock(),
        )
        bbox = {'x': 11, 'y': 11, 'width': 30, 'height': 40}

        match = _best_overlapping_annotation(bbox, [other, selected], bbox_iou)
        track_id = uuid.uuid4()
        _assign_track(match, track_id)

        self.assertIs(match, selected)
        self.assertEqual(selected.track_id, track_id)
        selected.save.assert_called_once_with(update_fields=['track_id', 'updated_at'])

    def test_duplicate_requires_iou_above_seventy_five_percent(self):
        existing = SimpleNamespace(
            data={'x': 10, 'y': 10, 'width': 70, 'height': 40},
            track_id=None,
        )
        exactly_seventy_five = {'x': 20, 'y': 10, 'width': 70, 'height': 40}

        self.assertEqual(DUPLICATE_IOU_THRESHOLD, 0.75)
        self.assertAlmostEqual(bbox_iou(exactly_seventy_five, existing.data), 0.75)
        self.assertIsNone(
            _best_overlapping_annotation(exactly_seventy_five, [existing], bbox_iou)
        )
