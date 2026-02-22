from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np

from project_kg.models import Node, Edge, SyncState

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    source_id TEXT,
    source_uri TEXT,
    project TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type);
CREATE INDEX IF NOT EXISTS idx_nodes_source ON nodes(source, source_id);
CREATE INDEX IF NOT EXISTS idx_nodes_project ON nodes(project);
CREATE INDEX IF NOT EXISTS idx_nodes_updated ON nodes(updated_at DESC);

CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
    title, body, content=nodes, content_rowid=rowid
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS nodes_ai AFTER INSERT ON nodes BEGIN
    INSERT INTO nodes_fts(rowid, title, body) VALUES (new.rowid, new.title, new.body);
END;
CREATE TRIGGER IF NOT EXISTS nodes_ad AFTER DELETE ON nodes BEGIN
    INSERT INTO nodes_fts(nodes_fts, rowid, title, body) VALUES ('delete', old.rowid, old.title, old.body);
END;
CREATE TRIGGER IF NOT EXISTS nodes_au AFTER UPDATE ON nodes BEGIN
    INSERT INTO nodes_fts(nodes_fts, rowid, title, body) VALUES ('delete', old.rowid, old.title, old.body);
    INSERT INTO nodes_fts(rowid, title, body) VALUES (new.rowid, new.title, new.body);
END;

CREATE TABLE IF NOT EXISTS edges (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES nodes(id),
    target_id TEXT NOT NULL REFERENCES nodes(id),
    type TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    metadata TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(source_id, target_id, type)
);

CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);

