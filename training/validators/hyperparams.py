import re

from rest_framework import serializers


HYPERPARAM_RULES = {
    'epochs': {
        'type': int,
        'minimum': 1,
        'maximum': 10000,
    },
    'batch': {
        'type': int,
        'minimum': 1,
        'maximum': 1024,
    },
    'seed': {
        'type': int,
        'minimum': 0,
        'maximum': 2**32 - 1,
    },
}

SPECIAL_HYPERPARAMS = {'device', 'imgsz', 'lr', 'lr0'}
DEVICE_PATTERN = re.compile(r'^\d+(,\d+)*$')


def _validate_bounded_integer(name, value, rule):
    if isinstance(value, bool) or not isinstance(value, rule['type']):
        raise serializers.ValidationError({name: 'Must be an integer.'})
    if not rule['minimum'] <= value <= rule['maximum']:
        raise serializers.ValidationError({
            name: f'Must be between {rule["minimum"]} and {rule["maximum"]}.'
        })


def _validate_device(value):
    if isinstance(value, bool):
        raise serializers.ValidationError({'device': 'Must be a GPU index, GPU index list, cpu, or mps.'})
    if isinstance(value, int):
        if 0 <= value <= 128:
            return
    elif isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {'cpu', 'mps'}:
            return
        if DEVICE_PATTERN.fullmatch(normalized):
            indices = [int(index) for index in normalized.split(',')]
            if all(index <= 128 for index in indices):
                return
    raise serializers.ValidationError({'device': 'Must be a GPU index, GPU index list, cpu, or mps.'})


def _validate_image_size(value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise serializers.ValidationError({'imgsz': 'Must be an integer number of pixels.'})
    if not 32 <= value <= 4096:
        raise serializers.ValidationError({'imgsz': 'Must be between 32 and 4096 pixels.'})


def _validate_learning_rate(name, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise serializers.ValidationError({name: 'Must be a number.'})
    if not 0 < value <= 1:
        raise serializers.ValidationError({name: 'Must be greater than 0 and at most 1.'})


def validate_hyperparams(value):
    if not isinstance(value, dict):
        raise serializers.ValidationError('Must be an object of hyperparameter names and values.')
    supported = set(HYPERPARAM_RULES) | SPECIAL_HYPERPARAMS
    unknown = set(value) - supported
    if unknown:
        raise serializers.ValidationError(
            f'Unsupported parameters: {", ".join(sorted(unknown))}'
        )

    for name, item in value.items():
        if name in HYPERPARAM_RULES:
            _validate_bounded_integer(name, item, HYPERPARAM_RULES[name])
        elif name == 'device':
            _validate_device(item)
        elif name == 'imgsz':
            _validate_image_size(item)
        else:
            _validate_learning_rate(name, item)
    return value
