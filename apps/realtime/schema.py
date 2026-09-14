"""OpenAPI : Channels n’est pas une vue DRF — on injecte le WS dans le schéma."""


def add_presence_websocket(result, generator, request, public):
    """Documente GET /ws/v1/presence (handshake WebSocket). Pas un endpoint HTTP."""
    result.setdefault("paths", {})
    result["paths"]["/ws/v1/presence"] = {
        "get": {
            "operationId": "ws_v1_presence",
            "tags": ["Me"],
            "summary": "WebSocket présence",
            "description": (
                "Canal **WebSocket** (pas REST). Servir avec Daphne / ASGI ; "
                "`runserver` WSGI ne l’expose pas.\n\n"
                "Auth : query `token=<access JWT>` **ou** header `Authorization: Bearer`. "
                "Perm `iam.profile.read`. Portes AUTH-F (CGU + wizard) dans le consumer.\n\n"
                "Fermeture : **4401** JWT KO ; **4403** `TOS_REQUIRED` / "
                "`ONBOARDING_REQUIRED` / `FORBIDDEN`.\n\n"
                "Messages JSON :\n"
                "- C→S `PING` `{}` → S→C `PONG` `{at}`\n"
                "- C→S `WATCH` / `UNWATCH` `{user_ids}` (max 100)\n"
                "- S→C `USER_STATUS_CHANGED` `{user_id, status, badge, status_message}` "
                "(masqué PROF-25 : status/badge null, pas de message)\n\n"
                "Connect = liveness Redis ; dernier socket = DEL (effective OFFLINE)."
            ),
            "parameters": [
                {
                    "name": "token",
                    "in": "query",
                    "required": False,
                    "schema": {"type": "string"},
                    "description": "JWT access (alternative au Bearer).",
                }
            ],
            "security": [{"bearerAuth": []}],
            "responses": {
                "101": {
                    "description": (
                        "Switching Protocols. Ensuite messages JSON (PING/PONG, WATCH, "
                        "USER_STATUS_CHANGED)."
                    )
                }
            },
        }
    }
    return result
