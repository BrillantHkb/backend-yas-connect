from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import AllowAny

admin.site.site_header = "YAS Connect"
admin.site.site_title = "YAS Connect"
admin.site.index_title = "Administration lab (IAM)"

urlpatterns = [
    path("admin/", admin.site.urls),  # cookie session ; rôle ADMIN seulement
    path("", include("apps.core.urls")),
    path(
        "api/schema/",
        SpectacularAPIView.as_view(authentication_classes=[], permission_classes=[AllowAny]),
        name="schema",
    ),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(
            url_name="schema",
            authentication_classes=[],
            permission_classes=[AllowAny],
        ),
        name="docs",
    ),
    path("api/v1/auth/", include("apps.iam.urls")),
]
