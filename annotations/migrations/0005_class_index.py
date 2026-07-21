from django.db import migrations, models


def populate_class_indexes(apps, schema_editor):
    annotation_class = apps.get_model('annotations', 'Class')
    project_ids = (
        annotation_class.objects
        .order_by()
        .values_list('project_id', flat=True)
        .distinct()
    )
    for project_id in project_ids.iterator():
        classes = list(annotation_class.objects.filter(project_id=project_id).order_by('id'))
        for index, item in enumerate(classes):
            item.index = index
        annotation_class.objects.bulk_update(classes, ['index'])


class Migration(migrations.Migration):
    dependencies = [
        ('annotations', '0004_alter_class_color'),
    ]

    operations = [
        migrations.AddField(
            model_name='class',
            name='index',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.RunPython(populate_class_indexes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='class',
            name='index',
            field=models.PositiveIntegerField(blank=True),
        ),
        migrations.AddConstraint(
            model_name='class',
            constraint=models.UniqueConstraint(
                fields=('project', 'index'),
                name='unique_class_index_per_project',
            ),
        ),
        migrations.AlterModelOptions(
            name='class',
            options={'ordering': ['index', 'id'], 'verbose_name_plural': 'Classes'},
        ),
    ]
