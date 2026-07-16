"""Lightweight tester identity for the Human Persona Layer — not real
authentication, just a string label so multiple people testing the same
ECHO install each get their own RelationshipProfile/PersonaSettings/mood/
thread/ritual data instead of silently sharing one. "default" is the
primary user (Aravind) — every existing call that doesn't send the header
keeps working unchanged, scoped to "default" exactly as before this layer
existed.
"""

from fastapi import Header

DEFAULT_TESTER_ID = "default"


def get_tester_id(x_tester_id: str | None = Header(default=None)) -> str:
    tester_id = (x_tester_id or "").strip()
    return tester_id or DEFAULT_TESTER_ID
