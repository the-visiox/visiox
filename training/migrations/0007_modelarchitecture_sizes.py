from django.db import migrations, models


SIZES = (
    ('n', 'Nano'),
    ('s', 'Small'),
    ('m', 'Medium'),
    ('l', 'Large'),
    ('x', 'Extra Large'),
)

FAMILIES = (
    ('yolov11', 'YOLO11'),
    ('yolo26', 'YOLO26'),
)

REPLACED_NAMES = (
    'YOLOv8 Detection',
    'YOLOv9 Detection',
    'YOLOv11 Detection',
    'YOLO26 Detection',
)


def seed_sized_architectures(apps, schema_editor):
    ModelArchitecture = apps.get_model('training', 'ModelArchitecture')
    ModelArchitecture.objects.filter(name__in=REPLACED_NAMES).update(is_active=False)
    ModelArchitecture.objects.filter(backbone__startswith='yolov8').update(is_active=False)
    ModelArchitecture.objects.filter(backbone__startswith='yolov9').update(is_active=False)

    for family, display_name in FAMILIES:
        checkpoint_prefix = 'yolo11' if family == 'yolov11' else 'yolo26'
        for size, size_name in SIZES:
            checkpoint = f'{checkpoint_prefix}{size}.pt'
            ModelArchitecture.objects.update_or_create(
                name=f'{display_name} Detection - {size_name}',
                defaults={
                    'backbone': family,
                    'task_type': 'object_detection',
                    'description': f'Ultralytics {display_name} {size_name}; checkpoint: {checkpoint}.',
                    'default_config': {
                        'architecture': family,
                        'size': size,
                        'checkpoint': checkpoint,
                        'epochs': 100,
                        'batch': 16,
                        'imgsz': 640,
                        'lr': 0.001,
                    },
                    'is_builtin': True,
                    'is_active': True,
                },
            )


def restore_previous_architectures(apps, schema_editor):
    ModelArchitecture = apps.get_model('training', 'ModelArchitecture')
    sized_names = [
        f'{display_name} Detection - {size_name}'
        for _family, display_name in FAMILIES
        for _size, size_name in SIZES
    ]
    ModelArchitecture.objects.filter(name__in=sized_names).update(is_active=False)
    ModelArchitecture.objects.filter(name__in=REPLACED_NAMES).update(is_active=True)
    ModelArchitecture.objects.filter(backbone__startswith='yolov8').update(is_active=True)
    ModelArchitecture.objects.filter(backbone__startswith='yolov9').update(is_active=True)


class Migration(migrations.Migration):
    dependencies = [('training', '0006_trainingjob_fine_tuning')]

    operations = [
        migrations.AddField(
            model_name='modelarchitecture',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(seed_sized_architectures, restore_previous_architectures),
    ]
