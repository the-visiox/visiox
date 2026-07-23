import json
import logging
import posixpath
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from types import SimpleNamespace

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Q
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response

from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

from core.jwt_query_auth import JWTAuthQueryOrHeader

from annotations.colors import class_color_for_index
from annotations.models import Annotation, Class
from annotations.serializers import AnnotationSerializer, JobAnnotationsReplaceSerializer
from core.permissions import HasPerm
from datasets.models import AugmentationJob, Dataset, DatasetImportJob, Media
from datasets.serializers import (
    DatasetSerializer,
    MediaSerializer,
    MediaUploadSerializer,
    MediaBulkDeleteSerializer,
)
from django.http import HttpResponse

from datasets.services.media_browser import (
    browser_payload,
    image_media_for_frame,
    guess_content_type,
    ordered_image_media,
    raw_image_media,
)
from datasets.services.video_extraction import (
    normalize_video_extraction_config,
    run_video_extraction_job,
)

logger = logging.getLogger(__name__)

DEFAULT_IMPORT_STORAGE_WORKERS = 4
MAX_IMPORT_STORAGE_WORKERS = 16
DEFAULT_IMPORT_BATCH_SIZE = 16
DEFAULT_DIRECT_UPLOAD_EXPIRES = 3600
DEFAULT_IMPORT_MAX_FILES = 5000
MAX_IMPORT_FILES = 10000


def _dataset_import_storage_workers() -> int:
    configured = int(getattr(settings, 'DATASET_IMPORT_STORAGE_WORKERS', DEFAULT_IMPORT_STORAGE_WORKERS))
    return max(1, min(configured, MAX_IMPORT_STORAGE_WORKERS))


def _dataset_import_batch_size() -> int:
    configured = int(getattr(settings, 'DATASET_IMPORT_BATCH_SIZE', DEFAULT_IMPORT_BATCH_SIZE))
    return max(1, configured)


def _dataset_import_max_files() -> int:
    configured = int(getattr(settings, 'DATASET_IMPORT_MAX_FILES', DEFAULT_IMPORT_MAX_FILES))
    return max(1, min(configured, MAX_IMPORT_FILES))


def _chunked(items: list, size: int):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _save_media_file(entry) -> None:
    media, filename, content = entry
    media.file.save(filename, content, save=False)


def _delete_unsaved_media_files(media_items: list[Media]) -> None:
    for media in media_items:
        storage_name = getattr(media.file, 'name', '')
        if not storage_name:
            continue
        try:
            media.file.storage.delete(storage_name)
        except Exception:
            logger.warning('Unable to clean up imported media file %s', storage_name, exc_info=True)


def _save_media_batch(entries: list[tuple[Media, str, object]]) -> None:
    """Upload a bounded batch concurrently while keeping ORM writes on the main thread."""
    if not entries:
        return

    media_items = [entry[0] for entry in entries]
    workers = min(_dataset_import_storage_workers(), len(entries))
    try:
        if workers == 1:
            for entry in entries:
                _save_media_file(entry)
            return
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix='dataset-storage') as executor:
            list(executor.map(_save_media_file, entries))
    except Exception:
        _delete_unsaved_media_files(media_items)
        raise


def _enqueue_dataset_label_cache_refresh(dataset_id: int) -> None:
    from datasets.tasks import enqueue_dataset_label_cache_refresh

    enqueue_dataset_label_cache_refresh(dataset_id)


def _enqueue_dataset_label_cache_clear(dataset_id: int) -> None:
    from datasets.tasks import enqueue_dataset_label_cache_clear

    enqueue_dataset_label_cache_clear(dataset_id)


def _verification_is_current(dataset: Dataset) -> bool:
    if dataset.verification_status != 'verified' or not dataset.verified_at:
        return False
    images = dataset.media_files.filter(type='image').filter(
        Q(metadata__category__isnull=True) | ~Q(metadata__category='augmented')
    )
    return not (
        images.filter(uploaded_at__gt=dataset.verified_at).exists()
        or images.filter(annotations__updated_at__gt=dataset.verified_at).exists()
    )


def _extract_image_dimensions(file):
    try:
        from PIL import Image
        img = Image.open(file)
        width, height = img.size
        file.seek(0)
        return width, height
    except Exception:
        return None, None


def _media_display_name(media) -> str:
    if media.original_filename:
        return media.original_filename
    if media.file:
        return media.file.name.rsplit('/', 1)[-1]
    return f'media-{media.id}'


def _build_transform_lists(pre: dict, aug: dict):
    """Build the Albumentations preprocessing and augmentation transform lists."""
    import cv2
    import albumentations as A

    pre_transforms = []
    if pre.get('resize') and pre.get('resize_width') and pre.get('resize_height'):
        pre_transforms.append(A.Resize(height=int(pre['resize_height']), width=int(pre['resize_width'])))
    if pre.get('grayscale'):
        pre_transforms.append(A.ToGray(num_output_channels=3, p=1.0))

    aug_transforms = []
    if aug.get('flip_h'):
        aug_transforms.append(A.HorizontalFlip(p=1.0))
    if aug.get('flip_v'):
        aug_transforms.append(A.VerticalFlip(p=1.0))
    if aug.get('rotate90'):
        aug_transforms.append(A.RandomRotate90(p=1.0))
    if float(aug.get('rotation', 0)) > 0:
        aug_transforms.append(A.Rotate(limit=float(aug['rotation']), border_mode=cv2.BORDER_REFLECT_101, p=1.0))
    if float(aug.get('shear', 0)) > 0:
        aug_transforms.append(A.Affine(shear=(-float(aug['shear']), float(aug['shear'])), p=1.0))
    brightness = float(aug.get('brightness', 0))
    contrast = float(aug.get('contrast', 0))
    if brightness > 0 or contrast > 0:
        aug_transforms.append(A.RandomBrightnessContrast(brightness_limit=brightness, contrast_limit=contrast, p=1.0))
    hue = float(aug.get('hue', 0))
    saturation = float(aug.get('saturation', 0))
    if hue > 0 or saturation > 0:
        aug_transforms.append(A.HueSaturationValue(
            hue_shift_limit=int(hue), sat_shift_limit=int(saturation), val_shift_limit=0, p=1.0,
        ))
    if float(aug.get('blur', 0)) > 0:
        sigma = max(0.1, float(aug['blur']))
        aug_transforms.append(A.GaussianBlur(blur_limit=(3, 3), sigma_limit=(sigma, sigma), p=1.0))
    if float(aug.get('noise', 0)) > 0:
        noise = float(aug['noise'])
        aug_transforms.append(A.GaussNoise(std_range=(noise * 0.5, noise), p=1.0))
    if float(aug.get('motion_blur', 0)) > 0:
        k = max(3, int(aug['motion_blur']))
        if k % 2 == 0:
            k += 1
        aug_transforms.append(A.MotionBlur(blur_limit=(k, k), p=1.0))
    if aug.get('cutout'):
        aug_transforms.append(
            A.CoarseDropout(
                num_holes_range=(4, 8),
                hole_height_range=(0.05, 0.15),
                hole_width_range=(0.05, 0.15),
                p=1.0,
            )
        )

    return pre_transforms, aug_transforms


def _build_pipelines(pre: dict, aug: dict):
    """Build Albumentations preprocessing and augmentation pipelines from config dicts."""
    import albumentations as A

    pre_transforms, aug_transforms = _build_transform_lists(pre, aug)
    pre_pipeline = A.Compose(pre_transforms) if pre_transforms else None
    aug_pipeline = A.Compose(aug_transforms) if aug_transforms else None
    return pre_pipeline, aug_pipeline


def _load_media_np(media, pre: dict, pre_pipeline) -> 'np.ndarray':
    import numpy as np
    from PIL import Image, ImageOps

    with media.file.open('rb') as f:
        pil_img = Image.open(f).convert('RGB')
        pil_img.load()

    if pre.get('auto_orient'):
        pil_img = ImageOps.exif_transpose(pil_img)

    img_np = np.array(pil_img)
    if pre_pipeline is not None:
        img_np = pre_pipeline(image=img_np)['image']
    return img_np


def _make_thumbnail_bytes(image_bytes: bytes, max_size: int = 400, quality: int = 70) -> bytes:
    """Downscale + re-encode to a small JPEG for gallery views."""
    import io
    from PIL import Image, ImageOps

    img = Image.open(io.BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img)
    if img.mode not in ('RGB', 'L'):
        img = img.convert('RGB')
    img.thumbnail((max_size, max_size))
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=quality)
    return buf.getvalue()


