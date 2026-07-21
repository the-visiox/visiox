import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage, storages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from annotations.models import Annotation, Class
from datasets.models import Dataset, Media
from projects.models import Project
from training.label_cache import (
    build_dataset_label_cache,
    build_dataset_label_cache_by_id,
    clear_dataset_label_cache,
    promote_dataset_cache_to_job,
)
from training.agent import build_training_request
from training.models import ModelArchitecture, TrainingJob
from training.serializers import TrainingJobListSerializer, TrainingJobSerializer


@override_settings(
    USE_MINIO=False,
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    },
)
class DatasetLabelCacheTests(TestCase):
    def setUp(self):
        super().setUp()
        self._tmpdir = tempfile.TemporaryDirectory()
        self._override = override_settings(MEDIA_ROOT=self._tmpdir.name)
        self._override.enable()
        storages._storages = {}

        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username='cache-user',
            email='cache@example.com',
            password='Secret123!',
        )
        self.project = Project.objects.create(
            owner=self.user,
            name='Cache Project',
            task_type='object_detection',
        )
        self.dataset = Dataset.objects.create(
            project=self.project,
            name='Cache Dataset',
            verification_status='verified',
            verified_by=self.user,
            verified_at=timezone.now(),
            split_config={'train': 50, 'val': 50, 'test': 0, 'seed': 42, 'strategy': 'random'},
            split_updated_at=timezone.now(),
        )
        self.class_label = Class.objects.create(project=self.project, name='defect', color='#ff7300')

        self.train_media = self._create_media('train.jpg', 'train')
        self.val_media = self._create_media('val.jpg', 'val')
        self._create_box(self.train_media, x=10, y=20, width=30, height=40)
        self._create_box(self.val_media, x=15, y=25, width=35, height=45)

        self.architecture = ModelArchitecture.objects.create(
            name='YOLO26 Detection - Nano',
            backbone='yolo26',
            task_type='object_detection',
            default_config={'checkpoint': 'yolo26n.pt', 'size': 'n'},
        )

    def tearDown(self):
        storages._storages = {}
        self._override.disable()
        self._tmpdir.cleanup()
        super().tearDown()

    def _create_media(self, name: str, split: str) -> Media:
        upload = SimpleUploadedFile(name, b'fake-image-bytes', content_type='image/jpeg')
        return Media.objects.create(
            dataset=self.dataset,
            type='image',
            file=upload,
            original_filename=name,
            width=100,
            height=100,
            metadata={'split': split, 'category': 'raw'},
        )

    def _create_box(self, media: Media, **data) -> Annotation:
        return Annotation.objects.create(
            media=media,
            class_label=self.class_label,
            annotator=self.user,
            type='rectangle',
            data=data,
        )

    def test_build_dataset_label_cache_writes_split_labels(self):
        metadata = build_dataset_label_cache(self.dataset)

        self.assertTrue(metadata['ready'])
        self.assertEqual(metadata['counts']['train'], 1)
        self.assertEqual(metadata['counts']['val'], 1)
        self.assertEqual(len(metadata['labels']), 2)
        self.assertTrue(default_storage.exists(f"{metadata['prefix']}/manifest.json"))
        self.assertTrue(default_storage.exists(f"{metadata['prefix']}/metadata.json"))
        self.assertTrue(default_storage.exists(f"{metadata['prefix']}/data.yaml"))
        for key in metadata['labels']:
            self.assertTrue(default_storage.exists(key), key)

    def test_promote_dataset_cache_to_job_copies_job_snapshot(self):
        job = TrainingJob.objects.create(
            project=self.project,
            dataset=self.dataset,
            architecture=self.architecture,
            created_by=self.user,
            name='Snapshot Run',
        )

        promoted = promote_dataset_cache_to_job(job)

        self.assertEqual(len(promoted['labels']), 2)
        self.assertEqual(len(promoted['job_label_keys']), 2)
        for key in promoted['job_label_keys']:
            self.assertTrue(default_storage.exists(key), key)
            self.assertIn(f'training-jobs/{job.id}/labels/', key)

    def test_clear_dataset_label_cache_removes_revision_prefix(self):
        metadata = build_dataset_label_cache(self.dataset)
        prefix_path = Path(default_storage.path(metadata['labels'][0])).parents[3]

        self.assertTrue(default_storage.exists(metadata['labels'][0]))
        self.assertTrue(prefix_path.exists())

        clear_dataset_label_cache(self.dataset.id)

        self.assertFalse(prefix_path.exists())

    def test_build_dataset_label_cache_by_id_returns_not_ready_without_split(self):
        self.dataset.split_config = {}
        self.dataset.split_updated_at = None
        self.dataset.save(update_fields=['split_config', 'split_updated_at', 'updated_at'])

        result = build_dataset_label_cache_by_id(self.dataset.id)

        self.assertFalse(result['ready'])
        self.assertEqual(result['reason'], 'not_ready')

    def test_training_job_artifact_urls_only_include_existing_files(self):
        job = TrainingJob.objects.create(
            project=self.project,
            dataset=self.dataset,
            architecture=self.architecture,
            created_by=self.user,
            name='Artifact Run',
            artifacts={
                'best.pt': {'storage_key': 'training-jobs/999/artifacts/best.pt'},
                'confusion_matrix.png': {'storage_key': 'training-jobs/999/artifacts/confusion_matrix.png'},
                'metrics.json': {'storage_key': 'training-jobs/999/artifacts/metrics.json'},
            },
        )
        default_storage.save('training-jobs/999/artifacts/best.pt', SimpleUploadedFile('best.pt', b'weights'))
        default_storage.save(
            'training-jobs/999/artifacts/confusion_matrix.png',
            SimpleUploadedFile('confusion_matrix.png', b'png'),
        )

        urls = TrainingJobSerializer(job).data['artifact_urls']

        self.assertIn('best.pt', urls)
        self.assertIn('confusion_matrix.png', urls)
        self.assertNotIn('metrics.json', urls)

    def test_training_job_list_uses_saved_artifact_metadata_without_storage_checks(self):
        job = TrainingJob.objects.create(
            project=self.project,
            dataset=self.dataset,
            architecture=self.architecture,
            created_by=self.user,
            name='Listed Artifact Run',
            artifacts={
                'best.pt': {'storage_key': 'training-jobs/1000/artifacts/best.pt'},
            },
        )
        storage = Mock()
        storage.url.side_effect = lambda key: f'/media/{key}'

        with patch('training.services.artifact_service.get_artifacts_storage', return_value=storage):
            urls = TrainingJobListSerializer(
                job,
            ).data['artifact_urls']

        self.assertEqual(urls, {
            'best.pt': '/media/training-jobs/1000/artifacts/best.pt',
        })
        storage.exists.assert_not_called()

    @override_settings(
        USE_MINIO=True,
        TRAINING_CALLBACK_TOKEN='callback-token',
        TRAINING_CALLBACK_BASE_URL='http://127.0.0.1:18080',
        AWS_S3_ENDPOINT_URL='http://10.29.30.20:9000',
        AWS_STORAGE_BUCKET_NAME='visiox-media',
        AWS_S3_ADDRESSING_STYLE='path',
    )
    @patch('training.agent.promote_dataset_cache_to_job', return_value={
        'job_label_keys': [],
        'manifest': {'train': [], 'val': [], 'test': []},
        'test_dataset_id': None,
    })
    def test_build_training_request_uses_configured_callback_base_url(self, _promote):
        job = TrainingJob.objects.create(
            project=self.project,
            dataset=self.dataset,
            architecture=self.architecture,
            created_by=self.user,
            name='Callback URL Run',
            hyperparams={'epochs': 10},
        )

        payload = build_training_request(job)

        self.assertEqual(
            payload['callbacks']['metrics_url'],
            f'http://127.0.0.1:18080/api/v1/internal/training-jobs/{job.id}/metrics/',
        )
        self.assertEqual(
            payload['callbacks']['heartbeat_url'],
            f'http://127.0.0.1:18080/api/v1/internal/training-jobs/{job.id}/heartbeat/',
        )
        self.assertEqual(payload['architecture'], 'yolo26')
        self.assertEqual(payload['architecture_checkpoint'], 'yolo26n.pt')
