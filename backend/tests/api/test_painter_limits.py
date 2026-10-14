"""Native image generation bounds cover the actual outgoing request and response."""

import asyncio
import base64
import json

import httpx
import pytest

from nlab.api import pictures
from nlab.api.pictures import Painter

pytestmark = pytest.mark.anyio


async def test_painter_caps_generation_and_counts_paid_thought_tokens():
    sent = []

    def reply(request):
        sent.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "inlineData": {
                                        "mimeType": "image/png",
                                        "data": base64.b64encode(b"painting").decode(),
                                    }
                                }
                            ]
                        }
                    }
                ],
                "usageMetadata": {"promptTokenCount": 20, "candidatesTokenCount": 50, "thoughtsTokenCount": 100},
            },
        )

    result = await Painter("test", transport=httpx.MockTransport(reply)).paint("A field")
    assert sent[0]["generationConfig"]["maxOutputTokens"] == 8192
    assert sent[0]["generationConfig"]["candidateCount"] == 1
    assert result.tokens_out == 150


async def test_painter_rejects_an_oversized_response_before_loading_json():
    painter = Painter(
        "test",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=b" " * 8_000_001),
        ),
    )
    with pytest.raises(ValueError, match="response.*large"):
        await painter.paint("A field")


async def test_painter_has_a_total_deadline(monkeypatch):
    monkeypatch.setattr(pictures, "MAX_PAINT_SECONDS", 0.02, raising=False)

    async def slow_reply(_):
        await asyncio.sleep(0.1)
        return httpx.Response(200, json={})

    painter = Painter("test", transport=httpx.MockTransport(slow_reply))
    with pytest.raises(TimeoutError):
        await painter.paint("A field")


async def test_production_refuses_image_models_without_reviewed_token_limits():
    from nlab.api.app import create_app
    from nlab.api.settings import Settings
    from tests.llm.fakes import FakeProvider

    settings = Settings(
        _env_file=None,
        production=True,
        secret_key="K" * 48,
        db_password="P" * 48,
        public_url="https://training.example.org",
        session_retention_days=365,
        daily_spend_ceiling_usd=0,
    )
    with pytest.raises(ValueError, match="IMAGE_MODEL"):
        create_app(settings, providers={}, llm=(FakeProvider([]), None), painter=Painter("test", model="unreviewed"))
