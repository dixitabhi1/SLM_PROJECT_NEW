# System Architecture: SLM Specialization & Evaluation Framework
**Target Platform:** Edge / Laptop Compute (NVIDIA GeForce RTX 3050 Laptop GPU, 6 GB GDDR6 VRAM, ~5.1 GiB Usable)  
**Operating Constraint:** Strictly Zero Cloud Spend, Hard Rule 8 Family Isolation, 100% GPU Offload ($c=4096$)

---

## 1. High-Level End-to-End Architecture

```mermaid
flowchart TD
    subgraph ClientLayer ["1. Task Intake & Orchestration Layer"]
        CLI["CLI & Automated Batch Runner<br/>(scripts/benchmark_parallelism_50.py)"]
        DatasetLock["Cryptographic Dataset Lock<br/>(SHA-256 Verified Dev & Held-Out Splits)"]
        Router["Task Router & Specialist Dispatcher<br/>(Domain Tagger: Code, Math, SQL, Theory)"]
        DatasetLock --> CLI --> Router
    end

    subgraph ServingEngine ["2. Serving & Execution Engine (Configuration f)"]
        OllamaServer["Local Inference Server (Ollama + Vulkan/CUDA Backend)<br/>Host: 127.0.0.1:11434 | Concurrency: W=2 Parallel Slots | Context: 4096 Tokens"]
        ActiveBase["Active Loaded Base SLM (≤8B)<br/>Qwen Family (e.g., Qwen2.5-7B-Q3 / Qwen3-4B)<br/>100% GPU Offload (4.2–4.4 GB VRAM)"]
        
        subgraph AdapterPool ["Swappable LoRA / PEFT Adapter Pool (Fast Switching)"]
            AdCode["Coding Specialist Adapter<br/>(Python / Algorithms)"]
            AdMath["Math Specialist Adapter<br/>(GSM8K / Reasoning)"]
            AdSQL["SQL Specialist Adapter<br/>(Spider DDL / Relational)"]
            AdGen["Generalist / Base Mode<br/>(MCQ / Science)"]
        end

        OllamaServer --> ActiveBase
        ActiveBase --- AdapterPool
    end

    subgraph HardwareLayer ["3. Hardware & VRAM Guardrail"]
        GPU["NVIDIA GeForce RTX 3050 Laptop GPU<br/>VRAM: 6 GB GDDR6 (Usable: ~5.1 GiB)"]
        Monitor["Hardware VRAM & Thermal Telemetry<br/>(NVML / nvidia-smi API | 100% GPU Check)"]
        GPU --- Monitor
        ServingEngine -.->|"VRAM Budget: ≤4.5 GB Peak"| GPU
    end

    subgraph BaselineLadder ["4. Multi-Tier Baselines (Strict Hard Rule 8 Family Isolation)"]
        GroqT1["Tier 1 (20B Baseline)<br/>openai/gpt-oss-20b (Groq API)<br/>Free: 1,000 RPD | Family: OpenAI"]
        GoogleT1["Tier 1 Alt (26B/31B Baseline)<br/>gemma-4-26b-a4b-it (Google AI Studio API)<br/>Free: 1,500 RPD | Family: Google"]
        GroqT3["Tier 3 (120B Ceiling Baseline)<br/>openai/gpt-oss-120b (Groq API)<br/>Free Tier | Family: OpenAI"]
    end

    subgraph EvalLayer ["5. Two-Track Ground-Truth Verification Engine"]
        subgraph TrackA ["Track A: Deterministic Ground-Truth Checkers (Zero Cost / Zero Judge)"]
            CheckCode["Code Execution Sandbox<br/>(Python Ast / Safe Subprocess Test)"]
            CheckMath["Math Exact Extractor<br/>(Normalized Numerical / Algebraic Match)"]
            CheckSQL["SQLite In-Memory Execution<br/>(Schema Init + Result Set Match)"]
            CheckMCQ["MCQ Letter Extractor<br/>(Normalized Regex Choice Match)"]
        end

        subgraph TrackB ["Track B: Secondary Qualitative Verification"]
            Checklist["Automated Fact Checklist Scorer<br/>(Objective Token / Proposition Check)"]
            HeldOutJudge["LLM Judge (Postponed to Frozen Run)<br/>(Strictly barred from dev loops)"]
        end
    end

    subgraph GovernanceLayer ["6. Integrity & Audit Ledger"]
        AuditSuite["Automated Rule Auditor (src/audit/audit_rules.py)<br/>• Hard Rule 1: Zero fabricated numbers<br/>• Hard Rule 2: Immutable append-only logs<br/>• Hard Rule 7: Digest-pinned models<br/>• Hard Rule 8: Disjoint family matrix<br/>• Secret scan: Zero API key leakage"]
        Ledger["PROGRESS.md Validity Ledger<br/>(Stand/Superseded Records VL-001...VL-026)"]
        IncidentLog["Incident Log & Audit Evidence<br/>(INC-001 ... INC-004)"]
    end

    Router -->|"Slot 1 / Slot 2"| OllamaServer
    Router -->|"Parallel Benchmark Query"| BaselineLadder
    
    OllamaServer -->|"Specialist Predictions"| EvalLayer
    BaselineLadder -->|"Baseline Outputs"| EvalLayer
    
    EvalLayer -->|"Execution Results"| AuditSuite
    AuditSuite --> Ledger
    AuditSuite --> IncidentLog
```

---

## 2. Concurrency Model: Configuration (f) Deep Dive

In Configuration (f), we resolve the 6 GB VRAM physical boundary by hosting **one single base model at a time** configured with $W=2$ parallel request slots and dynamic adapter dispatching, preventing multi-model GPU out-of-memory thrashing:

