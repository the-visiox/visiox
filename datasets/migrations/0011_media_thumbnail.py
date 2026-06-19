import datasets.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('datasets', '0010_augmentationjob'),
    ]

    operations = [
        migrations.AddField(
            model_name='media',
            name='thumbnail',
            field=models.FileField(blank=True, max_length=500, null=True, upload_to=datasets.models.media_thumb_path),
        ),
    ]
