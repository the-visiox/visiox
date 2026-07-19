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
    'auto_label',
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
        # Persistent connections: reuse across requests instead of opening a new
        # one each time. With many web replicas, put PgBouncer in front and keep
        # this modest. 0 = close after each request (default).
        'CONN_MAX_AGE': int(os.getenv('DATABASE_CONN_MAX_AGE', '60')),
        'CONN_HEALTH_CHECKS': True,
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

# Dataset imports accept up to 500 files in one multipart request. Django's
# default limit is 100, which rejects larger imports before DRF can validate
# them and only returns a generic "Bad Request" response.
DATA_UPLOAD_MAX_NUMBER_FILES = int(os.getenv('DATA_UPLOAD_MAX_NUMBER_FILES', '600'))

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'core.UserModel'

# ── Email ──────────────────────────────────────────────────────────────────────
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True') == 'True'
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'VisioX <noreply@visiox.ai>')
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000')

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
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '60/min',
        'user': '300/min',
        'login': '5/min',
        'register': '3/min',
        'token_refresh': '10/min',
    },
    'EXCEPTION_HANDLER': 'rest_framework.views.exception_handler',
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
    'APPEND_COMPONENTS': {
        'securitySchemes': {
            'BearerAuth': {
                'type': 'http',
                'scheme': 'bearer',
                'bearerFormat': 'JWT',
                'description': 'Paste the access_token from POST /api/v1/auth/login/',
            },
        }
    },
    'SECURITY': [{'BearerAuth': []}],
}

# Celery
# When True, long jobs (augmentation) are dispatched to Celery workers; otherwise
# they run in a background thread (fine for the dev server). Turn on in production.
USE_CELERY = os.getenv('USE_CELERY', 'False') == 'True'
# Keep Auto Label runnable from the API host until the dedicated datasets
# worker has been deployed with the auto_label task. Enable explicitly after
# that worker is updated.
AUTO_LABEL_USE_CELERY = os.getenv('AUTO_LABEL_USE_CELERY', 'False') == 'True'
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# Dataset imports use a small thread pool only for storage I/O. ORM writes stay
# on the Celery task thread. Keep this bounded to avoid overwhelming MinIO.
DATASET_IMPORT_STORAGE_WORKERS = int(os.getenv('DATASET_IMPORT_STORAGE_WORKERS', '4'))
DATASET_IMPORT_BATCH_SIZE = int(os.getenv('DATASET_IMPORT_BATCH_SIZE', '16'))

# GPU training agent. The callback URL must be reachable from the GPU host
# (use the API container/LAN address, never localhost in production).
TRAINING_AGENT_URL = os.getenv('TRAINING_AGENT_URL', 'http://localhost:8002').rstrip('/')
TRAINING_AGENT_TOKEN = os.getenv('TRAINING_AGENT_TOKEN', '')
TRAINING_CALLBACK_TOKEN = os.getenv('TRAINING_CALLBACK_TOKEN', '')
TRAINING_CALLBACK_BASE_URL = os.getenv(
    'TRAINING_CALLBACK_BASE_URL', 'http://localhost:8000'
).rstrip('/')
TRAINING_AGENT_TIMEOUT = int(os.getenv('TRAINING_AGENT_TIMEOUT', '15'))
TRAINING_LABEL_DELIVERY = os.getenv(
    'TRAINING_LABEL_DELIVERY',
    os.getenv('TRAINING_LABEL_SOURCE', 'minio'),
).lower()
TRAINING_LABEL_SOURCE = TRAINING_LABEL_DELIVERY
TRAINING_AGENT_MINIO_ENDPOINT = os.getenv('TRAINING_AGENT_MINIO_ENDPOINT', '').rstrip('/')
INFERENCE_API_URL = os.getenv('INFERENCE_API_URL', '').rstrip('/')
INFERENCE_AGENT_TOKEN = os.getenv('INFERENCE_AGENT_TOKEN') or TRAINING_AGENT_TOKEN

# Storage — local by default, switch to MinIO via env
USE_MINIO = os.getenv('USE_MINIO', 'False') == 'True'

if USE_MINIO:
    AWS_ACCESS_KEY_ID = os.getenv('MINIO_ACCESS_KEY')
    AWS_SECRET_ACCESS_KEY = os.getenv('MINIO_SECRET_KEY')
    AWS_STORAGE_BUCKET_NAME = os.getenv('MINIO_BUCKET', 'visiox-media')
    AWS_S3_REGION_NAME = 'us-east-1'
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None
    AWS_S3_ENDPOINT_URL = os.getenv('MINIO_ENDPOINT', 'http://10.29.30.20:9000')
    AWS_S3_ADDRESSING_STYLE = 'path'
    AWS_S3_SIGNATURE_VERSION = 's3v4'
    AWS_QUERYSTRING_AUTH = True  # presigned URL cho private bucket
    STORAGES = {
        'default': {
            'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage',
        },
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    }

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

# OAuth login. Frontend redirects to /auth/callback and posts provider code here.
GOOGLE_OAUTH_CLIENT_ID = os.getenv('GOOGLE_OAUTH_CLIENT_ID', '')
GOOGLE_OAUTH_CLIENT_SECRET = os.getenv('GOOGLE_OAUTH_CLIENT_SECRET', '')
GITHUB_OAUTH_CLIENT_ID = os.getenv('GITHUB_OAUTH_CLIENT_ID', '')
GITHUB_OAUTH_CLIENT_SECRET = os.getenv('GITHUB_OAUTH_CLIENT_SECRET', '')

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
