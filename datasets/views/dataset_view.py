import json
import logging

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response

from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

from core.permissions import HasPerm
from datasets.models import Dataset, Media
from datasets.serializers import DatasetSerializer, MediaSerializer, MediaUploadSerializer
from django.http import HttpResponse

from datasets.services.cvat import (
    ensure_cvat_task,
    get_cvat_task_url,
    get_cvat_task_metadata,
    get_cvat_task_stats,
    get_cvat_browser_data,
    get_cvat_frame_image,
    upload_cvat_data,
    delete_cvat_task,
    update_cvat_task,
    repair_orphaned_datasets,
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


def _push_new_images_to_cvat_if_task_empty(dataset: Dataset, image_paths: list[str]) -> None:
    """Send images to CVAT only while the task has no frames (CVAT allows one data upload)."""
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
        if self.action in ('upload', 'upload_batch'):
            return [HasPerm('datasets.upload_media')]
        return super().get_permissions()

    def perform_create(self, serializer):
        dataset = serializer.save()
        try:
            ensure_cvat_task(dataset)
        except Exception:
            logger.exception('Failed to auto-provision CVAT task for dataset %d', dataset.id)

    def perform_update(self, serializer):
        old_name = serializer.instance.name
        dataset = serializer.save()
        if dataset.name != old_name and dataset.cvat_task_id:
            try:
                update_cvat_task(dataset.cvat_task_id, name=dataset.name)
            except Exception:
                logger.exception('Failed to sync name change to CVAT task %d', dataset.cvat_task_id)

    def perform_destroy(self, instance):
        if instance.cvat_task_id:
            try:
                delete_cvat_task(instance.cvat_task_id)
            except Exception:
                logger.exception('Failed to delete CVAT task %d', instance.cvat_task_id)
        instance.delete()

    # ── Custom actions ───────────────────────────────────────────────────────

    @action(detail=True, methods=['get'])
    def annotate_url(self, request, pk=None):
        dataset = self.get_object()
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

    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def upload(self, request, pk=None):
        dataset = self.get_object()
        serializer = MediaUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data['file']
        media_type = serializer.validated_data['type']
        metadata = serializer.validated_data.get('metadata', {})

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
        """Upload many files in one request. Images are pushed to CVAT in a single batch if the task is still empty."""
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
        if not dataset.cvat_task_id:
            return Response({'error': 'No CVAT task linked'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            project_id = dataset.project.cvat_project_id if dataset.project else None
            data = get_cvat_browser_data(dataset.cvat_task_id, project_id)
            data['dataset_id'] = dataset.id
            data['dataset_name'] = dataset.name
            data['version'] = dataset.version
            return Response(data)
        except Exception:
            logger.exception('Failed to get browser data for dataset %d', dataset.id)
            return Response({'error': 'Failed to load browser data'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get'], url_path=r'frames/(?P<frame_num>\d+)',
            authentication_classes=[], permission_classes=[AllowAny])
    def frame_image(self, request, pk=None, frame_num=None):
        """Proxy a single frame image from CVAT.

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

    @action(detail=False, methods=['post'], url_path='repair-cvat')
    def repair_cvat(self, request):
        """Find and repair datasets whose CVAT tasks no longer exist."""
        repaired = repair_orphaned_datasets()
        return Response({
            'status': 'ok',
            'repaired_count': len(repaired),
            'repaired': repaired,
        })
