"""Multi-source data fabric.

A live, testable demo of heterogeneous data sources + an agentic router that
decides *which* database a natural-language question should hit, then queries it.

Docker (and real Postgres/MySQL/MongoDB servers) are not available on this
machine, so the physical engines are embedded — SQLite standing in for the two
SQL dialects and a small in-process document store standing in for MongoDB.
The connector interface, per-engine query dialects, connection metadata, and
routing logic are all real, so this swaps to actual servers by replacing the
engine classes only.
"""
from forge.fabric.service import fabric

__all__ = ["fabric"]
