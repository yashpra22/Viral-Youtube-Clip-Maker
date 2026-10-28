"""OpenAI-compatible provider.

Deliberately the widest adapter in AutoClip. Because ``base_url`` is
configurable and the Chat Completions shape is a de-facto standard, this one
class also covers OpenRouter, Groq, DeepSeek, Together, Fireworks, vLLM, and a
local LM Studio server. "Bring any API key" is mostly this file.
"""

from __future__ import annotations

import logging

from .base import DetectionConfig, LLMProvider, ProviderError, ProviderStatus

log = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4o"

SUGGESTED_MODELS = [
    "gpt-4o",
    "gpt-4o-mini",
    "o4-mini",
]

#: Ready-made endpoints for the settings UI. Users can enter any other URL.
KNOWN_ENDPOINTS = {
    "OpenAI": "https://api.openai.com/v1",
    "OpenRouter": "https://openrouter.ai/api/v1",
    "Groq": "https://api.groq.com/openai/v1",
    "DeepSeek": "https://api.deepseek.com/v1",
    "Together": "https://api.together.xyz/v1",
    "NVIDIA NIM": "https://integrate.api.nvidia.com/v1",
    "LM Studio (local)": "http://localhost:1234/v1",
    "NVIDIA NIM": "https://integrate.api.nvidia.com/v1",
}


class OpenAIProvider(LLMProvider):
    name = "openai"
    requires_key = True

    def __init__(self, model: str = "", *, api_key: str | None = None, base_url: str | None = None):
        super().__init__(model or DEFAULT_MODEL, api_key=api_key, base_url=base_url)

    def _client(self):
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover - openai is a core dep
            raise ProviderError("The openai package is not installed.", provider=self.name) from exc

        # Local servers ignore the key but the SDK still requires a non-empty
        # value, so supply a placeholder rather than failing the request.
        key = self.api_key or ("not-needed" if self._is_local() else None)
        if not key:
            raise ProviderError(
                "No API key is set for the OpenAI-compatible provider.",
                provider=self.name,
                hint="Add one with `autoclip config set-secret openai`.",
            )

        kwargs = {"api_key": key}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        if self.base_url and "integrate.api.nvidia.com" in self.base_url:
            # Free hosted inference can queue for a long time; bound a stuck
            # request so one transcript window cannot stall the batch forever.
            kwargs["timeout"] = 180.0
            kwargs["max_retries"] = 0
        elif self.base_url and "openrouter.ai" in self.base_url:
            # OpenRouter free endpoints can queue; keep a slow provider from
            # holding up a batch indefinitely.
            kwargs["timeout"] = 120.0
            kwargs["max_retries"] = 0
        return AsyncOpenAI(**kwargs)

    def _is_local(self) -> bool:
        return bool(self.base_url) and (
            "localhost" in self.base_url or "127.0.0.1" in self.base_url
        )

    async def _complete(self, system: str, user: str, config: DetectionConfig) -> str:
        client = self._client()
        request = {
            "model": self.model,
            "temperature": config.temperature,
            # Clip metadata is short; an unbounded response wastes time and
            # can make reasoning models spend far longer than the pipeline
            # needs on every transcript window.
            "max_tokens": 2048,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if (
            self.base_url
            and "integrate.api.nvidia.com" in self.base_url
            and self.model.startswith("deepseek-ai/deepseek-v4")
        ):
            # NVIDIA's hosted DeepSeek V4 endpoint defaults to high reasoning
            # effort. Clip selection needs a concise JSON result, so disable
            # its long reasoning pass when the endpoint supports this control.
            request["reasoning_effort"] = "none"
        elif (
            self.base_url
            and "integrate.api.nvidia.com" in self.base_url
            and self.model == "nvidia/nemotron-3.5-lightning-30b-a3b"
        ):
            request["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
        # Only OpenAI's own endpoint reliably honours this; other vendors 400 on
        # it, so a failed request is retried once without it.
        # This free OpenRouter variant rejects response_format even though it
        # otherwise speaks Chat Completions. The prompt already requests JSON.
        openrouter_free_nemotron = (
            self.base_url
            and "openrouter.ai" in self.base_url
            and self.model == "nvidia/nemotron-3.5-lightning:free"
        )
        if openrouter_free_nemotron:
            try:
                response = await client.chat.completions.create(**request)
            except Exception as exc:
                raise _translate(exc, self.name, self.model) from exc
        else:
            try:
                response = await client.chat.completions.create(
                    **request, response_format={"type": "json_object"}
                )
            except Exception as exc:
                if _is_unsupported_parameter(exc):
                    log.debug("Endpoint rejected response_format; retrying without it.")
                    try:
                        response = await client.chat.completions.create(**request)
                    except Exception as retry_exc:
                        raise _translate(retry_exc, self.name, self.model) from retry_exc
                else:
                    raise _translate(exc, self.name, self.model) from exc

        choices = response.choices or []
        if not choices:
            raise ProviderError("The endpoint returned no choices.", provider=self.name)
        return choices[0].message.content or ""

    async def health_check(self) -> ProviderStatus:
        if not self.api_key and not self._is_local():
            return ProviderStatus(
                name=self.name, available=False, detail="No API key set", models=SUGGESTED_MODELS
            )
        try:
            client = self._client()
            models = await client.models.list()
            names = sorted(m.id for m in models.data)[:50]
        except Exception as exc:
            return ProviderStatus(name=self.name, available=False, detail=str(exc)[:200])
        return ProviderStatus(
            name=self.name,
            available=True,
            detail=self.base_url or "https://api.openai.com/v1",
            models=names or SUGGESTED_MODELS,
        )


def _is_unsupported_parameter(exc: Exception) -> bool:
    lowered = str(exc).lower()
    return "response_format" in lowered or "unsupported" in lowered or "unrecognized" in lowered


def _translate(exc: Exception, provider: str, model: str) -> ProviderError:
    message = str(exc)
    lowered = message.lower()

    if "401" in lowered or "invalid api key" in lowered or "incorrect api key" in lowered:
        return ProviderError(
            "The endpoint rejected the API key.",
            provider=provider,
            hint="Re-add it with `autoclip config set-secret openai`.",
        )
    if "429" in lowered or "rate limit" in lowered:
        return ProviderError(
            "Rate limit reached.",
            provider=provider,
            hint="Wait and retry, or switch providers.",
        )
    if "404" in lowered or "does not exist" in lowered or "model_not_found" in lowered:
        return ProviderError(
            f"The endpoint does not recognise the model '{model}'.",
            provider=provider,
            hint="Check the model name against your provider's catalogue.",
        )
    if "connection" in lowered or "connect" in lowered:
        return ProviderError(
            "Could not reach the endpoint.",
            provider=provider,
            hint="Check the base URL in settings, and that any local server is running.",
        )
    if "quota" in lowered or "billing" in lowered:
        return ProviderError("The account has no remaining quota.", provider=provider)

    return ProviderError(f"Request failed: {message}", provider=provider)
