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
    path('api/auth/', include('authentication.urls')),

    # Core resources
    path('api/', include('teams.urls')),
    path('api/', include('projects.urls')),
    path('api/', include('datasets.urls')),
    path('api/', include('annotations.urls')),
    path('api/', include('dataverse.urls')),

    # Phase 3–5
    path('api/', include('training.urls')),
    path('api/', include('deployments.urls')),
    path('api/', include('billing.urls')),

    # OpenAPI
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
