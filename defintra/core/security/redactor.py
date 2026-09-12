"""
Automated Secret Detection & Redaction Engine (§45, §48).
Scans and redacts credentials, API keys, private keys, connection strings,
and prompt injection delimiters before persistence into the Defintra Knowledge Graph.
"""

import re
from typing import Dict, List, Optional, Pattern


class SecretPattern:
    def __init__(self, name: str, pattern: str, flags: int = 0):
        self.name = name
        self.regex: Pattern[str] = re.compile(pattern, flags)


class SecretRedactor:
    """
    Scans and redacts sensitive credentials from PRDs, requirements, decisions,
    code comments, and incident stack traces before graph storage.
    """

    PATTERNS: List[SecretPattern] = [
        # Private Keys
        SecretPattern(
            "PRIVATE_KEY",
            r"-----BEGIN [A-Z\s]+PRIVATE KEY-----[\s\S]*?-----END [A-Z\s]+PRIVATE KEY-----",
        ),
        # Anthropic API Keys (placed before generic sk- keys)
        SecretPattern("ANTHROPIC_KEY", r"sk-ant-[a-zA-Z0-9_-]{20,}"),
        # OpenAI API Keys
        SecretPattern("OPENAI_KEY", r"sk-(?!ant-)(?:proj-)?[a-zA-Z0-9_-]{20,}"),
        # GitHub Tokens
        SecretPattern("GITHUB_TOKEN", r"gh[pousr]_[A-Za-z0-9_]{36,}"),
        # AWS Access Key IDs
        SecretPattern("AWS_ACCESS_KEY", r"\b(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}\b"),
        # Database Connection Strings (Postgres, MySQL, Mongo, Redis)
        SecretPattern(
            "DB_CONNECTION_STRING",
            r"(?:postgres(?:ql)?|mysql|mongodb|redis):\/\/[a-zA-Z0-9_.-]+:.+?@[a-zA-Z0-9_.-]+(?::[0-9]+)?\/[^\s\"']+",
        ),
        # Generic JWTs
        SecretPattern(
            "JWT_TOKEN",
            r"\beyJ[A-Za-z0-9-_=]+\.eyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_.+/=]+\b",
        ),
        # HTTP Bearer Tokens
        SecretPattern("BEARER_TOKEN", r"(?i)Bearer\s+[A-Za-z0-9\-._~+/]+=*"),
        # Key/value password or token assignments: password="xyz", api_key: "abc"
        SecretPattern(
            "CREDENTIAL_ASSIGNMENT",
            r"""(?i)\b(password|secret|api_key|apikey|auth_token|client_secret)\b\s*[:=]\s*["']([^"'\s]{8,})["']""",
        ),
    ]

    # Prompt injection delimiters that could hijack compiled context payloads
    PROMPT_INJECTION_DELIMITERS: List[SecretPattern] = [
        SecretPattern("CONTEXT_DELIMITER", r"<\/?defintra_context>", re.IGNORECASE),
        SecretPattern("CHATML_DELIMITER", r"<\|im_(?:start|end)\|>", re.IGNORECASE),
        SecretPattern("LLAMA_DELIMITER", r"\[\/?INST\]", re.IGNORECASE),
        SecretPattern("SYSTEM_TAG", r"<\/?system>", re.IGNORECASE),
    ]

    @classmethod
    def redact(cls, text: Optional[str]) -> str:
        """
        Replaces all detected credentials with sanitized placeholder tags.
        """
        if not text:
            return "" if text is None else text

        result = text
        for p in cls.PATTERNS:
            if p.name == "CREDENTIAL_ASSIGNMENT":
                # Only redact the value part, keeping the key
                result = p.regex.sub(r'\1: "[REDACTED_SECRET:\1]"', result)
            else:
                result = p.regex.sub(f"[REDACTED_SECRET:{p.name}]", result)

        return result

    @classmethod
    def sanitize_prompt_delimiters(cls, text: Optional[str]) -> str:
        """
        Neutralizes prompt injection tags to prevent escaping out of context blocks.
        """
        if not text:
            return "" if text is None else text

        result = text
        for p in cls.PROMPT_INJECTION_DELIMITERS:
            result = p.regex.sub(f"[SANITIZED_DELIMITER:{p.name}]", result)
        return result

    @classmethod
    def sanitize_all(cls, text: Optional[str]) -> str:
        """
        Performs both secret redaction and prompt delimiter sanitization.
        """
        return cls.sanitize_prompt_delimiters(cls.redact(text))

    @classmethod
    def scan(cls, text: Optional[str]) -> List[Dict[str, str]]:
        """
        Detects secrets and returns a summary list of detected types without exposing the values.
        """
        if not text:
            return []

        findings = []
        for p in cls.PATTERNS:
            for match in p.regex.finditer(text):
                findings.append({
                    "type": p.name,
                    "start": match.start(),
                    "end": match.end(),
                })
        return findings

    @classmethod
    def contains_secrets(cls, text: Optional[str]) -> bool:
        """
        Returns True if any sensitive credentials are found in the text.
        """
        if not text:
            return False
        return any(bool(p.regex.search(text)) for p in cls.PATTERNS)
