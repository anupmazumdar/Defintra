import json
from unittest.mock import MagicMock, patch

from defintra.core.discovery.llm import (
    DeepPathEngine,
    GeminiLLMProvider,
    OpenAILLMProvider,
)
from defintra.core.models.entities import EARSPattern, RequirementPriority


def test_openai_llm_provider_decomposition_mocked():
    fake_openai_json = {
        "decomposed_requirements": [
            {
                "title": "OAuth2 Token Issuance",
                "system": "Auth Gateway",
                "pattern": "EVENT_DRIVEN",
                "trigger": "a valid authorization code is received from the identity provider",
                "response": "generate signed JWT access and refresh token pair",
                "priority": "CRITICAL",
                "constraints": ["Token generation under 50ms"],
                "acceptance_criteria": ["JWT contains sub, exp, and roles claims"],
            }
        ],
        "discovered_unknowns": [
            {
                "question": "What is the token expiration TTL (e.g. 15m vs 1h)?",
                "impact": "MEDIUM",
                "category": "SECURITY",
            }
        ],
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(fake_openai_json),
                }
            }
        ]
    }

    with patch("httpx.Client.post", return_value=mock_response):
        provider = OpenAILLMProvider(api_key="sk-mock-openai-key", model="gpt-4o")
        engine = DeepPathEngine(provider=provider)

        reqs, unknowns = engine.decompose("project_openai_test", "Build enterprise SSO auth gateway")

        assert len(reqs) == 1
        assert reqs[0].title == "OAuth2 Token Issuance"
        assert reqs[0].ears_pattern == EARSPattern.EVENT_DRIVEN
        assert reqs[0].priority == RequirementPriority.CRITICAL
        assert "Token generation under 50ms" in reqs[0].constraints

        assert len(unknowns) == 1
        assert "token expiration TTL" in unknowns[0].question
        assert unknowns[0].impact == "MEDIUM"


def test_gemini_llm_provider_decomposition_mocked():
    fake_gemini_json = {
        "decomposed_requirements": [
            {
                "title": "Real-Time GPS Geofence Verification",
                "system": "Attendance System",
                "pattern": "STATE_DRIVEN",
                "state": "student is physically inside the classroom coordinates",
                "response": "allow attendance check-in button to become active",
                "priority": "HIGH",
                "constraints": ["Geofence radius max 50 meters"],
                "acceptance_criteria": ["Outside classroom coordinates returns error"],
            }
        ],
        "discovered_unknowns": [
            {
                "question": "Is offline check-in with later batch sync required?",
                "impact": "HIGH",
                "category": "ARCHITECTURE",
            }
        ],
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": json.dumps(fake_gemini_json),
                        }
                    ]
                }
            }
        ]
    }

    with patch("httpx.Client.post", return_value=mock_response):
        provider = GeminiLLMProvider(api_key="mock-gemini-key", model="gemini-1.5-flash")
        engine = DeepPathEngine(provider=provider)

        reqs, unknowns = engine.decompose("project_gemini_test", "Build student attendance app with geofence")

        assert len(reqs) == 1
        assert reqs[0].title == "Real-Time GPS Geofence Verification"
        assert reqs[0].priority == RequirementPriority.HIGH

        assert len(unknowns) == 1
        assert "offline check-in" in unknowns[0].question
        assert unknowns[0].category == "ARCHITECTURE"
