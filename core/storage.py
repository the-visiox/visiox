from django.conf import settings


def _s3_bucket(bucket_name):
    """Return an S3Boto3Storage subclass targeting a specific MinIO bucket."""
    from storages.backends.s3boto3 import S3Boto3Storage

    class _BucketStorage(S3Boto3Storage):
        pass

    _BucketStorage.bucket_name = bucket_name
    _BucketStorage.__name__ = f'{bucket_name.replace("-", "_")}_storage'
    return _BucketStorage


def get_artifacts_storage():
    """Storage for model weights and training artifacts (visiox-artifacts bucket)."""
    if getattr(settings, 'USE_MINIO', False):
        return _s3_bucket('visiox-artifacts')()
    from django.core.files.storage import FileSystemStorage
    return FileSystemStorage()
