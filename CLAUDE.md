# Skein — Claude Code Instructions

## Work Tracking (CRITICAL)

This project is tracked in WCP namespace `SKEIN`.

**When the user asks "where are we", "status", "what's next", or starts a new session:** immediately call `wcp_list` with namespace `SKEIN` and `wcp_get` on active items to load current state. Do this BEFORE responding.

- `wcp_list` with namespace `SKEIN` — see all work items and their status
- `wcp_get` on active items — full context, body, and activity log
- `wcp_comment` — log session progress before ending a session
- `wcp_update` — change item status as work progresses

## Project Overview

Skein is a knowledge graph system for AI-assisted knowledge work. It captures decisions, context, and discoveries across projects and surfaces relevant connections when you need them.

**Architecture:**
- **WCP** feeds structured work items and activity logs into Skein
- **SQLite** stores entities and explicit relationships
- **Vector store** enables semantic similarity search across all knowledge
- **AI agents** consume context from Skein to inform their work

## Tech Stack

- **Python 3.11+** with hatchling build
- **FastMCP** — MCP server (stdio transport)
- **SQLite** with FTS5 — nodes, edges, embeddings, sync state
- **fastembed** (BAAI/bge-small-en-v1.5) — local ONNX embeddings, 384 dims
- **NumPy** — brute-force cosine similarity

## Project Structure

```
src/skein/
  __init__.py        # re-exports main
  __main__.py        # python -m skein entry point
  server.py          # FastMCP server, 5 tools, lifespan pattern
  db.py              # SkeinDB — SQLite schema, CRUD, FTS5, embeddings
  models.py          # Node, Edge, SearchResult, SyncState dataclasses
  search.py          # Combined FTS + vector search with score fusion
  embeddings.py      # EmbeddingEngine — fastembed wrapper
  config.py          # SkeinConfig — loads skein.yaml
  connectors/        # Phase 2+ — WCP, git, filesystem connectors
```

## Commands

```bash
uv run python -m skein                    # Start MCP server (stdio)
uv run python -m skein --transport sse    # Start with SSE transport
uv sync                                  # Install/update deps
```

## MCP Tools

| Tool | Purpose |
|------|---------|
| `skein_search` | FTS + vector similarity search, filtered by type/project |
| `skein_get` | Get node + graph neighborhood (N hops) |
| `skein_add` | Add node with auto-embedding, optional edges |
| `skein_connect` | Create edge between two nodes |
| `skein_status` | Counts by type/project, recent nodes, sync state |

## Quick Reference

- **Location:** `e:/Claude Code Projects/Personal Projects/Skein`
- **Namespace:** `SKEIN`
- **DB file:** `./skein.db` (created on first run)
- **Config:** `./skein.yaml` (optional, has defaults)
