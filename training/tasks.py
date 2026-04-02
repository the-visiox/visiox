"""
Celery tasks for training job execution.
The `run_training_job` task is a mock runner that simulates metric emission
every epoch. Real PyTorch/TF runners can be plugged in by replacing the
simulation block with actual model training code.
"""
import random
import time

from celery import shared_task
from django.utils import timezone


@shared_task(bind=True)
def run_training_job(self, job_id: int):
    from training.models import TrainingJob, Experiment, RunMetric

    try:
        job = TrainingJob.objects.get(pk=job_id)
    except TrainingJob.DoesNotExist:
        return {'error': f'TrainingJob {job_id} not found'}

    job.status = 'running'
    job.started_at = timezone.now()
    job.celery_task_id = self.request.id
    job.save(update_fields=['status', 'started_at', 'celery_task_id'])

    experiment = Experiment.objects.create(
        job=job,
        name=f"Run {job.name}",
    )

    epochs = job.hyperparams.get('epochs', 10)
    base_loss = 2.0

    try:
        for epoch in range(1, epochs + 1):
            time.sleep(0.1)
            decay = 1 / (1 + 0.3 * epoch)
            noise = random.uniform(-0.05, 0.05)
            loss = base_loss * decay + noise
            val_loss = loss + random.uniform(0.01, 0.1)
            map50 = min(0.99, 0.5 + 0.04 * epoch + random.uniform(-0.01, 0.01))
            f1 = min(0.99, 0.45 + 0.05 * epoch + random.uniform(-0.01, 0.01))

            RunMetric.objects.create(
                experiment=experiment,
                epoch=epoch,
                loss=round(loss, 4),
                val_loss=round(val_loss, 4),
                map50=round(map50, 4),
                f1=round(f1, 4),
            )

            self.update_state(
                state='PROGRESS',
                meta={'epoch': epoch, 'total_epochs': epochs, 'loss': round(loss, 4)},
            )

        job.status = 'completed'
    except Exception as exc:
        job.status = 'failed'
        job.error_message = str(exc)

    job.finished_at = timezone.now()
    job.save(update_fields=['status', 'finished_at', 'error_message'])
    return {'job_id': job_id, 'status': job.status}
