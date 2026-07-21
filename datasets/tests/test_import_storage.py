import threading
import time
import zipfile
from io import BytesIO
from unittest.mock import Mock

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test.client import RequestFactory
from django.test import SimpleTestCase, override_settings

from datasets.views.dataset_view import (
    _dataset_import_batch_size,
    _dataset_import_storage_workers,
    _duplicate_names_error,
    _yolo_image_name_map,
    _read_yolo_label_rows,
    _save_media_batch,
    _yolo_class_color,
    _yolo_class_index_offset,
)
from datasets.services.video_extraction import (
    Candidate,
    build_timestamps,
    descriptor_distance,
    normalize_video_extraction_config,
    select_diverse_candidates,
)


class _FakeFieldFile:
    def __init__(self, tracker, *, fail=False):
        self.name = ''
        self.storage = Mock()
        self._tracker = tracker
        self._fail = fail

    def save(self, filename, content, save=False):
        del content, save
        with self._tracker['lock']:
            self._tracker['active'] += 1
            self._tracker['maximum'] = max(self._tracker['maximum'], self._tracker['active'])
        try:
            time.sleep(0.02)
            if self._fail:
                raise OSError('storage failed')
            self.name = f'uploaded/{filename}'
        finally:
            with self._tracker['lock']:
                self._tracker['active'] -= 1


class _FakeMedia:
    def __init__(self, tracker, *, fail=False):
        self.file = _FakeFieldFile(tracker, fail=fail)


