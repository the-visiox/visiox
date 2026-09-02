import io
import tempfile
import zipfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from annotations.models import Annotation, Class
from core.models import UserModel
from datasets.models import Dataset, Media
from projects.models import Project


TEST_STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}


@override_settings(STORAGES=TEST_STORAGES)
class DatasetExportViewTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls._media_root = tempfile.TemporaryDirectory()
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root.name)
        cls._media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._media_override.disable()
        cls._media_root.cleanup()

    def setUp(self):
        self.user = UserModel.objects.create_user(
            username='export-owner',
            password='secret',
        )
        self.project = Project.objects.create(
            owner=self.user,
            name='Export project',
            task_type='object_detection',
        )
        self.dataset = Dataset.objects.create(
            project=self.project,
            name='Export dataset',
        )
        self.media = Media.objects.create(
            dataset=self.dataset,
            type='image',
            file=SimpleUploadedFile(
                'sample.jpg',
                b'image-bytes',
                content_type='image/jpeg',
            ),
            original_filename='sample.jpg',
            width=100,
            height=80,
        )
        self.label = Class.objects.create(
            project=self.project,
            name='Object',
            color='#ff7300',
        )
        Annotation.objects.bulk_create([
            Annotation(
                media=self.media,
                class_label=self.label,
                annotator=self.user,
                type='bbox',
                data={'x': 10, 'y': 12, 'width': 30, 'height': 20},
            ),
            Annotation(
                media=self.media,
                class_label=self.label,
                annotator=self.user,
                type='polygon',
                data={'points': [10, 10, 40, 10, 40, 30, 10, 30]},
            ),
            Annotation(
                media=self.media,
                class_label=self.label,
                annotator=self.user,
                type='keypoint',
                data={'points': [20, 20, 30, 30]},
            ),
            Annotation(
                media=self.media,
                class_label=self.label,
                annotator=self.user,
                type='tag',
                data={},
            ),
        ])
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = reverse('dataset-export', args=[self.dataset.id])

    def assert_zip_response(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/zip')
        self.assertTrue(response.content.startswith(b'PK'))
        archive = zipfile.ZipFile(io.BytesIO(response.content))
        self.assertIsNone(archive.testzip())
        return archive

    def test_exports_every_supported_format_with_export_format_query(self):
        expected_entries = {
            'coco': 'annotations/instances.json',
            'yolo': 'classes.txt',
            'voc': 'Annotations/sample.xml',
            'mask': 'masks/sample.png',
            'coco_keypoints': 'annotations/person_keypoints.json',
            'imagenet': 'labels.txt',
        }

        for export_format, expected_entry in expected_entries.items():
            with self.subTest(export_format=export_format):
                response = self.client.get(
                    self.url,
                    {'export_format': export_format},
                )
                with self.assert_zip_response(response) as archive:
                    self.assertIn(expected_entry, archive.namelist())

    def test_legacy_format_query_remains_supported(self):
        response = self.client.get(self.url, {'format': 'yolo'})

        with self.assert_zip_response(response) as archive:
            members = archive.namelist()
            self.assertIn('classes.txt', members)
            self.assertIn('labels/sample.txt', members)
            # data.yaml is now always included, even for un-split datasets
            self.assertIn('data.yaml', members)
            data_yaml = archive.read('data.yaml').decode()
            self.assertIn('train: images', data_yaml)
            self.assertIn('val: images', data_yaml)

    def test_save_images_includes_source_file(self):
        response = self.client.get(
            self.url,
            {'export_format': 'voc', 'save_images': '1'},
        )

        with self.assert_zip_response(response) as archive:
            self.assertIn('JPEGImages/sample.jpg', archive.namelist())

    def test_yolo_export_uses_configured_train_valid_test_folders(self):
        self.media.metadata = {'split': 'train'}
        self.media.save(update_fields=['metadata'])
        for filename, split in [('validation.jpg', 'val'), ('testing.jpg', 'test')]:
            Media.objects.create(
                dataset=self.dataset,
                type='image',
                file=SimpleUploadedFile(filename, f'{split}-bytes'.encode()),
                original_filename=filename,
                width=100,
                height=80,
                metadata={'split': split},
            )
        self.dataset.split_config = {'train': 70, 'val': 20, 'test': 10}
        self.dataset.save(update_fields=['split_config'])

        response = self.client.get(
            self.url,
            {'export_format': 'yolo', 'save_images': '1'},
        )

        with self.assert_zip_response(response) as archive:
            members = archive.namelist()
            self.assertIn('train/images/sample.jpg', members)
            self.assertIn('train/labels/sample.txt', members)
            self.assertIn('valid/images/validation.jpg', members)
            self.assertIn('valid/labels/validation.txt', members)
            self.assertIn('test/images/testing.jpg', members)
            self.assertIn('test/labels/testing.txt', members)
            data_yaml = archive.read('data.yaml').decode()
            self.assertIn('train: train/images', data_yaml)
            self.assertIn('val: valid/images', data_yaml)
            self.assertIn('test: test/images', data_yaml)
            self.assertIn('0: "Object"', data_yaml)

    def test_yolo_export_uses_fixed_test_dataset(self):
        self.media.metadata = {'split': 'train'}
        self.media.save(update_fields=['metadata'])
        Media.objects.create(
            dataset=self.dataset,
            type='image',
            file=SimpleUploadedFile('validation.jpg', b'validation-bytes'),
            original_filename='validation.jpg',
            width=100,
            height=80,
            metadata={'split': 'val'},
        )
        test_dataset = Dataset.objects.create(
            project=self.project,
            name='Fixed test dataset',
        )
        Media.objects.create(
            dataset=test_dataset,
            type='image',
            file=SimpleUploadedFile('fixed-test.jpg', b'fixed-test-bytes'),
            original_filename='fixed-test.jpg',
            width=100,
            height=80,
        )
        Media.objects.create(
            dataset=test_dataset,
            type='image',
            file=SimpleUploadedFile('augmented.jpg', b'augmented-bytes'),
            original_filename='augmented.jpg',
            width=100,
            height=80,
            metadata={'category': 'augmented'},
        )
        self.dataset.split_config = {
            'train': 80,
            'val': 20,
            'test': 0,
            'test_dataset_id': test_dataset.id,
        }
        self.dataset.save(update_fields=['split_config'])

        response = self.client.get(
            self.url,
            {'export_format': 'yolo', 'save_images': '1'},
        )

        with self.assert_zip_response(response) as archive:
            members = archive.namelist()
            self.assertIn('test/images/fixed-test.jpg', members)
            self.assertIn('test/labels/fixed-test.txt', members)
            self.assertNotIn('test/images/augmented.jpg', members)

    def test_invalid_export_format_returns_400(self):
        response = self.client.get(
            self.url,
            {'export_format': 'unsupported'},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('Unsupported format', response.json()['error'])

    def test_user_without_project_access_receives_404(self):
        outsider = UserModel.objects.create_user(
            username='export-outsider',
            password='secret',
        )
        self.client.force_authenticate(outsider)

        response = self.client.get(
            self.url,
            {'export_format': 'coco'},
        )

        self.assertEqual(response.status_code, 404)
