from celery import shared_task
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def provision_cvat_task(self, dataset_id: int):
    """Asynchronously create the CVAT project/task for a newly created dataset."""
    from datasets.models import Dataset
    from datasets.services.cvat import ensure_cvat_task

    try:
        dataset = Dataset.objects.select_related('project').get(pk=dataset_id)
    except Dataset.DoesNotExist:
        logger.warning('provision_cvat_task: dataset %d not found, skipping', dataset_id)
        return

    try:
        ensure_cvat_task(dataset)
    except Exception as exc:
        logger.exception('provision_cvat_task: CVAT provisioning failed for dataset %d', dataset_id)
        raise self.retry(exc=exc)
