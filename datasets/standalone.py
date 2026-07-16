"""VisioX-only dataset browser (no CVAT): frames and thumbnails from stored Media."""

import mimetypes

from django.db.models import Prefetch

from datasets.models import Dataset, Media


def ordered_image_media(dataset: Dataset):
    return dataset.media_files.filter(type='image').order_by('uploaded_at', 'id')


def is_augmented(media: Media) -> bool:
    """True if this media was produced by the augmentation pipeline."""
    if (media.metadata or {}).get('category') == 'augmented':
        return True
    name = media.file.name if media.file else ''
    return '/augmented/' in (name or '')


def raw_image_media(dataset: Dataset):
    """Original (non-augmented) images only."""
    return [m for m in ordered_image_media(dataset) if not is_augmented(m)]


def _annotation_to_dict(ann) -> dict:
    """Convert an Annotation instance to the browser frame annotation format."""
    data = ann.data or {}
    ann_type = ann.type
    points = data.get('points', [])
    if ann_type == 'bbox':
        ann_type = 'rectangle'
    if ann_type == 'rectangle' and not points:
        x = float(data.get('x') or 0)
        y = float(data.get('y') or 0)
        width = float(data.get('width') or 0)
        height = float(data.get('height') or 0)
        points = [x, y, x + width, y, x + width, y + height, x, y + height]
    return {
        'id': ann.id,
        'type': ann_type,
        'label_id': ann.class_label_id,
        'label': ann.class_label.name,
        'color': getattr(ann.class_label, 'color', None) or '#40e020',
        'points': points,
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
            'augmented': is_augmented(m),
            'split': (m.metadata or {}).get('split'),
        })

    return {
        'task_id': 0,
        'frame_count': len(frames),
        'labels': list(labels_map.values()),
        'frames': frames,
        'annotation_count': total_annotation_count,
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
