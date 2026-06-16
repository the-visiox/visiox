import json
import logging

from django.db import transaction
from django.db.models import Q
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response

from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

from core.jwt_query_auth import JWTAuthQueryOrHeader

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

from datasets.standalone import (
    browser_payload,
    image_media_for_frame,
    guess_content_type,
    ordered_image_media,
    raw_image_media,
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


def _media_display_name(media) -> str:
    if media.original_filename:
        return media.original_filename
    if media.file:
        return media.file.name.rsplit('/', 1)[-1]
    return f'media-{media.id}'


def _build_pipelines(pre: dict, aug: dict):
    """Build Albumentations preprocessing and augmentation pipelines from config dicts."""
    import cv2
    import albumentations as A

    pre_transforms = []
    if pre.get('resize') and pre.get('resize_width') and pre.get('resize_height'):
        pre_transforms.append(A.Resize(height=int(pre['resize_height']), width=int(pre['resize_width'])))
    if pre.get('grayscale'):
        pre_transforms.append(A.ToGray(num_output_channels=3, p=1.0))
    pre_pipeline = A.Compose(pre_transforms) if pre_transforms else None

    aug_transforms = []
    if aug.get('flip_h'):
        aug_transforms.append(A.HorizontalFlip(p=1.0))
    if aug.get('flip_v'):
        aug_transforms.append(A.VerticalFlip(p=1.0))
    if aug.get('rotate90'):
        aug_transforms.append(A.RandomRotate90(p=1.0))
    if float(aug.get('rotation', 0)) > 0:
        aug_transforms.append(A.Rotate(limit=float(aug['rotation']), border_mode=cv2.BORDER_REFLECT_101, p=1.0))
    if float(aug.get('shear', 0)) > 0:
        aug_transforms.append(A.Affine(shear=(-float(aug['shear']), float(aug['shear'])), p=1.0))
    brightness = float(aug.get('brightness', 0))
    contrast = float(aug.get('contrast', 0))
    if brightness > 0 or contrast > 0:
        aug_transforms.append(A.RandomBrightnessContrast(brightness_limit=brightness, contrast_limit=contrast, p=1.0))
    hue = float(aug.get('hue', 0))
    saturation = float(aug.get('saturation', 0))
    if hue > 0 or saturation > 0:
        aug_transforms.append(A.HueSaturationValue(
            hue_shift_limit=int(hue), sat_shift_limit=int(saturation), val_shift_limit=0, p=1.0,
        ))
    if float(aug.get('blur', 0)) > 0:
        sigma = max(0.1, float(aug['blur']))
        aug_transforms.append(A.GaussianBlur(blur_limit=(3, 3), sigma_limit=(sigma, sigma), p=1.0))
    if float(aug.get('noise', 0)) > 0:
        noise = float(aug['noise'])
        aug_transforms.append(A.GaussNoise(std_range=(noise * 0.5, noise), p=1.0))
    if float(aug.get('motion_blur', 0)) > 0:
        k = max(3, int(aug['motion_blur']))
        if k % 2 == 0:
            k += 1
        aug_transforms.append(A.MotionBlur(blur_limit=(k, k), p=1.0))
    if aug.get('cutout'):
        aug_transforms.append(A.CoarseDropout(num_holes_range=(4, 8), hole_height_range=(0.05, 0.15), hole_width_range=(0.05, 0.15), p=1.0))
    aug_pipeline = A.Compose(aug_transforms) if aug_transforms else None

    return pre_pipeline, aug_pipeline


def _load_media_np(media, pre: dict, pre_pipeline) -> 'np.ndarray':
    import numpy as np
    from PIL import Image, ImageOps

    with media.file.open('rb') as f:
        pil_img = Image.open(f).convert('RGB')
        pil_img.load()

    if pre.get('auto_orient'):
        pil_img = ImageOps.exif_transpose(pil_img)

    img_np = np.array(pil_img)
    if pre_pipeline is not None:
        img_np = pre_pipeline(image=img_np)['image']
    return img_np


def _media_name_exists(dataset: Dataset, name: str) -> bool:
    if not name:
        return False
    return dataset.media_files.filter(original_filename=name).exists()


def _existing_media_names_in_dataset(dataset: Dataset, names: list[str]) -> set[str]:
    return set(dataset.media_files.filter(original_filename__in=names).values_list('original_filename', flat=True))


class DatasetViewSet(viewsets.ModelViewSet):
    serializer_class = DatasetSerializer
    queryset = Dataset.objects.none()

    def get_queryset(self):
        user = self.request.user
        # Scope to datasets the user can reach: projects they own, or projects
        # shared with a team they belong to.
        queryset = Dataset.objects.filter(
            Q(project__owner=user)
            | Q(project__team__owner=user)
            | Q(project__team__members__user=user)
        ).distinct().select_related('project__team')
        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        return queryset

    def get_permissions(self):
        if self.action == 'frame_image':
            return [IsAuthenticated()]
        if self.action == 'destroy':
            return [HasPerm('datasets.delete_dataset')]
        if self.action in ('upload', 'upload_batch'):
            return [HasPerm('datasets.upload_media')]
        if self.action == 'media' and self.request.method == 'DELETE':
            return [HasPerm('datasets.upload_media')]
        return super().get_permissions()

    # ── Custom actions ───────────────────────────────────────────────────────

    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        dataset = self.get_object()
        media_count = ordered_image_media(dataset).count()
        ann_count = Annotation.objects.filter(media__dataset=dataset, is_valid=True).count()
        return Response({
            'id': dataset.id,
            'name': dataset.name,
            'version': dataset.version,
            'project_id': dataset.project_id,
            'project_name': dataset.project.name if dataset.project else None,
            'created_at': dataset.created_at,
            'updated_at': dataset.updated_at,
            'size': media_count,
            'annotation_count': ann_count,
        })

    @action(detail=True, methods=['get', 'delete'])
    def media(self, request, pk=None):
        dataset = self.get_object()

        if request.method == 'DELETE':
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

            deleted_ids: list[int] = []
            for m in list(qs):
                if m.file:
                    m.file.delete(save=False)
                deleted_ids.append(m.id)
                m.delete()
            return Response({'deleted': len(deleted_ids), 'ids': deleted_ids})

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

        return Response(
            MediaSerializer(created, many=True, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'], url_path='versions')
    def new_version(self, request, pk=None):
        dataset = self.get_object()
        dataset.version += 1
        dataset.save(update_fields=['version'])
        return Response(DatasetSerializer(dataset, context={'request': request}).data)

    @action(detail=True, methods=['get'])
    def browser(self, request, pk=None):
        dataset = self.get_object()
        data = browser_payload(dataset)
        data['dataset_id'] = dataset.id
        data['dataset_name'] = dataset.name
        data['version'] = dataset.version
        return Response(data)

    @action(detail=True, methods=['post'], url_path='augmentations/preview')
    def augment_preview(self, request, pk=None):
        import io, base64
        import numpy as np
        import cv2
        import albumentations as A
        from PIL import Image, ImageOps

        dataset = self.get_object()
        data = request.data
        pre = data.get('preprocess', {})
        aug = data.get('augment', {})
        count = min(int(data.get('count', 6)), 12)

        pre_pipeline, aug_pipeline = _build_pipelines(pre, aug)
        media_list = raw_image_media(dataset)[:count]
        previews = []

        for media in media_list:
            try:
                img_np = _load_media_np(media, pre, pre_pipeline)
                if aug_pipeline is not None:
                    img_np = aug_pipeline(image=img_np)['image']

                buf = io.BytesIO()
                Image.fromarray(img_np).save(buf, format='JPEG', quality=82)
                b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                name = _media_display_name(media)
                previews.append({'media_id': media.id, 'name': name, 'augmented_url': f'data:image/jpeg;base64,{b64}'})
            except Exception:
                logger.exception('Failed to generate augment preview for media %d', media.id)

        return Response({'previews': previews})

    @action(detail=True, methods=['post'], url_path='augmentations')
    def augment_apply(self, request, pk=None):
        import io
        import numpy as np
        import cv2
        import albumentations as A
        from PIL import Image, ImageOps
        from django.core.files.base import ContentFile

        dataset = self.get_object()
        data = request.data
        pre = data.get('preprocess', {})
        aug = data.get('augment', {})
        multiplier = max(1, min(int(data.get('multiplier', 1)), 5))

        pre_pipeline, aug_pipeline = _build_pipelines(pre, aug)
        # Only augment original images — never re-augment previously generated ones.
        media_list = raw_image_media(dataset)
        generated = 0

        for media in media_list:
            try:
                base_np = _load_media_np(media, pre, pre_pipeline)
                original_name = _media_display_name(media)

                for i in range(multiplier):
                    img_np = base_np.copy()
                    if aug_pipeline is not None:
                        img_np = aug_pipeline(image=img_np)['image']

                    pil_out = Image.fromarray(img_np)
                    buf = io.BytesIO()
                    pil_out.save(buf, format='JPEG', quality=88)
                    buf.seek(0)

                    aug_name = f'aug_{i + 1}_{original_name}'
                    new_media = Media(
                        dataset=dataset,
                        type='image',
                        original_filename=aug_name,
                        width=pil_out.width,
                        height=pil_out.height,
                        metadata={'category': 'augmented'},
                    )
                    new_media._upload_category = 'augmented'
                    new_media.file.save(f'{aug_name}.jpg', ContentFile(buf.read()), save=True)
                    generated += 1
            except Exception:
                logger.exception('Failed to apply augmentation for media %d', media.id)

        return Response({'generated': generated, 'total': len(media_list) * multiplier})

    @action(detail=True, methods=['get'], url_path=r'frames/(?P<frame_num>\d+)',
            authentication_classes=[JWTAuthQueryOrHeader], permission_classes=[IsAuthenticated])
    def frame_image(self, request, pk=None, frame_num=None):
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

    @action(detail=True, methods=['get', 'put'],
            url_path=r'frames/(?P<frame_num>\d+)/annotations')
    def frame_annotations(self, request, pk=None, frame_num=None):
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
