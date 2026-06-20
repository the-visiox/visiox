from django.http import HttpResponse
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from datasets.models import Dataset
from annotations.services import export as export_svc
from core.access import project_access_q


EXPORTERS = {
    'coco': export_svc.export_coco,
    'yolo': export_svc.export_yolo,
    'voc': export_svc.export_voc,
    'mask': export_svc.export_segmentation_mask,
    'coco_keypoints': export_svc.export_coco_keypoints,
    'imagenet': export_svc.export_imagenet,
}
_TRUTHY = {'1', 'true', 'yes', 'on'}


class DatasetExportView(APIView):
    @extend_schema(
        parameters=[
            OpenApiParameter('format', OpenApiTypes.STR, OpenApiParameter.QUERY,
                             enum=list(EXPORTERS), description='Export format'),
            OpenApiParameter('save_images', OpenApiTypes.BOOL, OpenApiParameter.QUERY,
                             description='Include source images in the archive'),
        ],
        responses={200: OpenApiTypes.BINARY},
    )
    def get(self, request, dataset_id):
        try:
            dataset = Dataset.objects.select_related('project').get(
                project_access_q(request.user, 'project__'),
                pk=dataset_id,
            )
        except Dataset.DoesNotExist:
            return Response({'error': 'Dataset not found.'}, status=status.HTTP_404_NOT_FOUND)

        fmt = request.query_params.get('format', 'coco').lower()
        exporter = EXPORTERS.get(fmt)
        if exporter is None:
            return Response(
                {'error': f'Unsupported format "{fmt}". Use one of: {", ".join(EXPORTERS)}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        save_images = request.query_params.get('save_images', '').lower() in _TRUTHY
        buf = exporter(dataset, save_images=save_images)
        return HttpResponse(
            buf.read(),
            content_type='application/zip',
            headers={'Content-Disposition': f'attachment; filename="{dataset.name}_{fmt}.zip"'},
        )
