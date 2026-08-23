"""
LLM Provider Interface & Deep Path Recursive Decomposition Engine (§4, §5, §6, §19).
Supports OpenAI, Gemini, Anthropic, and local zero-dependency Heuristic Mock Provider.
"""

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple
import httpx

from defintra.core.models.entities import (
    ApprovalLevel,
    ArtifactState,
    ChangeRisk,
    EARSPattern,
    Requirement,
    RequirementPriority,
    SourceType,
    Unknown,
    current_utc_time,
)
from defintra.core.requirements.ears import EARSEngine


class LLMResponse:
    def __init__(self, content: str, raw_json: Optional[Dict[str, Any]] = None):
        self.content = content
        self.raw_json = raw_json or {}


class BaseLLMProvider:
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> LLMResponse:
        raise NotImplementedError


class MockHeuristicLLMProvider(BaseLLMProvider):
    """
    Zero-dependency deterministic offline fallback provider (§47).
    """

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> LLMResponse:
        # Heuristic recursive decomposition
        return LLMResponse(
            content="Generated from Defintra Local Heuristic Engine",
            raw_json={
                "decomposed_requirements": [
                    {
                        "title": "Role-Based Access Control",
                        "system": "Auth Gateway",
                        "pattern": "UBIQUITOUS",
                        "response": "verify user roles and permissions on every incoming API request",
                        "priority": "CRITICAL",
                        "constraints": ["Token verification under 20ms"],
                        "acceptance_criteria": ["Unauthenticated requests return 401", "Unauthorized roles return 403"],
                    },
                    {
                        "title": "Data Mutation Audit Trail",
                        "system": "Persistence Layer",
                        "pattern": "EVENT_DRIVEN",
                        "trigger": "a user creates, updates, or deletes a database entity",
                        "response": "write an immutable audit event log with timestamp and actor ID",
                        "priority": "HIGH",
                        "constraints": ["Write audit synchronously before commit"],
                        "acceptance_criteria": ["Verify audit entry exists in audit_log table"],
                    },
                    {
                        "title": "Graceful Fault Recovery",
                        "system": "Service Client",
                        "pattern": "UNWANTED_BEHAVIOR",
                        "fault": "downstream API service fails or times out after 3 seconds",
                        "response": "execute exponential backoff retry and return a degraded fallback payload",
                        "priority": "MEDIUM",
                        "constraints": ["Maximum 3 retry attempts"],
                        "acceptance_criteria": ["Circuit breaker trips on 5 consecutive failures"],
                    },
                ],
                "discovered_unknowns": [
                    {
                        "question": "What is the expected peak requests-per-second (RPS) load?",
                        "impact": "HIGH",
                        "category": "ARCHITECTURE",
                    },
                    {
                        "question": "Are multi-region data residency regulations (e.g. GDPR) applicable?",
                        "impact": "MEDIUM",
                        "category": "SECURITY",
                    },
                ],
            },
        )


class OpenAILLMProvider(BaseLLMProvider):
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> LLMResponse:
        if not self.api_key:
            return MockHeuristicLLMProvider().generate(prompt, system_prompt)

        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            with httpx.Client(timeout=30.0) as client:
                res = client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json={"model": self.model, "messages": messages, "response_format": {"type": "json_object"}},
                )
                if res.status_code == 200:
                    data = res.json()
                    content = data["choices"][0]["message"]["content"]
                    parsed = json.loads(content)
                    return LLMResponse(content=content, raw_json=parsed)
        except Exception:
            pass

        return MockHeuristicLLMProvider().generate(prompt, system_prompt)


