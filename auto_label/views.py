from pathlib import Path

from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from annotations.colors import class_color_for_index
from annotations.models import Class
from auto_label.models import AutoLabelDatasetJob, AutoLabelModel, ObjectPropagationJob
from auto_label.propagation import normalize_bbox
from auto_label.providers import PROVIDERS, provider_by_id
from auto_label.serializers import AutoLabelModelSerializer
from auto_label.services import (
    AutoLabelInferenceError,
    inference_confidence,
    prediction_bbox_data,
    prediction_polygon_data,
    purge_temporary_model,
    request_predictions,
)
from auto_label.tasks import enqueue_auto_label_dataset_job, enqueue_object_propagation_job
from core.access import project_access_q
from datasets.models import Dataset
from datasets.services.media_browser import ordered_image_media


class AutoLabelModelViewSet(viewsets.ModelViewSet):
    serializer_class = AutoLabelModelSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    http_method_names = ['get', 'post', 'delete', 'head', 'options']

    def get_queryset(self):
        queryset = AutoLabelModel.objects.filter(
            project_access_q(self.request.user, 'project__'),
        ).distinct().select_related('project', 'created_by')
        if self.action == 'list':
            queryset = queryset.filter(is_temporary=False)
        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        return queryset


class AutoLabelProviderListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(PROVIDERS)


def dataset_job_payload(job):
    return {
        'id': job.id,
        'dataset': job.dataset_id,
        'model': job.model_id,
        'model_name': job.model.name,
        'output_type': job.output_type,
        'confidence': job.confidence,
        'status': job.status,
        'total': job.total,
        'done': job.done,
        'labeled_images': job.labeled_images,
        'saved_annotations': job.saved_annotations,
        'skipped_predictions': job.skipped_predictions,
        'error': job.error,
        'created_at': job.created_at,
        'updated_at': job.updated_at,
    }


def propagation_job_payload(job):
    return {
        'id': job.id,
        'dataset': job.dataset_id,
        'source_frame': job.source_frame,
        'source_media': job.source_media_id,
        'class_label': job.class_label_id,
        'class_name': job.class_label.name,
        'seed_bbox': job.seed_bbox,
        'similarity_threshold': job.similarity_threshold,
        'max_frames': job.max_frames,
        'track_id': str(job.track_id),
        'status': job.status,
        'total': job.total,
        'done': job.done,
        'matched_frames': job.matched_frames,
        'saved_annotations': job.saved_annotations,
        'error': job.error,
        'created_at': job.created_at,
        'updated_at': job.updated_at,
    }


