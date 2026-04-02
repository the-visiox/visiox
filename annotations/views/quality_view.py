from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from annotations.services.quality import media_agreement
from datasets.models import Dataset, Media


class MediaQualityView(APIView):
    @extend_schema(
        parameters=[OpenApiParameter('media_id', int, OpenApiParameter.PATH)],
        responses={200: dict},
    )
    def get(self, request, media_id):
        try:
            media = Media.objects.select_related('dataset__project').get(
                pk=media_id,
                dataset__project__team__members__user=request.user,
            )
        except Media.DoesNotExist:
            return Response({'error': 'Media not found.'}, status=status.HTTP_404_NOT_FOUND)

        result = media_agreement(media.id)
        return Response(result)


class DatasetQualityView(APIView):
    @extend_schema(
        parameters=[OpenApiParameter('dataset_id', int, OpenApiParameter.PATH)],
        responses={200: dict},
    )
    def get(self, request, dataset_id):
        try:
            dataset = Dataset.objects.select_related('project').get(
                pk=dataset_id,
                project__team__members__user=request.user,
            )
        except Dataset.DoesNotExist:
            return Response({'error': 'Dataset not found.'}, status=status.HTTP_404_NOT_FOUND)

        media_ids = list(dataset.media_files.values_list('id', flat=True))
        results = [media_agreement(mid) for mid in media_ids]

        scored = [r for r in results if r.get('cohens_kappa') is not None]
        avg_iou = (
            sum(r['mean_iou'] for r in results if r.get('mean_iou')) / len(results)
            if results else 0.0
        )
        avg_kappa = (
            sum(r['cohens_kappa'] for r in scored) / len(scored)
            if scored else None
        )

        return Response({
            'dataset_id': dataset_id,
            'media_count': len(media_ids),
            'average_iou': round(avg_iou, 4),
            'average_cohens_kappa': round(avg_kappa, 4) if avg_kappa is not None else None,
            'per_media': results,
        })
