# Project KG — Claude Code Instructions

## Work Tracking (CRITICAL)

This project is tracked in WCP namespace `KG`.

**When the user asks "where are we", "status", "what's next", or starts a new session:** immediately call `wcp_list` with namespace `KG` and `wcp_get` on active items to load current state. Do this BEFORE responding.

- `wcp_list` with namespace `KG` — see all work items and their status
- `wcp_get` on active items — full context, body, and activity log
- `wcp_comment` — log session progress before ending a session
- `wcp_update` — change item status as work progresses

## Project Overview

Project KG is a knowledge graph system for AI-assisted knowledge work. It passively captures context, decisions, and discoveries across projects, then surfaces relevant connections when you need them.

**Architecture:**
- **WCP** feeds structured work items and activity logs into Project KG
- **SQLite** stores entities and explicit relationships
- **Vector store** enables semantic similarity search across all knowledge
- **AI agents** consume context from Project KG to inform their work

## Tech Stack

- **Python 3.11+** with hatchling build
- **FastMCP** — MCP server (stdio transport)
- **SQLite** with FTS5 — nodes, edges, embeddings, sync state
- **fastembed** (BAAI/bge-small-en-v1.5) — local ONNX embeddings, 384 dims
- **NumPy** — brute-force cosine similarity

## Project Structure

```
src/project_kg/
  __init__.py        # re-exports main
  __main__.py        # python -m project_kg entry point
  server.py          # FastMCP server, 6 tools, lifespan pattern
  db.py              # KGDB — SQLite schema, CRUD, FTS5, embeddings
  models.py          # Node, Edge, SearchResult, SyncState dataclasses
  search.py          # Combined FTS + vector search with score fusion
  embeddings.py      # EmbeddingEngine — fastembed wrapper
  config.py          # KGConfig — loads kg.yaml
  connectors/        # Data connectors (WCP, future: git, filesystem)
```

## Commands

```bash
uv run python -m project_kg                    # Start MCP server (stdio)
uv run python -m project_kg --transport sse    # Start with SSE transport
uv sync                                        # Install/update deps
```

## MCP Tools

| Tool | Purpose |
|------|---------|
| `kg_search` | FTS + vector similarity search, filtered by type/project |
| `kg_get` | Get node + graph neighborhood (N hops) |
| `kg_add` | Add node with auto-embedding, optional edges |
| `kg_connect` | Create edge between two nodes |
| `kg_sync` | Run connectors to ingest external data |
| `kg_status` | Counts by type/project, recent nodes, sync state |

## Quick Reference

- **Location:** `e:/Claude Code Projects/Personal Projects/Skein` (folder retains old name)
- **Namespace:** `KG`
- **DB file:** `./kg.db` (created on first run)
- **Config:** `./kg.yaml` (optional, has defaults)
