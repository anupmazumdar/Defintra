"""
Defintra Security & Data Protection Module (§45, §48).
Provides automated secret detection & redaction, input sanitization,
and prompt injection defense across the knowledge graph.
"""

from defintra.core.security.redactor import SecretRedactor

__all__ = ["SecretRedactor"]