def _existing_media_names_in_dataset(dataset: Dataset, names: list[str]) -> set[str]:
    return set(dataset.media_files.filter(original_filename__in=names).values_list('original_filename', flat=True))


def _augment_dataset(dataset: Dataset, pre: dict, aug: dict, multiplier: int, progress=None) -> int:
    """Generate `multiplier` augmented copies of each original image, carrying the
    annotations (and per-image label profile) through the same transform so labels
    follow the augmentation. Calls progress(done, generated) after every copy."""
    import io
    from collections import defaultdict
    import albumentations as A
    from PIL import Image
    from django.core.files.base import ContentFile
    from datasets.models import MediaLabelProfile

    pre_transforms, aug_transforms = _build_transform_lists(pre, aug)
    transforms = pre_transforms + aug_transforms
    if not transforms:
        return 0
    ann_pipeline = A.Compose(
        transforms,
        bbox_params=A.BboxParams(format='pascal_voc', label_fields=['bbox_idx'], clip=True, min_visibility=0.0),
        keypoint_params=A.KeypointParams(format='xy', label_fields=['kp_idx'], remove_invisible=False),
    ) if transforms else None

    def _clamp(v, lo, hi):
        return max(lo, min(hi, v))

    media_list = [media for media in raw_image_media(dataset) if (media.metadata or {}).get('split') == 'train']
    generated = 0
    done = 0

    for media in media_list:
        try:
            raw_np = _load_media_np(media, {'auto_orient': pre.get('auto_orient')}, None)
            src_h, src_w = raw_np.shape[:2]
            original_stem = _media_display_name(media).rsplit('.', 1)[0]
            src_anns = list(
                Annotation.objects.filter(media=media, is_valid=True).select_related('class_label')
            )
            src_profile = MediaLabelProfile.objects.filter(media=media).values_list('labels', flat=True).first()

            base_bboxes, base_bbox_idx = [], []
            base_kps, base_kp_idx = [], []
            for ai, ann in enumerate(src_anns):
                d = ann.data or {}
                t = ann.type
                if t in ('bbox', 'rectangle'):
                    x = _clamp(float(d.get('x', 0)), 0, src_w)
                    y = _clamp(float(d.get('y', 0)), 0, src_h)
                    x2 = _clamp(x + float(d.get('width', 0)), 0, src_w)
                    y2 = _clamp(y + float(d.get('height', 0)), 0, src_h)
                    if x2 > x and y2 > y:
                        base_bboxes.append([x, y, x2, y2])
                        base_bbox_idx.append(ai)
                elif t in ('polygon', 'polyline', 'point'):
                    pts = d.get('points', []) or []
                    for vi in range(0, len(pts) - 1, 2):
                        base_kps.append((_clamp(float(pts[vi]), 0, src_w), _clamp(float(pts[vi + 1]), 0, src_h)))
                        base_kp_idx.append(ai)
                elif t == 'tag':
                    base_kps.append((_clamp(float(d.get('x', 0)), 0, src_w), _clamp(float(d.get('y', 0)), 0, src_h)))
                    base_kp_idx.append(ai)
        except Exception:
            logger.exception('Failed to prepare augmentation for media %d', media.id)
            done += multiplier
            if progress:
                progress(done, generated)
            continue

        for i in range(multiplier):
            try:
                if ann_pipeline is not None:
                    out = ann_pipeline(
                        image=raw_np,
                        bboxes=list(base_bboxes), bbox_idx=list(base_bbox_idx),
                        keypoints=list(base_kps), kp_idx=list(base_kp_idx),
                    )
                    img_np = out['image']
                    t_bboxes, t_bbox_idx = out['bboxes'], out['bbox_idx']
                    t_kps, t_kp_idx = out['keypoints'], out['kp_idx']
                else:
                    img_np = raw_np
                    t_bboxes, t_bbox_idx = base_bboxes, base_bbox_idx
                    t_kps, t_kp_idx = base_kps, base_kp_idx

                out_h, out_w = img_np.shape[:2]
                pil_out = Image.fromarray(img_np)
                buf = io.BytesIO()
                pil_out.save(buf, format='JPEG', quality=88)
                full_bytes = buf.getvalue()

                aug_name = f'aug_{i + 1}_{original_stem}.jpg'
                new_media = Media(
                    dataset=dataset, type='image', original_filename=aug_name,
                    width=pil_out.width, height=pil_out.height,
                    metadata={'category': 'augmented', 'source_media_id': media.id, 'split': 'train'},
                )
                new_media._upload_category = 'augmented'
                new_media.file.save(aug_name, ContentFile(full_bytes), save=True)
                # Precompute the gallery thumbnail now (image already in memory).
                try:
                    new_media.thumbnail.save(f'{aug_name}', ContentFile(_make_thumbnail_bytes(full_bytes)), save=True)
                except Exception:
                    logger.exception('Failed to build thumbnail for augmented media %s', new_media.id)

                new_anns = []
                for bb, ai in zip(t_bboxes, t_bbox_idx):
                    x_min, y_min, x_max, y_max = (round(float(v), 2) for v in bb)
                    src = src_anns[int(ai)]
                    new_anns.append(Annotation(
                        media=new_media, class_label=src.class_label, annotator=src.annotator,
                        type=src.type, frame=0,
                        data={
                            'x': x_min,
                            'y': y_min,
                            'width': round(x_max - x_min, 2),
                            'height': round(y_max - y_min, 2),
                        },
                    ))
                grouped = defaultdict(list)
                for (kx, ky), ai in zip(t_kps, t_kp_idx):
                    grouped[int(ai)].append(
                        (
                            round(_clamp(float(kx), 0, out_w), 2),
                            round(_clamp(float(ky), 0, out_h), 2),
                        )
                    )
                for ai, pts in grouped.items():
                    src = src_anns[ai]
                    ann_data = (
                        {'x': pts[0][0], 'y': pts[0][1]}
                        if src.type == 'tag'
                        else {
                            'points': [
                                coordinate
                                for point in pts
                                for coordinate in point
                            ]
                        }
                    )
                    new_anns.append(Annotation(
                        media=new_media, class_label=src.class_label, annotator=src.annotator,
                        type=src.type, frame=0, data=ann_data,
                    ))
                if new_anns:
                    Annotation.objects.bulk_create(new_anns)
                # Carry the per-image label roster so the augmented frame's LABELS panel matches the origin.
                if src_profile:
                    MediaLabelProfile.objects.update_or_create(media=new_media, defaults={'labels': src_profile})
                generated += 1
            except Exception:
                logger.exception('Failed to apply augmentation for media %d', media.id)
            finally:
                done += 1
                if progress:
                    progress(done, generated)

    return generated


def run_augmentation_job(job_id: int, dataset_id: int, pre: dict, aug: dict, multiplier: int):
    """Execute an augmentation job and persist progress to the AugmentationJob row.

    Runs either in a background thread (dev) or a Celery worker (production) — the
    DB-backed progress means any web worker can report status, and it survives
    process restarts.
    """
    from django.db import connection
    from django.utils import timezone

    try:
        dataset = Dataset.objects.get(id=dataset_id)
        total = AugmentationJob.objects.filter(id=job_id).values_list('total', flat=True).first() or 0
        step = max(1, total // 50)  # throttle DB writes to ~50 updates + final

        def _progress(done, generated):
            # updated_at doubles as a heartbeat for stale-job detection; .update()
            # does not trigger auto_now, so set it explicitly.
            if done % step == 0 or done >= total:
                AugmentationJob.objects.filter(id=job_id).update(
                    done=done, generated=generated, updated_at=timezone.now(),
                )

        _augment_dataset(dataset, pre, aug, multiplier, _progress)
        AugmentationJob.objects.filter(id=job_id).update(status='done', updated_at=timezone.now())
    except Exception as exc:
        logger.exception('Augmentation job %s failed', job_id)
        AugmentationJob.objects.filter(id=job_id).update(status='error', error=str(exc), updated_at=timezone.now())
    finally:
        connection.close()


# A running job whose heartbeat (updated_at) is older than this is treated as dead
# (worker crashed / was restarted mid-run).
AUG_JOB_STALE_SECONDS = 300


YOLO_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}
MEDIA_IMAGE_EXTENSIONS = YOLO_IMAGE_EXTENSIONS | {'.gif', '.tif', '.tiff'}
MEDIA_VIDEO_EXTENSIONS = {'.mp4', '.webm', '.mov', '.mkv', '.avi', '.m4v'}


