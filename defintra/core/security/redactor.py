"""
Automated Secret Detection & Redaction Engine (§45, §48).
Scans and redacts credentials, API keys, private keys, connection strings,
and prompt injection delimiters before persistence into the Defintra Knowledge Graph.
"""

import collections
import math
import re
from typing import Dict, List, Optional, Pattern


def _shannon_entropy(data: str) -> float:
    """
    Calculates the Shannon entropy (in bits) of a given string.
    Random base64/hex tokens typically have high entropy (> 3.2).
    """
    if not data:
        return 0.0
    entropy = 0.0
    length = len(data)
    for count in collections.Counter(data).values():
        p = count / length
        entropy -= p * math.log2(p)
    return entropy


def _is_high_entropy_token(token: str) -> bool:
    """
    Determines whether a token looks like a random hex or base64 credential.
    Distinguishes high-entropy random keys from natural language / snake_case configuration identifiers.
    """
    if len(token) < 24:
        return False
    # If the token contains multiple underscore-separated natural language words, it is an identifier, not a secret
    if "_" in token:
        parts = token.split("_")
        if len(parts) >= 3 and all(p.isalpha() for p in parts if p):
            return False
    # Check if hex token (e.g. 32-char md5/sha hex or API secret)
    is_hex = all(c in "0123456789abcdefABCDEF" for c in token)
    if is_hex and len(token) >= 32 and _shannon_entropy(token) >= 3.0:
        return True
    # Check if base64 / alphanumeric random string (mixture of letters and numbers with high entropy)
    has_digit = any(c.isdigit() for c in token)
    has_alpha = any(c.isalpha() for c in token)
    entropy = _shannon_entropy(token)
    if has_digit and has_alpha and entropy >= 3.8:
        return True
    return False


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
        # Slack Tokens (bot xoxb-, user xoxp-, app xoxe-, etc.)
        SecretPattern("SLACK_TOKEN", r"\bxox[baprs]-[0-9a-zA-Z-]{10,}\b"),
        # Stripe API Keys (sk_live_, rk_live_, sk_test_, etc.)
        SecretPattern("STRIPE_KEY", r"\b(?:sk|rk)_(?:live|test)_[0-9a-zA-Z]{24,}\b"),
        # SendGrid API Keys (SG. prefix)
        SecretPattern("SENDGRID_KEY", r"\bSG\.[a-zA-Z0-9_-]{16,}\b"),
        # Twilio API Credentials (Account SID AC..., API Key / Auth Token SK...)
        SecretPattern("TWILIO_KEY", r"\b(?:AC|SK)[0-9a-fA-F]{32}\b"),
        # Google API / Gemini Keys (AIza prefix)
        SecretPattern("GOOGLE_API_KEY", r"\bAIza[0-9A-Za-z\-_]{32,45}\b"),
        # GitHub Tokens
        SecretPattern("GITHUB_TOKEN", r"gh[pousr]_[A-Za-z0-9_]{36,}"),
        # AWS Access Key IDs
        SecretPattern("AWS_ACCESS_KEY", r"\b(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}\b"),
        # Azure Storage & Service Connection Strings
        SecretPattern(
            "AZURE_CONNECTION_STRING",
            r"(?i)\b(?:DefaultEndpointsProtocol=https?;(?:[^\s;]+;)*(?:AccountKey|SharedAccessKey)=[A-Za-z0-9+/=]{20,}(?:;[^\s;]+)*|AccountKey=[A-Za-z0-9+/=]{40,}={0,2})\b",
        ),
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
        # Key/value password or token assignments: password="xyz", api_key: "abc", or KEY=value unquoted .env
        SecretPattern(
            "CREDENTIAL_ASSIGNMENT",
            r"""(?i)\b(password|secret|api_key|apikey|auth_token|client_secret|access_token|private_key)\b\s*[:=]\s*(?:["']([^"'\r\n\s]{8,})["']|([^\s"'#;\r\n]{8,}))""",
        ),
    ]

    # Generic high-entropy credential pattern fallback:
    # Matches tokens near words like key/secret/token/password that exhibit high Shannon entropy
    HIGH_ENTROPY_PATTERN: Pattern[str] = re.compile(
        r"""(?i)\b([a-zA-Z0-9_]*(?:password|secret|api_key|apikey|auth_token|client_secret|access_token|private_key|token|key))\b\s*([:=])\s*["']?([A-Za-z0-9+/=_-]{24,})["']?"""
    )

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

        # High-entropy fallback check for credentials near key/secret/token indicators
        def _replace_high_entropy(match):
            key_name = match.group(1)
            sep = match.group(2)
            token = match.group(3)
            # Do not re-redact existing redaction tags
            if "[REDACTED_SECRET" in token:
                return match.group(0)
            if _is_high_entropy_token(token):
                return f'{key_name}{sep} "[REDACTED_SECRET:HIGH_ENTROPY_TOKEN]"'
            return match.group(0)

        result = cls.HIGH_ENTROPY_PATTERN.sub(_replace_high_entropy, result)
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

        for match in cls.HIGH_ENTROPY_PATTERN.finditer(text):
            token = match.group(3)
            if "[REDACTED_SECRET" not in token and _is_high_entropy_token(token):
                findings.append({
                    "type": "HIGH_ENTROPY_TOKEN",
                    "start": match.start(3),
                    "end": match.end(3),
                })

        return findings

    @classmethod
    def contains_secrets(cls, text: Optional[str]) -> bool:
        """
        Returns True if any sensitive credentials are found in the text.
        """
        if not text:
            return False
        if any(bool(p.regex.search(text)) for p in cls.PATTERNS):
            return True
        for match in cls.HIGH_ENTROPY_PATTERN.finditer(text):
            token = match.group(3)
            if "[REDACTED_SECRET" not in token and _is_high_entropy_token(token):
                return True
        return False


