from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('auto_label', '0005_objectpropagationjob'),
    ]

    operations = [
        migrations.AlterField(
            model_name='autolabeldatasetjob',
            name='model',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='dataset_jobs',
                to='auto_label.autolabelmodel',
            ),
        ),
        migrations.AddField(
            model_name='autolabeldatasetjob',
            name='source',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