def _zip_file_members(archive: zipfile.ZipFile) -> list[str]:
    return [
        name.replace('\\', '/')
        for name in archive.namelist()
        if name and not name.endswith('/') and not name.startswith('__MACOSX/')
    ]


def _parse_yolo_names(data_yaml: str) -> list[str]:
    names: list[str] = []
    in_names_block = False
    for raw_line in data_yaml.splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('names:'):
            value = line.split(':', 1)[1].strip()
            if value.startswith('[') and value.endswith(']'):
                return [
                    item.strip().strip('"\'')
                    for item in value[1:-1].split(',')
                    if item.strip().strip('"\'')
                ]
            if value:
                return [value.strip('"\'')]
            in_names_block = True
            continue
        if in_names_block:
            if line.startswith('- '):
                names.append(line[2:].strip().strip('"\''))
                continue
            if ':' in line:
                _, value = line.split(':', 1)
                value = value.strip().strip('"\'')
                if value:
                    names.append(value)
                continue
            break
    return names


def _yolo_label_key(image_key: str) -> str:
    parts = image_key.split('/')
    try:
        images_idx = parts.index('images')
    except ValueError:
        return ''
    label_parts = parts[:]
    label_parts[images_idx] = 'labels'
    label_parts[-1] = posixpath.splitext(label_parts[-1])[0] + '.txt'
    return '/'.join(label_parts)


def _yolo_split_name(image_key: str) -> str | None:
    for part in image_key.split('/'):
        if part in ('train', 'test'):
            return part
        if part in ('valid', 'val'):
            return 'val'
    return None


def _yolo_image_name_map(image_keys: list[str], split_map: dict[str, str | None]) -> dict[str, str]:
    """Return stable unique media names while preserving every archive image."""
    if len(image_keys) != len(set(image_keys)):
        raise ValueError('YOLO ZIP contains duplicate image paths.')

    base_name_counts: dict[str, int] = {}
    for image_key in image_keys:
        base_name = posixpath.basename(image_key)
        base_name_counts[base_name] = base_name_counts.get(base_name, 0) + 1

    result = {
        image_key: posixpath.basename(image_key)
        for image_key in image_keys
        if base_name_counts[posixpath.basename(image_key)] == 1
    }
    used_names = set(result.values())
    for image_key in sorted(image_keys):
        base_name = posixpath.basename(image_key)
        if base_name_counts[base_name] == 1:
            continue
        stem, extension = posixpath.splitext(base_name)
        split = split_map.get(image_key) or 'image'
        candidate = f'{split}__{stem}{extension}'
        sequence = 2
        while candidate in used_names:
            candidate = f'{split}__{stem}__{sequence}{extension}'
            sequence += 1
        result[image_key] = candidate
        used_names.add(candidate)
    return result


