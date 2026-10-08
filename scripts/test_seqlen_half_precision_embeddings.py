"""
Empirical test for sequence lengths 512 and 1024 with:
1. Embedding matrix kept in half-precision (bfloat16) instead of casting up to float32.
2. Attention projections only: target_modules = ["qkv_proj", "o_proj"].
3. Gradient checkpointing enabled.
4. PagedAdamW8bit optimizer.
5. Measures and reports dedicated VRAM at sequence lengths 512 and 1024.
"""

import os
import sys
import time
import json
import torch
import bitsandbytes as bnb
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_NAME = "microsoft/Phi-4-mini-instruct"

def measure_seqlen(seq_len: int):
    print("\n" + "=" * 70)
    print(f"TESTING SEQUENCE LENGTH: {seq_len} tokens (Attention-Only, Half-Precision Embeddings)")
    print("=" * 70)

    torch.cuda.empty_cache()
    time.sleep(1.0)

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    print("Loading base 4-bit model...")
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        quantization_config=bnb_config,
        device_map={"": 0},
        trust_remote_code=False,
    )

    # Prepare for kbit training with gradient checkpointing
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    model.gradient_checkpointing_enable()

    # Re-cast input embeddings back to bfloat16 if PEFT upcast to float32
    embed_layer = model.get_input_embeddings()
    print(f"Original embed_tokens dtype: {embed_layer.weight.dtype}")
    if embed_layer.weight.dtype == torch.float32:
        print("Re-casting embed_tokens to bfloat16 to save 1.23 GB VRAM...")
        embed_layer.to(torch.bfloat16)
        print(f"New embed_tokens dtype: {embed_layer.weight.dtype}")

    # Attention projections only
    peft_config = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["qkv_proj", "o_proj"],
    )
    model = get_peft_model(model, peft_config)

    trainable_params, all_params = model.get_nb_trainable_parameters()
    print(f"Trainable params: {trainable_params:,} / {all_params:,} ({trainable_params/all_params*100:.2f}%)")

    # Hook forward to ensure embeddings output requires grad for backward
    def make_inputs_require_grad(module, inp, out):
        out.requires_grad_(True)
    embed_layer.register_forward_hook(make_inputs_require_grad)

    optimizer = bnb.optim.PagedAdamW8bit(model.parameters(), lr=1e-4)

    dummy_input_ids = torch.randint(100, 5000, (1, seq_len), device="cuda:0")
    dummy_labels = dummy_input_ids.clone()

    torch.cuda.reset_peak_memory_stats()
    step_times = []
    oom = False
    error_msg = None

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
            cuda_alloc = torch.cuda.memory_allocated() / (1024 * 1024)
            cuda_peak = torch.cuda.max_memory_allocated() / (1024 * 1024)
            print(f"  Step [{s}/3] | Loss: {loss.item():.4f} | Time: {dt:.3f} s | Alloc: {cuda_alloc:.1f} MiB | Peak: {cuda_peak:.1f} MiB")

        peak_vram_mb = round(torch.cuda.max_memory_allocated() / (1024 * 1024), 1)
        avg_step_s = round(sum(step_times) / len(step_times), 3)

    except torch.cuda.OutOfMemoryError as e:
        oom = True
        peak_vram_mb = round(torch.cuda.max_memory_allocated() / (1024 * 1024), 1)
        avg_step_s = 0.0
        error_msg = "CUDA OutOfMemoryError"
        print(f"  OOM encountered at seq_len={seq_len}! Peak allocated before OOM: {peak_vram_mb} MiB")

    except Exception as e:
        oom = True
        peak_vram_mb = round(torch.cuda.max_memory_allocated() / (1024 * 1024), 1)
        avg_step_s = 0.0
        error_msg = str(e)
        print(f"  Error at seq_len={seq_len}: {e}")

    finally:
        del model
        del optimizer
        del dummy_input_ids
        del dummy_labels
        torch.cuda.empty_cache()

    return {
        "seq_len": seq_len,
        "oom": oom,
        "peak_vram_mb": peak_vram_mb,
        "avg_step_s": avg_step_s,
        "error": error_msg
    }

def main():
    print("EXPLORING QLORA VRAM FOOTPRINT AT SEQUENCE LENGTHS 512 & 1024")
    res_512 = measure_seqlen(512)
    time.sleep(2.0)
    res_1024 = measure_seqlen(1024)

    results = {
        "model": MODEL_NAME,
        "targets": ["qkv_proj", "o_proj"],
        "optimizer": "PagedAdamW8bit",
        "gradient_checkpointing": True,
        "embedding_dtype": "bfloat16",
        "results": [res_512, res_1024]
    }

    out_path = os.path.join(REPO_ROOT, "results", "benchmarks", "qlora_seqlen_half_precision_exploration.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 70)
    print("QLORA SEQUENCE LENGTH VRAM SUMMARY:")
    print(f"SeqLen 512:  OOM={res_512['oom']} | Peak VRAM={res_512['peak_vram_mb']} MiB | Time/Step={res_512['avg_step_s']} s")
    print(f"SeqLen 1024: OOM={res_1024['oom']} | Peak VRAM={res_1024['peak_vram_mb']} MiB | Time/Step={res_1024['avg_step_s']} s")
    print(f"Saved results to: {out_path}")
    print("=" * 70)

if __name__ == "__main__":
    main()

