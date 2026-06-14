from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0003_project_cvat_project_id'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='project',
            name='cvat_project_id',
        ),
    ]
