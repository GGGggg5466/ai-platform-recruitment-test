from gateway.app.auth import UserCtx

ROLE_TO_SCOPES = {
    "intern": ["public.*"],
    # employee can access internal tools in this HW
    "employee": ["public.*", "internal.*"],
    "admin": ["public.*", "internal.*", "admin.*"],
}


def is_allowed(user: UserCtx, required_scope: str) -> bool:
    # simple wildcard matching: "internal.*" matches "internal.db" / "internal.exec" etc.
    for s in user.scopes:
        if s.endswith(".*"):
            prefix = s[:-2]
            if required_scope.startswith(prefix + ".") or required_scope == prefix:
                return True
        if s == required_scope:
            return True
    return False