```mermaid
sequenceDiagram
    autonumber
    participant Client as Test Runner (W=2 Concurrency)
    participant Engine as Ollama Server (Port 11434, Vulkan/CUDA)
    participant VRAM as RTX 3050 VRAM (6 GB Limit)
    participant Adapter as LoRA Adapter Swapper
    participant Eval as Subtask Execution Checker

    Note over VRAM: Base Model Loaded: Qwen2.5-7B-Q3 (3.8 GB) + KV Buffer (448 MB) = 4.25 GB Peak

    par Request Slot 1 (Task i: SQL Query)
        Client->>Engine: POST /api/generate (Slot 1, Context: 4096 tokens)
        Engine->>Adapter: Activate SQL Specialist Adapter
        Engine->>VRAM: Stream inference on Slot 1
        Engine-->>Client: Return Generated SQL Answer
    and Request Slot 2 (Task i+1: Python Code)
        Client->>Engine: POST /api/generate (Slot 2, Context: 4096 tokens)
        Engine->>Adapter: Activate Code Specialist Adapter
        Engine->>VRAM: Stream inference on Slot 2 (Overlapping KV)
        Engine-->>Client: Return Generated Code Answer
    end

    Note over Engine,Client: Measured Concurrency: C ≈ 1.98 (Continuous Overlap) | 100% GPU Offload

    Client->>Eval: Dispatch Outputs to Track A Checkers
    Eval->>Eval: SQLite In-Memory Execution (Slot 1)
    Eval->>Eval: Isolated Python Sandbox Execution (Slot 2)
    Eval-->>Client: Record Accurate Pass/Fail & Execution Metrics
```

---

## 3. Strict Hard Rule 8: Model Family Isolation Matrix

Hard Rule 8 mandates that specialist pool models, baseline models, and judges **must belong to non-overlapping model families**:

| Component | Selected Family | Primary Models | Serving Endpoint | Access & Cost | Status |
|---|---|---|---|---|---|
| **Specialist Pool** | **Qwen (Alibaba)** | `Qwen/Qwen2.5-7B-Instruct` (Q3_K_M) / `Qwen3-4B` | Local Laptop GPU (Ollama) | 100% Local / Free | **Active Active Pool** |
| **Baseline Tier 1 (20B)** | **OpenAI (Open-Weight)** | `openai/gpt-oss-20b` | Groq Cloud API | Free (1,000 RPD) | **Active Primary Baseline** |
| **Baseline Tier 1 Alt (26B)** | **Gemma (Google)** | `gemma-4-26b-a4b-it` | Google AI Studio API | Free (1,500 RPD) | **Verified Standby Baseline** |
| **Baseline Tier 3 (120B)** | **OpenAI (Open-Weight)** | `openai/gpt-oss-120b` | Groq Cloud API | Free Tier Ceiling | **Active Ceiling Baseline** |
| **Secondary Judge (Track B)** | **Postponed / Checklist** | Automated Fact Checklist (Dev); Gemini (Held-Out only) | Local Rule Check / API | Zero Spend / Cardless | **Track A Primary** |

> [!NOTE]
> **Disqualification Enforcement:**
> - Meta (`llama3.2:3b`) was evaluated and formally rejected (40.0% accuracy vs. 66.0% for Qwen-7B-Q3).
> - Alibaba models (`qwen3.8-27b`) are strictly barred from the baseline roster to prevent self-family evaluation bias.

---

## 4. Verification Engine: Two-Track Evaluation Flow

```mermaid
flowchart LR
    Output["Model Generation Output"] --> TypeCheck{"Subtask Type?"}

    subgraph TrackA ["Track A: Deterministic Checkers (100% Automated, 0 Cost)"]
        TypeCheck -->|"Code"| PyExec["Python Sandbox Test<br/>• AST syntax check<br/>• Isolated exec() test harness<br/>• Strict assert validation"]
        TypeCheck -->|"Math"| MathExec["Exact Match Extractor<br/>• Regex Boxed / Final value<br/>• Normalized float/fraction comparison"]
        TypeCheck -->|"SQL"| SQLExec["SQLite Execution Test<br/>• In-memory DB creation<br/>• Schema DDL + Data Insertion<br/>• Compare Result Set vs Gold SQL"]
        TypeCheck -->|"MCQ"| MCQExec["MCQ Letter Matcher<br/>• Strict letter extraction (A/B/C/D)<br/>• Ambiguity rejection"]
    end

    subgraph TrackB ["Track B: Qualitative Grounding"]
        TypeCheck -->|"Qualitative / Free-form"| FactCheck["Automated Checklist Check<br/>• Named Entity & Fact Verification<br/>• Truthful Proposition Count"]
    end

    PyExec --> Res["Structured Evaluation Record<br/>{status: COMPLETE, is_correct: True/False, checker: name}"]
    MathExec --> Res
    SQLExec --> Res
    MCQExec --> Res
    FactCheck --> Res

    Res --> Disk["Append-Only Raw Record on Disk<br/>(results/benchmarks/*.jsonl)"]
```

---

## 5. Summary of Architectural Advantages

1. **Hardware Feasibility:** Restricts peak VRAM to **4.2–4.4 GB**, comfortably inside the laptop GPU's ~5.1 GiB usable ceiling at $c=4096$, guaranteeing **zero CPU swapping**.
2. **High Concurrency:** Configuration (f) delivers a **1.7× throughput speedup** over serial execution ($\bar{C} \approx 1.98$) via parallel request batching.
3. **Audit Immunity:** Track A uses deterministic unit tests and SQLite execution, meaning **zero LLM judge bias, zero API costs, and zero quota bottlenecks**.
4. **Strict Integrity:** Model digests, raw outputs, and test logs are cryptographically immutable with an automated pre-commit audit gate.

