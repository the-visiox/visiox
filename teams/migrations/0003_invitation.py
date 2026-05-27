import uuid
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('teams', '0002_alter_teammember_options'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Invitation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.EmailField(max_length=254)),
                ('role', models.CharField(
                    choices=[('admin', 'Admin'), ('member', 'Member'), ('viewer', 'Viewer')],
                    default='member',
                    max_length=50,
                )),
                ('token', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending'),
                        ('accepted', 'Accepted'),
                        ('expired', 'Expired'),
                        ('cancelled', 'Cancelled'),
                    ],
                    default='pending',
                    max_length=20,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField()),
                ('team', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='invitations',
                    to='teams.team',
                )),
                ('invited_by', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='sent_invitations',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'team_invitations',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='invitation',
            constraint=models.UniqueConstraint(
                condition=models.Q(status='pending'),
                fields=['team', 'email'],
                name='unique_pending_invitation',
            ),
        ),
    ]
