from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('auto_label', '0003_autolabelmodel_is_temporary'),
    ]

    operations = [
        migrations.AlterField(
            model_name='autolabeldatasetjob',
            name='confidence',
            field=models.FloatField(default=0.45),
        ),
    ]
