import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('projects', '0003_project_cvat_project_id'),
    ]

    operations = [
        migrations.CreateModel(
            name='DataverseProject',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255)),
                ('summary', models.TextField(blank=True)),
                ('tags', models.JSONField(blank=True, default=list)),
                ('license', models.CharField(default='Community', max_length=100)),
                ('is_public', models.BooleanField(default=True)),
                ('fork_count', models.PositiveIntegerField(default=0)),
                ('view_count', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='dataverse_projects', to=settings.AUTH_USER_MODEL)),
                ('source_project', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='dataverse_listing', to='projects.project')),
            ],
            options={
                'db_table': 'dataverse_projects',
                'ordering': ['-updated_at'],
            },
        ),
    ]

