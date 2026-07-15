from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('datasets', '0011_media_thumbnail'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='dataset',
            name='verification_status',
            field=models.CharField(
                choices=[('unverified', 'Unverified'), ('verified', 'Verified for training')],
                default='unverified',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='dataset',
            name='verified_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='dataset',
            name='verified_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='verified_datasets',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
