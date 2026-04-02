from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response

from datasets.models import Dataset, Media
from datasets.serializers import DatasetSerializer, MediaSerializer, MediaUploadSerializer


def _extract_image_dimensions(file):
    try:
        from PIL import Image
        img = Image.open(file)
        width, height = img.size
        file.seek(0)
        return width, height
    except Exception:
        return None, None


class DatasetViewSet(viewsets.ModelViewSet):
    serializer_class = DatasetSerializer
    queryset = Dataset.objects.none()

    def get_queryset(self):
        user = self.request.user
        return Dataset.objects.filter(
            project__team__members__user=user
        ).distinct().select_related('project')

    def perform_create(self, serializer):
        serializer.save()

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
        return Response(
            MediaSerializer(media, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'])
    def new_version(self, request, pk=None):
        dataset = self.get_object()
        dataset.version += 1
        dataset.save(update_fields=['version'])
        return Response(DatasetSerializer(dataset).data)
