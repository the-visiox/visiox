import json

from django.http import HttpResponse
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from datasets.models import Dataset
from annotations.services.export import export_coco, export_yolo, export_voc
from core.access import project_access_q


class DatasetExportView(APIView):
    @extend_schema(
        parameters=[
            OpenApiParameter('format', str, OpenApiParameter.QUERY, enum=['coco', 'yolo', 'voc'],
                             description='Export format'),
        ],
        responses={200: bytes},
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

        if fmt == 'coco':
            data = export_coco(dataset)
            content = json.dumps(data, indent=2).encode()
            return HttpResponse(
                content,
                content_type='application/json',
                headers={'Content-Disposition': f'attachment; filename="{dataset.name}_coco.json"'},
            )
        elif fmt == 'yolo':
            buf = export_yolo(dataset)
            return HttpResponse(
                buf.read(),
                content_type='application/zip',
                headers={'Content-Disposition': f'attachment; filename="{dataset.name}_yolo.zip"'},
            )
        elif fmt == 'voc':
            buf = export_voc(dataset)
            return HttpResponse(
                buf.read(),
                content_type='application/zip',
                headers={'Content-Disposition': f'attachment; filename="{dataset.name}_voc.zip"'},
            )
        else:
            return Response(
                {'error': f'Unsupported format "{fmt}". Use coco, yolo, or voc.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
