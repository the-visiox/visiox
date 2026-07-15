from django.db import migrations


ARCHITECTURES = [
    ('YOLOv8 Detection', 'yolov8', 'yolov8n.pt'),
    ('YOLOv9 Detection', 'yolov9', 'yolov9t.pt'),
    ('YOLOv10 Detection', 'yolov10', 'yolov10n.pt'),
    ('YOLOv11 Detection', 'yolov11', 'yolo11n.pt'),
    ('YOLO26 Detection', 'yolo26', 'yolo26n.pt'),
]


def seed_architectures(apps, schema_editor):
    ModelArchitecture = apps.get_model('training', 'ModelArchitecture')
    for name, key, checkpoint in ARCHITECTURES:
        ModelArchitecture.objects.update_or_create(
            name=name,
            defaults={
                'backbone': key,
                'task_type': 'object_detection',
                'description': f'Ultralytics {name}; GPU agent checkpoint: {checkpoint}.',
                'default_config': {
                    'architecture': key,
                    'checkpoint': checkpoint,
                    'epochs': 100,
                    'batch': 16,
                    'imgsz': 640,
                    'lr': 0.001,
                },
                'is_builtin': True,
            },
        )


def remove_architectures(apps, schema_editor):
    ModelArchitecture = apps.get_model('training', 'ModelArchitecture')
    ModelArchitecture.objects.filter(
        name__in=[item[0] for item in ARCHITECTURES],
        is_builtin=True,
    ).delete()


class Migration(migrations.Migration):
    dependencies = [('training', '0003_training_agent_fields')]

    operations = [migrations.RunPython(seed_architectures, remove_architectures)]
