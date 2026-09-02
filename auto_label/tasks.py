import json
import logging
import threading

from celery import shared_task
from django.conf import settings


logger = logging.getLogger(__name__)
_BBOX_KEYS = ('x', 'y', 'width', 'height')
DUPLICATE_IOU_THRESHOLD = 0.75


def _best_overlapping_annotation(
    bbox,
    annotations,
    bbox_iou,
    threshold=DUPLICATE_IOU_THRESHOLD,
):
    best_annotation = None
    best_iou = threshold
    for annotation in annotations:
        data = annotation.data or {}
        if not all(key in data for key in _BBOX_KEYS):
            continue
        overlap = bbox_iou(bbox, data)
        if overlap > best_iou:
            best_annotation = annotation
            best_iou = overlap
    return best_annotation


def _assign_track(annotation, track_id):
    if annotation.track_id == track_id:
        return
    annotation.track_id = track_id
    annotation.save(update_fields=['track_id', 'updated_at'])


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
        source = job.source or (
            {'kind': 'uploaded_model', 'model_id': model.id} if model else {}
        )
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
            if source.get('kind') == 'provider':
                provider_id = source['provider']
                engine = {
                    'provider': provider_id,
                    'model': source['model'],
                    'prompts': source['prompts'],
                }
                compatibility_model = None
                auto_label_source = 'provider'
                engine_name = source['model']
            else:
                if model is None:
                    raise ValueError('Uploaded Auto Label model is missing.')
                provider_id = 'uploaded_yolo'
                engine = {
                    'provider': provider_id,
                    'model_id': model.id,
                    'name': model.name,
                    'version': model.version,
                    'format': 'pt',
                    'task_type': model.task_type,
                    'storage_key': model.model_file.name,
                    'checksum': model.checksum,
                }
                compatibility_model = {
                    'registry_id': model.id,
                    'name': model.name,
                    'version': model.version,
                    'format': 'pt',
                    'storage_key': model.model_file.name,
                    'checksum': model.checksum,
                }
                auto_label_source = 'uploaded_model'
                engine_name = model.name
            payload = {
                'engine': engine,
                'dataset': {'id': dataset.id, 'media_ids': list(media_by_id)},
                'output_type': job.output_type,
                'confidence': job.confidence,
            }
            if compatibility_model:
                payload['model'] = compatibility_model
            result = request_predictions(payload)
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
                        'auto_label_source': auto_label_source,
                        'auto_label_model_id': model.id if model else None,
                        'auto_label_provider': provider_id,
                        'auto_label_engine_name': engine_name,
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
        if job.model:
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


def run_object_propagation_job(job_id):
    from annotations.models import Annotation
    from auto_label.models import ObjectPropagationJob
    from auto_label.propagation import bbox_iou, crop_bbox, read_media_image, track_next_bbox
    from datasets.services.media_browser import ordered_image_media
    from datasets.tasks import enqueue_dataset_label_cache_clear

    claimed = ObjectPropagationJob.objects.filter(
        pk=job_id,
        status='queued',
    ).update(status='running', error='')
    if not claimed:
        logger.info('Skipping propagation job %s because it is no longer queued.', job_id)
        return

    job = ObjectPropagationJob.objects.select_related(
        'dataset', 'class_label', 'source_media', 'created_by',
    ).get(pk=job_id)

    try:
        media_items = list(ordered_image_media(job.dataset))
        try:
            source_index = next(index for index, media in enumerate(media_items) if media.id == job.source_media_id)
        except StopIteration as exc:
            raise RuntimeError('The source frame is no longer available.') from exc
        targets = media_items[source_index + 1:]
        if job.max_frames:
            targets = targets[:job.max_frames]
        job.total = len(targets)
        job.save(update_fields=['total', 'updated_at'])

        source_image = read_media_image(job.source_media)
        if source_image is None:
            raise RuntimeError('Could not read the source frame.')
        seed_bbox = job.seed_bbox
        seed_template = crop_bbox(source_image, seed_bbox)
        if seed_template.shape[0] < 8 or seed_template.shape[1] < 8:
            raise RuntimeError('The selected bounding box is too small to track.')

        previous_bbox = seed_bbox
        previous_template = seed_template
        previous_height, previous_width = source_image.shape[:2]
        existing_by_media = {}
        relevant_media_ids = [job.source_media_id, *(media.id for media in targets)]
        for annotation in Annotation.objects.filter(
            media_id__in=relevant_media_ids,
            class_label=job.class_label,
            is_valid=True,
            type__in=('bbox', 'rectangle'),
        ).only('id', 'media_id', 'data', 'track_id'):
            existing_by_media.setdefault(annotation.media_id, []).append(annotation)

        source_annotation = _best_overlapping_annotation(
            seed_bbox,
            existing_by_media.get(job.source_media_id, []),
            bbox_iou,
        )
        if source_annotation is not None:
            _assign_track(source_annotation, job.track_id)

        matched = 0
        saved = 0
        for index, media in enumerate(targets, start=1):
            image = read_media_image(media)
            if image is not None:
                current_height, current_width = image.shape[:2]
                expected_bbox = {
                    'x': previous_bbox['x'] * current_width / previous_width,
                    'y': previous_bbox['y'] * current_height / previous_height,
                    'width': previous_bbox['width'] * current_width / previous_width,
                    'height': previous_bbox['height'] * current_height / previous_height,
                }
                result = track_next_bbox(
                    image,
                    expected_bbox,
                    previous_template,
                    seed_template,
                    job.similarity_threshold,
                )
                if result is not None:
                    bbox, confidence, next_template = result
                    bbox = {key: round(float(value), 2) for key, value in bbox.items()}
                    matched += 1
                    existing_annotation = _best_overlapping_annotation(
                        bbox,
                        existing_by_media.get(media.id, []),
                        bbox_iou,
                    )
                    if existing_annotation is not None:
                        _assign_track(existing_annotation, job.track_id)
                        saved += 1
                    else:
                        created = Annotation.objects.create(
                            media=media,
                            class_label=job.class_label,
                            annotator=job.created_by,
                            type='bbox',
                            data={
                                **bbox,
                                'source': 'auto_label',
                                'confidence': round(confidence, 4),
                                'auto_label_source': 'propagation',
                                'auto_label_provider': 'visual_tracker',
                                'auto_label_engine_name': 'Visual object tracker',
                            },
                            frame=0,
                            track_id=job.track_id,
                        )
                        existing_by_media.setdefault(media.id, []).append(created)
                        saved += 1
                    previous_bbox = bbox
                    previous_template = next_template
                else:
                    previous_bbox = expected_bbox
                previous_height, previous_width = current_height, current_width

            job.done = index
            job.matched_frames = matched
            job.saved_annotations = saved
            job.save(update_fields=['done', 'matched_frames', 'saved_annotations', 'updated_at'])

        job.status = 'done'
        job.save(update_fields=['status', 'updated_at'])
        job.dataset.invalidate_training_verification()
        enqueue_dataset_label_cache_clear(job.dataset_id)
    except Exception as exc:
        job.status = 'error'
        job.error = str(exc)[:2000]
        job.save(update_fields=['status', 'error', 'updated_at'])
        raise


@shared_task(bind=True, max_retries=0)
def object_propagation_task(self, job_id):
    run_object_propagation_job(job_id)
    return {'job_id': job_id}


def enqueue_object_propagation_job(job_id):
    if getattr(settings, 'AUTO_LABEL_USE_CELERY', False):
        object_propagation_task.apply_async(args=[job_id], queue='datasets')
        return
    threading.Thread(target=run_object_propagation_job, args=(job_id,), daemon=True).start()
