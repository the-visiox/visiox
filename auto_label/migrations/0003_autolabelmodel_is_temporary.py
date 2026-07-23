from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('auto_label', '0002_autolabeldatasetjob'),
    ]

    operations = [
        migrations.AddField(
            model_name='autolabelmodel',
            name='is_temporary',
            field=models.BooleanField(default=False),
        ),
    ]