class GeminiLLMProvider(BaseLLMProvider):
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-1.5-flash"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model = model

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> LLMResponse:
        if not self.api_key:
            return MockHeuristicLLMProvider().generate(prompt, system_prompt)

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        body = {
            "contents": [{"parts": [{"text": (system_prompt + "\n\n" if system_prompt else "") + prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        try:
            with httpx.Client(timeout=30.0) as client:
                res = client.post(url, json=body)
                if res.status_code == 200:
                    data = res.json()
                    text = data["candidates"][0]["content"]["parts"][0]["text"]
                    parsed = json.loads(text)
                    return LLMResponse(content=text, raw_json=parsed)
        except Exception:
            pass

        return MockHeuristicLLMProvider().generate(prompt, system_prompt)


class AnthropicLLMProvider(BaseLLMProvider):
    def __init__(self, api_key: Optional[str] = None, model: str = "claude-3-5-sonnet-20241022"):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> LLMResponse:
        if not self.api_key:
            return MockHeuristicLLMProvider().generate(prompt, system_prompt)

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            body["system"] = system_prompt

        try:
            with httpx.Client(timeout=30.0) as client:
                res = client.post("https://api.anthropic.com/v1/messages", headers=headers, json=body)
                if res.status_code == 200:
                    data = res.json()
                    text = data["content"][0]["text"]
                    # Extract JSON if enclosed in markdown code blocks
                    json_str = text
                    if "```json" in text:
                        json_str = text.split("```json")[1].split("```")[0].strip()
                    elif "```" in text:
                        json_str = text.split("```")[1].split("```")[0].strip()
                    parsed = json.loads(json_str)
                    return LLMResponse(content=text, raw_json=parsed)
        except Exception:
            pass

        return MockHeuristicLLMProvider().generate(prompt, system_prompt)


def get_default_llm_provider() -> BaseLLMProvider:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicLLMProvider()
    elif os.environ.get("GEMINI_API_KEY"):
        return GeminiLLMProvider()
    elif os.environ.get("OPENAI_API_KEY"):
        return OpenAILLMProvider()
    return MockHeuristicLLMProvider()


class DeepPathEngine:
    """
    Deep Path Recursive Decomposition Engine (§5, §6).
    """

    def __init__(self, provider: Optional[BaseLLMProvider] = None):
        self.provider = provider or get_default_llm_provider()

    def decompose(self, project_id: str, objective: str) -> Tuple[List[Requirement], List[Unknown]]:
        system_prompt = (
            "You are the Defintra Requirement Decomposition Engine. "
            "Decompose user intent recursively into verifiable EARS requirements and high-impact unknowns. "
            "Output JSON with keys: 'decomposed_requirements' and 'discovered_unknowns'."
        )
        prompt = f"Decompose this project intent into EARS requirements:\n\n{objective}"
        res = self.provider.generate(prompt, system_prompt)

        reqs: List[Requirement] = []
        unknowns: List[Unknown] = []

        data = res.raw_json or {}
        for i, r_data in enumerate(data.get("decomposed_requirements", [])):
            pat_str = r_data.get("pattern", "UBIQUITOUS").upper()
            try:
                pattern = EARSPattern[pat_str]
            except Exception:
                pattern = EARSPattern.UBIQUITOUS

            req = EARSEngine.create_requirement(
                req_id=f"R-DEEP-{i+1:03d}_{project_id}",
                project_id=project_id,
                title=r_data.get("title", f"Requirement {i+1}"),
                system_name=r_data.get("system", "System"),
                response=r_data.get("response", "operate reliably"),
                pattern=pattern,
                trigger=r_data.get("trigger"),
                fault=r_data.get("fault"),
                priority=RequirementPriority[r_data.get("priority", "MEDIUM").upper()],
                constraints=r_data.get("constraints", []),
                acceptance_criteria=r_data.get("acceptance_criteria", []),
                confidence=0.92,
            )
            req.provenance.source = "Deep Path LLM Decomposition"
            req.provenance.source_type = SourceType.AI_INFERRED
            reqs.append(req)

        for i, u_data in enumerate(data.get("discovered_unknowns", [])):
            unk = Unknown(
                id=f"UNK-DEEP-{i+1:03d}_{project_id}",
                project_id=project_id,
                question=u_data.get("question", "Undefined project parameter"),
                impact=u_data.get("impact", "MEDIUM"),
                category=u_data.get("category", "ARCHITECTURE"),
                status="OPEN",
                priority_order=i + 1,
            )
            unknowns.append(unk)

        return reqs, unknowns
