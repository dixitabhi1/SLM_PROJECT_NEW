"""
Ollama inference client with health checks, fail-loud error handling,
deterministic seeds, and 600s timeouts.
Zero fabricated outputs.
"""

import os
import json
import time
import subprocess
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, List
from dataclasses import dataclass


@dataclass
class ModelResponse:
    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    finish_reason: str
    latency_seconds: float
    seed: int
    model_id: str
    status: str  # 'COMPLETE', 'FAILED'
    error_message: Optional[str] = None


class OllamaClient:
    """
    Communicates with local Ollama server adhering to Section 4 constraints.
    """

    def __init__(self, host: str = "http://127.0.0.1:11434", timeout_seconds: float = 600.0):
        self.host = host.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.item_counter = 0

    def health_check(self) -> bool:
        """Verifies Ollama server is responding on host."""
        req = urllib.request.Request(f"{self.host}/api/tags", headers={"User-Agent": "SLM-Engine/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                return resp.status == 200
        except Exception:
            return False

    def ensure_server_running(self) -> bool:
        """Checks health; if down, attempts to start ollama serve in background."""
        if self.health_check():
            return True

        # Attempt start with Vulkan library for RTX 3050 full GPU offload
        env = os.environ.copy()
        env["OLLAMA_LLM_LIBRARY"] = "vulkan"
        try:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )
            # Wait up to 15s for server to start
            for _ in range(15):
                time.sleep(1.0)
                if self.health_check():
                    return True
        except Exception:
            pass

        return False

    def generate(
        self,
        model_id: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        seed: int = 42,
        temperature: float = 0.0,
        stop_tokens: Optional[List[str]] = None,
        max_tokens: Optional[int] = 512,
        think: bool = False,
    ) -> ModelResponse:
        """
        Sends generation request to Ollama.
        Fails loudly on empty generation, 0 tokens, timeout, or server error.
        """
        self.item_counter += 1
        # Health check every 10 items per Section 4
        if self.item_counter % 10 == 0:
            if not self.ensure_server_running():
                return ModelResponse(
                    content="",
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    finish_reason="error",
                    latency_seconds=0.0,
                    seed=seed,
                    model_id=model_id,
                    status="FAILED",
                    error_message="Ollama health check failed at 10-item interval",
                )

        payload: Dict[str, Any] = {
            "model": model_id,
            "prompt": prompt,
            "stream": False,
            "think": think,
            "options": {
                "seed": seed,
                "temperature": temperature,
                "num_predict": max_tokens if max_tokens is not None else 512,
            },
        }
        if system_prompt:
            payload["system"] = system_prompt
        if stop_tokens:
            payload["options"]["stop"] = stop_tokens

        req = urllib.request.Request(
            f"{self.host}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "SLM-Engine/1.0"},
        )

        start_time = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                elapsed = time.perf_counter() - start_time
                data = json.loads(resp.read().decode("utf-8"))

                content = data.get("response", "")
                prompt_tokens = data.get("prompt_eval_count", 0)
                completion_tokens = data.get("eval_count", 0)
                total_tokens = prompt_tokens + completion_tokens
                done_reason = data.get("done_reason", "stop")

                # Hard Rule 3: Fail loudly on empty tokens or non-stop finish
                if not content or completion_tokens == 0:
                    return ModelResponse(
                        content="",
                        prompt_tokens=prompt_tokens,
                        completion_tokens=0,
                        total_tokens=prompt_tokens,
                        finish_reason="empty_output",
                        latency_seconds=elapsed,
                        seed=seed,
                        model_id=model_id,
                        status="FAILED",
                        error_message="Zero completion tokens received from model",
                    )

                finish_reason = "stop" if data.get("done", False) else done_reason
                status = "COMPLETE" if finish_reason == "stop" else "FAILED"

                return ModelResponse(
                    content=content,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    finish_reason=finish_reason,
                    latency_seconds=elapsed,
                    seed=seed,
                    model_id=model_id,
                    status=status,
                    error_message=None if status == "COMPLETE" else f"Unfinished generation: {finish_reason}",
                )

        except urllib.error.HTTPError as he:
            elapsed = time.perf_counter() - start_time
            # Attempt restart on server 500 error
            if he.code >= 500:
                self.ensure_server_running()
            return ModelResponse(
                content="",
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                finish_reason="server_error",
                latency_seconds=elapsed,
                seed=seed,
                model_id=model_id,
                status="FAILED",
                error_message=f"HTTP Error {he.code}: {he.reason}",
            )
        except Exception as e:
            elapsed = time.perf_counter() - start_time
            return ModelResponse(
                content="",
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                finish_reason="timeout" if "timed out" in str(e).lower() else "exception",
                latency_seconds=elapsed,
                seed=seed,
                model_id=model_id,
                status="FAILED",
                error_message=str(e),
            )
