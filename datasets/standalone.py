"""VisioX-only dataset browser (no CVAT): frames and thumbnails from stored Media."""

import mimetypes

from django.conf import settings
from django.db.models import Prefetch

from datasets.models import Dataset, Media


def standalone_enabled() -> bool:
    return bool(getattr(settings, 'VISIOX_STANDALONE', False))


def ordered_image_media(dataset: Dataset):
    return dataset.media_files.filter(type='image').order_by('uploaded_at', 'id')


def _annotation_to_dict(ann) -> dict:
    """Convert an Annotation instance to the browser frame annotation format."""
    data = ann.data or {}
    ann_type = ann.type
    if ann_type == 'bbox':
        ann_type = 'rectangle'
    return {
        'id': ann.id,
        'type': ann_type,
        'label_id': ann.class_label_id,
        'label': ann.class_label.name,
        'color': getattr(ann.class_label, 'color', None) or '#40e020',
        'points': data.get('points', []),
        'occluded': data.get('occluded', False),
        'attributes': [],
    }


def browser_payload(dataset: Dataset) -> dict:
    from annotations.models import Annotation

    media_qs = ordered_image_media(dataset).prefetch_related(
        Prefetch(
            'annotations',
            queryset=Annotation.objects.select_related('class_label').filter(is_valid=True),
        )
    )

    frames: list[dict] = []
    labels_map: dict[int, dict] = {}
    total_annotation_count = 0

    for i, m in enumerate(media_qs):
        name = m.original_filename or ''
        if not name and m.file:
            name = m.file.name.rsplit('/', 1)[-1]
        if not name:
            name = f'frame_{i}'

        frame_annotations = []
        for ann in m.annotations.all():
            frame_annotations.append(_annotation_to_dict(ann))
            if ann.class_label_id not in labels_map:
                labels_map[ann.class_label_id] = {
                    'id': ann.class_label_id,
                    'name': ann.class_label.name,
                    'color': getattr(ann.class_label, 'color', None) or '#40e020',
                }

        total_annotation_count += len(frame_annotations)
        frames.append({
            'frame': i,
            'media_id': m.id,
            'name': name,
            'width': m.width or 0,
            'height': m.height or 0,
            'annotations': frame_annotations,
        })

    return {
        'task_id': 0,
        'frame_count': len(frames),
        'labels': list(labels_map.values()),
        'frames': frames,
        'annotation_count': total_annotation_count,
    }


def synthetic_cvat_stats(dataset: Dataset) -> dict:
    from annotations.models import Annotation

    n = ordered_image_media(dataset).count()
    ann_count = Annotation.objects.filter(
        media__dataset=dataset, is_valid=True
    ).count()
    return {
        'exists': True,
        'task_id': 0,
        'name': dataset.name,
        'status': 'standalone',
        'size': n,
        'mode': 'annotation',
        'dimension': '2d',
        'jobs': [],
        'annotations': {'shapes': ann_count, 'tags': 0, 'tracks': 0, 'total': ann_count},
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