class DatasetImportStorageTests(SimpleTestCase):
    def test_video_extraction_config_uses_safe_defaults(self):
        config = normalize_video_extraction_config({'enabled': True, 'target': 120})

        self.assertEqual(config, {'enabled': True, 'target': 120})

    def test_video_extraction_config_rejects_invalid_target(self):
        with self.assertRaisesRegex(ValueError, 'target'):
            normalize_video_extraction_config({'enabled': True, 'target': 0})

    def test_video_timestamps_cover_each_target_bin(self):
        timestamps = build_timestamps(duration=100.0, target=5, candidates_per_target=3)

        self.assertEqual(len(timestamps), 15)
        self.assertEqual({bin_index for _, bin_index in timestamps}, set(range(5)))
        self.assertTrue(all(0 <= timestamp < 100 for timestamp, _ in timestamps))

    def test_video_selection_prefers_best_diverse_candidate_per_bin(self):
        candidates = [
            Candidate(1.0, 0, (1.0, 0.0), 100, 100, 0.4),
            Candidate(2.0, 0, (0.0, 1.0), 100, 100, 0.9),
            Candidate(7.0, 1, (0.0, 1.0), 100, 100, 0.9),
            Candidate(8.0, 1, (-1.0, 0.0), 100, 100, 0.7),
        ]

        selected = select_diverse_candidates(candidates, target=2)

        self.assertEqual([candidate.timestamp for candidate in selected], [2.0, 8.0])
        self.assertGreater(descriptor_distance((1.0, 0.0), (-1.0, 0.0)), 0.9)

    def test_multipart_parser_accepts_169_image_files(self):
        self.assertGreaterEqual(settings.DATA_UPLOAD_MAX_NUMBER_FILES, 500)
        files = [
            SimpleUploadedFile(f'image-{index}.jpg', b'image', content_type='image/jpeg')
            for index in range(169)
        ]

        request = RequestFactory().post('/datasets/1/start-import/', {'files': files})

        self.assertEqual(len(request.FILES.getlist('files')), 169)

    @override_settings(DATASET_IMPORT_STORAGE_WORKERS=3)
    def test_storage_batch_runs_with_bounded_concurrency(self):
        tracker = {'active': 0, 'maximum': 0, 'lock': threading.Lock()}
        media_items = [_FakeMedia(tracker) for _ in range(6)]

        _save_media_batch([
            (media, f'image-{index}.jpg', object())
            for index, media in enumerate(media_items)
        ])

        self.assertGreater(tracker['maximum'], 1)
        self.assertLessEqual(tracker['maximum'], 3)
        self.assertTrue(all(media.file.name for media in media_items))

    @override_settings(DATASET_IMPORT_STORAGE_WORKERS=2)
    def test_storage_batch_cleans_up_completed_files_after_failure(self):
        tracker = {'active': 0, 'maximum': 0, 'lock': threading.Lock()}
        successful = _FakeMedia(tracker)
        failing = _FakeMedia(tracker, fail=True)

        with self.assertRaisesRegex(OSError, 'storage failed'):
            _save_media_batch([
                (successful, 'success.jpg', object()),
                (failing, 'failure.jpg', object()),
            ])

        successful.file.storage.delete.assert_called_once_with('uploaded/success.jpg')

    @override_settings(DATASET_IMPORT_STORAGE_WORKERS=99, DATASET_IMPORT_BATCH_SIZE=24)
    def test_import_limits_are_sanitized(self):
        self.assertEqual(_dataset_import_storage_workers(), 16)
        self.assertEqual(_dataset_import_batch_size(), 24)

    def test_standard_yolo_class_ids_keep_zero_based_index(self):
        self.assertEqual(_yolo_class_index_offset({0, 2}, 3), 0)

    def test_duplicate_yolo_basenames_are_prefixed_with_split(self):
        image_keys = [
            'dataset/test/images/camera.jpg',
            'dataset/train/images/camera.jpg',
            'dataset/train/images/unique.jpg',
        ]
        split_map = {image_key: _split for image_key, _split in zip(image_keys, ['test', 'train', 'train'])}

        names = _yolo_image_name_map(image_keys, split_map)

        self.assertEqual(names[image_keys[0]], 'test__camera.jpg')
        self.assertEqual(names[image_keys[1]], 'train__camera.jpg')
        self.assertEqual(names[image_keys[2]], 'unique.jpg')
        self.assertEqual(len(set(names.values())), len(image_keys))

    def test_yolo_generated_name_does_not_collide_with_real_basename(self):
        image_keys = [
            'dataset/test/images/camera.jpg',
            'dataset/train/images/camera.jpg',
            'dataset/train/images/test__camera.jpg',
        ]
        split_map = {image_key: _split for image_key, _split in zip(image_keys, ['test', 'train', 'train'])}

        names = _yolo_image_name_map(image_keys, split_map)

        self.assertEqual(names[image_keys[0]], 'test__camera__2.jpg')
        self.assertEqual(len(set(names.values())), len(image_keys))

    def test_yolo_class_colors_are_distinct_and_repeat_safely(self):
        colors = [_yolo_class_color(index) for index in range(4)]

        self.assertEqual(len(set(colors)), 4)
        self.assertTrue(all(color != '#000000' for color in colors))
        self.assertEqual(_yolo_class_color(16), colors[0])

    def test_unambiguous_one_based_yolo_class_ids_are_normalized(self):
        self.assertEqual(_yolo_class_index_offset({1, 3}, 3), 1)

    def test_invalid_yolo_class_ids_are_rejected(self):
        with self.assertRaisesRegex(ValueError, r'0\.\.2'):
            _yolo_class_index_offset({0, 3}, 3)

    def test_yolo_label_rows_normalize_one_based_class_ids(self):
        archive_bytes = BytesIO()
        with zipfile.ZipFile(archive_bytes, 'w') as archive:
            archive.writestr('train/labels/sample.txt', '3 0.5 0.5 0.2 0.3\n')
        archive_bytes.seek(0)

        with zipfile.ZipFile(archive_bytes) as archive:
            rows, offset = _read_yolo_label_rows(
                archive,
                set(archive.namelist()),
                ['train/images/sample.jpg'],
                3,
            )

        self.assertEqual(offset, 1)
        self.assertEqual(rows['train/images/sample.jpg'][0][0], 2)

    def test_duplicate_name_error_is_shortened(self):
        message = _duplicate_names_error({f'image-{index:02}.jpg' for index in range(20)})

        self.assertIn('image-00.jpg', message)
        self.assertIn('and 10 more', message)
        self.assertNotIn('image-19.jpg', message)
