"""Celery tasks for the datasets app.

Heavy/long work (e.g. dataset augmentation) runs here so it executes on dedicated
worker processes instead of tying up web workers. Enabled when USE_CELERY=True;
otherwise the view falls back to a background thread.
"""
from celery import shared_task

from datasets.views.dataset_view import run_augmentation_job


@shared_task(bind=True, max_retries=0)
def augment_dataset_task(self, job_id, dataset_id, pre, aug, multiplier):
    run_augmentation_job(job_id, dataset_id, pre, aug, multiplier)
