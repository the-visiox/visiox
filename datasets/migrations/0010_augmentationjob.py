import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('datasets', '0009_media_file_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='AugmentationJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('running', 'Running'), ('done', 'Done'), ('error', 'Error')], default='running', max_length=20)),
                ('total', models.PositiveIntegerField(default=0)),
                ('done', models.PositiveIntegerField(default=0)),
                ('generated', models.PositiveIntegerField(default=0)),
                ('error', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('dataset', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='augmentation_jobs', to='datasets.dataset')),
            ],
            options={
                'db_table': 'augmentation_jobs',
                'ordering': ['-created_at'],
            },
        ),
    ]
