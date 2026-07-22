from rest_framework import serializers
from django.db.models import Q

from datasets.models import Dataset, Media


class MediaSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = Media
        fields = [
            'id',
            'dataset',
            'type',
            'file',
            'file_url',
            'original_filename',
            'width',
            'height',
            'file_size',
            'metadata',
            'uploaded_at',
        ]
        read_only_fields = [
            'id',
            'file_url',
            'original_filename',
            'width',
            'height',
            'file_size',
            'uploaded_at',
        ]

    def get_file_url(self, obj):
        request = self.context.get('request')
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return None


class MediaUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    type = serializers.ChoiceField(choices=['image', 'video'])
    metadata = serializers.JSONField(required=False, default=dict)


class MediaBulkDeleteSerializer(serializers.Serializer):
    media_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
        max_length=500,
    )


class DatasetSerializer(serializers.ModelSerializer):
    media_count = serializers.SerializerMethodField()
    image_count = serializers.SerializerMethodField()
    annotated_count = serializers.SerializerMethodField()
    unlabeled_count = serializers.SerializerMethodField()
    labeling_progress = serializers.SerializerMethodField()
    approved_count = serializers.SerializerMethodField()
    review_progress = serializers.SerializerMethodField()
    is_label_complete = serializers.SerializerMethodField()
    verification_is_current = serializers.SerializerMethodField()
    verified_by_username = serializers.CharField(source='verified_by.username', read_only=True)
    generation_is_complete = serializers.SerializerMethodField()
    is_train_ready = serializers.SerializerMethodField()
    thumbnail = serializers.SerializerMethodField()
    latest_import_job = serializers.SerializerMethodField()

    class Meta:
        model = Dataset
        fields = [
            'id',
            'project',
            'name',
            'description',
            'version',
            'media_count',
            'image_count',
            'annotated_count',
            'unlabeled_count',
            'labeling_progress',
            'approved_count',
            'review_progress',
            'is_label_complete',
            'verification_status',
            'verification_is_current',
            'verified_by',
            'verified_by_username',
            'verified_at',
            'generation_is_complete',
            'is_train_ready',
            'split_config',
            'split_updated_at',
            'latest_import_job',
            'thumbnail',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id', 'version', 'verification_status', 'verified_by',
            'verified_at', 'split_config', 'split_updated_at', 'created_at', 'updated_at',
        ]

    def get_media_count(self, obj) -> int:
        return obj.media_files.count()

    def _training_stats(self, obj) -> dict:
        cached = getattr(obj, '_training_readiness_stats', None)
        if cached is None:
            images = obj.media_files.filter(type='image').filter(
                Q(metadata__category__isnull=True) | ~Q(metadata__category='augmented')
            )
            cached = {
                'images': images.count(),
                'annotated': images.filter(
                    annotations__isnull=False,
                    annotations__is_valid=True,
                ).distinct().count(),
                'approved': images.filter(
                    labeling_tasks__status='approved',
                ).distinct().count(),
                'has_classes': obj.project.classes.exists(),
            }
            obj._training_readiness_stats = cached
        return cached

    def get_image_count(self, obj) -> int:
        return self._training_stats(obj)['images']

    def get_annotated_count(self, obj) -> int:
        return self._training_stats(obj)['annotated']

    def get_unlabeled_count(self, obj) -> int:
        return max(0, self.get_image_count(obj) - self.get_annotated_count(obj))

    def get_labeling_progress(self, obj) -> float:
        total = self.get_image_count(obj)
        return round(self.get_annotated_count(obj) * 100 / total, 1) if total else 0

    def get_approved_count(self, obj) -> int:
        return self._training_stats(obj)['approved']

    def get_review_progress(self, obj) -> float:
        total = self.get_image_count(obj)
        return round(self.get_approved_count(obj) * 100 / total, 1) if total else 0

    def get_is_label_complete(self, obj) -> bool:
        total = self.get_image_count(obj)
        return total >= 2 and self.get_annotated_count(obj) == total

    def get_verification_is_current(self, obj) -> bool:
        if obj.verification_status != 'verified' or not obj.verified_at:
            return False
        images = obj.media_files.filter(type='image').filter(
            Q(metadata__category__isnull=True) | ~Q(metadata__category='augmented')
        )
        return not (
            images.filter(uploaded_at__gt=obj.verified_at).exists()
            or images.filter(annotations__updated_at__gt=obj.verified_at).exists()
        )

    def get_is_train_ready(self, obj) -> bool:
        total = self.get_image_count(obj)
        return (
            total >= 2
            and self.get_annotated_count(obj) > 0
            and self.get_verification_is_current(obj)
            and bool(obj.split_config)
            and bool(obj.split_updated_at)
            and obj.generation_is_current
            and self._training_stats(obj)['has_classes']
        )

    def get_generation_is_complete(self, obj) -> bool:
        return obj.generation_is_current

    def get_thumbnail(self, obj) -> str | None:
        first = obj.media_files.filter(type='image').order_by('uploaded_at').first()
        if not first or not first.file:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(first.file.url)
        return first.file.url

    def get_latest_import_job(self, obj) -> dict | None:
        job = next(iter(obj.import_jobs.all()), None)
        if not job:
            return None
        return {
            'id': job.id,
            'format': job.format,
            'status': job.status,
            'total': job.total,
            'done': job.done,
            'summary': job.summary or {},
            'error': job.error,
            'created_at': job.created_at,
            'updated_at': job.updated_at,
        }
