from django.db import migrations, models


def copy_primary_dataset(apps, schema_editor):
    TrainingJob = apps.get_model('training', 'TrainingJob')
    for job in TrainingJob.objects.exclude(dataset_id=None).iterator():
        job.dataset_ids = [job.dataset_id]
        job.save(update_fields=['dataset_ids'])


class Migration(migrations.Migration):
    dependencies = [
        ('training', '0004_seed_yolo_architectures'),
    ]

    operations = [
        migrations.AddField(
            model_name='trainingjob',
            name='dataset_ids',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.RunPython(copy_primary_dataset, migrations.RunPython.noop),
    ]