def _clamp_float(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _yolo_class_color(index: int) -> str:
    return class_color_for_index(index)


def _yolo_class_index_offset(class_ids: set[int], class_count: int) -> int:
    """Return 0 for standard YOLO ids or 1 for an unambiguous 1-based export."""
    if not class_ids:
        return 0
    if all(0 <= class_id < class_count for class_id in class_ids):
        return 0
    if (
        0 not in class_ids
        and class_count in class_ids
        and all(1 <= class_id <= class_count for class_id in class_ids)
    ):
        return 1
    observed = ', '.join(str(class_id) for class_id in sorted(class_ids)[:10])
    raise ValueError(
        f'YOLO label class ids must be 0..{class_count - 1}. '
        f'Observed: {observed or "none"}.'
    )


def _read_yolo_label_rows(
    archive: zipfile.ZipFile,
    members: set[str],
    image_keys: list[str],
    class_count: int,
) -> tuple[dict[str, list[tuple[int, float, float, float, float]]], int]:
    rows_by_image: dict[str, list[tuple[int, float, float, float, float]]] = {}
    class_ids: set[int] = set()
    for image_key in image_keys:
        label_key = _yolo_label_key(image_key)
        rows = []
        if label_key and label_key in members:
            label_text = archive.read(label_key).decode('utf-8', errors='ignore')
            for line in label_text.splitlines():
                parts = line.strip().split()
                if not parts:
                    continue
                if len(parts) < 5:
                    raise ValueError(f'Invalid YOLO label row in {label_key}: {line.strip()}')
                try:
                    class_idx = int(float(parts[0]))
                    cx, cy, bw, bh = [float(value) for value in parts[1:5]]
                except (TypeError, ValueError) as exc:
                    raise ValueError(f'Invalid YOLO label row in {label_key}: {line.strip()}') from exc
                class_ids.add(class_idx)
                rows.append((class_idx, cx, cy, bw, bh))
        rows_by_image[image_key] = rows

    offset = _yolo_class_index_offset(class_ids, class_count)
    if offset:
        rows_by_image = {
            image_key: [
                (class_idx - offset, cx, cy, bw, bh)
                for class_idx, cx, cy, bw, bh in rows
            ]
            for image_key, rows in rows_by_image.items()
        }
    return rows_by_image, offset


def _duplicate_names_error(names: set[str]) -> str:
    ordered = sorted(names)
    preview = ', '.join(ordered[:10])
    remaining = len(ordered) - min(len(ordered), 10)
    suffix = f' and {remaining} more' if remaining else ''
    return f'One or more image names already exist in this dataset: {preview}{suffix}.'


def _delete_staged_files(staged_files: list[dict]) -> None:
    for item in staged_files:
        key = item.get('key')
        if key:
            try:
                default_storage.delete(key)
            except Exception:
                logger.warning('Unable to delete staged import file %s', key, exc_info=True)


def _infer_media_type(uploaded_file, forced_media_type: str | None = None) -> str | None:
    if forced_media_type in ('image', 'video'):
        return forced_media_type
    content_type = (getattr(uploaded_file, 'content_type', '') or '').lower()
    if content_type.startswith('image/'):
        return 'image'
    if content_type.startswith('video/'):
        return 'video'
    extension = posixpath.splitext(getattr(uploaded_file, 'name', '') or '')[1].lower()
    if extension in MEDIA_IMAGE_EXTENSIONS:
        return 'image'
    if extension in MEDIA_VIDEO_EXTENSIONS:
        return 'video'
    return None


def _validate_dataset_import_files(
    dataset: Dataset,
    import_format: str,
    files: list,
    *,
    forced_media_type: str | None = None,
    max_files: int | None = None,
) -> None:
    if not files:
        raise ValueError('No files provided. Use form field "files".')
    if max_files is not None and len(files) > max_files:
        raise ValueError(f'Maximum {max_files} files per import job.')

    if import_format == 'yolo26':
        if len(files) != 1:
            raise ValueError('YOLO26 import requires exactly one .zip archive.')
        if not files[0].name.lower().endswith('.zip'):
            raise ValueError('YOLO26 import requires a .zip archive.')
        return

    if import_format != 'images':
        raise ValueError('Only Images and YOLO26 imports are currently supported.')

    names = [posixpath.basename(getattr(file_obj, 'name', '') or '') for file_obj in files]
    if not all(names):
        raise ValueError('Every file must have a non-empty name.')
    if len(names) != len(set(names)):
        raise ValueError('This import contains duplicate file names.')
    clashes = _existing_media_names_in_dataset(dataset, names)
    if clashes:
        raise ValueError(f'One or more file names already exist in this dataset: {", ".join(sorted(clashes))}')

    unsupported = sorted(
        posixpath.basename(getattr(file_obj, 'name', '') or '')
        for file_obj in files
        if _infer_media_type(file_obj, forced_media_type) is None
    )
    if unsupported:
        raise ValueError(
            f'Unsupported files for image/video import: {", ".join(unsupported[:10])}'
        )


def _dataset_import_options(raw_video_extraction, import_format: str, files: list) -> dict:
    if not raw_video_extraction:
        return {}
    if isinstance(raw_video_extraction, dict):
        parsed_video_extraction = raw_video_extraction
    else:
        try:
            parsed_video_extraction = json.loads(raw_video_extraction)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError('video_extraction must be valid JSON.') from exc

    video_extraction = normalize_video_extraction_config(parsed_video_extraction)
    if not video_extraction.get('enabled'):
        return {}
    if import_format != 'images':
        raise ValueError('Video extraction is only available for Images imports.')
    non_videos = [
        posixpath.basename(getattr(file_obj, 'name', '') or '')
        for file_obj in files
        if _infer_media_type(file_obj) != 'video'
    ]
    if non_videos:
        raise ValueError(
            'When video extraction is enabled, upload video files only. '
            f'Remove: {", ".join(non_videos[:10])}'
        )
    return {'video_extraction': video_extraction}


def _import_job_data(job: DatasetImportJob) -> dict:
    return {
        'id': job.id,
        'format': job.format,
        'status': job.status,
        'total': job.total,
        'done': job.done,
    }


def _accepted_import_response(request, dataset: Dataset, job: DatasetImportJob) -> Response:
    dataset.refresh_from_db()
    return Response(
        {
            'accepted': True,
            'dataset': DatasetSerializer(dataset, context={'request': request}).data,
            'job': _import_job_data(job),
        },
        status=status.HTTP_202_ACCEPTED,
    )


def _direct_upload_url(storage_key: str, content_type: str) -> str:
    if not getattr(settings, 'USE_MINIO', False):
        raise RuntimeError('Direct upload requires MinIO storage.')
    storage = default_storage
    normalized_key = storage._normalize_name(storage_key)  # django-storages adds its optional location prefix.
    expires = int(getattr(settings, 'DATASET_DIRECT_UPLOAD_EXPIRES', DEFAULT_DIRECT_UPLOAD_EXPIRES))
    return storage.connection.meta.client.generate_presigned_url(
        'put_object',
        Params={
            'Bucket': storage.bucket_name,
            'Key': normalized_key,
            'ContentType': content_type,
        },
        ExpiresIn=max(60, expires),
    )


def _stage_dataset_import_file(entry) -> dict:
    index, uploaded_file, dataset_id, job_id, forced_media_type = entry
    filename = posixpath.basename(uploaded_file.name)
    stage_key = (
        f'import-staging/datasets/{dataset_id}/jobs/{job_id}/'
        f'{index + 1}_{uuid.uuid4().hex}_{filename}'
    )
    saved_key = default_storage.save(stage_key, uploaded_file)
    return {
        'key': saved_key,
        'name': filename,
        'size': uploaded_file.size,
        'content_type': getattr(uploaded_file, 'content_type', ''),
        'media_type': _infer_media_type(uploaded_file, forced_media_type),
    }


def _queue_dataset_import_job(
    request,
    dataset: Dataset,
    files: list,
    import_format: str,
    *,
    forced_media_type: str | None = None,
    replace_existing: bool = False,
    import_options: dict | None = None,
) -> Response:
    job = DatasetImportJob.objects.create(
        dataset=dataset,
        format=import_format,
        status='queued',
        total=len(files),
        done=0,
        summary={'replace_existing': replace_existing, **(import_options or {})},
        created_by=request.user,
    )

    staged_files = []
    try:
        entries = [
            (index, uploaded_file, dataset.id, job.id, forced_media_type)
            for index, uploaded_file in enumerate(files)
        ]
        workers = min(_dataset_import_storage_workers(), len(entries))
        if workers == 1:
            staged_files = [_stage_dataset_import_file(entry) for entry in entries]
        else:
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix='dataset-staging') as executor:
                futures = [executor.submit(_stage_dataset_import_file, entry) for entry in entries]
                try:
                    staged_files = [future.result() for future in futures]
                except Exception:
                    staged_files = [
                        future.result()
                        for future in futures
                        if future.done() and not future.cancelled() and future.exception() is None
                    ]
                    raise
    except Exception as exc:
        _delete_staged_files(staged_files)
        job.status = 'error'
        job.error = f'Could not stage uploaded files: {exc}'
        job.save(update_fields=['status', 'error', 'updated_at'])
        logger.exception('Could not stage files for dataset import job %s', job.id)
        return Response(
            {'detail': 'Could not stage uploaded files. Please try again.', 'job_id': job.id},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    job.staged_files = staged_files
    job.save(update_fields=['staged_files', 'updated_at'])

    from datasets.tasks import enqueue_dataset_import_job

    transaction.on_commit(lambda job_id=job.id: enqueue_dataset_import_job(job_id))
    return _accepted_import_response(request, dataset, job)


def _import_staged_media_files(job: DatasetImportJob) -> dict:
    dataset = job.dataset
    staged_files = list(job.staged_files or [])
    names = [item.get('name') for item in staged_files if item.get('name')]
    if len(names) != len(set(names)):
        raise ValueError('This import contains duplicate file names.')
    clashes = _existing_media_names_in_dataset(dataset, names)
    if clashes:
        raise ValueError(f'One or more file names already exist in this dataset: {", ".join(sorted(clashes))}')

    # Resolve upload-path relationships before storage threads start so worker
    # threads never trigger lazy ORM queries on their own database connections.
    dataset.project.owner

    created = 0
    batch_size = _dataset_import_batch_size()
    for item_batch in _chunked(staged_files, batch_size):
        media_batch = []
        storage_entries = []
        with ExitStack() as sources:
            for item in item_batch:
                name = item.get('name')
                key = item.get('key')
                media_type = item.get('media_type') or 'image'
                if not name or not key:
                    continue

                source = sources.enter_context(default_storage.open(key, 'rb'))
                staged_file = File(source, name=name)
                width, height = (None, None)
                if media_type == 'image':
                    width, height = _extract_image_dimensions(staged_file)
                    staged_file.seek(0)

                media = Media(
                    dataset=dataset,
                    type=media_type,
                    original_filename=name,
                    width=width,
                    height=height,
                    file_size=item.get('size') or getattr(staged_file, 'size', None),
                    metadata={'import_format': 'images', 'import_job_id': job.id},
                )
                media_batch.append(media)
                storage_entries.append((media, name, staged_file))

            _save_media_batch(storage_entries)

        try:
            Media.objects.bulk_create(media_batch)
        except Exception:
            _delete_unsaved_media_files(media_batch)
            raise

        created += len(media_batch)
        job.done = created
        job.save(update_fields=['done', 'updated_at'])

    return {'format': 'images', 'files': created}


def _import_yolo26_archive_from_file(
    dataset: Dataset,
    archive_file,
    archive_name: str,
    user,
    job: DatasetImportJob | None = None,
) -> dict:
    try:
        archive = zipfile.ZipFile(archive_file)
    except zipfile.BadZipFile as exc:
        raise ValueError('The uploaded file is not a valid ZIP archive.') from exc

    with archive:
        members = _zip_file_members(archive)
        data_yaml_key = next(
            (name for name in members if posixpath.basename(name).lower() in ('data.yaml', 'data.yml')),
            None,
        )
        if not data_yaml_key:
            raise ValueError('YOLO26 ZIP must include data.yaml.')

        try:
            data_yaml = archive.read(data_yaml_key).decode('utf-8')
        except UnicodeDecodeError as exc:
            raise ValueError('data.yaml must be UTF-8 encoded.') from exc

        class_names = _parse_yolo_names(data_yaml)
        if not class_names:
            raise ValueError('data.yaml must define at least one class in names.')

        image_keys = [
            name
            for name in members
            if '/images/' in f'/{name}'
            and posixpath.splitext(name)[1].lower() in YOLO_IMAGE_EXTENSIONS
        ]
        if not image_keys:
            raise ValueError('YOLO26 ZIP must include images under train/valid/test images folders.')

        image_split_map = {name: _yolo_split_name(name) for name in image_keys}
        missing_split = [name for name, split in image_split_map.items() if split is None]
        if missing_split:
            raise ValueError('Every YOLO26 image must be under train/images, valid/images, val/images, or test/images.')
        available_splits = set(image_split_map.values())
        if 'train' not in available_splits or 'val' not in available_splits:
            raise ValueError('YOLO26 ZIP must include both train and valid/val image splits.')

        if job:
            job.total = len(image_keys)
            job.done = 0
            job.save(update_fields=['total', 'done', 'updated_at'])

        image_name_map = _yolo_image_name_map(image_keys, image_split_map)
        filenames = list(image_name_map.values())
        label_rows_by_image, class_index_offset = _read_yolo_label_rows(
            archive,
            set(members),
            image_keys,
            len(class_names),
        )
        replace_existing = bool(job and (job.summary or {}).get('replace_existing'))
        existing_media_by_name = {
            media.original_filename: media
            for media in dataset.media_files.filter(original_filename__in=filenames)
        }
        clashes = set(existing_media_by_name)
        if clashes and not replace_existing:
            raise ValueError(_duplicate_names_error(clashes))

        split_counts = {'train': 0, 'val': 0, 'test': 0}
        class_split_counts = {
            class_name: {'train': 0, 'val': 0, 'test': 0}
            for class_name in class_names
        }
        with transaction.atomic():
            classes = []
            for class_index, class_name in enumerate(class_names):
                class_color = _yolo_class_color(class_index)
                class_obj, created = Class.objects.get_or_create(
                    project=dataset.project,
                    name=class_name,
                    defaults={'color': class_color},
                )
                if not created and class_obj.color.lower() == '#000000':
                    class_obj.color = class_color
                    class_obj.save(update_fields=['color'])
                classes.append(class_obj)

            dataset.project.owner
            if existing_media_by_name:
                Annotation.objects.filter(media__in=existing_media_by_name.values()).delete()

            processed_media = []
            created_count = 0
            reused_count = 0
            annotations = []
            batch_size = _dataset_import_batch_size()
            for image_batch in _chunked(image_keys, batch_size):
                prepared_media = []
                storage_entries = []
                new_media_batch = []
                existing_media_batch = []
                for image_key in image_batch:
                    source_image_name = posixpath.basename(image_key)
                    image_name = image_name_map[image_key]
                    split = image_split_map[image_key]
                    metadata = {
                        'import_format': 'yolo26',
                        'source_archive': archive_name,
                        'source_archive_path': image_key,
                    }
                    if image_name != source_image_name:
                        metadata['source_filename'] = source_image_name
                    if job:
                        metadata['import_job_id'] = job.id
                    if split:
                        metadata['split'] = split
                        if metadata['split'] in split_counts:
                            split_counts[metadata['split']] += 1

                    media = existing_media_by_name.get(image_name)
                    if media:
                        width, height = media.width, media.height
                        if not width or not height:
                            image_content = ContentFile(archive.read(image_key), name=image_name)
                            width, height = _extract_image_dimensions(image_content)
                            media.width = width
                            media.height = height
                        merged_metadata = dict(media.metadata or {})
                        merged_metadata.update(metadata)
                        media.metadata = merged_metadata
                        metadata = merged_metadata
                        existing_media_batch.append(media)
                        reused_count += 1
                    else:
                        image_content = ContentFile(archive.read(image_key), name=image_name)
                        width, height = _extract_image_dimensions(image_content)
                        image_content.seek(0)
                        media = Media(
                            dataset=dataset,
                            type='image',
                            original_filename=image_name,
                            width=width,
                            height=height,
                            file_size=image_content.size,
                            metadata=metadata,
                        )
                        new_media_batch.append(media)
                        storage_entries.append((media, image_name, image_content))
                        created_count += 1
                    prepared_media.append((image_key, media, width, height, metadata))

                if storage_entries:
                    _save_media_batch(storage_entries)
                    try:
                        Media.objects.bulk_create(new_media_batch)
                    except Exception:
                        _delete_unsaved_media_files(new_media_batch)
                        raise
                if existing_media_batch:
                    Media.objects.bulk_update(existing_media_batch, ['width', 'height', 'metadata'])

                for image_key, media, width, height, metadata in prepared_media:
                    processed_media.append(media)
                    if not width or not height:
                        continue
                    media_class_splits = set()
                    for class_idx, cx, cy, bw, bh in label_rows_by_image.get(image_key, []):
                        media_split = metadata.get('split')
                        if media_split in ('train', 'val', 'test'):
                            media_class_splits.add((class_names[class_idx], media_split))

                        box_width = bw * width
                        box_height = bh * height
                        x = (cx * width) - (box_width / 2)
                        y = (cy * height) - (box_height / 2)
                        x = _clamp_float(x, 0, width)
                        y = _clamp_float(y, 0, height)
                        box_width = _clamp_float(box_width, 0, width - x)
                        box_height = _clamp_float(box_height, 0, height - y)
                        if box_width <= 0 or box_height <= 0:
                            continue

                        annotations.append(
                            Annotation(
                                media=media,
                                class_label=classes[class_idx],
                                annotator=user,
                                type='bbox',
                                data={
                                    'x': round(x, 2),
                                    'y': round(y, 2),
                                    'width': round(box_width, 2),
                                    'height': round(box_height, 2),
                                },
                                frame=0,
                            )
                        )
                    for class_name, media_split in media_class_splits:
                        class_split_counts[class_name][media_split] += 1

                if job:
                    job.done = len(processed_media)
                    job.save(update_fields=['done', 'updated_at'])

            if annotations:
                Annotation.objects.bulk_create(annotations, batch_size=1000)

            from django.utils import timezone

            now = timezone.now()
            total_images = sum(split_counts.values()) or len(processed_media)
            dataset.verification_status = 'verified'
            dataset.verified_by = user
            dataset.verified_at = now
            dataset.split_updated_at = now
            dataset.split_config = {
                'source': 'imported_yolo26',
                'format': 'yolo26',
                'archive_name': archive_name,
                'train': round(split_counts['train'] * 100 / total_images) if total_images else 0,
                'val': round(split_counts['val'] * 100 / total_images) if total_images else 0,
                'test': round(split_counts['test'] * 100 / total_images) if total_images else 0,
                'seed': None,
                'strategy': 'imported',
                'test_dataset_id': None,
                'test_dataset_name': None,
                'summary': {
                    'train': {'raw': split_counts['train'], 'augmented': 0},
                    'val': {'raw': split_counts['val'], 'augmented': 0},
                    'test': {'raw': split_counts['test'], 'augmented': 0},
                    'classes': [
                        {
                            'name': class_name,
                            **class_split_counts[class_name],
                        }
                        for class_name in class_names
                    ],
                },
            }
            dataset.save(update_fields=[
                'verification_status',
                'verified_by',
                'verified_at',
                'split_config',
                'split_updated_at',
                'updated_at',
            ])

        return {
            'format': 'yolo26',
            'images': len(processed_media),
            'created_images': created_count,
            'reused_images': reused_count,
            'annotations': len(annotations),
            'classes': len(class_names),
            'splits': split_counts,
            'class_index_base': 1 if class_index_offset else 0,
            'renamed_images': sum(
                image_name_map[image_key] != posixpath.basename(image_key)
                for image_key in image_keys
            ),
        }


def run_dataset_import_job(job_id: int) -> None:
    from django.db import connection

    job = DatasetImportJob.objects.select_related(
        'dataset__project__owner',
        'created_by',
    ).get(id=job_id)
    job.status = 'running'
    job.error = ''
    job.save(update_fields=['status', 'error', 'updated_at'])

    try:
        if job.format == 'images':
            video_extraction = (job.summary or {}).get('video_extraction') or {}
            if video_extraction.get('enabled'):
                summary = run_video_extraction_job(job, video_extraction)
            else:
                summary = _import_staged_media_files(job)
        elif job.format == 'yolo26':
            staged = (job.staged_files or [])[0] if job.staged_files else None
            if not staged or not staged.get('key'):
                raise ValueError('No staged YOLO26 archive found.')
            with default_storage.open(staged['key'], 'rb') as archive_file:
                summary = _import_yolo26_archive_from_file(
                    job.dataset,
                    archive_file,
                    staged.get('name') or 'dataset.zip',
                    job.created_by,
                    job,
                )
            transaction.on_commit(lambda dataset_id=job.dataset_id: _enqueue_dataset_label_cache_refresh(dataset_id))
        else:
            raise ValueError('Only Images and YOLO26 imports are currently supported.')

        job.summary = summary
        job.done = job.total
        job.status = 'done'
        job.error = ''
        job.save(update_fields=['summary', 'done', 'status', 'error', 'updated_at'])
    except Exception as exc:
        logger.exception('Dataset import job %s failed', job.id)
        job.status = 'error'
        job.error = str(exc)
        job.save(update_fields=['status', 'error', 'updated_at'])
    finally:
        _delete_staged_files(job.staged_files or [])
        connection.close()


class DatasetViewSet(viewsets.ModelViewSet):
    serializer_class = DatasetSerializer
    queryset = Dataset.objects.none()

    def get_queryset(self):
        user = self.request.user
        # Scope to datasets the user can reach: projects they own, or projects
        # shared with a team they belong to.
        queryset = Dataset.objects.filter(
            Q(project__owner=user)
            | Q(project__team__owner=user)
            | Q(project__team__members__user=user)
        ).distinct().select_related('project__team').prefetch_related('import_jobs')
        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        return queryset

    def get_permissions(self):
        if self.action == 'frame_image':
            return [IsAuthenticated()]
        if self.action == 'destroy':
            return [HasPerm('datasets.delete_dataset')]
        if self.action in (
            'upload',
            'upload_batch',
            'import_archive',
            'start_import',
            'prepare_import',
            'commit_import',
            'abort_import',
            'delete_frame',
        ):
            return [HasPerm('datasets.upload_media')]
        if self.action == 'verify':
            return [HasPerm('annotations.approve_annotation')]
        if self.action == 'media' and self.request.method == 'DELETE':
            return [HasPerm('datasets.upload_media')]
        return super().get_permissions()

    # ── Custom actions ───────────────────────────────────────────────────────

    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        dataset = self.get_object()
        media_count = ordered_image_media(dataset).count()
        ann_count = Annotation.objects.filter(media__dataset=dataset, is_valid=True).count()
        return Response({
            'id': dataset.id,
            'name': dataset.name,
            'version': dataset.version,
            'project_id': dataset.project_id,
            'project_name': dataset.project.name if dataset.project else None,
            'created_at': dataset.created_at,
            'updated_at': dataset.updated_at,
            'size': media_count,
            'annotation_count': ann_count,
        })

    @action(detail=True, methods=['post', 'delete'], url_path='verify')
    def verify(self, request, pk=None):
        from django.utils import timezone

        dataset = self.get_object()
        if request.method == 'DELETE':
            with transaction.atomic():
                augmented_media = dataset.media_files.filter(type='image').filter(
                    Q(metadata__category='augmented') | Q(file__contains='/augmented/')
                )
                deleted_augmented_count = augmented_media.count()
                augmented_media.delete()
                dataset.augmentation_jobs.all().delete()
                dataset.invalidate_training_verification()
                transaction.on_commit(lambda dataset_id=dataset.id: _enqueue_dataset_label_cache_clear(dataset_id))
                dataset.refresh_from_db()
            response = DatasetSerializer(dataset, context={'request': request}).data
            response['deleted_augmented_count'] = deleted_augmented_count
            return Response(response)

        images = dataset.media_files.filter(type='image').filter(
            Q(metadata__category__isnull=True) | ~Q(metadata__category='augmented')
        )
        image_count = images.count()
        labeled_count = images.filter(
            annotations__is_valid=True,
        ).distinct().count()
        errors = []
        if image_count < 2:
            errors.append('Dataset needs at least 2 images.')
        if labeled_count == 0:
            errors.append('Dataset needs at least 1 labeled image; remaining images may be background.')
        if not dataset.project.classes.exists():
            errors.append('Project needs at least 1 annotation class.')
        if errors:
            return Response(
                {'error': ' '.join(errors), 'image_count': image_count, 'labeled_count': labeled_count},
                status=status.HTTP_400_BAD_REQUEST,
            )

        background_count = image_count - labeled_count
        if background_count and request.data.get('confirm_background_images') is not True:
            return Response(
                {
                    'error': f'Confirm that {background_count} unlabeled images are intentional backgrounds.',
                    'image_count': image_count,
                    'labeled_count': labeled_count,
                    'background_count': background_count,
                    'requires_background_confirmation': True,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        dataset.verification_status = 'verified'
        dataset.verified_by = request.user
        dataset.verified_at = timezone.now()
        dataset.save(update_fields=['verification_status', 'verified_by', 'verified_at', 'updated_at'])
        transaction.on_commit(lambda dataset_id=dataset.id: _enqueue_dataset_label_cache_refresh(dataset_id))
        return Response(DatasetSerializer(dataset, context={'request': request}).data)

    @action(detail=True, methods=['post'], url_path='split')
    def split(self, request, pk=None):
        from datasets.services.splitting import configure_dataset_split

        dataset = self.get_object()
        if not _verification_is_current(dataset):
            return Response(
                {'error': 'Verify Annotations before configuring the dataset split.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ratios = {name: int(request.data.get(name)) for name in ('train', 'val', 'test')}
            seed = int(request.data.get('seed', 42))
        except (TypeError, ValueError):
            return Response({'error': 'Split ratios and seed must be integers.'}, status=status.HTTP_400_BAD_REQUEST)
        strategy = request.data.get('strategy', 'class')
        if strategy not in ('class', 'random'):
            return Response({'error': 'Strategy must be class or random.'}, status=status.HTTP_400_BAD_REQUEST)
        test_dataset = None
        test_dataset_id = request.data.get('test_dataset_id')
        if test_dataset_id not in (None, ''):
            try:
                test_dataset = self.get_queryset().get(id=int(test_dataset_id), project=dataset.project)
            except (Dataset.DoesNotExist, TypeError, ValueError):
                return Response(
                    {'error': 'The fixed test dataset is not available in this project.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if test_dataset.id == dataset.id:
                return Response(
                    {'error': 'Choose a different dataset for the fixed test set.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if test_dataset.verification_status != 'verified':
                return Response(
                    {'error': 'Verify the fixed test dataset before using it.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if sum(ratios.values()) != 100:
            return Response(
                {'error': 'Train, validation, and test ratios must total 100%.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if test_dataset and ratios['test'] != 0:
            return Response(
                {'error': 'Set Test to 0% when using a fixed test dataset.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if any(ratios[name] < 0 for name in ('train', 'val', 'test')):
            return Response(
                {'error': 'Split ratios cannot be negative.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            summary = configure_dataset_split(dataset, ratios, seed, strategy, test_dataset)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        transaction.on_commit(lambda dataset_id=dataset.id: _enqueue_dataset_label_cache_refresh(dataset_id))
        return Response({
            'dataset': DatasetSerializer(dataset, context={'request': request}).data,
            'summary': summary,
        })

    @action(detail=True, methods=['get', 'delete'])
    def media(self, request, pk=None):
        dataset = self.get_object()

        if request.method == 'DELETE':
            serializer = MediaBulkDeleteSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            ids = serializer.validated_data['media_ids']
            qs = Media.objects.filter(dataset=dataset, id__in=ids)
            found_ids = set(qs.values_list('id', flat=True))
            missing = sorted(set(ids) - found_ids)
            if missing:
                return Response(
                    {'detail': 'Some media ids are not in this dataset.', 'invalid_ids': missing},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            deleted_ids: list[int] = []
            for m in list(qs):
                deleted_ids.append(m.id)
                m.delete()
            return Response({'deleted': len(deleted_ids), 'ids': deleted_ids})

        media_qs = dataset.media_files.all()
        serializer = MediaSerializer(media_qs, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def upload(self, request, pk=None):
        dataset = self.get_object()
        serializer = MediaUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data['file']
        media_type = serializer.validated_data['type']
        try:
            _validate_dataset_import_files(
                dataset,
                'images',
                [uploaded_file],
                forced_media_type=media_type,
                max_files=1,
            )
        except ValueError as exc:
            detail = str(exc)
            status_code = status.HTTP_409_CONFLICT if 'already exist' in detail else status.HTTP_400_BAD_REQUEST
            return Response({'detail': detail}, status=status_code)

        return _queue_dataset_import_job(
            request,
            dataset,
            [uploaded_file],
            'images',
            forced_media_type=media_type,
        )

    @action(
        detail=True,
        methods=['post'],
        parser_classes=[MultiPartParser, FormParser],
        url_path='upload-batch',
    )
    def upload_batch(self, request, pk=None):
        dataset = self.get_object()
        files = request.FILES.getlist('files')
        media_type = request.data.get('type', 'image')
        if media_type not in ('image', 'video'):
            return Response({'detail': 'type must be "image" or "video".'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            _validate_dataset_import_files(dataset, 'images', files, forced_media_type=media_type, max_files=100)
        except ValueError as exc:
            detail = str(exc)
            status_code = status.HTTP_409_CONFLICT if 'already exist' in detail else status.HTTP_400_BAD_REQUEST
            return Response({'detail': detail}, status=status_code)

        return _queue_dataset_import_job(
            request,
            dataset,
            files,
            'images',
            forced_media_type=media_type,
        )

    @action(
        detail=True,
        methods=['post'],
        parser_classes=[MultiPartParser, FormParser],
        url_path='start-import',
    )
    def start_import(self, request, pk=None):
        dataset = self.get_object()
        import_format = request.data.get('format', 'images')
        replace_existing = str(request.data.get('replace_existing', '')).strip().lower() in ('1', 'true', 'yes', 'on')
        files = request.FILES.getlist('files') or ([request.FILES['file']] if 'file' in request.FILES else [])
        try:
            _validate_dataset_import_files(
                dataset,
                import_format,
                files,
                max_files=_dataset_import_max_files(),
            )
            import_options = _dataset_import_options(
                request.data.get('video_extraction'),
                import_format,
                files,
            )
        except ValueError as exc:
            detail = str(exc)
            status_code = status.HTTP_409_CONFLICT if 'already exist' in detail else status.HTTP_400_BAD_REQUEST
            return Response({'detail': detail}, status=status_code)

        return _queue_dataset_import_job(
            request,
            dataset,
            files,
            import_format,
            replace_existing=replace_existing and import_format == 'yolo26',
            import_options=import_options,
        )

    @action(detail=True, methods=['post'], url_path='prepare-import')
    def prepare_import(self, request, pk=None):
        """Create an import job and presign direct-to-MinIO staging uploads."""
        dataset = self.get_object()
        if not getattr(settings, 'USE_MINIO', False):
            return Response({'direct_upload': False})

        import_format = request.data.get('format', 'images')
        raw_files = request.data.get('files')
        if not isinstance(raw_files, list):
            return Response({'detail': 'files must be a list.'}, status=status.HTTP_400_BAD_REQUEST)

        files = []
        try:
            for item in raw_files:
                if not isinstance(item, dict):
                    raise ValueError('Every file descriptor must be an object.')
                name = posixpath.basename(str(item.get('name') or ''))
                size = int(item.get('size') or 0)
                if not name or size <= 0:
                    raise ValueError('Every file must have a name and positive size.')
                files.append(SimpleNamespace(
                    name=name,
                    size=size,
                    content_type=str(item.get('content_type') or 'application/octet-stream'),
                ))
            _validate_dataset_import_files(
                dataset,
                import_format,
                files,
                max_files=_dataset_import_max_files(),
            )
            import_options = _dataset_import_options(
                request.data.get('video_extraction'),
                import_format,
                files,
            )
        except (TypeError, ValueError) as exc:
            detail = str(exc)
            status_code = status.HTTP_409_CONFLICT if 'already exist' in detail else status.HTTP_400_BAD_REQUEST
            return Response({'detail': detail}, status=status_code)

        replace_existing = str(request.data.get('replace_existing', '')).strip().lower() in (
            '1', 'true', 'yes', 'on',
        )
        job = DatasetImportJob.objects.create(
            dataset=dataset,
            format=import_format,
            status='queued',
            total=len(files),
            done=0,
            summary={
                'replace_existing': replace_existing and import_format == 'yolo26',
                'upload_pending': True,
                **import_options,
            },
            created_by=request.user,
        )

        staged_files = []
        uploads = []
        try:
            for index, file_descriptor in enumerate(files):
                stage_key = (
                    f'import-staging/datasets/{dataset.id}/jobs/{job.id}/'
                    f'{index + 1}_{uuid.uuid4().hex}_{file_descriptor.name}'
                )
                content_type = file_descriptor.content_type or 'application/octet-stream'
                staged_files.append({
                    'key': stage_key,
                    'name': file_descriptor.name,
                    'size': file_descriptor.size,
                    'content_type': content_type,
                    'media_type': _infer_media_type(file_descriptor),
                })
                uploads.append({
                    'index': index,
                    'name': file_descriptor.name,
                    'url': _direct_upload_url(stage_key, content_type),
                    'headers': {'Content-Type': content_type},
                })
        except Exception as exc:
            job.delete()
            logger.exception('Could not prepare direct upload for dataset %s', dataset.id)
            return Response(
                {'detail': f'Could not prepare direct upload: {exc}'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        job.staged_files = staged_files
        job.save(update_fields=['staged_files', 'updated_at'])
        response = _accepted_import_response(request, dataset, job)
        response.status_code = status.HTTP_200_OK
        response.data.update({'direct_upload': True, 'uploads': uploads})
        return response

    @action(
        detail=True,
        methods=['post'],
        url_path=r'import-jobs/(?P<job_id>\d+)/commit',
    )
    def commit_import(self, request, pk=None, job_id=None):
        dataset = self.get_object()
        job = dataset.import_jobs.filter(id=job_id, created_by=request.user).first()
        if not job:
            return Response({'detail': 'Import job not found.'}, status=status.HTTP_404_NOT_FOUND)
        if not (job.summary or {}).get('upload_pending'):
            return _accepted_import_response(request, dataset, job)

        missing = [
            item.get('name') or item.get('key')
            for item in (job.staged_files or [])
            if not item.get('key') or not default_storage.exists(item['key'])
        ]
        if missing:
            return Response(
                {'detail': f'Upload is incomplete. Missing: {", ".join(missing[:10])}'},
                status=status.HTTP_409_CONFLICT,
            )

        summary = dict(job.summary or {})
        summary.pop('upload_pending', None)
        summary['upload_completed'] = True
        job.summary = summary
        job.save(update_fields=['summary', 'updated_at'])

        from datasets.tasks import enqueue_dataset_import_job

        transaction.on_commit(lambda current_job_id=job.id: enqueue_dataset_import_job(current_job_id))
        return _accepted_import_response(request, dataset, job)

    @action(
        detail=True,
        methods=['post'],
        url_path=r'import-jobs/(?P<job_id>\d+)/abort',
    )
    def abort_import(self, request, pk=None, job_id=None):
        dataset = self.get_object()
        job = dataset.import_jobs.filter(id=job_id, created_by=request.user).first()
        if not job:
            return Response({'detail': 'Import job not found.'}, status=status.HTTP_404_NOT_FOUND)
        if (job.summary or {}).get('upload_pending'):
            _delete_staged_files(job.staged_files or [])
            summary = dict(job.summary or {})
            summary.pop('upload_pending', None)
            job.summary = summary
            job.status = 'error'
            job.error = 'Upload was interrupted before the import started.'
            job.save(update_fields=['summary', 'status', 'error', 'updated_at'])
        return Response({'aborted': True, 'job': _import_job_data(job)})

    @action(
        detail=True,
        methods=['post'],
        parser_classes=[MultiPartParser, FormParser],
        url_path='import-archive',
    )
    def import_archive(self, request, pk=None):
        dataset = self.get_object()
        archive_file = request.FILES.get('file')
        import_format = request.data.get('format')
        replace_existing = str(request.data.get('replace_existing', '')).strip().lower() in ('1', 'true', 'yes', 'on')
        files = [archive_file] if archive_file is not None else []
        try:
            _validate_dataset_import_files(dataset, import_format, files, max_files=1)
        except ValueError as exc:
            detail = str(exc)
            status_code = status.HTTP_409_CONFLICT if 'already exist' in detail else status.HTTP_400_BAD_REQUEST
            return Response({'detail': detail}, status=status_code)

        return _queue_dataset_import_job(
            request,
            dataset,
            files,
            import_format,
            replace_existing=replace_existing and import_format == 'yolo26',
        )

    @action(detail=True, methods=['post'], url_path='versions')
    def new_version(self, request, pk=None):
        dataset = self.get_object()
        dataset.version += 1
        dataset.save(update_fields=['version'])
        return Response(DatasetSerializer(dataset, context={'request': request}).data)

    @action(detail=True, methods=['get'])
    def browser(self, request, pk=None):
        dataset = self.get_object()
        data = browser_payload(dataset)
        data['dataset_id'] = dataset.id
        data['dataset_name'] = dataset.name
        data['version'] = dataset.version
        return Response(data)

    @action(detail=True, methods=['post'], url_path='augmentations/preview')
    def augment_preview(self, request, pk=None):
        import io, base64
        import numpy as np
        import cv2
        import albumentations as A
        from PIL import Image, ImageOps

        dataset = self.get_object()
        if not _verification_is_current(dataset):
            return Response(
                {'error': 'Verify Annotations before generating a preview.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not dataset.split_config:
            return Response(
                {'error': 'Configure the dataset split before augmentation.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = request.data
        pre = data.get('preprocess', {})
        aug = data.get('augment', {})
        count = min(int(data.get('count', 6)), 12)

        pre_pipeline, aug_pipeline = _build_pipelines(pre, aug)
        media_list = [
            media for media in raw_image_media(dataset)
            if (media.metadata or {}).get('split') == 'train'
        ][:count]
        previews = []

        for media in media_list:
            try:
                img_np = _load_media_np(media, pre, pre_pipeline)
                if aug_pipeline is not None:
                    img_np = aug_pipeline(image=img_np)['image']

                buf = io.BytesIO()
                Image.fromarray(img_np).save(buf, format='JPEG', quality=82)
                b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                name = _media_display_name(media)
                previews.append({'media_id': media.id, 'name': name, 'augmented_url': f'data:image/jpeg;base64,{b64}'})
            except Exception:
                logger.exception('Failed to generate augment preview for media %d', media.id)

        return Response({'previews': previews})

    @action(detail=True, methods=['post'], url_path='augmentations')
    def augment_apply(self, request, pk=None):
        import threading

        dataset = self.get_object()
        if not _verification_is_current(dataset):
            return Response(
                {'error': 'Verify Annotations before generating a dataset.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not dataset.split_config:
            return Response(
                {'error': 'Configure the dataset split before augmentation.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = request.data
        pre = dict(data.get('preprocess', {}) or {})
        aug = dict(data.get('augment', {}) or {})
        multiplier = max(1, min(int(data.get('multiplier', 1)), 5))

        pre_transforms, aug_transforms = _build_transform_lists(pre, aug)
        has_transforms = bool(pre_transforms or aug_transforms)
        total = (
            sum(1 for media in raw_image_media(dataset) if (media.metadata or {}).get('split') == 'train') * multiplier
            if has_transforms else 0
        )
        job = AugmentationJob.objects.create(dataset=dataset, total=total, status='running')

        # Production: hand off to a Celery worker (scales independently, survives web
        # restarts). Dev/no-broker: run in a daemon thread. Both write progress to the
        # AugmentationJob row, so any web worker can report status.
        if getattr(settings, 'USE_CELERY', False):
            from datasets.tasks import augment_dataset_task
            augment_dataset_task.delay(job.id, dataset.id, pre, aug, multiplier)
        else:
            threading.Thread(
                target=run_augmentation_job,
                args=(job.id, dataset.id, pre, aug, multiplier),
                daemon=True,
            ).start()

        return Response({'job_id': str(job.id), 'total': total}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=['get'], url_path='augmentations/status')
    def augment_status(self, request, pk=None):
        self.get_object()  # enforce dataset access scope
        try:
            job = AugmentationJob.objects.get(id=request.query_params.get('job'), dataset_id=pk)
        except (AugmentationJob.DoesNotExist, ValueError, TypeError):
            return Response({'detail': 'Unknown augmentation job.'}, status=status.HTTP_404_NOT_FOUND)

        # Self-heal jobs whose worker died mid-run (no heartbeat) so the client
        # stops polling forever.
        if job.status == 'running':
            from django.utils import timezone
            age = (timezone.now() - job.updated_at).total_seconds()
            if age > AUG_JOB_STALE_SECONDS:
                job.status = 'error'
                job.error = 'Augmentation stopped unexpectedly (worker no longer reporting progress).'
                job.save(update_fields=['status', 'error'])

        return Response({
            'total': job.total, 'done': job.done, 'generated': job.generated,
            'status': job.status, 'error': job.error,
        })

    @action(detail=True, methods=['get'], url_path=r'frames/(?P<frame_num>\d+)',
            authentication_classes=[JWTAuthQueryOrHeader], permission_classes=[IsAuthenticated],
            throttle_classes=[])
    def frame_image(self, request, pk=None, frame_num=None):
        query_token = request.query_params.get('token')
        if query_token:
            jwt_auth = JWTAuthentication()
            try:
                validated = jwt_auth.get_validated_token(query_token)
                request.user = jwt_auth.get_user(validated)
            except (InvalidToken, Exception):
                return HttpResponse(b'Unauthorized', status=401, content_type='text/plain')
        elif not (request.user and request.user.is_authenticated):
            return HttpResponse(b'Unauthorized', status=401, content_type='text/plain')

        dataset = self.get_object()
        try:
            expected_media_id = request.query_params.get('media_id')
            media_id = int(expected_media_id) if expected_media_id is not None else None
            media = image_media_for_frame(dataset, int(frame_num), media_id=media_id)
        except (TypeError, ValueError):
            return HttpResponse(b'Invalid frame', status=400, content_type='text/plain')
        if not media or not media.file:
            return HttpResponse(b'Frame not found', status=404, content_type='text/plain')

        want_thumb = request.query_params.get('quality') == 'thumb'

        # Fast path: serve the precomputed thumbnail straight from storage (no decode,
        # no full-image read). CDN-cacheable.
        if want_thumb and media.thumbnail:
            try:
                with media.thumbnail.open('rb') as tf:
                    thumb_bytes = tf.read()
                response = HttpResponse(thumb_bytes, content_type='image/jpeg')
                response['Cache-Control'] = 'public, max-age=86400'
                return response
            except Exception:
                logger.exception('Failed to read thumbnail for media %s', media.id)

        try:
            with media.file.open('rb') as f:
                image_bytes = f.read()
        except Exception:
            logger.exception('Failed to read media file for dataset %s frame %s', dataset.id, frame_num)
            return HttpResponse(b'Failed to load frame', status=500, content_type='text/plain')

        # Thumbnail not precomputed yet (e.g. legacy media): build once, persist to
        # storage, and serve. Subsequent requests hit the fast path above.
        if want_thumb:
            try:
                from django.core.files.base import ContentFile
                thumb_bytes = _make_thumbnail_bytes(image_bytes)
                media.thumbnail.save(f'{media.id}.jpg', ContentFile(thumb_bytes), save=True)
                response = HttpResponse(thumb_bytes, content_type='image/jpeg')
                response['Cache-Control'] = 'public, max-age=86400'
                return response
            except Exception:
                logger.exception('Failed to build thumbnail for dataset %s frame %s', dataset.id, frame_num)
                # fall through to full image

        response = HttpResponse(image_bytes, content_type=guess_content_type(media))
        response['Cache-Control'] = 'public, max-age=3600'
        return response

    @action(
        detail=True,
        methods=['delete'],
        url_path=r'frames/(?P<frame_num>\d+)/delete',
        throttle_classes=[],
    )
    def delete_frame(self, request, pk=None, frame_num=None):
        dataset = self.get_object()
        try:
            frame_index = int(frame_num)
        except (TypeError, ValueError):
            return Response({'detail': 'Invalid frame.'}, status=status.HTTP_400_BAD_REQUEST)

        media = image_media_for_frame(dataset, frame_index)
        if media is None:
            return Response(
                {'detail': f'Frame {frame_index} not found in dataset {dataset.id}.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        media_id = media.id
        with transaction.atomic():
            media.delete()
            dataset.invalidate_training_verification()
            transaction.on_commit(lambda dataset_id=dataset.id: _enqueue_dataset_label_cache_clear(dataset_id))

        return Response({
            'deleted': 1,
            'media_id': media_id,
            'frame': frame_index,
            'remaining': ordered_image_media(dataset).count(),
        })

    @action(detail=True, methods=['get', 'put'],
            url_path=r'frames/(?P<frame_num>\d+)/annotations', throttle_classes=[])
    def frame_annotations(self, request, pk=None, frame_num=None):
        dataset = self.get_object()
        media = image_media_for_frame(dataset, int(frame_num))
        if media is None:
            return Response({'detail': f'Frame {frame_num} not found in dataset {dataset.id}.'},
                            status=status.HTTP_404_NOT_FOUND)

        if request.method == 'GET':
            qs = Annotation.objects.filter(media=media).select_related('class_label', 'annotator')
            return Response(AnnotationSerializer(qs, many=True).data)

        serializer = JobAnnotationsReplaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        items = serializer.validated_data['annotations']

        project_id = dataset.project_id
        for item in items:
            if item['class_label'].project_id != project_id:
                raise ValidationError(
                    {'annotations': f'Class {item["class_label"].pk} does not belong to this project.'}
                )

        user = request.user
        with transaction.atomic():
            Annotation.objects.filter(media=media).delete()
            Annotation.objects.bulk_create([
                Annotation(
                    media=media,
                    class_label=item['class_label'],
                    annotator=user,
                    type=item['type'],
                    data=item['data'],
                    frame=item.get('frame', 0),
                    track_id=item.get('track_id'),
                )
                for item in items
            ])
            if (media.metadata or {}).get('category') != 'augmented':
                dataset.invalidate_training_verification()
                transaction.on_commit(lambda dataset_id=dataset.id: _enqueue_dataset_label_cache_clear(dataset_id))
        qs = Annotation.objects.filter(media=media).select_related('class_label', 'annotator')
        return Response(AnnotationSerializer(qs, many=True).data)
