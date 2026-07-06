"""Config-driven data fabric for this generated app.

Connections live in ``app/connections.json``. Prefers each connection's real
database (Postgres / MySQL / MongoDB) and falls back to embedded sample data for
the bundled demo connections. See service.py.
"""
from .service import fabric

__all__ = ["fabric"]
