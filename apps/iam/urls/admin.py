"""D05 + AUTH-R sous /api/v1/admin/ — JWT + HasPermission, pas le cookie /admin/ Django."""

from django.urls import path

from apps.iam.views.admin_rbac import (
    PermissionDeleteView,
    PermissionListCreateView,
    RoleDetailView,
    RoleListCreateView,
    RolePermissionsView,
)
from apps.iam.views.admin_audit import AdminAuditLogListView
from apps.iam.views.admin_regions import AdminRegionDetailView, AdminRegionListCreateView
from apps.iam.views.admin_users import (
    AdminMfaResetView,
    AdminUserApproveView,
    AdminUserDetailView,
    AdminUserDisableView,
    AdminUserEnableView,
    AdminUserListView,
    AdminUserLoginsView,
    AdminUserPasswordView,
    AdminUserRejectView,
    AdminUserRevokeAllView,
    AdminUserRoleView,
    AdminUserUnlockView,
)
from apps.iam.views.devices import AdminDeviceClearCompromiseView, AdminDeviceCompromiseView

urlpatterns = [
    path("roles", RoleListCreateView.as_view(), name="admin-roles"),
    path(
        "roles/<uuid:pk>/permissions",
        RolePermissionsView.as_view(),
        name="admin-roles-permissions",
    ),
    path("roles/<uuid:pk>", RoleDetailView.as_view(), name="admin-roles-detail"),
    path("permissions", PermissionListCreateView.as_view(), name="admin-permissions"),
    path(
        "permissions/<uuid:pk>",
        PermissionDeleteView.as_view(),
        name="admin-permissions-delete",
    ),
    path("users", AdminUserListView.as_view(), name="admin-users"),
    path("users/<uuid:pk>/approve", AdminUserApproveView.as_view(), name="admin-users-approve"),
    path("users/<uuid:pk>/reject", AdminUserRejectView.as_view(), name="admin-users-reject"),
    path(
        "users/<uuid:pk>/mfa/reset",
        AdminMfaResetView.as_view(),
        name="admin-users-mfa-reset",
    ),
    path(
        "users/<uuid:pk>/unlock",
        AdminUserUnlockView.as_view(),
        name="admin-users-unlock",
    ),
    path(
        "users/<uuid:pk>/logins",
        AdminUserLoginsView.as_view(),
        name="admin-users-logins",
    ),
    path(
        "users/<uuid:pk>/role",
        AdminUserRoleView.as_view(),
        name="admin-users-role",
    ),
    path(
        "users/<uuid:pk>/disable",
        AdminUserDisableView.as_view(),
        name="admin-users-disable",
    ),
    path(
        "users/<uuid:pk>/enable",
        AdminUserEnableView.as_view(),
        name="admin-users-enable",
    ),
    path(
        "users/<uuid:pk>/password",
        AdminUserPasswordView.as_view(),
        name="admin-users-password",
    ),
    path(
        "users/<uuid:pk>/sessions/revoke-all",
        AdminUserRevokeAllView.as_view(),
        name="admin-users-revoke-all",
    ),
    path("users/<uuid:pk>", AdminUserDetailView.as_view(), name="admin-users-detail"),
    path("audit-logs", AdminAuditLogListView.as_view(), name="admin-audit-logs"),
    path("regions", AdminRegionListCreateView.as_view(), name="admin-regions"),
    path("regions/<uuid:pk>", AdminRegionDetailView.as_view(), name="admin-regions-detail"),
    path(
        "devices/<uuid:pk>/compromise",
        AdminDeviceCompromiseView.as_view(),
        name="admin-devices-compromise",
    ),
    path(
        "devices/<uuid:pk>/clear-compromise",
        AdminDeviceClearCompromiseView.as_view(),
        name="admin-devices-clear-compromise",
    ),
]