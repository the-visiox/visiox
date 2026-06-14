from django.db import migrations, models
import datasets.models


class Migration(migrations.Migration):

    dependencies = [
        ('datasets', '0008_remove_dataset_cvat_task_id'),
    ]

    operations = [
        migrations.AlterField(
            model_name='media',
            name='file',
            field=models.FileField(max_length=500, upload_to=datasets.models.media_upload_path),
        ),
    ]
