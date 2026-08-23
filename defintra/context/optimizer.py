"""
Token Optimizer Engine (§23).
Provides token estimation, semantic deduplication, redundancy stripping,
and priority-based token budgeting for context compilation.
"""

import re
from typing import Any, Dict, List, Set, Tuple


class TokenEstimator:
    """
    Estimates token counts using standard heuristics (~4 characters or 0.75 words per token).
    """

    @classmethod
    def estimate_tokens(cls, text: str) -> int:
        if not text:
            return 0
        char_estimate = len(text) / 3.8
        word_estimate = len(text.split()) * 1.25
        return max(1, int((char_estimate + word_estimate) / 2))

    @classmethod
    def estimate_dict_tokens(cls, data: Dict[str, Any]) -> int:
        import json
        text = json.dumps(data, ensure_ascii=False)
        return cls.estimate_tokens(text)


class TokenOptimizer:
    """
    Optimizes context payload to fit within token budgets without losing semantic correctness.
    """

    @classmethod
    def deduplicate_strings(cls, items: List[str]) -> List[str]:
        """
        Removes exact and near-exact duplicate strings while preserving order.
        """
        seen: Set[str] = set()
        deduped: List[str] = []
        for item in items:
            normalized = re.sub(r"\s+", " ", item.strip().lower())
            if normalized and normalized not in seen:
                seen.add(normalized)
                deduped.append(item.strip())
        return deduped

    @classmethod
    def compress_text(cls, text: str) -> str:
        """
        Safely compresses prose without losing key technical clauses.
        """
        text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()

    @classmethod
    def fit_to_budget(
        cls,
        items: List[Dict[str, Any]],
        max_tokens: int,
        priority_key: str = "priority_score",
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], int]:
        """
        Fits candidate context items into the token budget based on priority.
        Returns: (included_items, excluded_items, total_tokens_used)
        """
        sorted_items = sorted(items, key=lambda x: x.get(priority_key, 0.0), reverse=True)

        included: List[Dict[str, Any]] = []
        excluded: List[Dict[str, Any]] = []
        used_tokens = 0

        for item in sorted_items:
            item_text = str(item.get("content", item))
            item_tokens = TokenEstimator.estimate_tokens(item_text)

            if used_tokens + item_tokens <= max_tokens:
                included.append(item)
                used_tokens += item_tokens
            else:
                item_copy = dict(item)
                item_copy["exclusion_reason"] = f"Exceeded token budget ({used_tokens + item_tokens} > {max_tokens})"
                excluded.append(item_copy)

        return included, excluded, used_tokens
