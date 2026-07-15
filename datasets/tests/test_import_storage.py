import threading
import time
from unittest.mock import Mock

from django.test import SimpleTestCase, override_settings

from datasets.views.dataset_view import (
    _dataset_import_batch_size,
    _dataset_import_storage_workers,
    _save_media_batch,
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
