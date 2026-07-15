import hashlib
import json
import shutil
from pathlib import Path, PurePosixPath

import boto3
from botocore.client import Config
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage


SPLITS = ('train', 'val', 'test')


class DatasetLabelCacheError(RuntimeError):
    pass


class DatasetLabelCacheNotReady(DatasetLabelCacheError):
    pass


def _storage_bucket_name() -> str:
    return getattr(settings, 'AWS_STORAGE_BUCKET_NAME', 'visiox-media')


def _s3_client():
    return boto3.client(
        's3',
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME,
        config=Config(signature_version='s3v4', s3={'addressing_style': settings.AWS_S3_ADDRESSING_STYLE}),
    )


def _local_path(key: str) -> Path:
    try:
        return Path(default_storage.path(key))
    except (AttributeError, NotImplementedError):
        return Path(settings.MEDIA_ROOT) / Path(PurePosixPath(key))


def _write_text(key: str, content: str) -> None:
    payload = content.encode('utf-8')
    if default_storage.exists(key):
        default_storage.delete(key)
    default_storage.save(key, ContentFile(payload))


def _delete_prefix(prefix: str) -> None:
    normalized = prefix.rstrip('/')
    if not normalized:
        return
    if getattr(settings, 'USE_MINIO', False):
        client = _s3_client()
        bucket = _storage_bucket_name()
        paginator = client.get_paginator('list_objects_v2')
        keys = []
        for page in paginator.paginate(Bucket=bucket, Prefix=f'{normalized}/'):
            for item in page.get('Contents', []):
                keys.append({'Key': item['Key']})
        for i in range(0, len(keys), 1000):
            client.delete_objects(Bucket=bucket, Delete={'Objects': keys[i:i + 1000]})
        return
    path = _local_path(normalized)
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def _copy_key(src: str, dst: str) -> None:
    if getattr(settings, 'USE_MINIO', False):
        client = _s3_client()
        bucket = _storage_bucket_name()
        client.copy_object(Bucket=bucket, CopySource={'Bucket': bucket, 'Key': src}, Key=dst)
        return
    src_path = _local_path(src)
    dst_path = _local_path(dst)
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src_path, dst_path)


def _media_manifest_entry(media):
    metadata = media.metadata or {}
    return {
        'media_id': media.id,
        'key': media.file.name,
        'filename': media.original_filename or PurePosixPath(media.file.name).name,
        'width': media.width,
        'height': media.height,
        'category': metadata.get('category', 'raw'),
        'source_media_id': metadata.get('source_media_id'),
    }


def _label_filename(item, duplicate=False):
    filename = item.get('filename') or PurePosixPath(item.get('key') or '').name or f'media_{item["media_id"]}.jpg'
    stem = PurePosixPath(filename).stem or f'media_{item["media_id"]}'
    if duplicate:
        stem = f'{item["media_id"]}_{stem}'
    return f'{stem}.txt'


def _yolo_bbox_line(annotation, class_index, width, height):
    data = annotation.data or {}
    if annotation.type not in ('bbox', 'rectangle'):
        return None
    if not width or not height:
        return None

    try:
        x = float(data.get('x', 0))
        y = float(data.get('y', 0))
        box_width = float(data.get('width', 0))
        box_height = float(data.get('height', 0))
    except (TypeError, ValueError):
        return None

    x1 = max(0.0, min(float(width), x))
    y1 = max(0.0, min(float(height), y))
    x2 = max(0.0, min(float(width), x + box_width))
    y2 = max(0.0, min(float(height), y + box_height))
    if x2 <= x1 or y2 <= y1:
        return None

    center_x = ((x1 + x2) / 2) / width
    center_y = ((y1 + y2) / 2) / height
    norm_width = (x2 - x1) / width
    norm_height = (y2 - y1) / height
    return f'{class_index} {center_x:.6f} {center_y:.6f} {norm_width:.6f} {norm_height:.6f}'


