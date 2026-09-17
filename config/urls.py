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
    path("api/v1/auth/", include("apps.iam.urls")),  # urls/auth.py via package __init__
    path("api/v1/admin/", include("apps.iam.urls.admin")),  # JWT API, distinct de /admin/
    path("api/v1/admin/", include("apps.annuaire.urls.admin_org")),  # ANNUAIRE-B : organigramme
    path("api/v1/admin/", include("apps.annuaire.urls.admin_assignments")),  # ANNUAIRE-C
    path("api/v1/admin/", include("apps.annuaire.urls.admin_competences")),  # ANNUAIRE-D
    path("api/v1/admin/", include("apps.messaging.urls_admin")),  # MESSAGERIE-F signalements
    path("api/v1/me/", include("apps.iam.urls.me")),  # AUTH-E appareils + AUTH-F CGU/wizard + PROF-A
    path("api/v1/me/", include("apps.annuaire.urls.me_competences")),  # ANNUAIRE-D
    path("api/v1/me/", include("apps.messaging.urls_me")),  # MESSAGERIE-E/F signets + blocage
    path("api/v1/users/", include("apps.iam.urls.users")),  # PROF-A fiche collègue
    path("api/v1/media/", include("apps.media.urls")),  # PROF-A fichiers avatar
    path("api/v1/", include("apps.media.urls_documents")),  # MEDIA-E GED
    path("api/v1/", include("apps.config.urls")),  # GET /config plafonds publics (W40)
    path("api/v1/", include("apps.notifications.urls")),  # NOTIF-A inbox + prefs
    path("api/v1/crypto/", include("apps.crypto.urls")),  # CRYPTO-A bundles Signal
    path("api/v1/", include("apps.messaging.urls")),  # MESSAGERIE-A/B inbox + messages 1-to-1
    path("api/v1/directory/", include("apps.annuaire.urls")),  # publics, pas de Bearer
]
