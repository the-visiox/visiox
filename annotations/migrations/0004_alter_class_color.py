from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('annotations', '0003_annotation_frame_track_jobissue'),
    ]

    operations = [
        migrations.AlterField(
            model_name='class',
            name='color',
            field=models.CharField(default='#E66700', max_length=7),
        ),
    ]
