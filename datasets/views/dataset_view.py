import json
import logging

from django.db import transaction
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response

from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

from annotations.models import Annotation
from annotations.serializers import AnnotationSerializer, JobAnnotationsReplaceSerializer
from core.permissions import HasPerm
from datasets.models import Dataset, Media
from datasets.serializers import (
    DatasetSerializer,
    MediaSerializer,
    MediaUploadSerializer,
    MediaBulkDeleteSerializer,
)
from django.http import HttpResponse

from datasets.services.cvat import (
    ensure_cvat_task,
    get_cvat_task_url,
    get_cvat_task_metadata,
    get_cvat_task_stats,
    get_cvat_browser_data,
    get_cvat_frame_image,
    merge_cvat_deleted_frames,
    upload_cvat_data,
    delete_cvat_task,
    update_cvat_task,
    repair_orphaned_datasets,
)
from datasets.standalone import (
    standalone_enabled,
    browser_payload as standalone_browser_payload,
    synthetic_cvat_stats,
    image_media_for_frame,
    guess_content_type,
)

logger = logging.getLogger(__name__)


def _extract_image_dimensions(file):
    try:
        from PIL import Image
        img = Image.open(file)
        width, height = img.size
        file.seek(0)
        return width, height
    except Exception:
        return None, None


def _media_name_exists(dataset: Dataset, name: str) -> bool:
    if not name:
        return False
    return dataset.media_files.filter(original_filename=name).exists()


def _existing_media_names_in_dataset(dataset: Dataset, names: list[str]) -> set[str]:
    return set(dataset.media_files.filter(original_filename__in=names).values_list('original_filename', flat=True))


def _push_new_images_to_cvat_if_task_empty(dataset: Dataset, image_paths: list[str]) -> None:
    """Send images to CVAT only while the task has no frames (CVAT allows one data upload)."""
    if standalone_enabled():
        return
    if not image_paths or not dataset.cvat_task_id:
        return
    try:
        stats = get_cvat_task_stats(dataset.cvat_task_id)
        if not stats.get('exists'):
            return
        if int(stats.get('size') or 0) != 0:
            logger.info(
                'CVAT task %d already has frames; %d file(s) kept in VisioX media only',
                dataset.cvat_task_id,
                len(image_paths),
            )
            return
        upload_cvat_data(dataset.cvat_task_id, image_paths)
    except Exception:
        logger.exception(
            'Failed to upload %d image(s) to CVAT task %d',
            len(image_paths),
            dataset.cvat_task_id,
        )


