from __future__ import annotations

import uuid
from pathlib import Path

import frontmatter

from project_kg.connectors.base import Connector, SyncResult
from project_kg.db import KGDB
from project_kg.embeddings import EmbeddingEngine
from project_kg.models import Node, Edge, SyncState, _now

ACTIVITY_SEPARATOR = "---\n\n## Activity"


def parse_wcp_file(path: Path) -> dict:
    """Parse a WCP markdown file into frontmatter, body, and activity log."""
    raw = path.read_text(encoding="utf-8")
    post = frontmatter.loads(raw)
    content = post.content

    sep_idx = content.find(ACTIVITY_SEPARATOR)
    if sep_idx == -1:
        body = content.strip()
        activity = ""
    else:
        body = content[:sep_idx].strip()
        activity = content[sep_idx + len(ACTIVITY_SEPARATOR):].strip()

    return {
        "frontmatter": dict(post.metadata),
        "body": body,
        "activity": activity,
    }


class WCPConnector(Connector):
    name = "wcp"

    def __init__(self, data_path: str | Path):
        self.data_path = Path(data_path)

    def sync(
        self,
        db: KGDB,
        embeddings: EmbeddingEngine,
        full: bool = False,
    ) -> list[SyncResult]:
        if not self.data_path.exists():
            return [SyncResult(connector=self.name, source_key="*",
                               errors=[f"WCP data path not found: {self.data_path}"])]

        results = []
        for ns_dir in sorted(self.data_path.iterdir()):
            if not ns_dir.is_dir() or ns_dir.name.startswith("."):
                continue
            result = self._sync_namespace(db, embeddings, ns_dir, full=full)
            results.append(result)

        return results

    def _sync_namespace(
        self,
        db: KGDB,
        embeddings: EmbeddingEngine,
        ns_dir: Path,
        full: bool,
    ) -> SyncResult:
        namespace = ns_dir.name
        result = SyncResult(connector=self.name, source_key=namespace)

        sync_state = db.get_sync_state(self.name, namespace)
        last_sync = sync_state.last_sync if sync_state and not full else None

        md_files = sorted(ns_dir.glob("*.md"))

        for md_path in md_files:
            if last_sync and not full:
                mtime = md_path.stat().st_mtime
                import datetime
                file_time = datetime.datetime.fromtimestamp(mtime, tz=datetime.timezone.utc).isoformat()
                if file_time < last_sync:
                    continue

            try:
                self._sync_work_item(db, embeddings, md_path, namespace, result)
            except Exception as e:
                result.errors.append(f"{md_path.name}: {e}")

        for item_dir in sorted(ns_dir.iterdir()):
            if not item_dir.is_dir():
                continue
            for artifact_path in sorted(item_dir.glob("*.md")):
                if last_sync and not full:
                    mtime = artifact_path.stat().st_mtime
                    import datetime
                    file_time = datetime.datetime.fromtimestamp(mtime, tz=datetime.timezone.utc).isoformat()
                    if file_time < last_sync:
                        continue
                try:
                    self._sync_artifact(db, embeddings, artifact_path, namespace, item_dir.name, result)
                except Exception as e:
                    result.errors.append(f"{artifact_path}: {e}")

        now = _now()
        db.set_sync_state(SyncState(
            connector=self.name,
            source_key=namespace,
            last_sync=now,
            cursor=now,
        ))

        return result

    def _sync_work_item(
        self,
        db: KGDB,
        embeddings: EmbeddingEngine,
        md_path: Path,
        namespace: str,
        result: SyncResult,
    ):
        parsed = parse_wcp_file(md_path)
        fm = parsed["frontmatter"]
        item_id = fm.get("id", md_path.stem)

        body_parts = [parsed["body"]]
        if parsed["activity"]:
            body_parts.append(f"\n\n## Activity\n\n{parsed['activity']}")
        full_body = "\n".join(body_parts)

        node = Node(
            id=str(uuid.uuid4()),
            type="work_item",
            title=f"[{item_id}] {fm.get('title', md_path.stem)}",
            body=full_body,
            source="wcp",
            source_id=item_id,
            source_uri=str(md_path),
            project=namespace,
            created_at=_date_to_iso(fm.get("created")),
            updated_at=_date_to_iso(fm.get("updated")),
        )

        node, created = db.upsert_node(node)
        if created:
            result.nodes_created += 1
        else:
            result.nodes_updated += 1

        embed_text = f"{node.title}\n\n{parsed['body']}"
        vector = embeddings.embed(embed_text)
        db.store_embedding(node.id, vector, embeddings.model_name)

        parent_id = fm.get("parent")
        if parent_id:
            parent_node = db.find_node_by_source("wcp", parent_id)
            if parent_node:
                edge = Edge(
                    id=str(uuid.uuid4()),
                    source_id=node.id,
                    target_id=parent_node.id,
                    type="depends_on",
                    created_at=_now(),
                )
                db.upsert_edge(edge)
                result.edges_created += 1

    def _sync_artifact(
        self,
        db: KGDB,
        embeddings: EmbeddingEngine,
        artifact_path: Path,
        namespace: str,
        parent_callsign: str,
        result: SyncResult,
    ):
        content = artifact_path.read_text(encoding="utf-8")
        source_id = f"{parent_callsign}/{artifact_path.name}"

        title = artifact_path.stem.replace("-", " ").title()
        for line in content.split("\n"):
            if line.startswith("# "):
                title = line[2:].strip()
                break

        node = Node(
            id=str(uuid.uuid4()),
            type="document",
            title=title,
            body=content,
            source="wcp",
            source_id=source_id,
            source_uri=str(artifact_path),
            project=namespace,
        )

        node, created = db.upsert_node(node)
        if created:
            result.nodes_created += 1
        else:
            result.nodes_updated += 1

        embed_text = f"{node.title}\n\n{content[:2000]}"
        vector = embeddings.embed(embed_text)
        db.store_embedding(node.id, vector, embeddings.model_name)

        parent_node = db.find_node_by_source("wcp", parent_callsign)
        if parent_node:
            edge = Edge(
                id=str(uuid.uuid4()),
                source_id=parent_node.id,
                target_id=node.id,
                type="relates_to",
                created_at=_now(),
            )
            db.upsert_edge(edge)
            result.edges_created += 1


def _date_to_iso(val) -> str:
    """Convert WCP date values (str or date object) to ISO string."""
    if val is None:
        return _now()
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return str(val)
