"""LDAP / AD : settings, search DN+UPN+sAM, bind, UAC / accountExpires. Jamais le MDP AD en log."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from ldap3 import ALL, SUBTREE, Connection, Server
from ldap3.core.exceptions import LDAPException, LDAPSocketOpenError
from ldap3.utils.conv import escape_filter_chars

from apps.config.models import SystemSetting


class DirectoryUnavailable(Exception):
    """AD down, timeout, URI sans TLS, compte service KO."""


class LdapBindFailed(Exception):
    """DN introuvable, UAC non loggable, ou bind user KO — toujours 401 côté login."""


@dataclass(frozen=True)
class LdapSettings:
    uri: str
    bind_dn: str
    bind_password: str
    search_base: str
    timeout_seconds: int


@dataclass(frozen=True)
class AdIdentity:
    """Identité AD lue au search (AUTH-D02). Pas de displayName / title."""

    dn: str
    upn: str
    sam: str


def _setting(key: str):
    """Lecture runtime : secrets LDAP dans system_settings, jamais le .env."""
    row = SystemSetting.objects.filter(category="ldap", setting_key=key).first()
    if row is None:
        raise DirectoryUnavailable()  # conf absente = AD injoignable (503), pas 401
    return row.setting_value


def get_ldap_settings() -> LdapSettings:
    timeout = _setting("timeout_seconds")
    return LdapSettings(
        uri=str(_setting("uri")),
        bind_dn=str(_setting("bind_dn")),
        bind_password=str(_setting("bind_password")),
        search_base=str(_setting("search_base")),
        timeout_seconds=int(timeout),
    )


def _server(cfg: LdapSettings) -> Server:
    """TLS obligatoire : ldaps:// ou ldap:// + STARTTLS. Autre schéma → 503 (conf)."""
    use_ssl = cfg.uri.startswith("ldaps://")
    start_tls = cfg.uri.startswith("ldap://")
    if not use_ssl and not start_tls:
        raise DirectoryUnavailable()
    return Server(cfg.uri, get_info=ALL, connect_timeout=cfg.timeout_seconds, use_ssl=use_ssl)


def _service_bind(cfg: LdapSettings) -> Connection:
    """Bind du compte service (search). Échec = infra, pas un 401 user."""
    server = _server(cfg)
    if cfg.uri.startswith("ldaps://"):
        return Connection(
            server,
            user=cfg.bind_dn,
            password=cfg.bind_password,
            auto_bind=True,
            receive_timeout=cfg.timeout_seconds,
        )
    conn = Connection(
        server,
        user=cfg.bind_dn,
        password=cfg.bind_password,
        auto_bind=False,
        receive_timeout=cfg.timeout_seconds,
    )
    conn.open()
    if not conn.start_tls() or not conn.bind():
        raise DirectoryUnavailable()
    return conn


# Bits ADS_USER_FLAG_ENUM lus pour le statut logon. Masque jamais stocké en base.
ADS_UF_ACCOUNTDISABLE = 0x0002
ADS_UF_LOCKOUT = 0x0010
ADS_UF_TEMP_DUPLICATE_ACCOUNT = 0x0100
ADS_UF_NORMAL_ACCOUNT = 0x0200
ADS_UF_INTERDOMAIN_TRUST_ACCOUNT = 0x0800
ADS_UF_WORKSTATION_TRUST_ACCOUNT = 0x1000
ADS_UF_SERVER_TRUST_ACCOUNT = 0x2000
ADS_UF_SMARTCARD_REQUIRED = 0x40000
ADS_UF_PASSWORD_EXPIRED = 0x800000
ADS_UF_ACCOUNT_TYPE_MASK = (
    ADS_UF_TEMP_DUPLICATE_ACCOUNT
    | ADS_UF_NORMAL_ACCOUNT
    | ADS_UF_INTERDOMAIN_TRUST_ACCOUNT
    | ADS_UF_WORKSTATION_TRUST_ACCOUNT
    | ADS_UF_SERVER_TRUST_ACCOUNT
)
ACCOUNT_NEVER_EXPIRES = {0, 0x7FFFFFFFFFFFFFFF}
FILETIME_EPOCH = datetime(1601, 1, 1, tzinfo=UTC)


def _int_uac(value) -> int:
    """ldap3 peut renvoyer int, str ou liste d’attributs."""
    if value is None:
        return 0
    if isinstance(value, list):
        value = value[0] if value else 0
    return int(value)


def is_account_expired(account_expires) -> bool:
    """accountExpires AD : 0 / 0x7FFFFFFFFFFFFFFF = jamais. Sinon FILETIME ou datetime ldap3."""
    if account_expires is None:
        return False
    if isinstance(account_expires, list):
        account_expires = account_expires[0] if account_expires else None
        if account_expires is None:
            return False
    if isinstance(account_expires, datetime):
        exp = (
            account_expires
            if account_expires.tzinfo
            else account_expires.replace(tzinfo=UTC)
        )
        return exp <= datetime.now(UTC)
    ticks = int(account_expires)
    if ticks in ACCOUNT_NEVER_EXPIRES:
        return False
    exp = FILETIME_EPOCH + timedelta(microseconds=ticks / 10)
    return exp <= datetime.now(UTC)


