import os
from datetime import timedelta
from pathlib import Path

import dotenv

dotenv.load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-55!^nxpq^_oaw(-$+ey1ahk&l1zdh^jt#h9^g8duk3!ay0evt7')

DEBUG = os.getenv('DEBUG', 'True') == 'True'

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'django_filters',
    'drf_spectacular',
    'core',
    'authentication',
    'teams',
    'projects',
    'datasets',
    'annotations',
    'dataverse',
    'training',
    'deployments',
    'billing',
    'silk',
    'corsheaders',
    'django_celery_beat',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'silk.middleware.SilkyMiddleware',
]

ROOT_URLCONF = 'visiox.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'visiox.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DATABASE_NAME', 'visiox'),
        'USER': os.getenv('DATABASE_USER', 'postgres'),
        'PASSWORD': os.getenv('DATABASE_PASSWORD', 'postgres'),
        'HOST': os.getenv('DATABASE_HOST', 'localhost'),
        'PORT': os.getenv('DATABASE_PORT', '5432'),
        # Avoid hanging startup forever when DB endpoint is unreachable.
        'OPTIONS': {
            'connect_timeout': int(os.getenv('DATABASE_CONNECT_TIMEOUT', '5')),
        },
    },
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Ho_Chi_Minh'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'core.UserModel'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'billing.backends.APIKeyAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Visiox API',
    'DESCRIPTION': 'Computer Vision Platform API — annotation, training, deployment, billing.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

# Celery
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# Storage — local by default, switch to S3 via env
USE_S3 = os.getenv('USE_S3', 'False') == 'True'

if USE_S3:
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = os.getenv('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_REGION_NAME = os.getenv('AWS_S3_REGION_NAME', 'us-east-1')
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None

# Stripe
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY', '')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET', '')

# CORS — include :3001 because Next.js often falls back when :3000 is busy.
CORS_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        'CORS_ALLOWED_ORIGINS',
        'http://localhost:3000,http://127.0.0.1:3000,'
        'http://localhost:3001,http://127.0.0.1:3001',
    ).split(',')
    if o.strip()
]
CORS_ALLOW_CREDENTIALS = True

# CSRF — required for cross-origin browser requests when using SessionMiddleware + cookies;
# also list API origin if frontend posts to a different port (e.g. :3000 → :8080).
CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        'CSRF_TRUSTED_ORIGINS',
        'http://localhost:3000,http://127.0.0.1:3000,'
        'http://localhost:3001,http://127.0.0.1:3001,'
        'http://localhost:8080,http://127.0.0.1:8080',
    ).split(',')
    if o.strip()
]

# CVAT Integration
CVAT_INTERNAL_HOST = os.getenv('CVAT_HOST', 'http://localhost:8080')
CVAT_PUBLIC_URL = os.getenv('CVAT_PUBLIC_URL', 'http://localhost:8080')
CVAT_USERNAME = os.getenv('CVAT_USERNAME', 'admin')
CVAT_PASSWORD = os.getenv('CVAT_PASSWORD', 'master123')
CVAT_WEBHOOK_URL = os.getenv('CVAT_WEBHOOK_URL', 'http://host.docker.internal:8000/api/datasets/cvat-webhook/')

# When true: no CVAT provisioning, browser + frame images use VisioX Media only.
VISIOX_STANDALONE = os.getenv('VISIOX_STANDALONE', 'false').lower() in ('1', 'true', 'yes')

# Django Silk — request/query profiler (only active when DEBUG=True).
# NOTE: keep the Python profiler OFF by default — it hooks sys.setprofile() and
# slows every view/DB call (and collides with other profilers, flooding the
# console with "Another profiling tool is already active" tracebacks).
# Set SILKY_PYTHON_PROFILER=1 in .env only when you actually want to profile.
SILKY_PYTHON_PROFILER = os.getenv('SILKY_PYTHON_PROFILER', 'false').lower() in ('1', 'true', 'yes')
SILKY_PYTHON_PROFILER_BINARY = False
SILKY_MAX_RECORDED_REQUESTS = 1000
SILKY_MAX_RECORDED_REQUESTS_CHECK_PERCENT = 10
SILKY_AUTHENTICATION = True
SILKY_AUTHORISATION = True
