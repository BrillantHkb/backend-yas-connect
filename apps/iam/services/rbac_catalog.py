"""Catalogue seed AUTH-R : 58 permissions is_system (27 self + 31 admin).

Codes = {module}.{resource}.{action} (regex R01, 3 segments).
Écart table AUTH-R : `iam.user.security.read` → `iam.user_security.read` ;
`iam.user.role.assign` → `iam.user.role_assign`.
"""

# (module, resource, action, name)
_SELF = (
    ("iam", "profile", "read", "Lire son profil"),
    ("iam", "profile", "update", "Éditer son profil"),
    ("iam", "profile", "read_other", "Lire un collègue"),
    ("iam", "prefs", "read", "Lire ses préférences"),
    ("iam", "prefs", "update", "Modifier ses préférences"),
    ("iam", "privacy", "read", "Lire sa confidentialité"),
    ("iam", "privacy", "update", "Modifier sa confidentialité"),
    ("iam", "presence", "update", "Message de présence"),
    ("iam", "presence", "heartbeat", "Ping présence REST"),
    ("iam", "tos", "manage", "CGU"),
    ("iam", "onboarding", "manage", "Wizard"),
    ("iam", "password", "change", "Changer le mot de passe connecté"),
    ("iam", "session", "read", "Lister ses sessions"),
    ("iam", "session", "logout", "Déconnexion"),
    ("iam", "session", "heartbeat", "Heartbeat session"),
    ("iam", "device", "read", "Lister ses appareils"),
    ("iam", "device", "update", "Patch appareil (soi)"),
    ("iam", "device", "revoke", "Révoquer un appareil (soi)"),
    ("iam", "device", "compromise", "Signaler compromis (soi)"),
    ("iam", "login", "read", "Historique de ses connexions"),
    ("iam", "email", "change", "Changer / renvoyer e-mail"),
    ("iam", "mfa", "regenerate", "Régénérer codes secours"),
    ("media", "avatar", "manage", "Avatar"),
    ("annuaire", "skill", "read", "Lire ses compétences"),
    ("annuaire", "skill", "manage", "Gérer ses compétences"),
    ("annuaire", "certification", "read", "Lire ses certifications"),
    ("annuaire", "certification", "manage", "Gérer ses certifications"),
)

_ADMIN = (
    ("iam", "user", "approve", "Approuver un compte"),
    ("iam", "user", "reject", "Rejeter un compte"),
    ("iam", "user", "unlock", "Déverrouiller un compte"),
    ("iam", "user_security", "read", "Historique connexions d’un autre"),
    ("iam", "user", "role_assign", "Changer le rôle d’un user"),
    ("iam", "device", "manage", "Appareils admin"),
    ("iam", "mfa", "reset", "Reset TOTP admin"),
    ("iam", "role", "read", "Lister / voir rôles"),
    ("iam", "role", "manage", "Créer / patcher un rôle"),
    ("iam", "permission", "read", "Lister permissions"),
    ("iam", "permission", "manage", "Créer permission custom"),
    ("iam", "role", "grant", "Matrice permissions d’un rôle"),
    ("iam", "user", "read", "Liste / fiche admin users"),
    ("iam", "user", "create", "Créer un compte RH"),
    ("iam", "user", "disable", "Désactiver (hors AD)"),
    ("iam", "user", "enable", "Réactiver (hors AD)"),
    ("iam", "user", "reset_password", "Reset MDP app (admin)"),
    ("iam", "session", "revoke_other", "Kick toutes les sessions d’un user"),
    ("iam", "audit", "read", "Lire audit_logs"),
    ("iam", "region", "read", "Lister / voir régions (admin)"),
    ("iam", "region", "manage", "Créer / patcher / supprimer une région"),
    ("annuaire", "segment_type", "read", "Lister / voir types d’unité"),
    ("annuaire", "segment_type", "manage", "CRUD types d’unité"),
    ("annuaire", "segment", "read", "Lister / voir / arbre segments"),
    ("annuaire", "segment", "manage", "CRUD segments"),
    ("annuaire", "user_segment", "read", "Historique d’affectations"),
    ("annuaire", "user_segment", "manage", "Affecter / muter / clôturer"),
    ("annuaire", "user_skill", "read", "Skills d’un autre user"),
    ("annuaire", "user_skill", "manage", "CRUD skills d’un autre user"),
    ("annuaire", "user_certification", "read", "Certifs d’un autre user"),
    ("annuaire", "user_certification", "manage", "CRUD certifs d’un autre user"),
)


def _rows(items):
    return [
        {
            "module": module,
            "resource": resource,
            "action": action,
            "code": f"{module}.{resource}.{action}",
            "name": name,
            "description": "",
            "is_system": True,
        }
        for module, resource, action, name in items
    ]


SELF_PERMISSIONS = _rows(_SELF)
ADMIN_PERMISSIONS = _rows(_ADMIN)
SYSTEM_PERMISSIONS = SELF_PERMISSIONS + ADMIN_PERMISSIONS
SELF_PERMISSION_CODES = frozenset(p["code"] for p in SELF_PERMISSIONS)
ADMIN_PERMISSION_CODES = frozenset(p["code"] for p in ADMIN_PERMISSIONS)
ALL_SYSTEM_CODES = frozenset(p["code"] for p in SYSTEM_PERMISSIONS)

CODE_RE = r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$"
ROLE_CODE_RE = r"^[A-Z][A-Z0-9_]*$"

assert len(SELF_PERMISSIONS) == 27, len(SELF_PERMISSIONS)
assert len(ADMIN_PERMISSIONS) == 31, len(ADMIN_PERMISSIONS)
assert len(SYSTEM_PERMISSIONS) == 58
assert len(ALL_SYSTEM_CODES) == 58