def ad_logon_status(*, user_account_control, account_expires) -> str:
    """Statut logon AD : un seul code, bits bloquants en priorité."""
    uac = _int_uac(user_account_control)
    if uac & ADS_UF_ACCOUNTDISABLE:
        return "DISABLED"
    if uac & ADS_UF_LOCKOUT:
        return "LOCKED"
    if uac & ADS_UF_SMARTCARD_REQUIRED:
        return "SMARTCARD"
    if (uac & ADS_UF_ACCOUNT_TYPE_MASK) != ADS_UF_NORMAL_ACCOUNT:
        return "WRONG_TYPE"  # machine / trust — pas un user
    if uac & ADS_UF_PASSWORD_EXPIRED:
        return "PWD_EXPIRED"
    if is_account_expired(account_expires):
        return "EXPIRED"
    return "USABLE"


def _search_filter(*, email: str | None, username: str | None) -> str:
    """Filtre OR mail/UPN/sAM. escape_filter_chars = anti-injection LDAP."""
    parts: list[str] = []
    if email:
        mail = escape_filter_chars(email)
        parts.append(f"(mail={mail})")
        parts.append(f"(userPrincipalName={mail})")
    if username:
        sam = escape_filter_chars(username)
        parts.append(f"(sAMAccountName={sam})")
    if not parts:
        raise LdapBindFailed()
    return f"(|{''.join(parts)})"


_SEARCH_ATTRS = [
    "distinguishedName",
    "userPrincipalName",
    "sAMAccountName",
    "userAccountControl",
    "accountExpires",
]


def search_user_identity(*, email: str | None = None, username: str | None = None) -> AdIdentity:
    """DN + UPN + sAMAccountName. Introuvable ou non loggable → LdapBindFailed."""
    cfg = get_ldap_settings()
    flt = _search_filter(email=email, username=username)
    try:
        conn = _service_bind(cfg)
        ok = conn.search(
            search_base=cfg.search_base,
            search_filter=flt,
            search_scope=SUBTREE,
            attributes=_SEARCH_ATTRS,
            size_limit=1,
        )
        if not ok or not conn.entries:
            raise LdapBindFailed()  # absent → même 401 que bind KO (pas de leak)
        entry = conn.entries[0]
        status = ad_logon_status(
            user_account_control=entry.userAccountControl.value,
            account_expires=entry.accountExpires.value,
        )
        if status != "USABLE":
            raise LdapBindFailed()  # UAC / expire → 401, jamais 403 (bits AD)
        upn = str(entry.userPrincipalName.value or email or "").strip().lower()
        sam = str(entry.sAMAccountName.value or username or "").strip()
        if not upn or not sam:
            raise LdapBindFailed()
        return AdIdentity(dn=str(entry.entry_dn), upn=upn, sam=sam)
    except LdapBindFailed:
        raise
    except DirectoryUnavailable:
        raise
    except LDAPSocketOpenError as exc:
        raise DirectoryUnavailable() from exc
    except LDAPException as exc:
        raise DirectoryUnavailable() from exc


def search_user_dn(*, email: str | None = None, username: str | None = None) -> str:
    """DN AD du compte. Introuvable ou non loggable → LdapBindFailed."""
    return search_user_identity(email=email, username=username).dn


def bind_user_dn(*, dn: str, password: str) -> None:
    """Preuve mot de passe Windows. Le clair n’est jamais loggé ni stocké."""
    cfg = get_ldap_settings()
    try:
        conn = Connection(
            _server(cfg),
            user=dn,
            password=password,
            receive_timeout=cfg.timeout_seconds,
        )
        if cfg.uri.startswith("ldap://"):
            conn.open()
            if not conn.start_tls():
                raise DirectoryUnavailable()  # bind user aussi : jamais LDAP en clair
        if not conn.bind():
            raise LdapBindFailed()
    except LdapBindFailed:
        raise
    except DirectoryUnavailable:
        raise
    except LDAPSocketOpenError as exc:
        raise DirectoryUnavailable() from exc
    except LDAPException as exc:
        raise DirectoryUnavailable() from exc


def iter_ad_logon_state() -> dict[str, str]:
    """AUTH-16 : DN → statut ad_logon_status. Absent du dict = plus dans search_base."""
    cfg = get_ldap_settings()
    conn = _service_bind(cfg)
    state: dict[str, str] = {}
    for entry in conn.extend.standard.paged_search(
        search_base=cfg.search_base,
        search_filter="(objectClass=user)",
        search_scope=SUBTREE,
        attributes=["distinguishedName", "userAccountControl", "accountExpires"],
        paged_size=500,
        generator=True,
    ):
        dn = entry.get("dn")
        if not dn:
            continue  # entrée sans DN (page search) : ignorée
        attrs = entry.get("attributes") or {}
        state[dn] = ad_logon_status(
            user_account_control=attrs.get("userAccountControl"),
            account_expires=attrs.get("accountExpires"),
        )
    return state
