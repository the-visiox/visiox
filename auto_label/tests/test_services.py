from types import SimpleNamespace
from unittest.mock import Mock, patch

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
