from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from project_kg.db import KGDB
from project_kg.embeddings import EmbeddingEngine


@dataclass
class SyncResult:
    connector: str
    source_key: str
    nodes_created: int = 0
    nodes_updated: int = 0
    edges_created: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total_nodes(self) -> int:
        return self.nodes_created + self.nodes_updated

    def to_dict(self) -> dict:
        return {
            "connector": self.connector,
            "source_key": self.source_key,
            "nodes_created": self.nodes_created,
            "nodes_updated": self.nodes_updated,
            "edges_created": self.edges_created,
            "errors": self.errors,
        }


class Connector(ABC):
    """Base class for Project KG data connectors."""

    name: str  # e.g. "wcp", "git", "filesystem"

    @abstractmethod
    def sync(
        self,
        db: KGDB,
        embeddings: EmbeddingEngine,
        full: bool = False,
    ) -> list[SyncResult]:
        """Run sync. Returns one SyncResult per source_key (namespace/repo/dir).

        Args:
            db: Project KG database instance.
            embeddings: Embedding engine for vector generation.
            full: If True, re-sync everything. Otherwise incremental.
        """
        ...
