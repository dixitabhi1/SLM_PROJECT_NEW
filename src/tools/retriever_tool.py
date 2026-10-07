"""
Deterministic BM25Okapi retriever over a pinned corpus of documents.
Zero LLM inside.
"""

import math
import re
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass


@dataclass
class RetrievedPassage:
    doc_id: str
    text: str
    score: float
    rank: int


class BM25RetrieverTool:
    """
    In-memory, deterministic BM25 retriever for local corpus search.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus: List[Dict[str, str]] = []  # list of {'id': str, 'text': str}
        self.doc_len: List[int] = []
        self.avg_doc_len: float = 0.0
        self.doc_count: int = 0
        self.inverted_index: Dict[str, List[Tuple[int, int]]] = {}  # term -> [(doc_idx, tf), ...]
        self.idf: Dict[str, float] = {}

    @staticmethod
    def tokenize(text: str) -> List[str]:
        """Simple lowercase alphanumeric tokenizer."""
        return re.findall(r"\b\w+\b", text.lower())

    def index_corpus(self, documents: List[Dict[str, str]]) -> None:
        """
        Indexes a list of documents. Each document must have 'id' and 'text'.
        """
        self.corpus = documents
        self.doc_count = len(documents)
        self.doc_len = []
        self.inverted_index = {}
        term_doc_freq: Dict[str, int] = {}

        total_tokens = 0
        for doc_idx, doc in enumerate(documents):
            tokens = self.tokenize(doc["text"])
            length = len(tokens)
            self.doc_len.append(length)
            total_tokens += length

            counts: Dict[str, int] = {}
            for t in tokens:
                counts[t] = counts.get(t, 0) + 1

            for t, count in counts.items():
                if t not in self.inverted_index:
                    self.inverted_index[t] = []
                self.inverted_index[t].append((doc_idx, count))
                term_doc_freq[t] = term_doc_freq.get(t, 0) + 1

        self.avg_doc_len = total_tokens / self.doc_count if self.doc_count > 0 else 0.0

        # Calculate IDF for all indexed terms
        self.idf = {}
        for term, df in term_doc_freq.items():
            # Standard Lucene/BM25 IDF formula
            self.idf[term] = math.log(1.0 + (self.doc_count - df + 0.5) / (df + 0.5))

    def retrieve(self, query: str, top_k: int = 3) -> List[RetrievedPassage]:
        """
        Retrieves top_k relevant passages for the query.
        """
        if self.doc_count == 0:
            return []

        q_tokens = self.tokenize(query)
        if not q_tokens:
            return []

        scores: Dict[int, float] = {}

        for token in q_tokens:
            if token not in self.inverted_index:
                continue

            idf = self.idf[token]
            for doc_idx, tf in self.inverted_index[token]:
                dl = self.doc_len[doc_idx]
                numerator = tf * (self.k1 + 1.0)
                denominator = tf + self.k1 * (1.0 - self.b + self.b * (dl / self.avg_doc_len))
                term_score = idf * (numerator / denominator)
                scores[doc_idx] = scores.get(doc_idx, 0.0) + term_score

        # Sort descending by score
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

        results = []
        for rank, (doc_idx, score) in enumerate(ranked, 1):
            doc = self.corpus[doc_idx]
            results.append(
                RetrievedPassage(
                    doc_id=doc["id"],
                    text=doc["text"],
                    score=round(score, 4),
                    rank=rank,
                )
            )

        return results

