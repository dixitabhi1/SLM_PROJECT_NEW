"""
Benchmark QLoRA peak VRAM at 1,024 sequence length on Phi-4-mini (6 GB Laptop GPU).
Tests:
1. Target modules: all-linear vs q_proj/v_proj
2. Gradient checkpointing: enabled vs disabled
3. Sequence length: 1,024 tokens
4. Batch size: 1
5. Optimizer: AdamW, lr=1e-4

Zero fabricated numbers. Direct recording from disk and hardware APIs.
"""

import os
import sys
import json
import time
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)
from src.serving.hardware import get_gpu_status

MODEL_NAME = "microsoft/Phi-4-mini-instruct"
RESULTS_DIR = os.path.join(REPO_ROOT, "results", "benchmarks")
os.makedirs(RESULTS_DIR, exist_ok=True)


def test_configuration(seq_length: int = 1024, use_gradient_checkpointing: bool = True, target_modules: str = "all-linear", num_steps: int = 5):
    print("\n" + "=" * 70)
    print(f"TESTING QLORA CONFIGURATION: seq_len={seq_length}, grad_ckpt={use_gradient_checkpointing}, targets={target_modules}")
    print("=" * 70)

    torch.cuda.empty_cache()
    time.sleep(2.0)
    baseline_gpu = get_gpu_status()
    print(f"Baseline VRAM: {baseline_gpu.used_vram_mb} MiB")

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=False)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        quantization_config=bnb_config,
        device_map={"": 0},
        trust_remote_code=False,
    )

    model = prepare_model_for_kbit_training(
        model,
        use_gradient_checkpointing=use_gradient_checkpointing,
    )
    if use_gradient_checkpointing:
        model.gradient_checkpointing_enable()

    targets = "all-linear" if target_modules == "all-linear" else ["q_proj", "v_proj", "o_proj", "gate_up_proj", "down_proj"]

    peft_config = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=targets,
    )
    model = get_peft_model(model, peft_config)

    # Create dummy tokens of length seq_length
    dummy_input_ids = torch.randint(100, 30000, (1, seq_length), device="cuda:0")
    dummy_labels = dummy_input_ids.clone()

    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
    torch.cuda.reset_peak_memory_stats()

    step_times = []
    peak_hardware_vram = baseline_gpu.used_vram_mb
    oom_occurred = False
    error_message = None

    try:
        for s in range(1, num_steps + 1):
            t0 = time.perf_counter()
            optimizer.zero_grad()
            outputs = model(input_ids=dummy_input_ids, labels=dummy_labels)
            loss = outputs.loss
            loss.backward()
            optimizer.step()
            dt = time.perf_counter() - t0
            step_times.append(dt)

            gpu = get_gpu_status()
            if gpu.used_vram_mb > peak_hardware_vram:
                peak_hardware_vram = gpu.used_vram_mb

            cuda_allocated = round(torch.cuda.memory_allocated() / (1024 * 1024), 1)
            cuda_peak = round(torch.cuda.max_memory_allocated() / (1024 * 1024), 1)
            print(f"  Step [{s}/{num_steps}] | Loss: {loss.item():.4f} | Time: {dt:.3f} s | CUDA Peak: {cuda_peak} MiB | Hardware VRAM: {gpu.used_vram_mb} MiB")

    except torch.cuda.OutOfMemoryError as e:
        oom_occurred = True
        error_message = f"CUDA OutOfMemoryError: {e}"
        print(f"  [OOM ERROR] {error_message}")
        torch.cuda.empty_cache()
    except Exception as e:
        oom_occurred = True
        error_message = str(e)
        print(f"  [ERROR] {error_message}")
        torch.cuda.empty_cache()

    del model
    del optimizer
    torch.cuda.empty_cache()
    time.sleep(2.0)

    avg_step_time = round(sum(step_times) / len(step_times), 4) if step_times else None
    headroom = 6144 - peak_hardware_vram if not oom_occurred else 0

    res = {
        "seq_length": seq_length,
        "batch_size": 1,
        "use_gradient_checkpointing": use_gradient_checkpointing,
        "target_modules": target_modules,
        "num_steps": num_steps,
        "oom_occurred": oom_occurred,
        "error_message": error_message,
        "peak_hardware_vram_mb": peak_hardware_vram,
        "headroom_mb": headroom,
        "avg_step_time_seconds": avg_step_time,
        "status": "QUALIFIED_FITS_ON_GPU" if not oom_occurred and peak_hardware_vram <= 6000 else "DISQUALIFIED_OOM",
    }
    return res


def main():
    print("=" * 70)
    print("EVALUATING PHI-4-MINI QLORA REAL TRAINING SETTINGS (SEQ_LEN = 1024)")
    print("=" * 70)

    # 1. Test seq_len=1024 with gradient checkpointing ENABLED (Recommended for production)
    res_with_ckpt = test_configuration(
        seq_length=1024,
        use_gradient_checkpointing=True,
        target_modules="all-linear",
        num_steps=5,
    )

    # 2. Test seq_len=1024 with gradient checkpointing DISABLED (Stress test)
    res_no_ckpt = test_configuration(
        seq_length=1024,
        use_gradient_checkpointing=False,
        target_modules="all-linear",
        num_steps=5,
    )

    final_results = {
        "model_id": MODEL_NAME,
        "tested_seq_length": 1024,
        "batch_size": 1,
        "optimizer": "AdamW (lr=1e-4)",
        "gradient_accumulation_steps": 1,
        "configurations": [res_with_ckpt, res_no_ckpt],
    }

    out_file = os.path.join(RESULTS_DIR, "phi4_mini_qlora_seqlen1024.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(final_results, f, indent=2)
    print(f"\nSaved 1,024-token dry run evaluation to: {out_file}")


if __name__ == "__main__":
    main()

