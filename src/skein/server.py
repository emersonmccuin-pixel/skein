from __future__ import annotations

import argparse
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from skein.config import SkeinConfig
from skein.db import SkeinDB
from skein.embeddings import EmbeddingEngine
from skein.models import Node, Edge, _now
from skein import search as search_module


@dataclass
class SkeinContext:
    db: SkeinDB
    embeddings: EmbeddingEngine
    config: SkeinConfig


def create_lifespan(config: SkeinConfig):
    @asynccontextmanager
    async def lifespan(server: FastMCP) -> AsyncIterator[SkeinContext]:
        db = SkeinDB(config.db_path)
        embeddings = EmbeddingEngine(config.embedding_model)
        ctx = SkeinContext(db=db, embeddings=embeddings, config=config)
        register_tools(server, ctx)
        try:
            yield ctx
        finally:
            db.close()
    return lifespan


def register_tools(server: FastMCP, ctx: SkeinContext):

    @server.tool(
        name="skein_search",
        description=(
            "Search the Skein knowledge graph. Combines full-text search (BM25) with "
            "semantic vector similarity for ranked results. Use this to find decisions, "
            "patterns, discoveries, and other knowledge nodes."
        ),
    )
    def skein_search(
        query: Annotated[str, Field(description="Search query — keywords or natural language")],
        type: Annotated[str | None, Field(description="Filter by node type: decision, pattern, discovery, work_item, document, commit, note")] = None,
        project: Annotated[str | None, Field(description="Filter by project name")] = None,
        limit: Annotated[int, Field(description="Max results to return", ge=1, le=50)] = 10,
    ) -> list[dict]:
        results = search_module.search(
            ctx.db, ctx.embeddings, query,
            limit=limit, type_filter=type, project_filter=project,
        )
        return [
            {
                "id": r.node.id,
                "type": r.node.type,
                "title": r.node.title,
                "body": r.node.body[:500] + ("..." if len(r.node.body) > 500 else ""),
                "source": r.node.source,
                "project": r.node.project,
                "score": round(r.score, 4),
                "updated_at": r.node.updated_at,
            }
            for r in results
        ]

    @server.tool(
        name="skein_get",
        description=(
            "Get a knowledge node and its graph neighborhood. Returns the node plus "
            "connected nodes up to `depth` hops away, along with all edges between them."
        ),
    )
    def skein_get(
        id: Annotated[str, Field(description="Node ID (uuid)")],
        depth: Annotated[int, Field(description="How many hops to traverse", ge=0, le=3)] = 1,
    ) -> dict:
        node = ctx.db.get_node(id)
        if not node:
            return {"error": f"Node {id} not found"}

        if depth == 0:
            return {"node": node.to_dict(), "neighbors": [], "edges": []}

        nodes, edges = ctx.db.get_neighbors(id, depth=depth)
        return {
            "node": node.to_dict(),
            "neighbors": [n.to_dict() for n in nodes if n.id != id],
            "edges": [e.to_dict() for e in edges],
        }

    @server.tool(
        name="skein_add",
        description=(
            "Add a knowledge node to the graph. Automatically generates a vector embedding "
            "for semantic search. Optionally create edges to existing nodes in the same call."
        ),
    )
    def skein_add(
        type: Annotated[str, Field(description="Node type: decision, pattern, discovery, work_item, document, commit, note")],
        title: Annotated[str, Field(description="Short title for the node")],
        body: Annotated[str, Field(description="Full content — markdown supported")],
        source: Annotated[str, Field(description="Where this knowledge came from")] = "manual",
        source_id: Annotated[str | None, Field(description="ID in the source system")] = None,
        source_uri: Annotated[str | None, Field(description="URI back to the source")] = None,
        project: Annotated[str | None, Field(description="Project this belongs to")] = None,
        edges: Annotated[list[dict] | None, Field(description="Edges to create: [{target_id, type, weight?}]")] = None,
    ) -> dict:
        node_id = str(uuid.uuid4())
        now = _now()
        node = Node(
            id=node_id, type=type, title=title, body=body,
            source=source, source_id=source_id, source_uri=source_uri,
            project=project, created_at=now, updated_at=now,
        )
        ctx.db.insert_node(node)

        # Generate and store embedding
        embed_text = f"{title}\n\n{body}"
        vector = ctx.embeddings.embed(embed_text)
        ctx.db.store_embedding(node_id, vector, ctx.embeddings.model_name)

        # Create edges if provided
        created_edges = []
        if edges:
            for edge_spec in edges:
                edge = Edge(
                    id=str(uuid.uuid4()),
                    source_id=node_id,
                    target_id=edge_spec["target_id"],
                    type=edge_spec["type"],
                    weight=edge_spec.get("weight", 1.0),
                    created_at=now,
                )
                ctx.db.insert_edge(edge)
                created_edges.append(edge.to_dict())

        return {"id": node_id, "title": title, "edges_created": len(created_edges)}

    @server.tool(
        name="skein_connect",
        description="Create an edge between two existing knowledge nodes.",
    )
    def skein_connect(
        source_id: Annotated[str, Field(description="Source node ID")],
        target_id: Annotated[str, Field(description="Target node ID")],
        type: Annotated[str, Field(description="Edge type: depends_on, informed_by, supersedes, relates_to, implements, extracted_from")],
        weight: Annotated[float, Field(description="Edge weight (0-1)", ge=0, le=10)] = 1.0,
    ) -> dict:
        # Verify both nodes exist
        if not ctx.db.get_node(source_id):
            return {"error": f"Source node {source_id} not found"}
        if not ctx.db.get_node(target_id):
            return {"error": f"Target node {target_id} not found"}

        edge = Edge(
            id=str(uuid.uuid4()),
            source_id=source_id,
            target_id=target_id,
            type=type,
            weight=weight,
            created_at=_now(),
        )
        ctx.db.insert_edge(edge)
        return {"id": edge.id, "source_id": source_id, "target_id": target_id, "type": type}

    @server.tool(
        name="skein_sync",
        description=(
            "Run connectors to ingest data from external sources into the knowledge graph. "
            "Currently supports: 'wcp' (Work Context Protocol items). "
            "Incremental by default — only processes items modified since last sync."
        ),
    )
    def skein_sync(
        connector: Annotated[str | None, Field(description="Which connector to run: 'wcp', or None for all")] = None,
        full: Annotated[bool, Field(description="If true, re-sync everything (ignore last sync time)")] = False,
    ) -> dict:
        from skein.connectors.wcp import WCPConnector

        all_results = []

        if connector in (None, "wcp"):
            if not ctx.config.wcp_data_path:
                return {"error": "wcp_data_path not configured in skein.yaml"}
            wcp = WCPConnector(ctx.config.wcp_data_path)
            results = wcp.sync(ctx.db, ctx.embeddings, full=full)
            all_results.extend(r.to_dict() for r in results)

        if connector and connector not in ("wcp",):
            return {"error": f"Unknown connector: {connector}. Available: wcp"}

        total_created = sum(r.get("nodes_created", 0) for r in all_results)
        total_updated = sum(r.get("nodes_updated", 0) for r in all_results)
        total_edges = sum(r.get("edges_created", 0) for r in all_results)

        return {
            "summary": {
                "nodes_created": total_created,
                "nodes_updated": total_updated,
                "edges_created": total_edges,
            },
            "by_source": all_results,
        }

    @server.tool(
        name="skein_status",
        description=(
            "Get an overview of the knowledge graph: total nodes, counts by type and project, "
            "recently updated nodes, and connector sync status."
        ),
    )
    def skein_status() -> dict:
        return ctx.db.get_stats()


def main():
    parser = argparse.ArgumentParser(description="Skein Knowledge Graph MCP Server")
    parser.add_argument("--config", type=str, help="Path to skein.yaml config file")
    parser.add_argument("--transport", type=str, default="stdio", help="Transport: stdio, sse, streamable-http")
    parser.add_argument("--port", type=int, default=8111, help="Port for HTTP transports")
    args = parser.parse_args()

    config = SkeinConfig.load(args.config)
    server = FastMCP("Skein", lifespan=create_lifespan(config))

    if args.transport in ("sse", "streamable-http"):
        server.run(transport=args.transport, host="127.0.0.1", port=args.port)
    else:
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
