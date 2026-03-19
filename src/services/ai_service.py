import json
import time
import urllib.error
import urllib.request
import urllib.parse
from typing import Dict, Optional

from src.models.bot import Bot
from src.services.settings_store import SettingsStore


class AIService:
    def __init__(self, settings_store: Optional[SettingsStore] = None):
        self.settings_store = settings_store or SettingsStore()

    def generate(
        self,
        prompt: str,
        node_config: Optional[Dict[str, str]] = None,
        bot: Optional[Bot] = None,
        system_prompt: str = "",
    ) -> str:
        result = self.generate_with_metadata(
            prompt=prompt,
            node_config=node_config,
            bot=bot,
            system_prompt=system_prompt,
        )
        return result["response"]

    def generate_with_metadata(
        self,
        prompt: str,
        node_config: Optional[Dict[str, str]] = None,
        bot: Optional[Bot] = None,
        system_prompt: str = "",
    ) -> Dict[str, str]:
        config = node_config or {}
        settings = self.settings_store.load_settings()

        provider = self._resolve_provider(settings, config, bot)
        model = self._resolve_model(settings, provider, config, bot)
        temperature = self._resolve_temperature(config.get("temperature"), bot)
        max_tokens = self._resolve_max_tokens(config.get("max_tokens"), bot)

        resolved_system_prompt = system_prompt.strip()
        if not resolved_system_prompt and bot and bot.role.strip():
            resolved_system_prompt = bot.role.strip()

        started = time.perf_counter()
        response = ""
        if provider == "local":
            local_backend = self._resolve_local_backend(settings)
            response = self._call_local_backend(
                backend=local_backend,
                endpoint=self._resolve_local_endpoint(settings, local_backend),
                local_api_key=str(settings.get("local_ai_api_key", "")).strip(),
                model=model,
                prompt=prompt,
                system_prompt=resolved_system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        elif provider == "openai":
            response = self._call_openai(
                api_key=settings.get("openai_api_key", "").strip(),
                model=model,
                prompt=prompt,
                system_prompt=resolved_system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        elif provider == "anthropic":
            response = self._call_anthropic(
                api_key=settings.get("anthropic_api_key", "").strip(),
                model=model,
                prompt=prompt,
                system_prompt=resolved_system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        else:
            raise ValueError(f"Unsupported provider: {provider}")

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return {
            "provider": provider,
            "model": model,
            "response": response,
            "latency_ms": str(elapsed_ms),
            "local_backend": self._resolve_local_backend(settings) if provider == "local" else "",
        }

    def list_ollama_models(self, ollama_url: str = "") -> list[str]:
        settings = self.settings_store.load_settings()
        base_url = (
            ollama_url.strip()
            or str(settings.get("local_ai_endpoint", "")).strip()
            or str(settings.get("ollama_url", "")).strip()
        )
        if not base_url:
            base_url = "http://localhost:11434"
        base_url = self._normalize_ollama_base_url(base_url)

        url = f"{base_url.rstrip('/')}/api/tags"
        data = self._get_json(url)
        models = data.get("models", [])
        if not isinstance(models, list):
            return []

        names: list[str] = []
        for item in models:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if name:
                names.append(name)
        return names

    def list_local_models(
        self,
        local_backend: str = "",
        local_endpoint: str = "",
        local_api_key: str = "",
    ) -> list[str]:
        settings = self.settings_store.load_settings()
        backend = local_backend.strip().lower() or self._resolve_local_backend(settings)
        endpoint = (
            local_endpoint.strip()
            or str(settings.get("local_ai_endpoint", "")).strip()
            or self._default_local_endpoint(backend)
        )
        api_key = local_api_key.strip() or str(settings.get("local_ai_api_key", "")).strip()

        endpoints = self._local_endpoint_candidates(backend, endpoint)
        last_error: Exception | None = None
        for candidate in endpoints:
            try:
                if backend == "ollama":
                    models = self.list_ollama_models(candidate)
                else:
                    models = self._list_openai_compatible_models(candidate, api_key=api_key)
                if models:
                    return models
            except Exception as error:
                last_error = error
        if last_error:
            tried = ", ".join(endpoints)
            raise RuntimeError(f"{last_error} (tried: {tried})")
        return []

    def _resolve_provider(
        self, settings: Dict, node_config: Dict[str, str], bot: Optional[Bot]
    ) -> str:
        preferred_provider = str(settings.get("preferred_provider", "local")).strip().lower()
        configured_provider = str(node_config.get("provider", "")).strip().lower()

        if configured_provider and configured_provider != "inherit":
            provider = configured_provider
        elif bot and bot.provider.strip():
            provider = bot.provider.strip().lower()
        else:
            provider = preferred_provider

        if provider == "local" and not bool(settings.get("local_ai_enabled", True)):
            if settings.get("openai_api_key", "").strip():
                return "openai"
            if settings.get("anthropic_api_key", "").strip():
                return "anthropic"
            raise ValueError("Local AI is disabled and no cloud provider API key is configured.")

        return provider

    def _resolve_model(
        self,
        settings: Dict,
        provider: str,
        node_config: Dict[str, str],
        bot: Optional[Bot],
    ) -> str:
        configured_model = self._sanitize_model_name(str(node_config.get("model", "")).strip())
        if configured_model:
            return configured_model

        if bot and bot.model.strip():
            return self._sanitize_model_name(bot.model.strip())

        if provider == "local":
            local_model = self._sanitize_model_name(
                str(settings.get("default_local_model", "")).strip()
            )
            if local_model:
                return local_model

            backend = self._resolve_local_backend(settings)
            endpoint = self._resolve_local_endpoint(settings, backend)
            api_key = str(settings.get("local_ai_api_key", "")).strip()
            discovered = self.list_local_models(
                local_backend=backend,
                local_endpoint=endpoint,
                local_api_key=api_key,
            )
            if discovered:
                return self._sanitize_model_name(discovered[0])

            raise ValueError("No local model configured. Set one in Settings.")

        if provider == "openai":
            return "gpt-4.1-mini"

        if provider == "anthropic":
            return "claude-sonnet-4-5"

        raise ValueError(f"Unsupported provider: {provider}")

    def _call_ollama(
        self,
        ollama_url: str,
        model: str,
        prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        base_url = self._normalize_ollama_base_url(ollama_url.strip())
        if not base_url:
            base_url = "http://localhost:11434"

        url = f"{base_url}/api/chat"

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        response = self._post_json(url, payload, headers={"Content-Type": "application/json"})
        message = response.get("message", {})
        if isinstance(message, dict):
            content = str(message.get("content", "")).strip()
            if content:
                return content

        fallback = str(response.get("response", "")).strip()
        if fallback:
            return fallback

        raise ValueError("Ollama returned an empty response.")

    def _call_local_backend(
        self,
        backend: str,
        endpoint: str,
        local_api_key: str,
        model: str,
        prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        normalized = backend.strip().lower()
        endpoints = self._local_endpoint_candidates(normalized, endpoint)
        last_error: Exception | None = None
        for candidate in endpoints:
            try:
                if normalized == "ollama":
                    return self._call_ollama(
                        ollama_url=candidate,
                        model=model,
                        prompt=prompt,
                        system_prompt=system_prompt,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                return self._call_openai_compatible_local(
                    base_url=candidate,
                    api_key=local_api_key,
                    model=model,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception as error:
                last_error = error
        if last_error:
            tried = ", ".join(endpoints)
            raise RuntimeError(f"{last_error} (tried: {tried})")
        raise RuntimeError("No local endpoint candidates available.")

    def _call_openai_compatible_local(
        self,
        base_url: str,
        api_key: str,
        model: str,
        prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
            headers["x-api-key"] = api_key
            headers["api-key"] = api_key

        raw_input = base_url.strip().rstrip("/")
        normalized_base = self._normalize_openai_base_url(base_url)
        candidates: list[str] = []
        if raw_input and raw_input.lower().endswith("/chat/completions"):
            candidates.append(raw_input)
        candidates.append(f"{normalized_base}/chat/completions")
        if normalized_base.endswith("/v1"):
            candidates.append(f"{normalized_base.replace('/v1', '', 1)}/chat/completions")

        deduped_candidates: list[str] = []
        for item in candidates:
            if item and item not in deduped_candidates:
                deduped_candidates.append(item)

        response = None
        last_error: Exception | None = None
        for candidate in deduped_candidates:
            try:
                response = self._post_json(candidate, payload, headers=headers)
                break
            except Exception as error:
                last_error = error
        if response is None:
            tried = ", ".join(deduped_candidates)
            message = str(last_error) if last_error else "Local endpoint call failed."
            raise RuntimeError(f"{message} (tried: {tried})")
        return self._extract_openai_chat_text(
            response,
            empty_response_error="Local OpenAI-compatible endpoint returned an empty response.",
        )

    def _call_openai(
        self,
        api_key: str,
        model: str,
        prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        if not api_key:
            raise ValueError("OpenAI API key is missing. Add it in Settings.")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        response = self._post_json(
            "https://api.openai.com/v1/chat/completions",
            payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )

        return self._extract_openai_chat_text(
            response,
            empty_response_error="OpenAI returned an empty response.",
        )

    def _call_anthropic(
        self,
        api_key: str,
        model: str,
        prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        if not api_key:
            raise ValueError("Anthropic API key is missing. Add it in Settings.")

        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            payload["system"] = system_prompt

        response = self._post_json(
            "https://api.anthropic.com/v1/messages",
            payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )

        content = response.get("content", [])
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(str(item.get("text", "")))
            text = "\n".join([part for part in text_parts if part.strip()]).strip()
            if text:
                return text

        raise ValueError("Anthropic returned an empty response.")

    def _post_json(self, url: str, payload: Dict, headers: Dict[str, str]) -> Dict:
        headers = self._prepare_request_headers(headers)
        request_data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=request_data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"HTTP {error.code} error from provider: {body}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"Network error while calling provider: {error.reason}") from error

        try:
            return json.loads(raw)
        except json.JSONDecodeError as error:
            raise RuntimeError("Provider returned invalid JSON.") from error

    def _get_json(self, url: str, headers: Optional[Dict[str, str]] = None) -> Dict:
        prepared_headers = self._prepare_request_headers(headers or {})
        request = urllib.request.Request(url, headers=prepared_headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"HTTP {error.code} error from provider: {body}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"Network error while calling provider: {error.reason}") from error

        try:
            return json.loads(raw)
        except json.JSONDecodeError as error:
            raise RuntimeError("Provider returned invalid JSON.") from error

    def _extract_openai_chat_text(self, response: Dict, empty_response_error: str) -> str:
        choices = response.get("choices", [])
        if isinstance(choices, list) and choices:
            message = choices[0].get("message", {})
            if isinstance(message, dict):
                content = message.get("content", "")
                if isinstance(content, list):
                    parts = [str(item.get("text", "")) for item in content if isinstance(item, dict)]
                    content = "\n".join([part for part in parts if part.strip()])
                content_text = str(content).strip()
                if content_text:
                    return content_text
        raise ValueError(empty_response_error)

    def _list_openai_compatible_models(self, base_url: str, api_key: str = "") -> list[str]:
        headers: Dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
            headers["x-api-key"] = api_key
            headers["api-key"] = api_key
        normalized_base = self._normalize_openai_base_url(base_url)
        candidates = [
            f"{normalized_base}/models",
            f"{normalized_base.replace('/v1', '', 1)}/models"
            if normalized_base.endswith("/v1")
            else "",
        ]

        data: Dict = {}
        last_error: Exception | None = None
        for candidate in [item for item in candidates if item]:
            try:
                data = self._get_json(candidate, headers=headers)
                last_error = None
                break
            except Exception as error:
                last_error = error
        if not data and last_error:
            raise last_error

        models = data.get("data", [])
        if not isinstance(models, list):
            return []

        names: list[str] = []
        for item in models:
            if not isinstance(item, dict):
                continue
            model_id = self._sanitize_model_name(str(item.get("id", "")).strip())
            if model_id:
                names.append(model_id)
        return names

    def _normalize_openai_base_url(self, base_url: str) -> str:
        normalized = base_url.strip()
        if not normalized:
            return "http://localhost:1234/v1"

        if "://" not in normalized:
            normalized = f"http://{normalized}"
        parsed = urllib.parse.urlsplit(normalized)
        path = parsed.path.rstrip("/")

        for suffix in ["/chat/completions", "/completions", "/models"]:
            if path.endswith(suffix):
                path = path[: -len(suffix)]
                break

        if path.endswith("/v1"):
            base_path = path
        else:
            marker = "/v1/"
            marker_index = path.find(marker)
            if marker_index >= 0:
                base_path = path[: marker_index + 3]
            elif path == "":
                base_path = "/v1"
            else:
                base_path = f"{path}/v1"

        normalized_url = urllib.parse.urlunsplit(
            (
                parsed.scheme or "http",
                parsed.netloc,
                base_path,
                "",
                "",
            )
        ).rstrip("/")
        return normalized_url

    def _normalize_ollama_base_url(self, base_url: str) -> str:
        normalized = str(base_url).strip()
        if not normalized:
            return "http://localhost:11434"
        if "://" not in normalized:
            normalized = f"http://{normalized}"
        parsed = urllib.parse.urlsplit(normalized)
        path = parsed.path.rstrip("/")

        for suffix in ["/api/chat", "/api/generate", "/api/tags"]:
            if path.endswith(suffix):
                path = path[: -len(suffix)]
                break

        normalized_url = urllib.parse.urlunsplit(
            (
                parsed.scheme or "http",
                parsed.netloc,
                path,
                "",
                "",
            )
        ).rstrip("/")
        return normalized_url or "http://localhost:11434"

    def _sanitize_model_name(self, model: str) -> str:
        normalized = str(model).strip().strip("/")
        if not normalized:
            return ""
        for suffix in ["v1/chat/completions", "chat/completions", "v1/completions", "completions"]:
            if normalized.lower().endswith(suffix):
                trimmed = normalized[: -len(suffix)].rstrip("/")
                if trimmed:
                    return trimmed
        return normalized

    def _resolve_local_backend(self, settings: Dict) -> str:
        backend = str(settings.get("local_ai_backend", "ollama")).strip().lower()
        if backend in {
            "ollama",
            "lm_studio",
            "openai_compatible",
            "vllm",
            "llama_cpp",
            "text_generation_webui",
            "jan",
        }:
            return backend
        return "ollama"

    def _resolve_local_endpoint(self, settings: Dict, backend: str) -> str:
        endpoint = str(settings.get("local_ai_endpoint", "")).strip()
        if endpoint:
            return endpoint
        legacy = str(settings.get("ollama_url", "")).strip()
        if legacy:
            return legacy
        return self._default_local_endpoint(backend)

    def _default_local_endpoint(self, backend: str) -> str:
        normalized = str(backend).strip().lower()
        if normalized == "lm_studio":
            return "http://localhost:1234/v1"
        if normalized in {"openai_compatible", "vllm"}:
            return "http://localhost:8000/v1"
        if normalized == "llama_cpp":
            return "http://localhost:8080/v1"
        if normalized == "text_generation_webui":
            return "http://localhost:5000/v1"
        if normalized == "jan":
            return "http://localhost:1337/v1"
        return "http://localhost:11434"

    def _local_endpoint_candidates(self, backend: str, endpoint: str) -> list[str]:
        normalized_backend = str(backend).strip().lower()
        candidates: list[str] = []

        def add_candidate(value: str):
            item = str(value).strip()
            if not item:
                return
            if item not in candidates:
                candidates.append(item)

        configured_endpoint = str(endpoint).strip()
        add_candidate(configured_endpoint)
        endpoint_host = self._extract_endpoint_host(configured_endpoint)
        endpoint_is_local = self._is_local_host(endpoint_host)

        if not configured_endpoint:
            add_candidate(self._default_local_endpoint(normalized_backend))

        if endpoint_is_local:
            add_candidate(self._default_local_endpoint(normalized_backend))
            if normalized_backend == "ollama":
                add_candidate("http://127.0.0.1:11434")
                add_candidate("http://localhost:11434")
            elif normalized_backend == "lm_studio":
                add_candidate("http://127.0.0.1:1234/v1")
                add_candidate("http://localhost:1234/v1")
                add_candidate("http://127.0.0.1:1234")
                add_candidate("http://localhost:1234")
            elif normalized_backend == "llama_cpp":
                add_candidate("http://127.0.0.1:8080/v1")
                add_candidate("http://localhost:8080/v1")
                add_candidate("http://127.0.0.1:8080")
                add_candidate("http://localhost:8080")
            elif normalized_backend == "text_generation_webui":
                add_candidate("http://127.0.0.1:5000/v1")
                add_candidate("http://localhost:5000/v1")
                add_candidate("http://127.0.0.1:5000")
                add_candidate("http://localhost:5000")
            elif normalized_backend == "jan":
                add_candidate("http://127.0.0.1:1337/v1")
                add_candidate("http://localhost:1337/v1")
                add_candidate("http://127.0.0.1:1337")
                add_candidate("http://localhost:1337")
            else:
                add_candidate("http://127.0.0.1:8000/v1")
                add_candidate("http://localhost:8000/v1")
                add_candidate("http://127.0.0.1:8000")
                add_candidate("http://localhost:8000")

        return candidates

    def _extract_endpoint_host(self, endpoint: str) -> str:
        value = str(endpoint).strip()
        if not value:
            return ""
        parsed = urllib.parse.urlsplit(value if "://" in value else f"http://{value}")
        return str(parsed.hostname or "").strip().lower()

    def _is_local_host(self, host: str) -> bool:
        normalized = str(host).strip().lower()
        if not normalized:
            return True
        if normalized == "localhost" or normalized == "::1":
            return True
        if normalized.startswith("127."):
            return True
        return False

    def _prepare_request_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        prepared = dict(headers)
        prepared.setdefault("Accept", "application/json")
        prepared.setdefault(
            "User-Agent",
            "6X-Protocol-Studio/1.0 (+https://6xprotocol.local)",
        )
        return prepared

    def _resolve_temperature(self, node_value: Optional[str], bot: Optional[Bot]) -> float:
        # Node config should override bot profile defaults.
        if str(node_value or "").strip():
            return self._clamp_float(self._resolve_float(node_value, default=0.2), 0.0, 2.0)
        if bot and str(bot.temperature).strip():
            return self._clamp_float(self._resolve_float(bot.temperature, default=0.2), 0.0, 2.0)
        return 0.2

    def _resolve_max_tokens(self, node_value: Optional[str], bot: Optional[Bot]) -> int:
        # Node config should override bot profile defaults.
        if str(node_value or "").strip():
            return self._clamp_int(self._resolve_int(node_value, default=700), 64, 64000)
        if bot and str(bot.max_tokens).strip():
            return self._clamp_int(self._resolve_int(bot.max_tokens, default=700), 64, 64000)
        return 700

    def _resolve_float(self, value: Optional[str], default: float) -> float:
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _resolve_int(self, value: Optional[str], default: int) -> int:
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _clamp_float(self, value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, value))

    def _clamp_int(self, value: int, minimum: int, maximum: int) -> int:
        return max(minimum, min(maximum, value))
