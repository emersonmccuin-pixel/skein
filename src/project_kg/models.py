from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Node:
    id: str
    type: str  # decision, pattern, discovery, work_item, document, commit, note
    title: str
    body: str
    source: str = "manual"  # manual, wcp, git, filesystem
    source_id: str | None = None
    source_uri: str | None = None
    project: str | None = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    archived: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Edge:
    id: str
    source_id: str
    target_id: str
    type: str  # depends_on, informed_by, supersedes, relates_to, implements, extracted_from
    weight: float = 1.0
    metadata: dict | None = None
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SearchResult:
    node: Node
    score: float
    match_type: str = ""  # fts, vector, combined


@dataclass
class SyncState:
    connector: str
    source_key: str
    last_sync: str | None = None
    cursor: str | None = None
