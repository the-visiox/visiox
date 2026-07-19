from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from annotations.models import Annotation, Class
from datasets.models import Dataset, Media
from deployments.models import ModelRegistry
from projects.models import Project
from training.agent import build_training_request
from training.models import ModelArchitecture, TrainingJob
from training.serializers import TrainingJobSerializer


class FineTuningTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='trainer', password='secret')
        self.project = Project.objects.create(
            owner=self.user, name='Detection', task_type='object_detection'
        )
        self.class_label = Class.objects.create(project=self.project, name='person')
        self.dataset = Dataset.objects.create(project=self.project, name='People')
        media = []
        for index in range(2):
            media.append(Media.objects.create(
                dataset=self.dataset,
                type='image',
                file=SimpleUploadedFile(f'{index}.jpg', b'image', content_type='image/jpeg'),
                original_filename=f'{index}.jpg',
                width=64,
                height=64,
                metadata={'category': 'raw', 'split': 'train' if index == 0 else 'val'},
            ))
        Annotation.objects.create(
            media=media[0], class_label=self.class_label, annotator=self.user,
            type='rectangle', data={'x': 1, 'y': 1, 'width': 10, 'height': 10},
        )
        now = timezone.now()
        self.dataset.verification_status = 'verified'
        self.dataset.verified_by = self.user
        self.dataset.verified_at = now
        self.dataset.split_config = {
            'train': 50, 'val': 50, 'test': 0, 'source': 'imported_yolo26'
        }
        self.dataset.split_updated_at = now
        self.dataset.save()
        self.architecture = ModelArchitecture.objects.create(
            name='YOLOv8 Detection', backbone='yolov8n', task_type='object_detection'
        )
        self.parent_job = TrainingJob.objects.create(
            project=self.project,
            dataset=self.dataset,
            dataset_ids=[self.dataset.id],
            architecture=self.architecture,
            created_by=self.user,
            name='Run 1',
            status='completed',
            class_schema=[{'id': self.class_label.id, 'name': 'person'}],
        )
        self.registry = ModelRegistry.objects.create(
            training_job=self.parent_job,
            name='Run 1',
            format='pytorch',
            model_file='training-jobs/1/artifacts/best.pt',
            created_by=self.user,
        )

    def test_serializer_records_fine_tuning_lineage(self):
        request = APIRequestFactory().post('/api/v1/training-jobs/')
        request.user = self.user
        serializer = TrainingJobSerializer(data={
            'project': self.project.id,
            'dataset_ids': [self.dataset.id],
            'architecture': self.architecture.id,
            'initialization_mode': 'fine_tune',
            'base_model': self.registry.id,
            'name': 'Run 2',
            'hyperparams': {'epochs': 10},
        }, context={'request': request})

        self.assertTrue(serializer.is_valid(), serializer.errors)
        job = serializer.save()

        self.assertEqual(job.parent_job, self.parent_job)
        self.assertEqual(job.base_model, self.registry)
        self.assertEqual(job.class_schema, [{'id': self.class_label.id, 'name': 'person'}])

    @override_settings(
        USE_MINIO=True,
        TRAINING_CALLBACK_TOKEN='callback',
        TRAINING_CALLBACK_BASE_URL='http://api:8000',
        TRAINING_LABEL_DELIVERY='minio',
        AWS_STORAGE_BUCKET_NAME='visiox-media',
        AWS_S3_ADDRESSING_STYLE='path',
    )
    @patch('training.agent._artifact_download_url', return_value='https://minio/checkpoint')
    @patch('training.agent._artifact_upload_urls')
    @patch('training.agent.promote_dataset_cache_to_job')
    def test_agent_payload_contains_presigned_initial_checkpoint(
        self, promote, upload_urls, _download_url
    ):
        promote.return_value = {
            'job_label_keys': [],
            'manifest': {'train': [], 'val': [], 'test': []},
            'test_dataset_id': None,
        }
        upload_urls.return_value = {
            'best.pt': 'put-best',
            'best.onnx': 'put-onnx',
            'metrics.json': 'put-metrics',
            'training_log.json': 'put-log',
            'confusion_matrix.png': 'put-matrix',
        }
        job = TrainingJob.objects.create(
            project=self.project,
            dataset=self.dataset,
            dataset_ids=[self.dataset.id],
            architecture=self.architecture,
            parent_job=self.parent_job,
            base_model=self.registry,
            initialization_mode='fine_tune',
            class_schema=self.parent_job.class_schema,
            created_by=self.user,
            name='Run 2',
        )

        payload = build_training_request(job)

        self.assertEqual(payload['initial_checkpoint']['download_url'], 'https://minio/checkpoint')
        self.assertEqual(payload['initial_checkpoint']['source_training_job_id'], self.parent_job.id)
        self.assertEqual(payload['initial_checkpoint']['source_registry_id'], self.registry.id)