class DatasetViewSet(viewsets.ModelViewSet):
    serializer_class = DatasetSerializer
    queryset = Dataset.objects.none()

    def get_queryset(self):
        queryset = Dataset.objects.all().select_related('project')
        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        return queryset

    def get_permissions(self):
        if self.action == 'frame_image':
            return [AllowAny()]
        if self.action == 'destroy':
            return [HasPerm('datasets.delete_dataset')]
        if self.action in ('upload', 'upload_batch', 'delete_media'):
            return [HasPerm('datasets.upload_media')]
        return super().get_permissions()

    def perform_create(self, serializer):
        dataset = serializer.save()
        if standalone_enabled():
            return
        from datasets.tasks import provision_cvat_task
        provision_cvat_task.delay(dataset.id)

    def perform_update(self, serializer):
        old_name = serializer.instance.name
        dataset = serializer.save()
        if standalone_enabled():
            return
        if dataset.name != old_name and dataset.cvat_task_id:
            try:
                update_cvat_task(dataset.cvat_task_id, name=dataset.name)
            except Exception:
                logger.exception('Failed to sync name change to CVAT task %d', dataset.cvat_task_id)

    def perform_destroy(self, instance):
        if not standalone_enabled() and instance.cvat_task_id:
            try:
                delete_cvat_task(instance.cvat_task_id)
            except Exception:
                logger.exception('Failed to delete CVAT task %d', instance.cvat_task_id)
        instance.delete()

    # ── Custom actions ───────────────────────────────────────────────────────

    @action(detail=True, methods=['get'])
    def annotate_url(self, request, pk=None):
        dataset = self.get_object()
        if standalone_enabled():
            return Response(
                {
                    'error': 'CVAT is disabled (VISIOX_STANDALONE). Use native annotation in the UI.',
                    'native_only': True,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ensure_cvat_task(dataset)
        except Exception:
            return Response(
                {'error': 'Failed to provision CVAT task'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        url = get_cvat_task_url(dataset.cvat_task_id)
        return Response({'url': url})

    @action(detail=True, methods=['post'])
    def sync_cvat(self, request, pk=None):
        dataset = self.get_object()
        if standalone_enabled():
            return Response(
                {'error': 'CVAT sync is disabled in standalone mode (VISIOX_STANDALONE).'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not dataset.cvat_task_id:
            return Response({'error': 'No CVAT task linked.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            meta = get_cvat_task_metadata(dataset.cvat_task_id)
            dataset.version += 1
            dataset.save(update_fields=['version', 'updated_at'])

            return Response({
                'status': 'synced',
                'version': dataset.version,
                'cvat_status': meta['status'],
                'total_labels': meta['total_labels'],
            })
        except Exception:
            logger.exception('Sync failed for dataset %d', dataset.id)
            return Response({'error': 'Sync failed'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Return unified dataset statistics from both VisioX and CVAT."""
        dataset = self.get_object()
        result = {
            'id': dataset.id,
            'name': dataset.name,
            'version': dataset.version,
            'project_id': dataset.project_id,
            'project_name': dataset.project.name if dataset.project else None,
            'cvat_task_id': dataset.cvat_task_id,
            'created_at': dataset.created_at,
            'updated_at': dataset.updated_at,
            'cvat': None,
        }

        if standalone_enabled():
            result['cvat'] = synthetic_cvat_stats(dataset)
            return Response(result)

        if dataset.cvat_task_id:
            try:
                result['cvat'] = get_cvat_task_stats(dataset.cvat_task_id)
            except Exception:
                logger.exception('Failed to fetch CVAT stats for dataset %d', dataset.id)
                result['cvat'] = {'exists': False, 'error': 'Failed to fetch'}

        return Response(result)

    @action(detail=True, methods=['get'])
    def media(self, request, pk=None):
        dataset = self.get_object()
        media_qs = dataset.media_files.all()
        serializer = MediaSerializer(media_qs, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='delete-media')
    def delete_media(self, request, pk=None):
        """Delete dataset media files by id (removes stored files and DB rows)."""
        dataset = self.get_object()
        serializer = MediaBulkDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = serializer.validated_data['media_ids']
        qs = Media.objects.filter(dataset=dataset, id__in=ids)
        found_ids = set(qs.values_list('id', flat=True))
        missing = sorted(set(ids) - found_ids)
        if missing:
            return Response(
                {'detail': 'Some media ids are not in this dataset.', 'invalid_ids': missing},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # CVAT task must hide the same frame indices or the browser (CVAT-backed) still shows them.
        if not standalone_enabled() and dataset.cvat_task_id:
            ordered_images = list(
                dataset.media_files.filter(type='image').order_by('uploaded_at', 'id'),
            )
            id_to_frame_index = {m.id: i for i, m in enumerate(ordered_images)}
            frame_indices = sorted({id_to_frame_index[mid] for mid in ids if mid in id_to_frame_index})
            if frame_indices:
                try:
                    merge_cvat_deleted_frames(dataset.cvat_task_id, frame_indices)
                except Exception:
                    # Still delete Media below so the API is usable when CVAT is down or misconfigured.
                    # Images may still appear until CVAT sync or manual task fix.
                    logger.exception(
                        'CVAT data/meta update failed for task %s (dataset %s); continuing with DB delete',
                        dataset.cvat_task_id,
                        dataset.id,
                    )

        deleted_ids: list[int] = []
        for media in list(qs):
            if media.file:
                media.file.delete(save=False)
            deleted_ids.append(media.id)
            media.delete()
        return Response({'deleted': len(deleted_ids), 'ids': deleted_ids})

    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def upload(self, request, pk=None):
        dataset = self.get_object()
        serializer = MediaUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data['file']
        media_type = serializer.validated_data['type']
        metadata = serializer.validated_data.get('metadata', {})

        if _media_name_exists(dataset, uploaded_file.name):
            return Response(
                {'detail': 'A file with this name already exists in this dataset.'},
                status=status.HTTP_409_CONFLICT,
            )

        width, height = None, None
        if media_type == 'image':
            width, height = _extract_image_dimensions(uploaded_file)

        media = Media.objects.create(
            dataset=dataset,
            type=media_type,
            file=uploaded_file,
            original_filename=uploaded_file.name,
            width=width,
            height=height,
            file_size=uploaded_file.size,
            metadata=metadata,
        )

        if media_type == 'image':
            _push_new_images_to_cvat_if_task_empty(dataset, [media.file.path])

        return Response(
            MediaSerializer(media, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=['post'],
        parser_classes=[MultiPartParser, FormParser],
        url_path='upload-batch',
    )
    def upload_batch(self, request, pk=None):
        """Upload many files in one request. With CVAT enabled, images may be pushed when the task is still empty."""
        dataset = self.get_object()
        files = request.FILES.getlist('files')
        if not files:
            return Response({'detail': 'No files provided. Use form field "files".'}, status=status.HTTP_400_BAD_REQUEST)
        if len(files) > 100:
            return Response({'detail': 'Maximum 100 files per request.'}, status=status.HTTP_400_BAD_REQUEST)

        media_type = request.data.get('type', 'image')
        if media_type not in ('image', 'video'):
            return Response({'detail': 'type must be "image" or "video".'}, status=status.HTTP_400_BAD_REQUEST)

        metadata_raw = request.data.get('metadata')
        metadata = {}
        if metadata_raw not in (None, ''):
            try:
                metadata = json.loads(metadata_raw) if isinstance(metadata_raw, str) else metadata_raw
                if not isinstance(metadata, dict):
                    metadata = {}
            except (json.JSONDecodeError, TypeError):
                metadata = {}

        names = [f.name for f in files]
        if not all(names):
            return Response(
                {'detail': 'Every file must have a non-empty name.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(names) != len(set(names)):
            return Response(
                {'detail': 'This request contains duplicate file names.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        clashes = _existing_media_names_in_dataset(dataset, names)
        if clashes:
            return Response(
                {
                    'detail': 'One or more file names already exist in this dataset.',
                    'files': sorted(clashes),
                },
                status=status.HTTP_409_CONFLICT,
            )

        created = []
        image_paths: list[str] = []
        for uploaded_file in files:
            width, height = None, None
            if media_type == 'image':
                width, height = _extract_image_dimensions(uploaded_file)

            media = Media.objects.create(
                dataset=dataset,
                type=media_type,
                file=uploaded_file,
                original_filename=uploaded_file.name,
                width=width,
                height=height,
                file_size=uploaded_file.size,
                metadata=metadata,
            )
            created.append(media)
            if media_type == 'image':
                image_paths.append(media.file.path)

        if media_type == 'image':
            _push_new_images_to_cvat_if_task_empty(dataset, image_paths)

        return Response(
            MediaSerializer(created, many=True, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'])
    def new_version(self, request, pk=None):
        dataset = self.get_object()
        dataset.version += 1
        dataset.save(update_fields=['version'])
        return Response(DatasetSerializer(dataset, context={'request': request}).data)

    @action(detail=True, methods=['get'])
    def browser(self, request, pk=None):
        """Return frame list, labels, and annotations for the data browser."""
        dataset = self.get_object()
        if standalone_enabled():
            data = standalone_browser_payload(dataset)
            data['dataset_id'] = dataset.id
            data['dataset_name'] = dataset.name
            data['version'] = dataset.version
            return Response(data)
        if not dataset.cvat_task_id:
            return Response({'error': 'No CVAT task linked'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            project_id = dataset.project.cvat_project_id if dataset.project else None
            data = get_cvat_browser_data(dataset.cvat_task_id, project_id)
            data['dataset_id'] = dataset.id
            data['dataset_name'] = dataset.name
            data['version'] = dataset.version
            images = list(
                dataset.media_files.filter(type='image').order_by('uploaded_at', 'id')
            )
            for i, fr in enumerate(data.get('frames', [])):
                if i < len(images):
                    fr['media_id'] = images[i].id
            return Response(data)
        except Exception:
            logger.exception('Failed to get browser data for dataset %d', dataset.id)
            return Response({'error': 'Failed to load browser data'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get'], url_path=r'frames/(?P<frame_num>\d+)',
            authentication_classes=[], permission_classes=[AllowAny])
    def frame_image(self, request, pk=None, frame_num=None):
        """Return a frame image (CVAT proxy, or VisioX Media when VISIOX_STANDALONE).

        Supports JWT via query param ``token`` so that ``<img src>`` tags work
        without an ``Authorization`` header.
        """
        query_token = request.query_params.get('token')
        if query_token:
            jwt_auth = JWTAuthentication()
            try:
                validated = jwt_auth.get_validated_token(query_token)
                request.user = jwt_auth.get_user(validated)
            except (InvalidToken, Exception):
                return HttpResponse(b'Unauthorized', status=401, content_type='text/plain')
        elif not (request.user and request.user.is_authenticated):
            return HttpResponse(b'Unauthorized', status=401, content_type='text/plain')

        dataset = self.get_object()
        if standalone_enabled():
            try:
                media = image_media_for_frame(dataset, int(frame_num))
            except (TypeError, ValueError):
                return HttpResponse(b'Invalid frame', status=400, content_type='text/plain')
            if not media or not media.file:
                return HttpResponse(b'Frame not found', status=404, content_type='text/plain')
            try:
                with media.file.open('rb') as f:
                    image_bytes = f.read()
            except Exception:
                logger.exception('Failed to read media file for dataset %s frame %s', dataset.id, frame_num)
                return HttpResponse(b'Failed to load frame', status=500, content_type='text/plain')
            response = HttpResponse(image_bytes, content_type=guess_content_type(media))
            response['Cache-Control'] = 'public, max-age=3600'
            return response
        if not dataset.cvat_task_id:
            return HttpResponse(b'No CVAT task linked', status=400, content_type='text/plain')
        try:
            quality = request.query_params.get('quality', 'compressed')
            image_bytes, content_type = get_cvat_frame_image(
                dataset.cvat_task_id, int(frame_num), quality
            )
            response = HttpResponse(image_bytes, content_type=content_type)
            response['Cache-Control'] = 'public, max-age=3600'
            return response
        except Exception:
            logger.exception('Failed to get frame %s for dataset %d', frame_num, dataset.id)
            return HttpResponse(b'Failed to load frame', status=500, content_type='text/plain')

    @action(detail=True, methods=['get', 'put'],
            url_path=r'frames/(?P<frame_num>\d+)/annotations')
    def frame_annotations(self, request, pk=None, frame_num=None):
        """
        GET  /api/datasets/<id>/frames/<frame>/annotations/ — list annotations for a frame.
        PUT  /api/datasets/<id>/frames/<frame>/annotations/ — replace all annotations for that frame's media.
        """
        dataset = self.get_object()
        media = image_media_for_frame(dataset, int(frame_num))
        if media is None:
            return Response({'detail': f'Frame {frame_num} not found in dataset {dataset.id}.'},
                            status=status.HTTP_404_NOT_FOUND)

        if request.method == 'GET':
            qs = Annotation.objects.filter(media=media).select_related('class_label', 'annotator')
            return Response(AnnotationSerializer(qs, many=True).data)

        serializer = JobAnnotationsReplaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        items = serializer.validated_data['annotations']

        project_id = dataset.project_id
        for item in items:
            if item['class_label'].project_id != project_id:
                raise ValidationError(
                    {'annotations': f'Class {item["class_label"].pk} does not belong to this project.'}
                )

        user = request.user
        with transaction.atomic():
            Annotation.objects.filter(media=media).delete()
            Annotation.objects.bulk_create([
                Annotation(
                    media=media,
                    class_label=item['class_label'],
                    annotator=user,
                    type=item['type'],
                    data=item['data'],
                    frame=item.get('frame', 0),
                    track_id=item.get('track_id'),
                )
                for item in items
            ])
        qs = Annotation.objects.filter(media=media).select_related('class_label', 'annotator')
        return Response(AnnotationSerializer(qs, many=True).data)

    @action(detail=False, methods=['post'], url_path='repair-cvat')
    def repair_cvat(self, request):
        """Find and repair datasets whose CVAT tasks no longer exist."""
        if standalone_enabled():
            return Response(
                {'error': 'repair-cvat is disabled in standalone mode (VISIOX_STANDALONE).'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        repaired = repair_orphaned_datasets()
        return Response({
            'status': 'ok',
            'repaired_count': len(repaired),
            'repaired': repaired,
        })
