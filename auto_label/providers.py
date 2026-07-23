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
]


def provider_by_id(provider_id):
    return next((provider for provider in PROVIDERS if provider['id'] == provider_id), None)
