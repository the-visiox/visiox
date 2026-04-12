"""VisioX-only dataset browser (no CVAT): frames and thumbnails from stored Media."""

import mimetypes

from django.conf import settings

from datasets.models import Dataset, Media


def standalone_enabled() -> bool:
    return bool(getattr(settings, 'VISIOX_STANDALONE', False))


def ordered_image_media(dataset: Dataset):
    return dataset.media_files.filter(type='image').order_by('uploaded_at', 'id')


def browser_payload(dataset: Dataset) -> dict:
    frames: list[dict] = []
    for i, m in enumerate(ordered_image_media(dataset)):
        name = m.original_filename or ''
        if not name and m.file:
            name = m.file.name.rsplit('/', 1)[-1]
        if not name:
            name = f'frame_{i}'
        frames.append(
            {
                'frame': i,
                'media_id': m.id,
                'name': name,
                'width': m.width or 0,
                'height': m.height or 0,
                'annotations': [],
            }
        )
    return {
        'task_id': 0,
        'frame_count': len(frames),
        'labels': [],
        'frames': frames,
        'annotation_count': 0,
    }


def synthetic_cvat_stats(dataset: Dataset) -> dict:
    n = ordered_image_media(dataset).count()
    return {
        'exists': True,
        'task_id': 0,
        'name': dataset.name,
        'status': 'standalone',
        'size': n,
        'mode': 'annotation',
        'dimension': '2d',
        'jobs': [],
        'annotations': {'shapes': 0, 'tags': 0, 'tracks': 0, 'total': 0},
    }


def image_media_for_frame(dataset: Dataset, frame_num: int) -> Media | None:
    qs = list(ordered_image_media(dataset))
    if frame_num < 0 or frame_num >= len(qs):
        return None
    return qs[frame_num]


def guess_content_type(media: Media) -> str:
    name = media.original_filename or (media.file.name if media.file else '') or ''
    mime, _ = mimetypes.guess_type(name)
    if mime and mime.startswith('image/'):
        return mime
    return 'image/jpeg'
