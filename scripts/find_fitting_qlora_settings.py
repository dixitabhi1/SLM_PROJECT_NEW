"""
Systematic exploration of QLoRA settings on Phi-4-mini to find what fits on 6 GB VRAM.
Tests combinations of:
- Target modules: all-linear vs attention-only (qkv_proj, o_proj)
- Optimizer: AdamW vs PagedAdamW8bit
- Gradient checkpointing: enabled
- Sequence length: 1024, 768, 512

Direct recording from hardware.
"""

import os
import sys
import time
import json
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
import bitsandbytes as bnb

os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_NAME = "microsoft/Phi-4-mini-instruct"

def test_combination(seq_len: int, target_type: str, optimizer_type: str):
    print("\n" + "=" * 65)
    print(f"TESTING: seq_len={seq_len}, targets={target_type}, opt={optimizer_type}")
    print("=" * 65)

    torch.cuda.empty_cache()
    time.sleep(1.0)

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        quantization_config=bnb_config,
        device_map={"": 0},
        trust_remote_code=False,
    )
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    model.gradient_checkpointing_enable()

    if target_type == "all-linear":
        targets = "all-linear"
    elif target_type == "attention-only":
        targets = ["qkv_proj", "o_proj"]
    else:
        targets = ["qkv_proj"]

    peft_config = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=targets,
    )
    model = get_peft_model(model, peft_config)

    trainable_params, all_params = model.get_nb_trainable_parameters()
    print(f"Trainable params: {trainable_params:,} / {all_params:,} ({trainable_params/all_params*100:.2f}%)")

    dummy_input_ids = torch.randint(100, 5000, (1, seq_len), device="cuda:0")
    dummy_labels = dummy_input_ids.clone()

    if optimizer_type == "paged_adamw_8bit":
        optimizer = bnb.optim.PagedAdamW8bit(model.parameters(), lr=1e-4)
    else:
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)

    torch.cuda.reset_peak_memory_stats()
    step_times = []
    peak_vram_mb = 0
    oom = False
    err_msg = ""

    try:
        for s in range(1, 4):
            t0 = time.perf_counter()
            optimizer.zero_grad()
            outputs = model(input_ids=dummy_input_ids, labels=dummy_labels)
            loss = outputs.loss
            loss.backward()
            optimizer.step()
            dt = time.perf_counter() - t0
            step_times.append(dt)
            cuda_peak = torch.cuda.max_memory_allocated() / (1024 * 1024)
            print(f"  Step [{s}/3] | Loss: {loss.item():.4f} | Time: {dt:.3f} s | CUDA Peak: {cuda_peak:.1f} MiB")

        peak_vram_mb = round(torch.cuda.max_memory_allocated() / (1024 * 1024), 1)

    except torch.cuda.OutOfMemoryError as e:
        oom = True
        err_msg = "CUDA OutOfMemoryError"
        print(f"  [OOM ERROR] {err_msg}")
    except Exception as e:
        oom = True
        err_msg = str(e)
        print(f"  [ERROR] {err_msg}")

    del model
    del optimizer
    torch.cuda.empty_cache()
    time.sleep(1.5)

    return {
        "seq_len": seq_len,
        "target_type": target_type,
        "optimizer": optimizer_type,
        "trainable_params": trainable_params,
        "oom": oom,
        "error": err_msg,
        "peak_cuda_mb": peak_vram_mb if not oom else None,
        "avg_step_time_s": round(sum(step_times) / len(step_times), 3) if step_times else None,
        "fits": not oom,
    }


def main():
    trials = [
        # 1. Attention-only, 1024 seq_len, PagedAdamW8bit
        (1024, "attention-only", "paged_adamw_8bit"),
        # 2. Attention-only, 1024 seq_len, AdamW
        (1024, "attention-only", "adamw"),
        # 3. all-linear, 512 seq_len, PagedAdamW8bit
        (512, "all-linear", "paged_adamw_8bit"),
        # 4. all-linear, 512 seq_len, AdamW
        (512, "all-linear", "adamw"),
        # 5. all-linear, 768 seq_len, PagedAdamW8bit
        (768, "all-linear", "paged_adamw_8bit"),
    ]

    results = []
    for seq_len, target_type, opt in trials:
        res = test_combination(seq_len, target_type, opt)
        results.append(res)
        print(f"Result: Fits={res['fits']}, Peak={res['peak_cuda_mb']} MiB, Time={res['avg_step_time_s']} s")

    out_file = os.path.join(REPO_ROOT, "results", "benchmarks", "qlora_fitting_matrix.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved exploration matrix to: {out_file}")

if __name__ == "__main__":
    main()
