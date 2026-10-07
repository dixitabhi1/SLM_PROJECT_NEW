# Environment & Hardware Specification

All facts in this document were empirically verified via system commands on the host machine.

---

## 1. Hardware

| Component | Verified Specification | Source | Verification Date |
|---|---|---|---|
| **GPU** | NVIDIA GeForce RTX 3050 Laptop GPU (6,144 MiB / 6 GB GDDR6) | `nvidia-smi` | 2026-10-07 |
| **GPU Driver** | 546.18 | `nvidia-smi` | 2026-10-07 |
| **CUDA Driver Version** | 12.3 | `nvidia-smi` | 2026-10-07 |
| **GPU Power Cap** | 65 W | `nvidia-smi` | 2026-10-07 |
| **VRAM Baseline Idle** | ~615 MiB consumed by Windows/desktop background apps (~5,529 MiB free) | `nvidia-smi` | 2026-10-07 |
| **CPU** | 13th Gen Intel(R) Core(TM) i5-13420H (8 cores: 4 P-cores + 4 E-cores, 12 logical threads) | `Get-CimInstance Win32_Processor` | 2026-10-07 |
| **Host System RAM** | 16 GB (~16,473,976 KB visible) | `Get-CimInstance Win32_OperatingSystem` | 2026-10-07 |
| **Operating System** | Microsoft Windows 11 Home Single Language (Version 10.0.26200, 64-bit) | `Get-CimInstance Win32_OperatingSystem` | 2026-10-07 |

---

## 2. Software & Tooling Environment

| Tool / Runtime | Verified Version / State | Source | Verification Date |
|---|---|---|---|
| **Python** | 3.12.10 (64-bit) | `python --version` | 2026-10-07 |
| **Pip** | 25.0.1 | `python -m pip --version` | 2026-10-07 |
| **PyTorch** | 2.5.1+cu121 (`torch.cuda.is_available() == True`, CUDA arch sm_86) | `python -c "import torch; ..."` | 2026-10-07 |
| **Git** | 2.50.0.windows.1 | `git --version` | 2026-10-07 |
| **GitHub CLI** | Authenticated as `dixitabhi1` (repo scope confirmed) | `gh auth status` | 2026-10-07 |
| **Ollama** | Version 0.34.0 (binary at `C:\Users\ACER\AppData\Local\Programs\Ollama\ollama.exe`) | `ollama.exe serve` log | 2026-10-07 |
| **Ollama Models Dir** | `C:\Users\ACER\.ollama\models` | `ollama.exe serve` config log | 2026-10-07 |
| **Ollama Backend** | Vulkan (`OLLAMA_LLM_LIBRARY=vulkan`, `llama-server-vulkan`) | Empirical test | 2026-10-07 |
| **Groq API** | Verified active via `GROQ_API_KEY` in `.env` (Models: `qwen/qwen3.8-27b`, `openai/gpt-oss-120b`) | HTTP API test | 2026-10-07 |
| **Google AI Studio API** | Verified active via `GEMINI_API_KEY` in `.env` (`gemini-2.5-flash`) | HTTP API test | 2026-10-07 |

---

## 3. Ollama Execution Backend: Vulkan Rationale

During initial setup on Windows 11 with NVIDIA Driver 546.18 and CUDA 12.3:
- Ollama's default CUDA 12 backend (`llama-server-cuda_v12.exe`) failed with:
  `CUDA error: device kernel image is invalid` (`ggml_cuda_kernel_can_use_pdl`).
- The failure occurred because the precompiled CUDA 12 binary in Ollama 0.34.0 contained kernel PTX incompatible with the installed NVIDIA driver version (546.18, requiring either a driver update to 550+ or fallback runtime).
- To maintain zero-risk stability on the laptop without modifying system display drivers, the Vulkan runtime was evaluated:
  ```powershell
  $env:OLLAMA_LLM_LIBRARY = "vulkan"
  ollama serve
  ```
- **Verification:** Under Vulkan, `llama-server-vulkan.exe` initialized cleanly on the NVIDIA GeForce RTX 3050 Laptop GPU (device ID 0, 5,120 MiB available), offloaded 100% of model layers directly to VRAM (verified via `ollama ps`: `100% GPU`), achieved full generation speed (~49 tokens/second for 3.8B/3.2B models), and produced zero kernel compilation or execution errors.


---

## 4. Server Configuration & Execution Parameters

```powershell
# Server limits must be set explicitly to owner-approved config from parallelism benchmark (never left at defaults):
# Config (a): two bases <= 4B co-loaded: OLLAMA_MAX_LOADED_MODELS=2, OLLAMA_NUM_PARALLEL=1
# Config (b): three bases <= 3B co-loaded: OLLAMA_MAX_LOADED_MODELS=3, OLLAMA_NUM_PARALLEL=1
# Config (c): one base at a time with parallel slots: OLLAMA_MAX_LOADED_MODELS=1, OLLAMA_NUM_PARALLEL=2 (or owner-approved slots)
# Config (d): serial reference: OLLAMA_MAX_LOADED_MODELS=1, OLLAMA_NUM_PARALLEL=1
$env:OLLAMA_MAX_LOADED_MODELS = "1"
$env:OLLAMA_NUM_PARALLEL = "1"
$env:OLLAMA_KEEP_ALIVE = "5m"
$env:OLLAMA_HOST = "127.0.0.1:11434"
```

- **GPU Offload Verification:** Every batch start inspects `ollama` process allocation or llama.cpp layer offload to guarantee 100% layers fit in VRAM. Fallback to CPU aborts the run immediately.
- **Per-Call Timeout:** 600 s hard timeout enforced in subprocess runner.
- **Health Checks:** Conducted before every batch and after every 10 evaluation items; on server error, restart server and resume.
- **Execution Safeguards:** AC power strictly required; Windows sleep state disabled during all benchmark runs.
- **Laptop Discipline:** GPU memory and temperature logged at batch start; run budgeted in advance: items x calls x seconds.
