import json
import logging
import threading

from celery import shared_task
from django.conf import settings


logger = logging.getLogger(__name__)


def run_auto_label_dataset_job(job_id):
    from annotations.models import Annotation, Class
    from auto_label.models import AutoLabelDatasetJob
    from auto_label.services import (
        prediction_bbox_data,
        prediction_polygon_data,
        purge_temporary_model,
        request_predictions,
    )
    from datasets.tasks import enqueue_dataset_label_cache_clear

    job = AutoLabelDatasetJob.objects.select_related('dataset__project', 'model', 'created_by').get(pk=job_id)
    job.status = 'running'
    job.error = ''
    job.save(update_fields=['status', 'error', 'updated_at'])

    try:
        dataset = job.dataset
        model = job.model
        media_items = list(dataset.media_files.filter(type='image').order_by('uploaded_at', 'id').only(
            'id', 'width', 'height', 'dataset_id',
        ))
        job.total = len(media_items)
        job.save(update_fields=['total', 'updated_at'])
        class_by_name = {
            item.name.strip().casefold(): item
            for item in Class.objects.filter(project=dataset.project).order_by('id')
        }

        Annotation.objects.filter(
            media__dataset=dataset,
            data__source='auto_label',
        ).delete()

        labeled_media_ids = set()
        saved = 0
        skipped = 0
        batch_size = max(1, int(getattr(settings, 'AUTO_LABEL_DATASET_BATCH_SIZE', 32)))
        for offset in range(0, len(media_items), batch_size):
            batch = media_items[offset:offset + batch_size]
            media_by_id = {item.id: item for item in batch}
            engine = {
                'provider': 'uploaded_yolo',
                'model_id': model.id,
                'name': model.name,
                'version': model.version,
                'format': 'pt',
                'task_type': model.task_type,
                'storage_key': model.model_file.name,
                'checksum': model.checksum,
            }
            result = request_predictions({
                'engine': engine,
                'model': {
                    'registry_id': model.id,
                    'name': model.name,
                    'version': model.version,
                    'format': 'pt',
                    'storage_key': model.model_file.name,
                    'checksum': model.checksum,
                },
                'dataset': {'id': dataset.id, 'media_ids': list(media_by_id)},
                'output_type': job.output_type,
                'confidence': job.confidence,
            })
            profiling = result.get('profiling') or result.get('summary')
            if profiling:
                logger.info(
                    'Auto Label job %s batch %s-%s profiling: %s',
                    job.id,
                    offset,
                    offset + len(batch) - 1,
                    profiling,
                )

            annotations = []
            seen_predictions = set()
            for prediction in result.get('predictions', []):
                try:
                    media = media_by_id[int(prediction.get('media_id'))]
                except (KeyError, TypeError, ValueError):
                    skipped += 1
                    continue
                label = str(prediction.get('label') or '').strip()
                class_obj = class_by_name.get(label.casefold())
                if class_obj is None:
                    skipped += 1
                    continue
                if job.output_type == 'polygon':
                    data = prediction_polygon_data(prediction, media)
                    annotation_type = 'polygon'
                else:
                    data = prediction_bbox_data(prediction, media)
                    annotation_type = 'bbox'
                if data is None:
                    skipped += 1
                    continue
                prediction_key = (
                    media.id,
                    class_obj.id,
                    annotation_type,
                    json.dumps(data, sort_keys=True, separators=(',', ':')),
                )
                if prediction_key in seen_predictions:
                    skipped += 1
                    continue
                seen_predictions.add(prediction_key)
                annotations.append(Annotation(
                    media=media,
                    class_label=class_obj,
                    annotator=job.created_by,
                    type=annotation_type,
                    data={
                        **data,
                        'source': 'auto_label',
                        'confidence': prediction.get('confidence'),
                        'auto_label_source': 'uploaded_model',
                        'auto_label_model_id': model.id,
                        'auto_label_provider': 'uploaded_yolo',
                        'auto_label_engine_name': model.name,
                    },
                    frame=0,
                ))
                labeled_media_ids.add(media.id)

            if annotations:
                Annotation.objects.bulk_create(annotations, batch_size=1000)
                saved += len(annotations)
            job.done = min(offset + len(batch), job.total)
            job.labeled_images = len(labeled_media_ids)
            job.saved_annotations = saved
            job.skipped_predictions = skipped
            job.save(update_fields=[
                'done', 'labeled_images', 'saved_annotations', 'skipped_predictions', 'updated_at',
            ])

        job.status = 'done'
        job.save(update_fields=['status', 'updated_at'])
        dataset.invalidate_training_verification()
        enqueue_dataset_label_cache_clear(dataset.id)
    except Exception as exc:
        job.status = 'error'
        job.error = str(exc)[:2000]
        job.save(update_fields=['status', 'error', 'updated_at'])
        raise
    finally:
        purge_temporary_model(job.model)


@shared_task(bind=True, max_retries=0)
def auto_label_dataset_task(self, job_id):
    run_auto_label_dataset_job(job_id)
    return {'job_id': job_id}


def enqueue_auto_label_dataset_job(job_id):
    if getattr(settings, 'AUTO_LABEL_USE_CELERY', False):
        auto_label_dataset_task.apply_async(args=[job_id], queue='datasets')
        return
    threading.Thread(target=run_auto_label_dataset_job, args=(job_id,), daemon=True).start()
