# Run with: python manage.py shell < scripts/check_auth.py
from django.contrib.auth import authenticate
from core.models import UserModel
user = UserModel.objects.filter(username='admin@visiox.ai').first()
if user:
    print(f"User exists: {user.username}")
    print(f"Email: {user.email}")
    is_authed = authenticate(username='admin@visiox.ai', password='admin123')
    print(f"Authed with 'admin@visiox.ai': {is_authed}")
else:
    print("User 'admin@visiox.ai' does not exist")
