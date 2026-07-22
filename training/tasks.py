from celery import shared_task
from django.utils import timezone

from training.agent import submit_training_job


def _record_setup_metric(experiment, job, accepted: dict) -> None:
    from training.models import RunMetric

    total_epochs = (job.hyperparams or {}).get('epochs')
    progress = accepted.get('progress_percent') or accepted.get('progress') or 12
    RunMetric.objects.update_or_create(
        experiment=experiment,
        epoch=0,
        step=0,
        defaults={
            'loss': None,
            'val_loss': None,
            'map50': None,
            'map75': None,
            'f1': None,
            'accuracy': None,
            'extra': {
                'stage': accepted.get('stage') or 'preparing',
                'message': accepted.get('message') or 'GPU agent accepted the job and is preparing the dataset.',
                'progress_percent': progress,
                'total_epochs': total_epochs,
            },
        },
    )


@shared_task(bind=True)
def run_training_job(self, job_id: int):
    from training.models import TrainingJob, Experiment

    try:
        job = TrainingJob.objects.get(pk=job_id)
    except TrainingJob.DoesNotExist:
        return {'error': f'TrainingJob {job_id} not found'}

    job.celery_task_id = self.request.id
    job.save(update_fields=['celery_task_id'])

    experiment = Experiment.objects.create(
        job=job,
        name=f"Run {job.name}",
    )

    try:
        accepted = submit_training_job(job)
        job.status = accepted.get('status', 'queued')
        job.agent_job_id = accepted.get('agent_job_id', f'gpu-{job.id}')
        job.artifacts = {}
        job.error_message = ''
        _record_setup_metric(experiment, job, accepted)
    except Exception as exc:
        job.status = 'failed'
        job.error_message = str(exc)
        job.finished_at = timezone.now()
    job.save(update_fields=['status', 'agent_job_id', 'artifacts', 'error_message', 'finished_at'])
    return {'job_id': job_id, 'status': job.status}
