from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0005_alter_project_team'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='is_public',
            field=models.BooleanField(default=False),
        ),
    ]
