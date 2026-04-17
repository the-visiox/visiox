from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('datasets', '0005_remove_dataset_cvat_project_id'),
    ]

    operations = [
        migrations.CreateModel(
            name='MediaLabelProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('labels', models.JSONField(blank=True, default=list)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'media',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='label_profile',
                        to='datasets.media',
                    ),
                ),
            ],
            options={
                'db_table': 'media_label_profiles',
            },
        ),
    ]
