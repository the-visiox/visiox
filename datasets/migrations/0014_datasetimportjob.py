from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('datasets', '0013_dataset_split_config'),
    ]

    operations = [
        migrations.CreateModel(
            name='DatasetImportJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('format', models.CharField(choices=[('images', 'Images'), ('yolo26', 'YOLO26'), ('coco', 'COCO')], max_length=20)),
                ('status', models.CharField(choices=[('queued', 'Queued'), ('running', 'Running'), ('done', 'Done'), ('error', 'Error')], default='queued', max_length=20)),
                ('staged_files', models.JSONField(blank=True, default=list)),
                ('total', models.PositiveIntegerField(default=0)),
                ('done', models.PositiveIntegerField(default=0)),
                ('summary', models.JSONField(blank=True, default=dict)),
                ('error', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='dataset_import_jobs', to=settings.AUTH_USER_MODEL)),
                ('dataset', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='import_jobs', to='datasets.dataset')),
            ],
            options={
                'db_table': 'dataset_import_jobs',
                'ordering': ['-created_at'],
            },
        ),
    ]
