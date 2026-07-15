from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('training', '0002_alter_trainingjob_options')]

    operations = [
        migrations.AddField(model_name='trainingjob', name='agent_job_id', field=models.CharField(blank=True, max_length=255)),
        migrations.AddField(model_name='trainingjob', name='artifacts', field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name='trainingjob', name='last_heartbeat_at', field=models.DateTimeField(blank=True, null=True)),
    ]
