from django.db.models import Count, Exists, F, OuterRef, Q
from rest_framework import serializers

from annotations.models import Class as AnnotationClass
from datasets.models import AugmentationJob, Dataset


RAW_IMAGE_FILTER = Q(media_files__type='image') & (
    Q(media_files__metadata__category__isnull=True)
    | ~Q(media_files__metadata__category='augmented')
)


def normalize_dataset_ids(value):
    if not isinstance(value, list):
        raise serializers.ValidationError('Must be a list of dataset ids.')
    if any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in value):
        raise serializers.ValidationError('Every dataset id must be a positive integer.')
    return list(dict.fromkeys(value))


def _training_dataset_queryset(dataset_ids):
    completed_generation = AugmentationJob.objects.filter(
        dataset_id=OuterRef('pk'),
        status='done',
    ).filter(
        updated_at__gte=OuterRef('verified_at'),
    ).filter(
        updated_at__gte=OuterRef('split_updated_at'),
    )
    project_classes = AnnotationClass.objects.filter(project_id=OuterRef('project_id'))
    return Dataset.objects.filter(id__in=dataset_ids).select_related('project').annotate(
        training_raw_image_count=Count(
            'media_files',
            filter=RAW_IMAGE_FILTER,
            distinct=True,
        ),
        training_labeled_image_count=Count(
            'media_files',
            filter=RAW_IMAGE_FILTER & Q(media_files__annotations__is_valid=True),
            distinct=True,
        ),
        training_stale_image_count=Count(
            'media_files',
            filter=RAW_IMAGE_FILTER & (
                Q(media_files__uploaded_at__gt=F('verified_at'))
                | Q(media_files__annotations__updated_at__gt=F('verified_at'))
            ),
            distinct=True,
        ),
        has_completed_generation=Exists(completed_generation),
        has_annotation_classes=Exists(project_classes),
    )


def validate_training_datasets(project, dataset_ids):
    datasets = list(_training_dataset_queryset(dataset_ids))
    datasets_by_id = {dataset.id: dataset for dataset in datasets}
    if len(datasets_by_id) != len(dataset_ids):
        raise serializers.ValidationError({
            'dataset_ids': 'One or more selected datasets do not exist.'
        })
    selected = [datasets_by_id[dataset_id] for dataset_id in dataset_ids]

    if project and any(dataset.project_id != project.id for dataset in selected):
        raise serializers.ValidationError({
            'dataset_ids': 'Every dataset must belong to the selected project.'
        })
    if project and selected and not selected[0].has_annotation_classes:
        raise serializers.ValidationError({'dataset': 'Add at least 1 annotation class before training.'})

    for dataset in selected:
        if dataset.training_raw_image_count < 2:
            raise serializers.ValidationError({
                'dataset_ids': f'{dataset.name} needs at least 2 images for train/validation splits.'
            })
        if dataset.training_labeled_image_count == 0:
            raise serializers.ValidationError({
                'dataset_ids': f'{dataset.name} needs at least 1 labeled image; remaining images may be background.'
            })
        if dataset.verification_status != 'verified' or not dataset.verified_at:
            raise serializers.ValidationError({
                'dataset_ids': f'Verify {dataset.name} for training first.'
            })
        if dataset.training_stale_image_count:
            raise serializers.ValidationError({
                'dataset_ids': f'{dataset.name} changed after verification. Review and verify it again.'
            })
        if not dataset.split_config or not dataset.split_updated_at:
            raise serializers.ValidationError({
                'dataset_ids': f'Configure train, validation, and test splits for {dataset.name}.'
            })
        imported = (dataset.split_config or {}).get('source') in {'imported_yolo26', 'imported_coco'}
        if not imported and not dataset.has_completed_generation:
            raise serializers.ValidationError({
                'dataset_ids': f'Generate {dataset.name} successfully before training.'
            })
    return selected
