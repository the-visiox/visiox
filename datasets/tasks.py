"""Celery tasks for the datasets app.

Heavy/long work (e.g. dataset augmentation) runs here so it executes on dedicated
worker processes instead of tying up web workers. Enabled when USE_CELERY=True;
otherwise the view falls back to a background thread.
"""
import threading

from celery import shared_task
from django.conf import settings

from training.label_cache import build_dataset_label_cache_by_id, clear_dataset_label_cache
from datasets.views.dataset_view import run_augmentation_job, run_dataset_import_job


@shared_task(bind=True, max_retries=0)
def augment_dataset_task(self, job_id, dataset_id, pre, aug, multiplier):
    run_augmentation_job(job_id, dataset_id, pre, aug, multiplier)


@shared_task(bind=True, max_retries=0)
def build_dataset_label_cache_task(self, dataset_id: int):
    return build_dataset_label_cache_by_id(dataset_id)


@shared_task(bind=True, max_retries=0)
def clear_dataset_label_cache_task(self, dataset_id: int):
    clear_dataset_label_cache(dataset_id)
    return {'cleared': True, 'dataset_id': dataset_id}


@shared_task(bind=True, max_retries=0)
def process_dataset_import_task(self, job_id: int):
    run_dataset_import_job(job_id)
    return {'job_id': job_id}


def enqueue_dataset_import_job(job_id: int) -> None:
    use_celery = getattr(settings, 'DATASET_IMPORT_USE_CELERY', getattr(settings, 'USE_CELERY', False))
    if use_celery:
        process_dataset_import_task.apply_async(args=[job_id], queue='datasets')
        return
    threading.Thread(
        target=run_dataset_import_job,
        args=(job_id,),
        daemon=True,
    ).start()


def enqueue_dataset_label_cache_refresh(dataset_id: int) -> None:
    if getattr(settings, 'USE_CELERY', False):
        build_dataset_label_cache_task.delay(dataset_id)
        return
    threading.Thread(
        target=build_dataset_label_cache_by_id,
        args=(dataset_id,),
        daemon=True,
    ).start()


def enqueue_dataset_label_cache_clear(dataset_id: int) -> None:
    if getattr(settings, 'USE_CELERY', False):
        clear_dataset_label_cache_task.delay(dataset_id)
        return
    threading.Thread(
        target=clear_dataset_label_cache,
        args=(dataset_id,),
        daemon=True,
    ).start()
