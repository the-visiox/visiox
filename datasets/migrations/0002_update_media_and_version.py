from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('datasets', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='dataset',
            name='version',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='media',
            name='file',
            field=models.FileField(upload_to='media/%Y/%m/%d/', default=''),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='media',
            name='original_filename',
            field=models.CharField(blank=True, max_length=255, default=''),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='media',
            name='file_size',
            field=models.PositiveBigIntegerField(blank=True, null=True),
        ),
        migrations.RemoveField(
            model_name='media',
            name='file_path',
        ),
    ]
