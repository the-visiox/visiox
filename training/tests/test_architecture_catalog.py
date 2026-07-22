from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from training.models import ModelArchitecture


class ArchitectureCatalogTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='architecture-catalog-owner',
            password='secret',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_yolo11_and_yolo26_expose_all_supported_sizes(self):
        expected = {
            'yolov11': {f'yolo11{size}.pt' for size in 'nsmlx'},
            'yolo26': {f'yolo26{size}.pt' for size in 'nsmlx'},
        }

        for family, checkpoints in expected.items():
            architectures = ModelArchitecture.objects.filter(
                backbone=family,
                is_active=True,
            )
            self.assertEqual(
                {item.default_config.get('checkpoint') for item in architectures},
                checkpoints,
            )

    def test_yolov8_and_yolov9_are_not_active(self):
        self.assertFalse(
            ModelArchitecture.objects.filter(
                backbone__startswith='yolov8',
                is_active=True,
            ).exists()
        )

    def test_inactive_architectures_can_be_loaded_for_legacy_fine_tuning(self):
        legacy = ModelArchitecture.objects.create(
            name='Legacy fine-tune test architecture',
            backbone='yolo26',
            task_type='object_detection',
            default_config={'architecture': 'yolo26', 'checkpoint': 'yolo26n.pt'},
            is_active=False,
        )

        active_response = self.client.get('/api/v1/architectures/')
        all_response = self.client.get('/api/v1/architectures/?include_inactive=true')

        self.assertEqual(active_response.status_code, 200)
        self.assertEqual(all_response.status_code, 200)
        self.assertNotIn(legacy.id, [item['id'] for item in active_response.data['results']])
        self.assertIn(legacy.id, [item['id'] for item in all_response.data['results']])
        self.assertFalse(
            ModelArchitecture.objects.filter(
                backbone__startswith='yolov9',
                is_active=True,
            ).exists()
        )
