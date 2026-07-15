import random
from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from datasets.standalone import is_augmented


SPLITS = ('train', 'val', 'test')


def _raw_images(dataset):
    media = dataset.media_files.filter(type='image').exclude(file='').prefetch_related('annotations').order_by('id')
    return [item for item in media if not is_augmented(item)]


def _group_key(media):
    metadata = media.metadata or {}
    for key in ('capture_group', 'sequence_id', 'video_id', 'burst_id', 'camera_session_id'):
        if metadata.get(key) not in (None, ''):
            return f'{key}:{metadata[key]}'
    return f'media:{media.id}'


def _signature(media):
    classes = sorted(set(media.annotations.filter(is_valid=True).values_list('class_label_id', flat=True)))
    return tuple(classes) if classes else ('background',)


def configure_dataset_split(dataset, ratios, seed=42, strategy='class', test_dataset=None):
    """Split capture groups randomly or with class/background stratification."""
    raw = _raw_images(dataset)
    active_splits = tuple(name for name in SPLITS if ratios[name] > 0)
    if 'train' not in active_splits or 'val' not in active_splits:
        raise ValueError('Train and validation ratios must be greater than zero.')
    if len(raw) < len(active_splits):
        raise ValueError(f'Dataset needs at least {len(active_splits)} raw images for the selected split.')

    groups = defaultdict(list)
    for media in raw:
        groups[_group_key(media)].append(media)

    buckets = defaultdict(list)
    for key, members in groups.items():
        signature = tuple(sorted(set(value for media in members for value in _signature(media)), key=str))
        buckets[signature if strategy == 'class' else ('all',)].append((key, members))

    rng = random.Random(seed)
    assigned = {name: [] for name in SPLITS}
    totals = {name: 0 for name in SPLITS}
    targets = {name: len(raw) * ratios[name] / 100 for name in SPLITS}

    for bucket in buckets.values():
        rng.shuffle(bucket)
        bucket.sort(key=lambda item: len(item[1]), reverse=True)
        local = {name: 0 for name in SPLITS}
        bucket_size = sum(len(item[1]) for item in bucket)
        for _, members in bucket:
            split = max(
                active_splits,
                key=lambda name: (
                    ratios[name] / 100 * bucket_size - local[name],
                    targets[name] - totals[name],
                ),
            )
            assigned[split].extend(members)
            totals[split] += len(members)
            local[split] += len(members)

    for empty in (name for name in active_splits if not assigned[name]):
        donor = max(active_splits, key=lambda name: len(assigned[name]))
        donor_groups = defaultdict(list)
        for media in assigned[donor]:
            donor_groups[_group_key(media)].append(media)
        movable = min(donor_groups.values(), key=len)
        for media in movable:
            assigned[donor].remove(media)
            assigned[empty].append(media)

    external_test = _raw_images(test_dataset) if test_dataset else []
    raw_split = {media.id: name for name, members in assigned.items() for media in members}
    augmented = [media for media in dataset.media_files.filter(type='image') if is_augmented(media)]
    excluded_augmented = 0

    with transaction.atomic():
        for media in raw:
            metadata = dict(media.metadata or {})
            metadata['split'] = raw_split[media.id]
            media.metadata = metadata
            media.save(update_fields=['metadata'])
        for media in augmented:
            metadata = dict(media.metadata or {})
            if raw_split.get(metadata.get('source_media_id')) == 'train':
                metadata['split'] = 'train'
            else:
                metadata.pop('split', None)
                excluded_augmented += 1
            media.metadata = metadata
            media.save(update_fields=['metadata'])

        summary = {
            name: {
                'raw': len(external_test) if name == 'test' and test_dataset else len(assigned[name]),
                'augmented': sum(1 for media in augmented if (media.metadata or {}).get('split') == name),
            }
            for name in SPLITS
        }
        summary['excluded_augmented'] = excluded_augmented
        class_names = dict(dataset.project.classes.values_list('id', 'name'))
        class_rows = defaultdict(lambda: {name: 0 for name in SPLITS})
        display_members = {**assigned, 'test': external_test if test_dataset else assigned['test']}
        for split, members in display_members.items():
            for media in members:
                class_ids = set(media.annotations.filter(is_valid=True).values_list('class_label_id', flat=True))
                if not class_ids:
                    class_rows['Background'][split] += 1
                for class_id in class_ids:
                    class_rows[class_names.get(class_id, f'Class {class_id}')][split] += 1
        summary['classes'] = [
            {'name': name, **counts}
            for name, counts in sorted(class_rows.items(), key=lambda item: item[0].lower())
        ]
        dataset.split_config = {
            **ratios,
            'seed': seed,
            'strategy': strategy,
            'test_dataset_id': test_dataset.id if test_dataset else None,
            'test_dataset_name': test_dataset.name if test_dataset else None,
            'summary': summary,
        }
        dataset.split_updated_at = timezone.now()
        dataset.save(update_fields=['split_config', 'split_updated_at', 'updated_at'])
    return summary
