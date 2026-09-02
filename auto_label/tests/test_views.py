from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from annotations.models import Class
from datasets.models import Dataset, Media
from projects.models import Project


class FrameSam3PredictTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='sam3-owner', password='secret')
        self.project = Project.objects.create(
            owner=self.user,
            name='SAM 3 Project',
            task_type='semantic_segmentation',
        )
        self.dataset = Dataset.objects.create(project=self.project, name='Dataset')
        self.media = Media.objects.create(
            dataset=self.dataset,
            type='image',
            file='sam3/image.jpg',
            original_filename='image.jpg',
            width=200,
            height=100,
        )
        self.adapter = Class.objects.create(project=self.project, name='adapter')
        self.cable = Class.objects.create(project=self.project, name='cable')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    @patch('auto_label.views.request_predictions')
    def test_maps_prompt_indexes_back_to_database_label_ids(self, request_predictions):
        request_predictions.return_value = {
            'predictions': [{
                'media_id': self.media.id,
                'type': 'polygon',
                'label': 'cable',
                'label_id': 1,
                'confidence': 0.91,
                'normalized': False,
                'polygon': [10, 10, 80, 10, 80, 60],
            }],
            'summary': {},
        }

        response = self.client.post(
            f'/api/v1/datasets/{self.dataset.id}/frames/0/predict/',
            {
                'provider': 'sam3',
                'model': 'facebook/sam3',
                'label_ids': [self.adapter.id, self.cable.id],
                'output_type': 'polygon',
                'confidence': 0.35,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['predictions'][0]['label_id'], self.cable.id)
        self.assertEqual(response.data['predictions'][0]['class_label'], self.cable.id)
        self.assertEqual(
            request_predictions.call_args.args[0]['engine']['prompts'],
            ['adapter', 'cable'],
        )

    @patch('auto_label.views.request_predictions')
    def test_rejects_label_from_another_project_before_inference(self, request_predictions):
        other_project = Project.objects.create(
            owner=self.user,
            name='Other Project',
            task_type='semantic_segmentation',
        )
        foreign_label = Class.objects.create(project=other_project, name='foreign')

        response = self.client.post(
            f'/api/v1/datasets/{self.dataset.id}/frames/0/predict/',
            {
                'provider': 'sam3',
                'label_ids': [foreign_label.id],
                'output_type': 'polygon',
                'confidence': 0.35,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        request_predictions.assert_not_called()

    @patch('auto_label.views.request_predictions')
    def test_skips_out_of_range_prompt_index(self, request_predictions):
        request_predictions.return_value = {
            'predictions': [{
                'media_id': self.media.id,
                'type': 'polygon',
                'label': 'adapter',
                'label_id': 5,
                'confidence': 0.91,
                'polygon': [10, 10, 80, 10, 80, 60],
            }],
            'summary': {},
        }

        response = self.client.post(
            f'/api/v1/datasets/{self.dataset.id}/frames/0/predict/',
            {
                'provider': 'sam3',
                'label_ids': [self.adapter.id],
                'output_type': 'polygon',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['predictions'], [])

    @patch('auto_label.views.request_predictions')
    def test_rejects_duplicate_label_ids_before_inference(self, request_predictions):
        response = self.client.post(
            f'/api/v1/datasets/{self.dataset.id}/frames/0/predict/',
            {
                'provider': 'sam3',
                'label_ids': [self.adapter.id, self.adapter.id],
                'output_type': 'polygon',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        request_predictions.assert_not_called()
