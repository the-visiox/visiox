from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

urlpatterns = [
    path('admin/', admin.site.urls),

    # Profiler (only meaningful in DEBUG)
    path('silk/', include('silk.urls', namespace='silk')),

    # Auth
    path('api/v1/auth/', include('authentication.urls')),

    # Core resources
    path('api/v1/', include('teams.urls')),
    path('api/v1/', include('projects.urls')),
    path('api/v1/', include('datasets.urls')),
    path('api/v1/', include('annotations.urls')),
    path('api/v1/', include('dataverse.urls')),

    # Phase 3–5
    path('api/v1/', include('training.urls')),
    path('api/v1/', include('deployments.urls')),
    path('api/v1/', include('billing.urls')),

    # OpenAPI
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
