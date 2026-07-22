from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from annotations.models import Review
from annotations.serializers import ReviewSerializer
from core.access import project_access_q


class ReviewViewSet(viewsets.ModelViewSet):
    serializer_class = ReviewSerializer
    queryset = Review.objects.none()

    def get_queryset(self):
        user = self.request.user
        qs = Review.objects.filter(
            project_access_q(user, 'annotation__media__dataset__project__')
        ).distinct().select_related('reviewer', 'annotation')

        review_status = self.request.query_params.get('status')
        if review_status:
            qs = qs.filter(status=review_status)
        return qs

    @extend_schema(responses={200: ReviewSerializer})
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        review = self.get_object()
        review.status = 'approved'
        review.save()
        return Response(ReviewSerializer(review).data)

    @extend_schema(responses={200: ReviewSerializer})
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        review = self.get_object()
        review.status = 'rejected'
        review.comment = request.data.get('comment', review.comment)
        review.save()
        return Response(ReviewSerializer(review).data)

    @extend_schema(responses={200: ReviewSerializer})
    @action(detail=True, methods=['post'])
    def request_revision(self, request, pk=None):
        review = self.get_object()
        review.status = 'needs_revision'
        review.comment = request.data.get('comment', review.comment)
        review.save()
        return Response(ReviewSerializer(review).data)
