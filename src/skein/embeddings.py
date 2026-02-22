from __future__ import annotations

import numpy as np


class EmbeddingEngine:
    """Wraps fastembed for local ONNX-based text embeddings."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):
        self.model_name = model_name
        self._model = None

    def _get_model(self):
        if self._model is None:
            from fastembed import TextEmbedding
            self._model = TextEmbedding(model_name=self.model_name)
        return self._model

    def embed(self, text: str) -> np.ndarray:
        model = self._get_model()
        results = list(model.embed([text]))
        return np.array(results[0], dtype=np.float32)

    def embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        if not texts:
            return []
        model = self._get_model()
        return [np.array(v, dtype=np.float32) for v in model.embed(texts)]

    @staticmethod
    def cosine_similarity(query_vec: np.ndarray, vectors: np.ndarray) -> np.ndarray:
        """Compute cosine similarity between query and a matrix of vectors.

        Args:
            query_vec: 1D array (384,)
            vectors: 2D array (N, 384)

        Returns:
            1D array of similarities (N,)
        """
        if vectors.ndim == 1:
            vectors = vectors.reshape(1, -1)
        query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-10)
        vec_norms = vectors / (np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-10)
        return vec_norms @ query_norm

    @staticmethod
    def search_vectors(
        query_vec: np.ndarray,
        node_ids: list[str],
        vectors: list[np.ndarray],
        limit: int = 10,
    ) -> list[tuple[str, float]]:
        """Brute-force vector search. Returns (node_id, similarity) sorted descending."""
        if not vectors:
            return []
        mat = np.stack(vectors)
        sims = EmbeddingEngine.cosine_similarity(query_vec, mat)
        top_k = min(limit, len(sims))
        indices = np.argpartition(sims, -top_k)[-top_k:]
        indices = indices[np.argsort(sims[indices])[::-1]]
        return [(node_ids[i], float(sims[i])) for i in indices]