CREATE TABLE IF NOT EXISTS embeddings (
    node_id TEXT PRIMARY KEY REFERENCES nodes(id),
    vector BLOB NOT NULL,
    model TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_state (
    connector TEXT NOT NULL,
    source_key TEXT NOT NULL,
    last_sync TEXT,
    cursor TEXT,
    PRIMARY KEY (connector, source_key)
);
"""


class KGDB:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript(SCHEMA_SQL)

    def close(self):
        self.conn.close()

    # --- Nodes ---

    def insert_node(self, node: Node) -> Node:
        self.conn.execute(
            """INSERT INTO nodes (id, type, title, body, source, source_id, source_uri, project, created_at, updated_at, archived)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (node.id, node.type, node.title, node.body, node.source,
             node.source_id, node.source_uri, node.project,
             node.created_at, node.updated_at, int(node.archived)),
        )
        self.conn.commit()
        return node

    def upsert_node(self, node: Node) -> tuple[Node, bool]:
        """Insert or update a node by source+source_id. Returns (node, created)."""
        existing = self.find_node_by_source(node.source, node.source_id) if node.source_id else None
        if existing:
            self.conn.execute(
                """UPDATE nodes SET type=?, title=?, body=?, source_uri=?, project=?, updated_at=?
                   WHERE id=?""",
                (node.type, node.title, node.body, node.source_uri, node.project,
                 node.updated_at, existing.id),
            )
            self.conn.commit()
            node.id = existing.id
            node.created_at = existing.created_at
            return node, False
        self.insert_node(node)
        return node, True

    def find_node_by_source(self, source: str, source_id: str | None) -> Node | None:
        if not source_id:
            return None
        row = self.conn.execute(
            "SELECT * FROM nodes WHERE source = ? AND source_id = ?",
            (source, source_id),
        ).fetchone()
        return self._row_to_node(row) if row else None

    def upsert_edge(self, edge: Edge) -> Edge:
        """Insert or ignore an edge (unique on source_id+target_id+type)."""
        self.conn.execute(
            """INSERT OR IGNORE INTO edges (id, source_id, target_id, type, weight, metadata, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (edge.id, edge.source_id, edge.target_id, edge.type, edge.weight,
             json.dumps(edge.metadata) if edge.metadata else None, edge.created_at),
        )
        self.conn.commit()
        return edge

    def get_node(self, node_id: str) -> Node | None:
        row = self.conn.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_node(row)

    def list_nodes(self, type_filter: str | None = None, project_filter: str | None = None,
                   limit: int = 50) -> list[Node]:
        query = "SELECT * FROM nodes WHERE archived = 0"
        params: list = []
        if type_filter:
            query += " AND type = ?"
            params.append(type_filter)
        if project_filter:
            query += " AND project = ?"
            params.append(project_filter)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_node(r) for r in rows]

    @staticmethod
    def _row_to_node(row: sqlite3.Row) -> Node:
        return Node(
            id=row["id"], type=row["type"], title=row["title"], body=row["body"],
            source=row["source"], source_id=row["source_id"], source_uri=row["source_uri"],
            project=row["project"], created_at=row["created_at"], updated_at=row["updated_at"],
            archived=bool(row["archived"]),
        )

    # --- Edges ---

    def insert_edge(self, edge: Edge) -> Edge:
        self.conn.execute(
            """INSERT INTO edges (id, source_id, target_id, type, weight, metadata, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (edge.id, edge.source_id, edge.target_id, edge.type, edge.weight,
             json.dumps(edge.metadata) if edge.metadata else None, edge.created_at),
        )
        self.conn.commit()
        return edge

    def get_edges(self, node_id: str, direction: str = "both") -> list[Edge]:
        edges: list[Edge] = []
        if direction in ("out", "both"):
            rows = self.conn.execute("SELECT * FROM edges WHERE source_id = ?", (node_id,)).fetchall()
            edges.extend(self._row_to_edge(r) for r in rows)
        if direction in ("in", "both"):
            rows = self.conn.execute("SELECT * FROM edges WHERE target_id = ?", (node_id,)).fetchall()
            edges.extend(self._row_to_edge(r) for r in rows)
        return edges

    def get_neighbors(self, node_id: str, depth: int = 1) -> tuple[list[Node], list[Edge]]:
        """BFS traversal returning all nodes and edges within `depth` hops."""
        visited_nodes: set[str] = {node_id}
        all_edges: list[Edge] = []
        frontier = {node_id}

        for _ in range(depth):
            next_frontier: set[str] = set()
            for nid in frontier:
                edges = self.get_edges(nid)
                for edge in edges:
                    all_edges.append(edge)
                    other = edge.target_id if edge.source_id == nid else edge.source_id
                    if other not in visited_nodes:
                        visited_nodes.add(other)
                        next_frontier.add(other)
            frontier = next_frontier
            if not frontier:
                break

        nodes = []
        for nid in visited_nodes:
            node = self.get_node(nid)
            if node:
                nodes.append(node)

        return nodes, all_edges

    @staticmethod
    def _row_to_edge(row: sqlite3.Row) -> Edge:
        meta = json.loads(row["metadata"]) if row["metadata"] else None
        return Edge(
            id=row["id"], source_id=row["source_id"], target_id=row["target_id"],
            type=row["type"], weight=row["weight"], metadata=meta,
            created_at=row["created_at"],
        )

    # --- Embeddings ---

    def store_embedding(self, node_id: str, vector: np.ndarray, model: str):
        from project_kg.models import _now
        self.conn.execute(
            """INSERT OR REPLACE INTO embeddings (node_id, vector, model, created_at)
               VALUES (?, ?, ?, ?)""",
            (node_id, vector.astype(np.float32).tobytes(), model, _now()),
        )
        self.conn.commit()

    def get_all_embeddings(self, node_ids: list[str] | None = None) -> list[tuple[str, np.ndarray]]:
        if node_ids:
            placeholders = ",".join("?" for _ in node_ids)
            rows = self.conn.execute(
                f"SELECT node_id, vector FROM embeddings WHERE node_id IN ({placeholders})",
                node_ids,
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT e.node_id, e.vector FROM embeddings e "
                "JOIN nodes n ON e.node_id = n.id WHERE n.archived = 0"
            ).fetchall()
        return [(row["node_id"], np.frombuffer(row["vector"], dtype=np.float32)) for row in rows]

    # --- FTS ---

    def search_fts(self, query: str, limit: int = 10,
                   type_filter: str | None = None,
                   project_filter: str | None = None) -> list[tuple[str, float]]:
        """Returns (node_id, bm25_score) pairs. Lower bm25 = better match."""
        sql = """
            SELECT n.id, bm25(nodes_fts) as score
            FROM nodes_fts fts
            JOIN nodes n ON n.rowid = fts.rowid
            WHERE nodes_fts MATCH ? AND n.archived = 0
        """
        params: list = [query]
        if type_filter:
            sql += " AND n.type = ?"
            params.append(type_filter)
        if project_filter:
            sql += " AND n.project = ?"
            params.append(project_filter)
        sql += " ORDER BY score LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [(row["id"], row["score"]) for row in rows]

    # --- Sync State ---

    def get_sync_state(self, connector: str, source_key: str) -> SyncState | None:
        row = self.conn.execute(
            "SELECT * FROM sync_state WHERE connector = ? AND source_key = ?",
            (connector, source_key),
        ).fetchone()
        if row is None:
            return None
        return SyncState(
            connector=row["connector"], source_key=row["source_key"],
            last_sync=row["last_sync"], cursor=row["cursor"],
        )

    def set_sync_state(self, state: SyncState):
        self.conn.execute(
            """INSERT OR REPLACE INTO sync_state (connector, source_key, last_sync, cursor)
               VALUES (?, ?, ?, ?)""",
            (state.connector, state.source_key, state.last_sync, state.cursor),
        )
        self.conn.commit()

    # --- Stats ---

    def get_stats(self) -> dict:
        type_counts = self.conn.execute(
            "SELECT type, COUNT(*) as cnt FROM nodes WHERE archived = 0 GROUP BY type"
        ).fetchall()
        project_counts = self.conn.execute(
            "SELECT project, COUNT(*) as cnt FROM nodes WHERE archived = 0 AND project IS NOT NULL GROUP BY project"
        ).fetchall()
        total = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM nodes WHERE archived = 0"
        ).fetchone()["cnt"]
        recent = self.conn.execute(
            "SELECT id, type, title, updated_at FROM nodes WHERE archived = 0 ORDER BY updated_at DESC LIMIT 5"
        ).fetchall()
        sync_states = self.conn.execute("SELECT * FROM sync_state").fetchall()

        return {
            "total_nodes": total,
            "by_type": {r["type"]: r["cnt"] for r in type_counts},
            "by_project": {r["project"]: r["cnt"] for r in project_counts},
            "recent": [{"id": r["id"], "type": r["type"], "title": r["title"], "updated_at": r["updated_at"]} for r in recent],
            "sync": [{"connector": r["connector"], "source_key": r["source_key"], "last_sync": r["last_sync"]} for r in sync_states],
        }
