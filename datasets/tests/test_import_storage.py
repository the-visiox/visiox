import threading
import time
import zipfile
from io import BytesIO
from unittest.mock import Mock

from django.test import SimpleTestCase, override_settings

from datasets.views.dataset_view import (
    _dataset_import_batch_size,
    _dataset_import_storage_workers,
    _duplicate_names_error,
    _read_yolo_label_rows,
    _save_media_batch,
    _yolo_class_color,
    _yolo_class_index_offset,
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
