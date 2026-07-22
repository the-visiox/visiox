from pathlib import PurePosixPath
import logging

import requests
import boto3
from django.conf import settings
from botocore.client import Config
from core.storage import get_artifacts_storage
from training.label_cache import (
    build_dataset_split_manifest,
    promote_dataset_cache_to_job,
    promote_datasets_cache_to_job,
)


SUPPORTED_ARCHITECTURES = {'yolov10', 'yolov11', 'yolo26'}
LABEL_SOURCE_OF_TRUTH = 'postgres'
logger = logging.getLogger(__name__)


class TrainingAgentError(RuntimeError):
    pass


def _architecture_name(job):
    candidates = [job.architecture.name, job.architecture.backbone]
    for value in candidates:
        normalized = (value or '').lower().replace('-', '').replace('_', '').replace(' ', '')
        for architecture in SUPPORTED_ARCHITECTURES:
            if architecture in normalized:
                return architecture
    raise TrainingAgentError(f'Architecture "{job.architecture.name}" is not supported by the GPU agent.')


def _architecture_checkpoint(job):
    checkpoint = (job.architecture.default_config or {}).get('checkpoint')
    if not isinstance(checkpoint, str) or not checkpoint.endswith('.pt'):
        raise TrainingAgentError(
            f'Architecture "{job.architecture.name}" does not define a valid PyTorch checkpoint.'
        )
    return PurePosixPath(checkpoint).name


def _headers():
    token = settings.TRAINING_AGENT_TOKEN
    return {'Authorization': f'Bearer {token}'} if token else {}


def _agent_minio_endpoint():
    return settings.TRAINING_AGENT_MINIO_ENDPOINT or settings.AWS_S3_ENDPOINT_URL


def _artifact_upload_urls(job_id):
    client = boto3.client(
        's3', endpoint_url=_agent_minio_endpoint(),
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME,
        config=Config(signature_version='s3v4', s3={'addressing_style': settings.AWS_S3_ADDRESSING_STYLE}),
    )
    bucket = 'visiox-artifacts'
    names = ('best.pt', 'best.onnx', 'metrics.json', 'training_log.json', 'confusion_matrix.png')
    return {
        name: client.generate_presigned_url(
            'put_object', Params={'Bucket': bucket, 'Key': f'training-jobs/{job_id}/artifacts/{name}'},
            ExpiresIn=86400,
        )
        for name in names
    }


def _artifact_download_url(storage_key):
    client = boto3.client(
        's3', endpoint_url=_agent_minio_endpoint(),
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME,
        config=Config(signature_version='s3v4', s3={'addressing_style': settings.AWS_S3_ADDRESSING_STYLE}),
    )
    return client.generate_presigned_url(
        'get_object',
        Params={'Bucket': 'visiox-artifacts', 'Key': storage_key},
        ExpiresIn=86400,
    )


def _label_snapshot_prefix(job):
    return f'training-jobs/{job.id}/labels'


