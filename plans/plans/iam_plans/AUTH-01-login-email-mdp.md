# AUTH-01 — fusionné dans AUTH-A

La connexion email + mot de passe **n’est plus un ticket isolé**. Elle se livre **en même temps** que AUTH-02 … AUTH-12 (username, 403 compte, anti-énumération, rate-limit IP/identifiant, journal, last_login, JWT access, refresh, device, session/appareil).

**Plan d’implémentation unique :** [AUTH-A-connexion-locale.md](AUTH-A-connexion-locale.md)

| ID | Dans AUTH-A |
|----|-------------|
| AUTH-01 | Login `email` + MDP |
| AUTH-02 | Login `username` + MDP |
| AUTH-03 / 04 | `is_active` / `is_locked` |
| AUTH-05 / 06 / 07 / 08 | 401 générique, rate-limit, `login_history`, `last_login` |
| AUTH-09 / 10 | JWT access + refresh hashé + `POST /refresh` |
| AUTH-11 / 12 | Upsert `devices` + 1 session active par appareil |

Socle Django (venv, settings, health) : [00-application-A-Z.md](../00-application-A-Z.md).  
LDAP : [AUTH-B-sso-ldap.md](AUTH-B-sso-ldap.md). MFA : [AUTH-C-mfa-otp.md](AUTH-C-mfa-otp.md).  
Mot de passe (change / forgot / reset) : [AUTH-G-mot-de-passe.md](AUTH-G-mot-de-passe.md).  
Sessions / logout : [AUTH-H-sessions.md](AUTH-H-sessions.md).  
Sécurité compte : [AUTH-I-securite.md](AUTH-I-securite.md).  
Rôles & permissions : [AUTH-R-roles-permissions.md](AUTH-R-roles-permissions.md).
