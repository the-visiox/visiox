from django.contrib.auth import get_user_model
User = get_user_model()
try:
    u = User.objects.get(username='admin')
except User.DoesNotExist:
    u = User.objects.create_superuser('admin', 'admin@local.com', 'master123')
u.set_password('master123')
u.save()
print("PASSWORD SET CORRECTLY")