def build_training_request(job):
    selected_datasets = job.selected_datasets()
    if not selected_datasets:
        raise TrainingAgentError('A dataset is required for GPU training.')
    if not job.architecture_id:
        raise TrainingAgentError('A model architecture is required for GPU training.')
    if not settings.TRAINING_CALLBACK_TOKEN:
        raise TrainingAgentError('TRAINING_CALLBACK_TOKEN is not configured.')
    if not getattr(settings, 'USE_MINIO', False):
        raise TrainingAgentError('GPU training currently requires USE_MINIO=True.')

    class_rows = list(job.project.classes.order_by('index', 'id').values('id', 'name'))
    class_names = [item['name'] for item in class_rows]
    if not class_names:
        raise TrainingAgentError('The selected project has no annotation classes.')
    label_delivery = getattr(settings, 'TRAINING_LABEL_DELIVERY', getattr(settings, 'TRAINING_LABEL_SOURCE', 'minio'))
    label_keys = []
    test_dataset_ids = []
    if label_delivery == 'minio':
        try:
            promoted = (
                promote_dataset_cache_to_job(job)
                if len(selected_datasets) == 1
                else promote_datasets_cache_to_job(job, selected_datasets)
            )
        except RuntimeError as exc:
            raise TrainingAgentError(str(exc)) from exc
        label_keys = promoted['job_label_keys']
        split_manifest = promoted['manifest']
        if promoted.get('test_dataset_id'):
            test_dataset_ids.append(promoted['test_dataset_id'])
    elif label_delivery != 'postgres':
        raise TrainingAgentError(
            f'Unsupported TRAINING_LABEL_DELIVERY "{label_delivery}". Use "minio" or "postgres".'
        )
    else:
        split_manifest = {'train': [], 'val': [], 'test': []}
        try:
            for dataset in selected_datasets:
                dataset_manifest, test_dataset_id = build_dataset_split_manifest(dataset)
                for split, items in dataset_manifest.items():
                    split_manifest[split].extend(items)
                if test_dataset_id:
                    test_dataset_ids.append(test_dataset_id)
        except RuntimeError as exc:
            raise TrainingAgentError(str(exc)) from exc

    split_keys = {
        split: list(dict.fromkeys(item['key'] for item in items))
        for split, items in split_manifest.items()
    }

    base = settings.TRAINING_CALLBACK_BASE_URL
    callback_root = f'{base}/api/v1/internal/training-jobs/{job.id}'
    uploads = _artifact_upload_urls(job.id)
    hyperparams = dict(job.hyperparams or {})
    if 'batch_size' in hyperparams and 'batch' not in hyperparams:
        hyperparams['batch'] = hyperparams.pop('batch_size')

    payload = {
        'job_id': job.id,
        'dataset': {
            'storage': 'minio',
            'bucket': settings.AWS_STORAGE_BUCKET_NAME,
            'endpoint_url': _agent_minio_endpoint(),
            'addressing_style': settings.AWS_S3_ADDRESSING_STYLE,
            'images': [key for values in split_keys.values() for key in values],
            'splits': split_keys,
            'manifest': split_manifest,
            'counts': {split: len(items) for split, items in split_manifest.items()},
            'split_config': {
                'datasets': [
                    {'dataset_id': dataset.id, 'config': dataset.split_config}
                    for dataset in selected_datasets
                ],
            },
            'label_source': label_delivery,
            'label_source_of_truth': LABEL_SOURCE_OF_TRUTH,
            'label_snapshot': {
                'storage': 'minio' if label_delivery == 'minio' else 'postgres',
                'format': 'yolo_detection',
                'source_of_truth': LABEL_SOURCE_OF_TRUTH,
                'prefix': _label_snapshot_prefix(job) if label_delivery == 'minio' else None,
                'generated_by': 'django',
                'immutable_for_job': True,
            },
            'labels': label_keys,
            'dataset_id': job.dataset_id,
            'dataset_ids': [dataset.id for dataset in selected_datasets],
            'test_dataset_id': test_dataset_ids[0] if len(test_dataset_ids) == 1 else None,
            'test_dataset_ids': list(dict.fromkeys(test_dataset_ids)),
            'class_names': class_names,
        },
        'architecture': _architecture_name(job),
        'architecture_checkpoint': _architecture_checkpoint(job),
        'hyperparameters': hyperparams,
        'callbacks': {
            'metrics_url': f'{callback_root}/metrics/',
            'complete_url': f'{callback_root}/complete/',
            'failed_url': f'{callback_root}/failed/',
            'heartbeat_url': f'{callback_root}/heartbeat/',
        },
        'artifact_upload': {
            'best_pt_url': uploads['best.pt'],
            'best_onnx_url': uploads['best.onnx'],
            'metrics_url': uploads['metrics.json'],
            'training_log_url': uploads['training_log.json'],
            'confusion_matrix_url': uploads['confusion_matrix.png'],
        },
        'callback_token': settings.TRAINING_CALLBACK_TOKEN,
    }
    if job.initialization_mode == 'fine_tune':
        base_model = job.base_model
        parent_job = job.parent_job
        if base_model is None or parent_job is None or not base_model.model_file:
            raise TrainingAgentError('The fine-tuning checkpoint is no longer available.')
        storage_key = base_model.model_file.name
        payload['initial_checkpoint'] = {
            'mode': 'fine_tune',
            'format': 'pytorch',
            'storage_key': storage_key,
            'download_url': _artifact_download_url(storage_key),
            'source_training_job_id': parent_job.id,
            'source_registry_id': base_model.id,
            'class_schema': job.class_schema,
        }
    return payload


def submit_training_job(job):
    request_payload = build_training_request(job)
    callback_urls = request_payload.get('callbacks', {})
    logger.info(
        'Submitting training job %s to %s with callback base %s',
        job.id,
        settings.TRAINING_AGENT_URL,
        {
            key: callback_urls.get(key)
            for key in ('metrics_url', 'complete_url', 'failed_url', 'heartbeat_url')
        },
    )
    response = requests.post(
        f'{settings.TRAINING_AGENT_URL}/v1/train',
        json=request_payload, headers=_headers(),
        timeout=settings.TRAINING_AGENT_TIMEOUT,
    )
    if not response.ok:
        detail = response.text[:500]
        hint = ''
        if response.status_code == 400 and 'Unsupported architecture' in detail:
            hint = ' Restart or redeploy the GPU agent build that supports this architecture.'
        raise TrainingAgentError(f'GPU agent rejected the job ({response.status_code}): {detail}{hint}')
    return response.json()


def cancel_training_job(job):
    response = requests.delete(
        f'{settings.TRAINING_AGENT_URL}/v1/train/{job.id}',
        headers=_headers(), timeout=settings.TRAINING_AGENT_TIMEOUT,
    )
    if response.status_code not in (200, 202, 204, 404, 409):
        raise TrainingAgentError(f'GPU agent cancellation failed ({response.status_code}): {response.text[:500]}')


def get_training_job_status(job):
    response = requests.get(
        f'{settings.TRAINING_AGENT_URL}/v1/train/{job.id}',
        headers=_headers(),
        timeout=settings.TRAINING_AGENT_TIMEOUT,
    )
    if response.status_code == 404:
        return None
    if not response.ok:
        raise TrainingAgentError(f'GPU agent status check failed ({response.status_code}): {response.text[:500]}')
    return response.json()


def save_artifact(job, filename, content):
    safe_name = PurePosixPath(filename).name
    key = f'training-jobs/{job.id}/artifacts/{safe_name}'
    storage = get_artifacts_storage()
    if storage.exists(key):
        storage.delete(key)
    saved_key = storage.save(key, content)
    artifacts = dict(job.artifacts or {})
    artifacts[safe_name] = {'storage_key': saved_key, 'size': content.size}
    job.artifacts = artifacts
    job.save(update_fields=['artifacts', 'updated_at'])
    return artifacts[safe_name]
