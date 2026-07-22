from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('deployments', '0003_artifact_upload_path'),
        ('training', '0005_trainingjob_dataset_ids'),
    ]

    operations = [
        migrations.AddField(
            model_name='trainingjob',
            name='base_model',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='fine_tuning_jobs',
                to='deployments.modelregistry',
            ),
        ),
        migrations.AddField(
            model_name='trainingjob',
            name='class_schema',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='trainingjob',
            name='initialization_mode',
            field=models.CharField(
                choices=[
                    ('architecture', 'Architecture checkpoint'),
                    ('fine_tune', 'Fine-tune from registered model'),
                ],
                default='architecture',
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name='trainingjob',
            name='parent_job',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='child_jobs',
                to='training.trainingjob',
            ),
        ),
    ]