def build_dataset_split_manifest(dataset):
    from datasets.models import Dataset

    manifest = {split: [] for split in SPLITS}
    media_qs = dataset.media_files.filter(type='image').exclude(file='').order_by('id')

    for media in media_qs:
        split = (media.metadata or {}).get('split')
        if split in manifest:
            manifest[split].append(_media_manifest_entry(media))

    test_dataset_id = (dataset.split_config or {}).get('test_dataset_id')
    if test_dataset_id:
        test_dataset = Dataset.objects.filter(id=test_dataset_id, project=dataset.project).first()
        if not test_dataset:
            raise DatasetLabelCacheError('The configured fixed test dataset no longer exists.')
        manifest['test'] = [
            _media_manifest_entry(media)
            for media in test_dataset.media_files.filter(type='image').exclude(file='').order_by('id')
            if (media.metadata or {}).get('category') != 'augmented'
        ]

    if not manifest['train'] or not manifest['val']:
        raise DatasetLabelCacheNotReady('Configure dataset train and validation splits before building labels.')

    return manifest, test_dataset_id


def dataset_cache_revision(dataset) -> str:
    latest_done_augmentation = (
        dataset.augmentation_jobs.filter(status='done').order_by('-updated_at').values_list('updated_at', flat=True).first()
    )
    payload = {
        'dataset_id': dataset.id,
        'verified_at': dataset.verified_at.isoformat() if dataset.verified_at else None,
        'split_updated_at': dataset.split_updated_at.isoformat() if dataset.split_updated_at else None,
        'split_config': dataset.split_config or {},
        'augmentation_updated_at': latest_done_augmentation.isoformat() if latest_done_augmentation else None,
        'project_class_ids': list(dataset.project.classes.order_by('id').values_list('id', flat=True)),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha1(encoded).hexdigest()[:16]


def dataset_cache_base_prefix(dataset_id: int) -> str:
    return f'training-cache/datasets/{dataset_id}'


def dataset_cache_prefix(dataset) -> str:
    return f'{dataset_cache_base_prefix(dataset.id)}/revisions/{dataset_cache_revision(dataset)}'


def _write_split_labels(prefix: str, split_manifest: dict, class_id_to_index: dict) -> list[str]:
    from annotations.models import Annotation

    media_by_id = {
        item['media_id']: item
        for items in split_manifest.values()
        for item in items
        if item.get('media_id')
    }
    if not media_by_id:
        return []

    annotations = (
        Annotation.objects
        .filter(media_id__in=media_by_id.keys(), is_valid=True, type__in=('bbox', 'rectangle'))
        .select_related('class_label')
        .order_by('media_id', 'id')
    )
    lines_by_media = {media_id: [] for media_id in media_by_id}
    for annotation in annotations:
        class_index = class_id_to_index.get(annotation.class_label_id)
        if class_index is None:
            continue
        item = media_by_id.get(annotation.media_id) or {}
        line = _yolo_bbox_line(annotation, class_index, item.get('width'), item.get('height'))
        if line:
            lines_by_media[annotation.media_id].append(line)

    label_keys = []
    for split, items in split_manifest.items():
        stem_counts = {}
        for item in items:
            filename = item.get('filename') or PurePosixPath(item.get('key') or '').name or f'media_{item["media_id"]}.jpg'
            stem = PurePosixPath(filename).stem or f'media_{item["media_id"]}'
            stem_counts[stem] = stem_counts.get(stem, 0) + 1
        for item in items:
            media_id = item['media_id']
            filename = item.get('filename') or PurePosixPath(item.get('key') or '').name or f'media_{media_id}.jpg'
            stem = PurePosixPath(filename).stem or f'media_{media_id}'
            key = f'{prefix}/labels/{split}/{_label_filename(item, stem_counts[stem] > 1)}'
            content = '\n'.join(lines_by_media.get(media_id, []))
            if content:
                content += '\n'
            _write_text(key, content)
            label_keys.append(key)
    return label_keys


def _write_metadata_files(prefix: str, split_manifest: dict, class_names: list[str], metadata: dict) -> None:
    names_lines = '\n'.join(f'  {index}: {name}' for index, name in enumerate(class_names))
    data_yaml = '\n'.join([
        'path: .',
        'train: images/train',
        'val: images/val',
        'test: images/test',
        'names:',
        names_lines,
        '',
    ])
    _write_text(f'{prefix}/data.yaml', data_yaml)
    _write_text(f'{prefix}/manifest.json', json.dumps(split_manifest, indent=2, sort_keys=True))
    _write_text(f'{prefix}/metadata.json', json.dumps(metadata, indent=2, sort_keys=True))


def build_dataset_label_cache(dataset):
    if dataset.verification_status != 'verified' or not dataset.verified_at:
        raise DatasetLabelCacheNotReady('Dataset is not verified.')
    if not dataset.split_config or not dataset.split_updated_at:
        raise DatasetLabelCacheNotReady('Dataset split is not configured.')

    split_manifest, test_dataset_id = build_dataset_split_manifest(dataset)
    class_rows = list(dataset.project.classes.order_by('id').values('id', 'name'))
    class_names = [item['name'] for item in class_rows]
    if not class_names:
        raise DatasetLabelCacheNotReady('The selected project has no annotation classes.')

    revision = dataset_cache_revision(dataset)
    prefix = dataset_cache_prefix(dataset)
    _delete_prefix(dataset_cache_base_prefix(dataset.id))

    class_id_to_index = {item['id']: index for index, item in enumerate(class_rows)}
    label_keys = _write_split_labels(prefix, split_manifest, class_id_to_index)
    metadata = {
        'dataset_id': dataset.id,
        'dataset_name': dataset.name,
        'revision': revision,
        'prefix': prefix,
        'verified_at': dataset.verified_at.isoformat() if dataset.verified_at else None,
        'split_updated_at': dataset.split_updated_at.isoformat() if dataset.split_updated_at else None,
        'test_dataset_id': test_dataset_id,
        'class_names': class_names,
        'counts': {split: len(items) for split, items in split_manifest.items()},
        'labels': label_keys,
    }
    _write_metadata_files(prefix, split_manifest, class_names, metadata)
    return {
        'ready': True,
        'revision': revision,
        'prefix': prefix,
        'labels': label_keys,
        'manifest': split_manifest,
        'test_dataset_id': test_dataset_id,
        'class_names': class_names,
        'counts': metadata['counts'],
    }


def build_dataset_label_cache_by_id(dataset_id: int) -> dict:
    from datasets.models import Dataset

    try:
        dataset = Dataset.objects.select_related('project').get(id=dataset_id)
    except Dataset.DoesNotExist:
        return {'ready': False, 'reason': 'dataset_not_found'}
    try:
        return build_dataset_label_cache(dataset)
    except DatasetLabelCacheNotReady as exc:
        return {'ready': False, 'reason': 'not_ready', 'detail': str(exc)}


def clear_dataset_label_cache(dataset_id: int) -> None:
    _delete_prefix(dataset_cache_base_prefix(dataset_id))


def promote_dataset_cache_to_job(job) -> dict:
    cache_metadata = build_dataset_label_cache(job.dataset)
    job_prefix = f'training-jobs/{job.id}'
    labels_prefix = f'{job_prefix}/labels'
    _delete_prefix(labels_prefix)

    job_label_keys = []
    for cache_key in cache_metadata['labels']:
        relative = cache_key.split('/labels/', 1)[1]
        job_key = f'{labels_prefix}/{relative}'
        _copy_key(cache_key, job_key)
        job_label_keys.append(job_key)

    return {
        **cache_metadata,
        'job_prefix': job_prefix,
        'job_label_keys': job_label_keys,
    }
