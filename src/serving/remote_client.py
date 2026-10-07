"""
Remote API client for Baseline models (Groq) and Judge (Gemini).
Enforces fail-loud verification, seed logging, and rate-limit retries.
Zero fabricated outputs.
"""

import os
import json
import time
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv
from .ollama_client import ModelResponse

load_dotenv()


class GroqClient:
    """Communicates with Groq API for baseline open-weight models."""

    def __init__(self, api_key: Optional[str] = None, timeout_seconds: float = 600.0):
        self.api_key = api_key or os.getenv("GROQ_API_KEY", "")
        self.timeout_seconds = timeout_seconds
        self.endpoint = "https://api.groq.com/openai/v1/chat/completions"

    def generate(
        self,
        model_id: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        seed: int = 42,
        temperature: float = 0.0,
    ) -> ModelResponse:
        if not self.api_key:
            return ModelResponse(
                content="",
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                finish_reason="no_api_key",
                latency_seconds=0.0,
                seed=seed,
                model_id=model_id,
                status="FAILED",
                error_message="GROQ_API_KEY is missing from environment",
            )

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
            "seed": seed,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        }

        # Up to 3 retries on 429 rate limit
        for attempt in range(4):
            start_time = time.perf_counter()
            req = urllib.request.Request(
                self.endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                    elapsed = time.perf_counter() - start_time
                    data = json.loads(resp.read().decode("utf-8"))

                    choice = data["choices"][0]
                    content = choice["message"]["content"]
                    finish_reason = choice.get("finish_reason", "stop")
                    usage = data.get("usage", {})
                    p_tok = usage.get("prompt_tokens", 0)
                    c_tok = usage.get("completion_tokens", 0)
                    t_tok = usage.get("total_tokens", 0)

                    if not content or c_tok == 0:
                        return ModelResponse(
                            content="",
                            prompt_tokens=p_tok,
                            completion_tokens=0,
                            total_tokens=t_tok,
                            finish_reason="empty_output",
                            latency_seconds=elapsed,
                            seed=seed,
                            model_id=model_id,
                            status="FAILED",
                            error_message="Zero tokens received from Groq",
                        )

                    status = "COMPLETE" if finish_reason == "stop" else "FAILED"
                    return ModelResponse(
                        content=content,
                        prompt_tokens=p_tok,
                        completion_tokens=c_tok,
                        total_tokens=t_tok,
                        finish_reason=finish_reason,
                        latency_seconds=elapsed,
                        seed=seed,
                        model_id=model_id,
                        status=status,
                    )

            except urllib.error.HTTPError as he:
                elapsed = time.perf_counter() - start_time
                if he.code == 429 and attempt < 3:
                    time.sleep(2.0 * (attempt + 1))
                    continue
                return ModelResponse(
                    content="",
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    finish_reason="http_error",
                    latency_seconds=elapsed,
                    seed=seed,
                    model_id=model_id,
                    status="FAILED",
                    error_message=f"Groq HTTP Error {he.code}: {he.reason}",
                )
            except Exception as e:
                elapsed = time.perf_counter() - start_time
                return ModelResponse(
                    content="",
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    finish_reason="exception",
                    latency_seconds=elapsed,
                    seed=seed,
                    model_id=model_id,
                    status="FAILED",
                    error_message=str(e),
                )


class GeminiJudgeClient:
    """Communicates with Google Gemini API for Track B judging."""

    def __init__(self, api_key: Optional[str] = None, timeout_seconds: float = 600.0):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.timeout_seconds = timeout_seconds

    def generate(
        self,
        model_id: str = "gemini-2.5-flash",
        prompt: str = "",
        system_prompt: Optional[str] = None,
        seed: int = 42,
        temperature: float = 0.0,
    ) -> ModelResponse:
        if not self.api_key:
            return ModelResponse(
                content="",
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                finish_reason="no_api_key",
                latency_seconds=0.0,
                seed=seed,
                model_id=model_id,
                status="FAILED",
                error_message="GEMINI_API_KEY is missing from environment",
            )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={self.api_key}"

        payload: Dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "seed": seed,
            },
        }
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        headers = {"Content-Type": "application/json"}

        for attempt in range(4):
            start_time = time.perf_counter()
            req = urllib.request.Request(
                url, data=json.dumps(payload).encode("utf-8"), headers=headers
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                    elapsed = time.perf_counter() - start_time
                    data = json.loads(resp.read().decode("utf-8"))

                    candidates = data.get("candidates", [])
                    if not candidates:
                        return ModelResponse(
                            content="",
                            prompt_tokens=0,
                            completion_tokens=0,
                            total_tokens=0,
                            finish_reason="no_candidates",
                            latency_seconds=elapsed,
                            seed=seed,
                            model_id=model_id,
                            status="FAILED",
                            error_message="Gemini returned no candidates",
                        )

                    cand = candidates[0]
                    parts = cand.get("content", {}).get("parts", [])
                    content = parts[0].get("text", "") if parts else ""
                    finish_reason = cand.get("finishReason", "STOP").lower()
                    if finish_reason == "stop":
                        finish_reason = "stop"

                    usage = data.get("usageMetadata", {})
                    p_tok = usage.get("promptTokenCount", 0)
                    c_tok = usage.get("candidatesTokenCount", 0)
                    t_tok = usage.get("totalTokenCount", 0)

                    status = "COMPLETE" if finish_reason == "stop" and content else "FAILED"
                    return ModelResponse(
                        content=content,
                        prompt_tokens=p_tok,
                        completion_tokens=c_tok,
                        total_tokens=t_tok,
                        finish_reason=finish_reason,
                        latency_seconds=elapsed,
                        seed=seed,
                        model_id=model_id,
                        status=status,
                    )

            except urllib.error.HTTPError as he:
                elapsed = time.perf_counter() - start_time
                if he.code == 429 and attempt < 3:
                    time.sleep(2.0 * (attempt + 1))
                    continue
                return ModelResponse(
                    content="",
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    finish_reason="http_error",
                    latency_seconds=elapsed,
                    seed=seed,
                    model_id=model_id,
                    status="FAILED",
                    error_message=f"Gemini HTTP Error {he.code}: {he.reason}",
                )
            except Exception as e:
                elapsed = time.perf_counter() - start_time
                return ModelResponse(
                    content="",
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    finish_reason="exception",
                    latency_seconds=elapsed,
                    seed=seed,
                    model_id=model_id,
                    status="FAILED",
                    error_message=str(e),
                )

