from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('datasets', '0012_dataset_training_verification')]

    operations = [
        migrations.AddField(
            model_name='dataset',
            name='split_config',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='dataset',
            name='split_updated_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