class DatasetAutoLabelView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, dataset_id):
        dataset = Dataset.objects.filter(
            project_access_q(request.user, 'project__'),
            pk=dataset_id,
        ).select_related('project').first()
        if dataset is None:
            return Response({'error': 'Dataset not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            model_id = int(request.data.get('model_id'))
            confidence = inference_confidence(request.data.get('confidence'))
        except (TypeError, ValueError) as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        output_type = request.data.get('output_type', 'bbox')
        model = AutoLabelModel.objects.filter(
            project=dataset.project,
            pk=model_id,
            status='ready',
        ).first()
        if model is None:
            return Response({'error': 'Ready Auto Label model not found.'}, status=status.HTTP_404_NOT_FOUND)
        if output_type not in model.capabilities:
            return Response(
                {'error': f'The selected model does not support {output_type}.'},
                status=status.HTTP_409_CONFLICT,
            )
        active = AutoLabelDatasetJob.objects.filter(
            dataset=dataset,
            status__in=('queued', 'running'),
        ).select_related('model').first()
        if active:
            return Response(dataset_job_payload(active), status=status.HTTP_409_CONFLICT)
        total = dataset.media_files.filter(type='image').count()
        if total == 0:
            return Response({'error': 'Dataset has no images.'}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            job = AutoLabelDatasetJob.objects.create(
                dataset=dataset,
                model=model,
                output_type=output_type,
                confidence=confidence,
                total=total,
                created_by=request.user,
            )
            transaction.on_commit(lambda: enqueue_auto_label_dataset_job(job.id))
        return Response(dataset_job_payload(job), status=status.HTTP_202_ACCEPTED)


class DatasetAutoLabelJobView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = []

    def get(self, request, dataset_id, job_id):
        job = AutoLabelDatasetJob.objects.filter(
            project_access_q(request.user, 'dataset__project__'),
            dataset_id=dataset_id,
            pk=job_id,
        ).select_related('model').first()
        if job is None:
            return Response({'error': 'Auto Label job not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(dataset_job_payload(job))


class ObjectPropagationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, dataset_id, frame_num):
        dataset = Dataset.objects.filter(
            project_access_q(request.user, 'project__'),
            pk=dataset_id,
        ).select_related('project').first()
        if dataset is None:
            return Response({'error': 'Dataset not found.'}, status=status.HTTP_404_NOT_FOUND)
        source_media = ordered_image_media(dataset)[frame_num:frame_num + 1].first()
        if source_media is None:
            return Response({'error': 'Source frame not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            class_label_id = int(request.data.get('class_label'))
            threshold = float(request.data.get('similarity_threshold', 0.7))
            bbox = normalize_bbox(
                request.data.get('bbox'),
                image_width=source_media.width,
                image_height=source_media.height,
            )
            raw_max_frames = request.data.get('max_frames')
            max_frames = None if raw_max_frames in (None, '') else int(raw_max_frames)
        except (TypeError, ValueError) as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if not 0.3 <= threshold <= 0.95:
            return Response(
                {'error': 'similarity_threshold must be between 0.3 and 0.95.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if max_frames is not None and not 1 <= max_frames <= 10000:
            return Response(
                {'error': 'max_frames must be between 1 and 10000.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        class_label = Class.objects.filter(project=dataset.project, pk=class_label_id).first()
        if class_label is None:
            return Response({'error': 'Project class not found.'}, status=status.HTTP_404_NOT_FOUND)
        active = ObjectPropagationJob.objects.filter(
            dataset=dataset,
            status__in=('queued', 'running'),
        ).select_related('class_label').first()
        if active:
            if active.status == 'queued':
                enqueue_object_propagation_job(active.id)
            return Response(propagation_job_payload(active), status=status.HTTP_200_OK)
        remaining = ordered_image_media(dataset)[frame_num + 1:].count()
        total = min(remaining, max_frames) if max_frames else remaining
        if total == 0:
            return Response({'error': 'There are no later frames to label.'}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            job = ObjectPropagationJob.objects.create(
                dataset=dataset,
                source_media=source_media,
                source_frame=frame_num,
                class_label=class_label,
                seed_bbox=bbox,
                similarity_threshold=threshold,
                max_frames=max_frames,
                total=total,
                created_by=request.user,
            )
            transaction.on_commit(lambda: enqueue_object_propagation_job(job.id))
        return Response(propagation_job_payload(job), status=status.HTTP_202_ACCEPTED)


class ObjectPropagationJobView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = []

    def get(self, request, dataset_id, job_id):
        job = self._job(request, dataset_id, job_id)
        if job is None:
            return Response({'error': 'Object propagation job not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(propagation_job_payload(job))

    def post(self, request, dataset_id, job_id):
        job = self._job(request, dataset_id, job_id)
        if job is None:
            return Response({'error': 'Object propagation job not found.'}, status=status.HTTP_404_NOT_FOUND)
        if job.status == 'queued':
            enqueue_object_propagation_job(job.id)
        return Response(propagation_job_payload(job), status=status.HTTP_202_ACCEPTED)

    @staticmethod
    def _job(request, dataset_id, job_id):
        job = ObjectPropagationJob.objects.filter(
            project_access_q(request.user, 'dataset__project__'),
            dataset_id=dataset_id,
            pk=job_id,
        ).select_related('class_label').first()
        return job


class FrameAutoLabelPredictView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, dataset_id, frame_num):
        dataset = Dataset.objects.filter(
            project_access_q(request.user, 'project__'),
            pk=dataset_id,
        ).select_related('project').first()
        if dataset is None:
            return Response({'error': 'Dataset not found.'}, status=status.HTTP_404_NOT_FOUND)

        media = ordered_image_media(dataset)[frame_num:frame_num + 1].first()
        if media is None:
            return Response({'error': 'Frame not found.'}, status=status.HTTP_404_NOT_FOUND)

        source = request.data.get('source')
        output_type = request.data.get('output_type', 'bbox')
        if not isinstance(source, dict) or output_type not in ('bbox', 'polygon'):
            return Response(
                {'error': 'A valid source and output_type are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            confidence = inference_confidence(request.data.get('confidence'))
            engine, compatibility_model, source_response = self._resolve_source(request, dataset, source, output_type)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except LookupError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except RuntimeError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_409_CONFLICT)

        payload = {
            'engine': engine,
            'dataset': {'id': dataset.id, 'media_ids': [media.id]},
            'output_type': output_type,
            'confidence': confidence,
        }
        if compatibility_model:
            payload['model'] = compatibility_model
        try:
            result = request_predictions(payload)
        except AutoLabelInferenceError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        finally:
            if compatibility_model:
                temporary_model = AutoLabelModel.objects.filter(
                    pk=compatibility_model['registry_id'],
                    is_temporary=True,
                ).first()
                if temporary_model is not None:
                    purge_temporary_model(temporary_model)

        classes = list(Class.objects.filter(project=dataset.project).order_by('id'))
        class_by_name = {item.name.strip().casefold(): item for item in classes}
        create_missing = bool(request.data.get('create_missing_classes', False))
        created_classes = []
        unmapped_labels = set()
        predictions = []
        for prediction in result.get('predictions', []):
            if str(prediction.get('media_id')) != str(media.id):
                continue
            label = str(prediction.get('label') or '').strip()
            if not label:
                continue
            class_obj = class_by_name.get(label.casefold())
            if class_obj is None and create_missing:
                with transaction.atomic():
                    class_obj, created = Class.objects.get_or_create(
                        project=dataset.project,
                        name=label,
                        defaults={'color': class_color_for_index(len(class_by_name))},
                    )
                class_by_name[label.casefold()] = class_obj
                if created:
                    created_classes.append({'id': class_obj.id, 'name': class_obj.name, 'color': class_obj.color})
            if class_obj is None:
                unmapped_labels.add(label)
                continue
            shape_type = 'polygon' if output_type == 'polygon' else 'bbox'
            data = (
                prediction_polygon_data(prediction, media)
                if shape_type == 'polygon'
                else prediction_bbox_data(prediction, media)
            )
            if data is None:
                continue
            predictions.append({
                'type': shape_type,
                'class_label': class_obj.id,
                'label': class_obj.name,
                'confidence': prediction.get('confidence'),
                'data': data,
            })

        return Response({
            'dataset': dataset.id,
            'frame': frame_num,
            'media_id': media.id,
            'source': source_response,
            'predictions': predictions,
            'created_classes': created_classes,
            'unmapped_labels': sorted(unmapped_labels),
            'summary': result.get('summary') or {},
        })

    @staticmethod
    def _resolve_source(request, dataset, source, output_type):
        kind = source.get('kind')
        if kind == 'uploaded_model':
            try:
                model_id = int(source.get('model_id'))
            except (TypeError, ValueError) as exc:
                raise ValueError('source.model_id is required.') from exc
            model = AutoLabelModel.objects.filter(
                project_access_q(request.user, 'project__'),
                project=dataset.project,
                pk=model_id,
            ).first()
            if model is None:
                raise LookupError('Auto Label model not found.')
            if model.status != 'ready':
                raise RuntimeError('The selected Auto Label model is not ready.')
            if output_type not in model.capabilities:
                raise RuntimeError(f'The selected model does not support {output_type}.')
            artifact_format = Path(model.model_file.name).suffix.lower().lstrip('.') or 'pt'
            engine = {
                'provider': 'uploaded_yolo',
                'model_id': model.id,
                'name': model.name,
                'version': model.version,
                'format': artifact_format,
                'task_type': model.task_type,
                'storage_key': model.model_file.name,
            }
            compatibility_model = {
                'registry_id': model.id,
                'name': model.name,
                'version': model.version,
                'format': artifact_format,
                'storage_key': model.model_file.name,
            }
            return engine, compatibility_model, {
                'kind': kind, 'model_id': model.id, 'provider': 'uploaded_yolo', 'name': model.name,
            }

        if kind == 'provider':
            provider_id = str(source.get('provider') or '')
            provider = provider_by_id(provider_id)
            if provider is None:
                raise LookupError('Auto Label provider not found.')
            if output_type not in provider['capabilities']:
                raise RuntimeError(f'{provider["display_name"]} does not support {output_type}.')
            model_name = str(source.get('model') or '')
            if model_name not in provider['models']:
                raise ValueError('A valid provider model is required.')
            prompts = source.get('prompts')
            if not isinstance(prompts, list):
                raise ValueError('source.prompts must be a list of class names.')
            prompts = list(dict.fromkeys(str(item).strip() for item in prompts if str(item).strip()))
            if not prompts:
                raise ValueError('At least one YOLO World prompt is required.')
            return {
                'provider': provider_id,
                'model': model_name,
                'prompts': prompts[:100],
            }, None, {
                'kind': kind, 'provider': provider_id, 'model': model_name,
            }

        raise ValueError('source.kind must be uploaded_model or provider.')
