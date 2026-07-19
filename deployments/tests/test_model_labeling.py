from types import SimpleNamespace

from django.test import SimpleTestCase

from deployments.views.deployment_view import (
    _inference_confidence,
    _prediction_annotation_data,
    _prediction_preview,
)


class ModelLabelingHelperTests(SimpleTestCase):
    def setUp(self):
        self.media = SimpleNamespace(width=200, height=100)

    def test_xywh_prediction_uses_center_coordinates(self):
        data = _prediction_annotation_data({
            'bbox': [100, 50, 40, 20],
            'bbox_format': 'xywh',
            'normalized': False,
        }, self.media)

        self.assertEqual(data, {'x': 80.0, 'y': 40.0, 'width': 40.0, 'height': 20.0})

    def test_normalized_xyxy_prediction_is_scaled(self):
        data = _prediction_annotation_data({
            'bbox': [0.1, 0.2, 0.6, 0.8],
            'bbox_format': 'xyxy',
            'normalized': True,
        }, self.media)

        self.assertEqual(data, {'x': 20.0, 'y': 20.0, 'width': 100.0, 'height': 60.0})

    def test_invalid_prediction_box_is_skipped(self):
        self.assertIsNone(_prediction_annotation_data({'bbox': [1, 2, 3]}, self.media))

    def test_confidence_defaults_and_validates_range(self):
        self.assertEqual(_inference_confidence(None), 0.25)
        self.assertEqual(_inference_confidence('0.4'), 0.4)
        with self.assertRaisesRegex(ValueError, 'between 0 and 1'):
            _inference_confidence(1.1)

    def test_prediction_preview_maps_project_class_without_saving(self):
        self.media.id = 12
        classes = [SimpleNamespace(id=7, name='person')]

        predictions, unmapped, skipped = _prediction_preview({
            'predictions': [{
                'media_id': 12,
                'label': 'Person',
                'confidence': 0.91,
                'bbox': [100, 50, 40, 20],
                'bbox_format': 'xywh',
                'normalized': False,
            }],
        }, self.media, classes)

        self.assertEqual(predictions[0]['class_label'], 7)
        self.assertEqual(predictions[0]['data'], {'x': 80.0, 'y': 40.0, 'width': 40.0, 'height': 20.0})
        self.assertEqual(unmapped, [])
        self.assertEqual(skipped, 0)
