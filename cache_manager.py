import re
import time
import hashlib
import logging
import statistics
from pathlib import Path
from typing import Dict, Any, Optional, List

CACHE_FILE = Path("semantic_cache.json")

class CacheManager:
    """
    Semantic Cache Proxy (CacheManager)
    Intercepts LLM routing requests to reduce latency and token costs via exact and semantic matching.
    """
    def __init__(self, logger, cache_version: str = "v1", ttl_seconds: int = 86400, threshold: float = 0.95):
        self.logger = logger
        self.cache_version = cache_version
        self.ttl_seconds = ttl_seconds
        self.threshold = threshold
        
        # In-memory stores simulating Redis (Exact) and Vector Store (Semantic)
        self.exact_store: Dict[str, dict] = {}
        self.vector_store: List[dict] = []
        
        # Telemetry
        self.metrics = {
            "total_requests": 0,
            "exact_hits": 0,
            "semantic_hits": 0,
            "misses": 0,
            "tokens_saved": 0,
            "latencies_hit": [],
            "latencies_miss": []
        }
        
        # Guardrails regex for dynamic entities (dates, times, UUIDs, IDs)
        self.guardrails_regex = re.compile(
            r'\b(\d{4}-\d{2}-\d{2}|\d{2}:\d{2}(:\d{2})?|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|order\s*#?\s*\d+)\b|'
            r'(сегодня|вчера|завтра|сейчас|today|yesterday|tomorrow|now)'
        )

    def _is_cacheable(self, text: str) -> bool:
        """Guardrails Filter: checks if the text contains dynamic context."""
        if self.guardrails_regex.search(text):
            return False
        return True

    def _get_embedding(self, text: str) -> List[float]:
        """
        Mock Embedding model.
        In production, replace with local 'bge-micro' or API 'text-embedding-3-small'.
        Generates a deterministic vector based on character frequencies for basic semantic similarity.
        """
        # Simple mock vector: 16 dimensions based on char counts
        vec = [0.0] * 16
        for char in text:
            vec[ord(char) % 16] += 1.0
        # Normalize vector
        norm = sum(v*v for v in vec)**0.5
        if norm == 0:
            return vec
        return [v / norm for v in vec]

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculates cosine similarity between two vectors."""
        dot_product = sum(v1 * v2 for v1, v2 in zip(vec1, vec2))
        norm1 = sum(v*v for v in vec1)**0.5
        norm2 = sum(v*v for v in vec2)**0.5
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot_product / (norm1 * norm2)

    def _get_cache_key(self, normalized_text: str, user_context: str = "global") -> str:
        """Generates composite key: [cache_version]:[user_context]:[hash]"""
        text_hash = hashlib.sha256(normalized_text.encode('utf-8')).hexdigest()
        return f"{self.cache_version}:{user_context}:{text_hash}"

    def lookup(self, normalized_text: str, user_context: str = "global") -> Optional[str]:
        """
        Two-level cache lookup.
        Returns the cached agent_key if found, else None.
        """
        start_time = time.time()
        self.metrics["total_requests"] += 1
        
        # Step 1: Guardrails Filter
        if not self._is_cacheable(normalized_text):
            self.logger.debug("CacheManager: Request non-cacheable (dynamic context). Pass-through.")
            self.metrics["misses"] += 1
            return None

        cache_key = self._get_cache_key(normalized_text, user_context)
        
        # Level 1: Exact Match (O(1))
        if cache_key in self.exact_store:
            entry = self.exact_store[cache_key]
            if time.time() - entry["timestamp"] < self.ttl_seconds:
                self.logger.info(f"CacheManager: EXACT HIT for key {cache_key[:20]}...")
                self.metrics["exact_hits"] += 1
                self.metrics["tokens_saved"] += len(normalized_text.split()) # Rough estimate
                self.metrics["latencies_hit"].append((time.time() - start_time) * 1000)
                return entry["agent_key"]
            else:
                # Expired
                del self.exact_store[cache_key]

        # Level 2: Semantic Match (KNN)
        query_vec = self._get_embedding(normalized_text)
        
        best_match_agent = None
        best_similarity = 0.0
        
        for entry in self.vector_store:
            if time.time() - entry["timestamp"] > self.ttl_seconds:
                continue # Skip expired
                
            # In a real Vector DB, this would be a KNN search filtered by user_context prefix
            if entry["user_context"] == user_context:
                sim = self._cosine_similarity(query_vec, entry["vector"])
                if sim > best_similarity:
                    best_similarity = sim
                    best_match_agent = entry["agent_key"]

        if best_match_agent and best_similarity >= self.threshold:
            self.logger.info(f"CacheManager: SEMANTIC HIT (Sim: {best_similarity:.4f})")
            self.metrics["semantic_hits"] += 1
            self.metrics["tokens_saved"] += len(normalized_text.split())
            self.metrics["latencies_hit"].append((time.time() - start_time) * 1000)
            
            # Write-back to exact cache for future O(1) hits
            self.exact_store[cache_key] = {
                "agent_key": best_match_agent,
                "timestamp": time.time()
            }
            return best_match_agent

        self.logger.debug("CacheManager: MISS. Passing to LLM Router.")
        self.metrics["misses"] += 1
        self.metrics["latencies_miss"].append((time.time() - start_time) * 1000)
        return None

    def write_back(self, normalized_text: str, agent_key: str, user_context: str = "global") -> None:
        """
        Writes successful routing results back to both cache levels.
        Does not cache errors or fallbacks.
        """
        if not self._is_cacheable(normalized_text):
            return
            
        if not agent_key or agent_key == "coding": # Assuming 'coding' is the fallback, do not cache
            self.logger.debug(f"CacheManager: Skipping write-back for fallback/error agent '{agent_key}'.")
            return

        cache_key = self._get_cache_key(normalized_text, user_context)
        timestamp = time.time()
        
        # Write to Exact Store
        self.exact_store[cache_key] = {
            "agent_key": agent_key,
            "timestamp": timestamp
        }
        
        # Write to Vector Store
        vec = self._get_embedding(normalized_text)
        self.vector_store.append({
            "vector": vec,
            "agent_key": agent_key,
            "user_context": user_context,
            "timestamp": timestamp,
            "exact_hash": cache_key # Link for potential invalidation
        })
        
        self.logger.debug(f"CacheManager: Write-back successful for agent '{agent_key}'.")

    def get_stats(self) -> Dict[str, Any]:
        """Returns collected telemetry metrics."""
        total = self.metrics["total_requests"]
        hit_ratio = (self.metrics["exact_hits"] + self.metrics["semantic_hits"]) / total * 100 if total > 0 else 0
        avg_latency_hit = statistics.mean(self.metrics["latencies_hit"]) if self.metrics["latencies_hit"] else 0
        avg_latency_miss = statistics.mean(self.metrics["latencies_miss"]) if self.metrics["latencies_miss"] else 0
        
        return {
            "total_requests": total,
            "exact_hits": self.metrics["exact_hits"],
            "semantic_hits": self.metrics["semantic_hits"],
            "misses": self.metrics["misses"],
            "hit_ratio_%": round(hit_ratio, 2),
            "tokens_saved_est": self.metrics["tokens_saved"],
            "avg_latency_hit_ms": round(avg_latency_hit, 2),
            "avg_latency_miss_ms": round(avg_latency_miss, 2)
        }
