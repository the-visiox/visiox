from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('datasets', '0007_media_upload_path_minio'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='dataset',
            name='cvat_task_id',
        ),
    ]
