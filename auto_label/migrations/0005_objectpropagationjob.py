import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('annotations', '0005_class_index'),
        ('auto_label', '0004_alter_autolabeldatasetjob_confidence'),
        ('datasets', '0014_datasetimportjob'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ObjectPropagationJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source_frame', models.PositiveIntegerField()),
                ('seed_bbox', models.JSONField()),
                ('similarity_threshold', models.FloatField(default=0.7)),
                ('max_frames', models.PositiveIntegerField(blank=True, null=True)),
                ('track_id', models.UUIDField(default=uuid.uuid4, editable=False)),
                ('status', models.CharField(choices=[('queued', 'Queued'), ('running', 'Running'), ('done', 'Done'), ('error', 'Error')], default='queued', max_length=20)),
                ('total', models.PositiveIntegerField(default=0)),
                ('done', models.PositiveIntegerField(default=0)),
                ('matched_frames', models.PositiveIntegerField(default=0)),
                ('saved_annotations', models.PositiveIntegerField(default=0)),
                ('error', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('class_label', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='propagation_jobs', to='annotations.class')),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('dataset', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='propagation_jobs', to='datasets.dataset')),
                ('source_media', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='source_propagation_jobs', to='datasets.media')),
            ],
            options={
                'db_table': 'object_propagation_jobs',
                'ordering': ['-created_at'],
            },
        ),
    ]
