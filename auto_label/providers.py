PROVIDERS = [
    {
        'id': 'yolo_world',
        'display_name': 'YOLO World',
        'description': 'Open-vocabulary object detection from text prompts.',
        'capabilities': ['bbox'],
        'models': ['yolov8s-worldv2', 'yolov8m-worldv2', 'yolov8l-worldv2'],
        'parameters': {
            'prompts': {'type': 'string[]', 'required': True},
            'confidence': {'type': 'number', 'min': 0, 'max': 1, 'default': 0.45},
        },
    },
    {
        'id': 'sam3',
        'display_name': 'SAM 3',
        'description': 'Text-prompted semantic segmentation with editable polygon contours.',
        'capabilities': ['polygon'],
        'models': ['facebook/sam3'],
        'parameters': {
            'prompts': {'type': 'string[]', 'required': True, 'min_items': 1, 'max_items': 20},
            'confidence': {'type': 'number', 'min': 0, 'max': 1, 'default': 0.35},
        },
    },
]


def provider_by_id(provider_id):
    return next((provider for provider in PROVIDERS if provider['id'] == provider_id), None)
