"""
Episodic Vector Store Module.
Provides lightweight, local SQLite-backed vector storage and semantic retrieval
for personal long-term chat history archives.
"""

import os
import re
import json
import math
import sqlite3
import logging
from datetime import datetime
from collections import Counter
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Computes cosine similarity between two float vectors."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot_product / (norm1 * norm2)


def tokenize_text(text: str) -> List[str]:
    """
    Tokenizes text into alphanumeric words and Chinese unigrams + bigrams.
    Zero third-party dictionary dependency, robust for multilingual chat history.
    """
    if not text:
        return []
    tokens = []
    chunks = re.findall(r'[a-zA-Z0-9]+|[\u4e00-\u9fff]+', text.lower())
    for chunk in chunks:
        if re.match(r'^[a-zA-Z0-9]+$', chunk):
            tokens.append(chunk)
        else:
            chars = list(chunk)
            tokens.extend(chars)
            for i in range(len(chars) - 1):
                tokens.append(chars[i] + chars[i+1])
    return tokens


class EpisodicVectorStore:
    """
    Manages historical chat episodes storage and hybrid semantic retrieval.
    Stored in a single local SQLite database file with embeddings and BM25 indexing.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        mem_cfg = config.get("memory", {})
        episodic_cfg = mem_cfg.get("episodic", {})

        self.enabled = episodic_cfg.get("enabled", True)
        self.top_k = episodic_cfg.get("top_k", 3)
        self.min_score = episodic_cfg.get("min_score", 0.15)
        self.storage_dir = episodic_cfg.get("storage_dir", "logs/vector_db")
        self.db_path = os.path.join(self.storage_dir, "episodes.db")

        # Hybrid Search configuration
        self.search_mode = episodic_cfg.get("search_mode", "hybrid")  # hybrid | hybrid_rrf | vector | bm25
        hybrid_cfg = episodic_cfg.get("hybrid", {})
        self.bm25_weight = hybrid_cfg.get("bm25_weight", 0.5)
        self.vector_weight = hybrid_cfg.get("vector_weight", 0.5)
        self.rrf_k = hybrid_cfg.get("rrf_k", 60)

        if self.enabled:
            os.makedirs(self.storage_dir, exist_ok=True)
            self._init_db()

    def _init_db(self):
        """Initializes SQLite tables for episodes and metadata."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS episodes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        contact_name TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        content TEXT NOT NULL,
                        summary TEXT,
                        embedding_json TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_contact ON episodes(contact_name)")
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize episodic database: {e}")

    def get_embedding(self, text: str) -> List[float]:
        """
        Generates vector embedding for text.
        Attempts Vertex AI / Gemini API, falls back to OpenAI / Agnes,
        and finally falls back to local TF-IDF hash embedding if API is unavailable.
        """
        if not text or not text.strip():
            return [0.0] * 64

        clean_text = text.strip()[:1000]

        # 1. Try Vertex AI / Gemini Embedding
        primary_cfg = self.config.get("llm", {}).get("primary", {})
        project_id = primary_cfg.get("project_id")
        location = primary_cfg.get("location", "us-central1")

        # Normalize location for embeddings: 'global' is not supported by text-embedding-004
        embed_location = location if location != "global" else "us-central1"

        try:
            from google import genai
            if primary_cfg.get("provider") == "vertex_ai" and project_id and project_id != "YOUR_GCP_PROJECT_ID":
                client = genai.Client(vertexai=True, project=project_id, location=embed_location)
            else:
                client = genai.Client()
            
            res = client.models.embed_content(model="text-embedding-004", contents=clean_text)
            if hasattr(res, "embeddings") and res.embeddings:
                return list(res.embeddings[0].values)
        except Exception as e:
            logger.debug(f"Gemini embedding call skipped/failed: {e}")

        # 2. Try OpenAI / Agnes Embedding
        backup_cfg = self.config.get("llm", {}).get("backup", {})
        api_key = backup_cfg.get("api_key")
        if api_key and api_key != "YOUR_OPENAI_API_KEY":
            try:
                from openai import OpenAI
                client = OpenAI(api_key=api_key, base_url=backup_cfg.get("base_url"))
                resp = client.embeddings.create(model="text-embedding-3-small", input=clean_text)
                if resp.data and len(resp.data) > 0:
                    return list(resp.data[0].embedding)
            except Exception as e:
                logger.debug(f"OpenAI embedding call skipped/failed: {e}")

        # 3. Deterministic Local N-gram Hash Embedding Fallback (Zero Dependency)
        # Produces a stable 1024-dimensional vector based on char n-grams
        return self._local_hash_embedding(clean_text, dim=1024)

    def _local_hash_embedding(self, text: str, dim: int = 1024) -> List[float]:
        """Computes a normalized, deterministic character unigram + bigram hash vector."""
        vec = [0.0] * dim
        t = text.lower()
        # Unigram features (weight 0.5)
        for char in t:
            if not char.isspace():
                idx = abs(hash(char)) % dim
                vec[idx] += 0.5
        # Bigram features (weight 1.0)
        for i in range(len(t) - 1):
            gram = t[i:i+2]
            idx = abs(hash(gram)) % dim
            vec[idx] += 1.0
        # Normalize
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec

    def add_episode(
        self,
        contact_name: str,
        timestamp: str,
        content: str,
        summary: str = ""
    ) -> bool:
        """
        Saves a conversation chunk into the episodic vector store.
        """
        if not self.enabled or not content or not content.strip():
            return False

        try:
            # Generate embedding over summary + content
            text_to_embed = f"{summary}\n{content}" if summary else content
            embedding = self.get_embedding(text_to_embed)
            embedding_json = json.dumps(embedding)

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO episodes (contact_name, timestamp, content, summary, embedding_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (contact_name, timestamp, content.strip(), summary.strip(), embedding_json, now_str))
                conn.commit()

            logger.info(f"Episodic memory saved for [{contact_name}] at {timestamp}.")
            return True
        except Exception as e:
            logger.error(f"Failed to add episode for [{contact_name}]: {e}")
            return False

    def search(
        self,
        query: str,
        contact_name: str,
        top_k: Optional[int] = None,
        min_score: Optional[float] = None,
        search_mode: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Searches historical episodes for a specific contact matching query.
        Supports:
          - 'hybrid': Weighted Normalized Score Fusion (BM25 + Dense Vector, default)
          - 'hybrid_rrf': Reciprocal Rank Fusion (Standard RRF)
          - 'vector': Pure Dense Vector Cosine Similarity
          - 'bm25': Pure Sparse Keyword Search
        Returns sorted list of matching records.
        """
        if not self.enabled or not query or not query.strip():
            return []

        k = top_k or self.top_k
        threshold = min_score if min_score is not None else self.min_score
        mode = search_mode or self.search_mode
        clean_query = query.strip()

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, timestamp, content, summary, embedding_json
                    FROM episodes
                    WHERE contact_name = ?
                """, (contact_name,))
                rows = cursor.fetchall()

            if not rows:
                return []

            docs = []
            for row in rows:
                ep_id, timestamp, content, summary, emb_str = row
                try:
                    emb = json.loads(emb_str) if emb_str else []
                except Exception:
                    emb = []
                docs.append({
                    "id": ep_id,
                    "timestamp": timestamp,
                    "content": content,
                    "summary": summary or "",
                    "embedding": emb
                })

            # --- 1. Mode: Pure Vector Search ---
            if mode == "vector":
                query_vec = self.get_embedding(clean_query)
                scored = []
                for d in docs:
                    sim = cosine_similarity(query_vec, d["embedding"]) if d["embedding"] else 0.0
                    if sim >= threshold:
                        scored.append({
                            "id": d["id"],
                            "timestamp": d["timestamp"],
                            "content": d["content"],
                            "summary": d["summary"],
                            "score": round(sim, 4),
                            "vec_score": round(sim, 4),
                            "bm25_score": 0.0
                        })
                scored.sort(key=lambda x: x["score"], reverse=True)
                return scored[:k]

            # --- BM25 Tokenization & Setup for Lexical / Hybrid Modes ---
            query_tokens = tokenize_text(clean_query)
            doc_tokens = [tokenize_text(f"{d['summary']} {d['content']}") for d in docs]
            doc_lens = [len(toks) for toks in doc_tokens]
            N = len(docs)
            avgdl = sum(doc_lens) / N if N > 0 else 1.0

            df = Counter()
            for toks in doc_tokens:
                for t in set(toks):
                    df[t] += 1

            def _bm25_score(q_tokens: List[str], doc_idx: int, k1: float = 1.5, b: float = 0.75) -> float:
                toks = doc_tokens[doc_idx]
                tf = Counter(toks)
                dl = doc_lens[doc_idx]
                score = 0.0
                for q in q_tokens:
                    if q not in tf:
                        continue
                    n_q = df.get(q, 0)
                    idf = math.log(1.0 + (N - n_q + 0.5) / (n_q + 0.5))
                    freq = tf[q]
                    tf_comp = (freq * (k1 + 1.0)) / (freq + k1 * (1.0 - b + b * (dl / avgdl)))
                    score += idf * tf_comp
                return score

            bm25_scores = [_bm25_score(query_tokens, i) for i in range(N)]

            # --- 2. Mode: Pure BM25 Search ---
            if mode == "bm25":
                scored = []
                for idx, d in enumerate(docs):
                    bm_s = bm25_scores[idx]
                    if bm_s > 0.0:
                        scored.append({
                            "id": d["id"],
                            "timestamp": d["timestamp"],
                            "content": d["content"],
                            "summary": d["summary"],
                            "score": round(bm_s, 4),
                            "vec_score": 0.0,
                            "bm25_score": round(bm_s, 4)
                        })
                scored.sort(key=lambda x: x["score"], reverse=True)
                return scored[:k]

            # Compute Vector similarities for Hybrid Modes
            query_vec = self.get_embedding(clean_query)
            vec_sims = [
                cosine_similarity(query_vec, d["embedding"]) if d["embedding"] else 0.0
                for d in docs
            ]

            # --- 3. Mode: Hybrid RRF (Reciprocal Rank Fusion) ---
            if mode == "hybrid_rrf":
                # Compute vector rank
                vec_ranked = sorted(enumerate(vec_sims), key=lambda x: x[1], reverse=True)
                vec_rank_map = {idx: rank for rank, (idx, sim) in enumerate(vec_ranked, 1) if sim >= threshold}

                # Compute BM25 rank
                bm25_ranked = sorted(enumerate(bm25_scores), key=lambda x: x[1], reverse=True)
                bm25_rank_map = {idx: rank for rank, (idx, s) in enumerate(bm25_ranked, 1) if s > 0.0}

                candidate_indices = set(vec_rank_map.keys()) | set(bm25_rank_map.keys())
                rrf_list = []
                for idx in candidate_indices:
                    r_vec = vec_rank_map.get(idx)
                    r_bm = bm25_rank_map.get(idx)
                    s_vec = (self.vector_weight / (self.rrf_k + r_vec)) if r_vec is not None else 0.0
                    s_bm = (self.bm25_weight / (self.rrf_k + r_bm)) if r_bm is not None else 0.0
                    total_rrf = s_vec + s_bm
                    d = docs[idx]
                    rrf_list.append({
                        "id": d["id"],
                        "timestamp": d["timestamp"],
                        "content": d["content"],
                        "summary": d["summary"],
                        "score": round(total_rrf, 5),
                        "vec_score": round(vec_sims[idx], 4),
                        "bm25_score": round(bm25_scores[idx], 4)
                    })
                rrf_list.sort(key=lambda x: x["score"], reverse=True)
                return rrf_list[:k]

            # --- 4. Mode: Hybrid Score Fusion (Normalized Weighted Linear Fusion, Default) ---
            # Automatically adjusts weight based on query length:
            # - Short keyword queries (<= 4 chars) prioritize BM25 lexical precision (60% BM25, 40% Vector)
            # - Longer conversational queries prioritize Vector semantics (60% Vector, 40% BM25)
            max_bm = max(bm25_scores) if bm25_scores else 1.0
            if max_bm <= 0.0:
                max_bm = 1.0

            if len(clean_query) <= 4:
                w_bm = 0.6
                w_vec = 0.4
            else:
                w_bm = 0.4
                w_vec = 0.6

            hybrid_list = []
            for idx, d in enumerate(docs):
                norm_bm = bm25_scores[idx] / max_bm if max_bm > 0 else 0.0
                v_sim = max(0.0, vec_sims[idx])
                combined_score = (w_vec * v_sim) + (w_bm * norm_bm)

                if combined_score >= threshold:
                    hybrid_list.append({
                        "id": d["id"],
                        "timestamp": d["timestamp"],
                        "content": d["content"],
                        "summary": d["summary"],
                        "score": round(combined_score, 4),
                        "vec_score": round(v_sim, 4),
                        "bm25_score": round(bm25_scores[idx], 4)
                    })

            hybrid_list.sort(key=lambda x: x["score"], reverse=True)
            return hybrid_list[:k]

        except Exception as e:
            logger.error(f"Error searching episodic memory for [{contact_name}]: {e}")
            return []

    def get_contact_episodes_count(self, contact_name: str) -> int:
        """Returns total number of stored episodes for a given contact."""
        if not self.enabled:
            return 0
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM episodes WHERE contact_name = ?", (contact_name,))
                row = cursor.fetchone()
                return row[0] if row else 0
        except Exception:
            return 0
