from core.storage import get_artifacts_storage


KNOWN_TRAINING_ARTIFACTS = (
    'best.pt',
    'best.onnx',
    'metrics.json',
    'training_log.json',
    'confusion_matrix.png',
)


def training_artifact_urls(job, *, verify_exists):
    artifacts = dict(job.artifacts or {})
    if not verify_exists and not artifacts:
        return {}
    if verify_exists:
        for name in KNOWN_TRAINING_ARTIFACTS:
            artifacts.setdefault(name, {
                'storage_key': f'training-jobs/{job.id}/artifacts/{name}'
            })

    storage = get_artifacts_storage()
    urls = {}
    for name, metadata in artifacts.items():
        if not isinstance(metadata, dict) or not metadata.get('storage_key'):
            continue
        storage_key = metadata['storage_key']
        try:
            if verify_exists and not storage.exists(storage_key):
                continue
            urls[name] = storage.url(storage_key)
        except (NotImplementedError, ValueError):
            continue
    return urls
