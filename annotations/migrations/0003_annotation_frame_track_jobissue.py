# Generated manually for VisioX annotation platform (CVAT-style jobs API)

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('annotations', '0002_alter_annotation_options'),
    ]

    operations = [
        migrations.CreateModel(
            name='JobIssue',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('body', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('author', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='job_issues', to=settings.AUTH_USER_MODEL)),
                ('task', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='issues', to='annotations.labelingtask')),
            ],
            options={
                'db_table': 'job_issues',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddField(
            model_name='annotation',
            name='frame',
            field=models.PositiveIntegerField(default=0, help_text='Frame index for video; 0 for single images.'),
        ),
        migrations.AddField(
            model_name='annotation',
            name='track_id',
            field=models.UUIDField(blank=True, help_text='Optional stable id for video object tracks across frames.', null=True),
        ),
        migrations.AlterField(
            model_name='annotation',
            name='type',
            field=models.CharField(
                choices=[
                    ('bbox', 'Bounding Box'),
                    ('rectangle', 'Rectangle'),
                    ('polygon', 'Polygon'),
                    ('polyline', 'Polyline'),
                    ('point', 'Point'),
                    ('keypoint', 'Keypoint'),
                    ('mask', 'Mask'),
                    ('cuboid', 'Cuboid'),
                    ('tag', 'Tag'),
                ],
                max_length=50,
            ),
        ),
    ]
