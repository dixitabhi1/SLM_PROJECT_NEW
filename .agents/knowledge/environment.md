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
| **VRAM Baseline Idle** | ~306 MiB consumed by Windows/desktop background apps (~5,838 MiB free) | `nvidia-smi` | 2026-10-08 |
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
| **llama-server (Primary)** | Bundled build dated 2026-09-09 (`tools/llama_bin/llama-server.exe`, Vulkan GPU backend, SHA-256: `447F64D33C4A22AB7B18E9BB95C4CA1CF2E48C96AAFDF6A133E4857902B30E6E`, size: 22,920 bytes, copied from Ollama 0.34.0 bundled `lib/ollama/llama-server.exe`; companion `tools/llama_bin/ggml-vulkan.dll`, SHA-256: `8008867C58AB33CFBD4379D552BEF05E189EC315B8A807B403C947F869BEDCDF`, size: 21,373,440 bytes) | `llama-server.exe --list-devices` & `Get-FileHash` | 2026-10-08 |
| **Ollama (Legacy)** | Version 0.34.0 (binary at `C:\Users\ACER\AppData\Local\Programs\Ollama\ollama.exe`) | `ollama.exe serve` log | 2026-10-07 |
| **LoRA Adapter Converter** | `tools/llama_cpp/convert_lora_to_gguf.py` (llama.cpp commit `26394b4e6749a41c3633db040e0987500a5f7013`, 2026-09-21) | Git commit in repo tooling | 2026-10-08 |
| **Groq API** | Verified active via `GROQ_API_KEY` in `.env` (Models: `qwen/qwen3.8-27b`, `openai/gpt-oss-120b`) | HTTP API test | 2026-10-07 |
| **Google AI Studio API** | Verified active via `GEMINI_API_KEY` in `.env` (`gemini-2.5-flash`) | HTTP API test | 2026-10-07 |

---

## 3. Serving Backend: `llama-server.exe` with Vulkan GPU Offload

### 3.1 Architecture & Device Discovery
To avoid GPU kernel compilation errors present in CUDA 12 on driver 546.18, `llama-server.exe` uses the high-performance Vulkan backend (`ggml-vulkan.dll`).
- **Binary Provenance:** Copied directly from `C:\Users\ACER\AppData\Local\Programs\Ollama\lib\ollama\llama-server.exe` (SHA-256: `447F64D3...`) and `C:\Users\ACER\AppData\Local\Programs\Ollama\lib\ollama\vulkan\ggml-vulkan.dll` (SHA-256: `8008867C...`) into repository tooling (`tools/llama_bin/`).
- **Device Selection:**
  ```text
  Vulkan0: NVIDIA GeForce RTX 3050 6GB Laptop GPU (6017 MiB total, 5249 MiB free)
  ```
- **Context Per Slot Mechanics:**
  `llama-server`'s `-c` argument defines the **total context pool across all slots**. Per-slot context is calculated as:
  $$n_{\text{ctx\_slot}} = \frac{n_{\text{ctx}}}{n_{\text{parallel}}}$$
  To provide $\ge 4,096$ tokens per slot:
  - For $W = 3$ parallel slots: specify `-c 12288` (allocates exactly 4,096 tokens per slot).
  - For $W = 2$ parallel slots: specify `-c 12288` (allocates exactly 6,144 tokens per slot).

### 3.2 Canonical Launch Commands

```powershell
# Production Configuration (f): 3 parallel slots, 4,096 context per slot (Total ctx = 12,288)
tools\llama_bin\llama-server.exe `
  -m "C:\Users\ACER\.ollama\models\blobs\sha256-3c168af1dea0a414299c7d9077e100ac763370e5a98b3c53801a958a47f0a5db" `
  --device "Vulkan0" `
  -ngl 99 `
  -c 12288 `
  -np 3 `
  --port 8080 `
  --host 127.0.0.1

# Long Context Configuration: 2 parallel slots, 6,144 context per slot (Total ctx = 12,288)
tools\llama_bin\llama-server.exe `
  -m "C:\Users\ACER\.ollama\models\blobs\sha256-3c168af1dea0a414299c7d9077e100ac763370e5a98b3c53801a958a47f0a5db" `
  --device "Vulkan0" `
  -ngl 99 `
  -c 12288 `
  -np 2 `
  --port 8080 `
  --host 127.0.0.1
```

### 3.3 Measured Hardware Footprint & Adapter Switching
- **Dedicated VRAM (W=3, c_slot=4096, c_total=12288):** ~4,307 MiB (1,837 MiB headroom on 6,144 MiB GPU).
- **Dedicated VRAM (W=2, c_slot=6144, c_total=12288):** ~4,309 MiB (1,835 MiB headroom on 6,144 MiB GPU).
- **GPU Offload Percentage:** 100.0% (zero CPU layer spillover).
- **Runtime Adapter Switching Latency:** **1.815 ms** via `POST /lora-adapters` (8,700x faster than Ollama's 15.9 s disk reload).
- **Per-Request LoRA Concurrency:** Verified supported. Simultaneous concurrent requests passing distinct LoRA specifications execute on separate parallel slots with independent specialized weights.

---

## 4. Laptop Execution Discipline

- **AC Power Strictly Required:** Battery throttling reduces throughput by ~65%; all benchmark scripts verify AC line state before launching.
- **Sleep Prevention:** Windows modern standby disabled during all long-running tasks.
- **VRAM Verification Gate:** Before every batch, `nvidia-smi` confirms available VRAM $\ge$ required allocation.
- **Hard Timeout:** 600 s hard subprocess timeout on every individual evaluation query.

---

## 5. Training Compute Platform: Free Kaggle GPU (Owner-Approved Exception)

Per owner decision (2026-10-08), adapter fine-tuning (Phase 6, Rung C4) is offloaded to a free Kaggle GPU (NVIDIA T4 / P100, 16 GB VRAM) while inference serving, pipeline orchestration, tool execution, and all evaluation remain strictly on the host laptop.

### Rigorous Operational Protocols for Kaggle Training:
1. **Agent Prepares, Owner Runs:** Agent prepares a self-contained notebook and training data file; owner executes it on Kaggle.
2. **Strict Evaluation Isolation:** Training data contains strictly zero dev, held-out, reserve, or spent items, verified by cryptographic SHA-256 hash and near-duplicate scanning before upload. No evaluation data is ever uploaded to Kaggle.
3. **Zero Secrets:** No API keys, credentials, or secrets in notebooks or data files.
4. **Reproducibility & Pinned Artifacts:** Exact library versions, fixed seed (`42`), and the exact Hugging Face snapshot hash of Phi-4-mini (`844cc3c...`) from `model_registry.md` are pinned.
5. **Local Verification Gate:** Trained adapters, training logs, validation curves, and configs are downloaded to `adapters/<name>/`, cryptographically hashed, converted to GGUF using repo tooling, and verified locally on `llama-server`. An adapter is accepted only if it beats the base model on dev task accuracy.
6. **Execution Gating:** Fine-tuning starts only after Rungs C0 to C3 are measured on dev and owner gives explicit sign-off.
7. **Zero Spend Preserved:** Financial spend remains strictly $0.00.
