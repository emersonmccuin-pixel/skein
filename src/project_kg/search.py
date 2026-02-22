from __future__ import annotations

from project_kg.db import KGDB
from project_kg.embeddings import EmbeddingEngine
from project_kg.models import SearchResult

# Weights for combining FTS and vector scores
FTS_WEIGHT = 0.4
VECTOR_WEIGHT = 0.6


def search(
    db: KGDB,
    embeddings: EmbeddingEngine,
    query: str,
    limit: int = 10,
    type_filter: str | None = None,
    project_filter: str | None = None,
) -> list[SearchResult]:
    """Combined FTS + vector similarity search.

    Both signals are normalized to [0, 1] and combined with a weighted sum.
    """
    fts_results = _search_fts(db, query, limit=limit * 2,
                              type_filter=type_filter, project_filter=project_filter)
    vector_results = _search_vector(db, embeddings, query, limit=limit * 2,
                                    type_filter=type_filter, project_filter=project_filter)

    # Merge scores by node_id
    combined: dict[str, dict] = {}

    for node_id, score in fts_results:
        combined[node_id] = {"fts": score, "vector": 0.0}

    for node_id, score in vector_results:
        if node_id in combined:
            combined[node_id]["vector"] = score
        else:
            combined[node_id] = {"fts": 0.0, "vector": score}

    # Compute weighted scores
    scored: list[tuple[str, float]] = []
    for node_id, scores in combined.items():
        final = scores["fts"] * FTS_WEIGHT + scores["vector"] * VECTOR_WEIGHT
        scored.append((node_id, final))

    scored.sort(key=lambda x: x[1], reverse=True)
    scored = scored[:limit]

    # Fetch full nodes
    results: list[SearchResult] = []
    for node_id, score in scored:
        node = db.get_node(node_id)
        if node:
            results.append(SearchResult(node=node, score=score, match_type="combined"))

    return results


def _search_fts(
    db: KGDB, query: str, limit: int,
    type_filter: str | None, project_filter: str | None,
) -> list[tuple[str, float]]:
    """FTS5 search, returns (node_id, normalized_score) with scores in [0, 1]."""
    try:
        raw = db.search_fts(query, limit=limit,
                            type_filter=type_filter, project_filter=project_filter)
    except Exception:
        return []

    if not raw:
        return []

    raw_scores = [score for _, score in raw]
    min_score = min(raw_scores)
    max_score = max(raw_scores)
    score_range = max_score - min_score

    normalized: list[tuple[str, float]] = []
    for node_id, score in raw:
        if score_range > 0:
            norm = (max_score - score) / score_range
        else:
            norm = 1.0
        normalized.append((node_id, norm))

    return normalized


def _search_vector(
    db: KGDB, embeddings: EmbeddingEngine, query: str, limit: int,
    type_filter: str | None, project_filter: str | None,
) -> list[tuple[str, float]]:
    """Vector similarity search, returns (node_id, cosine_similarity)."""
    all_embeddings = db.get_all_embeddings()
    if not all_embeddings:
        return []

    if type_filter or project_filter:
        candidate_nodes = db.list_nodes(type_filter=type_filter, project_filter=project_filter, limit=10000)
        candidate_ids = {n.id for n in candidate_nodes}
        all_embeddings = [(nid, vec) for nid, vec in all_embeddings if nid in candidate_ids]

    if not all_embeddings:
        return []

    node_ids = [nid for nid, _ in all_embeddings]
    vectors = [vec for _, vec in all_embeddings]

    query_vec = embeddings.embed(query)

    results = EmbeddingEngine.search_vectors(query_vec, node_ids, vectors, limit=limit)
    return [(nid, (score + 1.0) / 2.0) for nid, score in results]
