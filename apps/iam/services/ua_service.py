"""Parse User-Agent → login_history.browser / browser_version (AUTH-07)."""

from ua_parser import user_agent_parser


def parse_user_agent(user_agent: str) -> tuple[str | None, str | None]:
    """Retourne (famille, major.minor) ou (None, None) si header vide."""
    if not user_agent:
        return None, None
    parsed = user_agent_parser.Parse(user_agent)
    ua = parsed.get("user_agent") or {}
    family = ua.get("family") or None  # ex. Chrome
    major = ua.get("major")
    minor = ua.get("minor")
    if not major:
        return family, None  # famille connue sans n° de version
    version = f"{major}.{minor}" if minor is not None else str(major)
    return family, version
