"""Dataset browser helpers backed by stored image media."""

import mimetypes

from django.db.models import Prefetch

from datasets.models import Dataset, Media


def ordered_image_media(dataset: Dataset):
    return dataset.media_files.filter(type='image').order_by('uploaded_at', 'id')


def is_augmented(media: Media) -> bool:
    """Return whether media was produced by the augmentation pipeline."""
    if (media.metadata or {}).get('category') == 'augmented':
        return True
    name = media.file.name if media.file else ''
    return '/augmented/' in (name or '')


def raw_image_media(dataset: Dataset):
    """Return original, non-augmented images in browser order."""
    return [media for media in ordered_image_media(dataset) if not is_augmented(media)]


def _annotation_to_dict(annotation) -> dict:
    data = annotation.data or {}
    annotation_type = annotation.type
    points = data.get('points', [])
    if annotation_type == 'bbox':
        annotation_type = 'rectangle'
    if annotation_type == 'rectangle' and not points:
        x = float(data.get('x') or 0)
        y = float(data.get('y') or 0)
        width = float(data.get('width') or 0)
        height = float(data.get('height') or 0)
        points = [x, y, x + width, y, x + width, y + height, x, y + height]
    return {
        'id': annotation.id,
        'type': annotation_type,
        'label_id': annotation.class_label_id,
        'label': annotation.class_label.name,
        'color': getattr(annotation.class_label, 'color', None) or '#40e020',
        'points': points,
        'occluded': data.get('occluded', False),
        'attributes': [],
    }


def browser_payload(dataset: Dataset) -> dict:
    from annotations.models import Annotation

    media_queryset = ordered_image_media(dataset).prefetch_related(
        Prefetch(
            'annotations',
            queryset=Annotation.objects.select_related('class_label').filter(is_valid=True),
        )
    )

    frames: list[dict] = []
    labels: dict[int, dict] = {}
    annotation_count = 0

    for frame_index, media in enumerate(media_queryset):
        name = media.original_filename or ''
        if not name and media.file:
            name = media.file.name.rsplit('/', 1)[-1]
        if not name:
            name = f'frame_{frame_index}'

        frame_annotations = []
        for annotation in media.annotations.all():
            frame_annotations.append(_annotation_to_dict(annotation))
            labels.setdefault(annotation.class_label_id, {
                'id': annotation.class_label_id,
                'name': annotation.class_label.name,
                'color': getattr(annotation.class_label, 'color', None) or '#40e020',
            })

        annotation_count += len(frame_annotations)
        frames.append({
            'frame': frame_index,
            'media_id': media.id,
            'name': name,
            'width': media.width or 0,
            'height': media.height or 0,
            'annotations': frame_annotations,
            'augmented': is_augmented(media),
            'split': (media.metadata or {}).get('split'),
        })

    return {
        # Retained for API compatibility with existing frontend BrowserData.
        'task_id': 0,
        'frame_count': len(frames),
        'labels': list(labels.values()),
        'frames': frames,
        'annotation_count': annotation_count,
    }


def image_media_for_frame(dataset: Dataset, frame_num: int) -> Media | None:
    images = list(ordered_image_media(dataset))
    if frame_num < 0 or frame_num >= len(images):
        return None
    return images[frame_num]


def guess_content_type(media: Media) -> str:
    name = media.original_filename or (media.file.name if media.file else '') or ''
    mime_type, _ = mimetypes.guess_type(name)
    if mime_type and mime_type.startswith('image/'):
        return mime_type
    return 'image/jpeg'
