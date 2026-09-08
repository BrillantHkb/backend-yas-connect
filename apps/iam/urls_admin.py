"""D05 sous /api/v1/admin/ — JWT + rôle ADMIN, pas le cookie /admin/ Django."""

from django.urls import path

from apps.iam.views_admin_users import (
    AdminMfaResetView,
    AdminUserApproveView,
    AdminUserListView,
    AdminUserRejectView,
)

urlpatterns = [
    path("users", AdminUserListView.as_view(), name="admin-users"),
    path("users/<uuid:pk>/approve", AdminUserApproveView.as_view(), name="admin-users-approve"),
    path("users/<uuid:pk>/reject", AdminUserRejectView.as_view(), name="admin-users-reject"),
    path(
        "users/<uuid:pk>/mfa/reset",
        AdminMfaResetView.as_view(),
        name="admin-users-mfa-reset",
    ),  # AUTH-24 : rôle ADMIN ; AUTH-R → iam.mfa.reset
]
