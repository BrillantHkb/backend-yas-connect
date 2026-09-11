"""PROF-A : chaîne d’unités Annuaire. Pas de manager_id IAM."""

from apps.annuaire.models import Segment

_DEPT_TYPES = frozenset({"DEPARTEMENT", "DEPT", "SERVICE"})
_MAX_DEPTH = 16


def _type_payload(segment: Segment) -> dict | None:
    st = segment.segment_type
    if st is None:
        return None
    return {"code": st.code, "name": st.name}


def _mini_user(user) -> dict:
    return {
        "id": str(user.id),
        "display_name": user.get_full_name(),
        "username": user.username,
    }


def resolve_org(user) -> dict | None:
    """Segment courant + parents. None si pas de FK / inactif."""
    if not user.segment_id:
        return None
    current = (
        Segment.objects.select_related("segment_type", "responsable")
        .filter(pk=user.segment_id, is_active=True)
        .first()
    )
    if current is None:
        return None
    nodes = []
    seen = set()
    while current is not None and current.id not in seen and len(nodes) < _MAX_DEPTH:
        seen.add(current.id)
        nodes.append(current)
        parent_id = current.parent_segment_id
        if not parent_id:
            break
        current = (
            Segment.objects.select_related("segment_type", "responsable")
            .filter(pk=parent_id)
            .first()
        )

    leaf = nodes[0]
    department = None
    direction = None
    manager = None
    path = []
    for node in nodes:
        st = node.segment_type
        code = st.code if st else ""
        path.append({"name": node.name, "type": code or None})
        if department is None and code in _DEPT_TYPES:
            department = {"id": str(node.id), "name": node.name}
        if direction is None and code == "DIRECTION":
            direction = {"id": str(node.id), "name": node.name}
        if manager is None and node.responsable_id:
            manager = _mini_user(node.responsable)

    st = leaf.segment_type
    return {
        "segment": {
            "id": str(leaf.id),
            "code": leaf.code,
            "name": leaf.name,
            "type": _type_payload(leaf),
        },
        "department": department,
        "direction": direction,
        "path": path,
        "manager": manager,
    }
