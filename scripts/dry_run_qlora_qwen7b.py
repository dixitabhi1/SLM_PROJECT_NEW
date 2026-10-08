"""
20-step QLoRA dry run script on Qwen 7B (4-bit bitsandbytes).
Measures:
- Peak VRAM allocated on 6 GB GPU
- Mean time per training step
- Confirms whether adapter saves and loads on quantised Ollama model.

Zero fabricated numbers. Direct recording from PyTorch CUDA memory and NVML APIs.
"""

import os
import sys
import time
import json
import subprocess
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

# Target model cached locally
MODEL_ID = "unsloth/Qwen2.5-Coder-7B-Instruct-bnb-4bit"
TOKENIZER_ID = "Qwen/Qwen2.5-Coder-7B-Instruct"
NUM_STEPS = 20
BATCH_SIZE = 1
SEQ_LEN = 256
ADAPTER_OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "adapters", "qwen7b_qlora_dryrun"))


def run_qlora_dry_run():
    print("=" * 60)
    print("Starting 20-step QLoRA Dry Run on Qwen 7B")
    print("=" * 60)

    if not torch.cuda.is_available():
        print("ERROR: CUDA not available.")
        sys.exit(1)

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()

    baseline_vram_mb = round(torch.cuda.memory_allocated() / (1024 ** 2), 2)
    print(f"Initial CUDA Allocated VRAM: {baseline_vram_mb} MiB")

    # 1. Configure 4-bit BitsAndBytes
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )

    print(f"Loading base model {MODEL_ID} in 4-bit...")
    t0_load = time.perf_counter()
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        quantization_config=bnb_config,
        device_map={"": 0},
        torch_dtype=torch.float16,
    )
    t_load = round(time.perf_counter() - t0_load, 2)
    print(f"Model loaded in {t_load}s. Allocated VRAM: {round(torch.cuda.memory_allocated() / (1024**2), 2)} MiB")

    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_ID)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # 2. Prepare model for kbit training
    model = prepare_model_for_kbit_training(model)

    # 3. Attach LoRA
    peft_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, peft_config)
    model.train()

    trainable_params, all_params = model.get_nb_trainable_parameters()
    print(f"Trainable params: {trainable_params:,} / {all_params:,} ({round(100 * trainable_params / all_params, 2)}%)")

    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-4)

    # Synthetic training batches of seq_len 256
    dummy_input_ids = torch.randint(100, 1000, (BATCH_SIZE, SEQ_LEN), device="cuda", dtype=torch.long)
    dummy_labels = dummy_input_ids.clone()

    step_times = []
    losses = []

    print(f"\nExecuting {NUM_STEPS} training steps...")
    for step in range(1, NUM_STEPS + 1):
        t_step_start = time.perf_counter()

        optimizer.zero_grad()
        outputs = model(input_ids=dummy_input_ids, labels=dummy_labels)
        loss = outputs.loss
        loss.backward()
        optimizer.step()

        t_step_end = time.perf_counter()
        step_elapsed = t_step_end - t_step_start
        step_times.append(step_elapsed)
        losses.append(loss.item())

        current_vram = round(torch.cuda.memory_allocated() / (1024 ** 2), 2)
        reserved_vram = round(torch.cuda.memory_reserved() / (1024 ** 2), 2)
        print(f"  Step {step:02d}/{NUM_STEPS}: loss={loss.item():.4f}, time={step_elapsed:.3f}s, VRAM alloc={current_vram} MiB, res={reserved_vram} MiB")

    peak_allocated_mb = round(torch.cuda.max_memory_allocated() / (1024 ** 2), 2)
    peak_reserved_mb = round(torch.cuda.max_memory_reserved() / (1024 ** 2), 2)
    avg_step_time = round(sum(step_times) / len(step_times), 3)

    print("\n" + "=" * 60)
    print("Dry Run Results Summary:")
    print(f"  Total Steps: {NUM_STEPS}")
    print(f"  Mean Time Per Step: {avg_step_time} s")
    print(f"  Peak Allocated VRAM: {peak_allocated_mb} MiB")
    print(f"  Peak Reserved VRAM: {peak_reserved_mb} MiB")
    print("=" * 60)

    # 4. Save Adapter
    os.makedirs(ADAPTER_OUTPUT_DIR, exist_ok=True)
    print(f"\nSaving LoRA adapter to {ADAPTER_OUTPUT_DIR}...")
    model.save_pretrained(ADAPTER_OUTPUT_DIR)
    tokenizer.save_pretrained(ADAPTER_OUTPUT_DIR)

    saved_files = os.listdir(ADAPTER_OUTPUT_DIR)
    print(f"Saved adapter files: {saved_files}")

    # 5. Test loading adapter in Ollama
    print("\nTesting adapter loading in Ollama...")
    modelfile_content = f"""FROM qwen2.5:7b-instruct-q3_k_m
ADAPTER "{ADAPTER_OUTPUT_DIR.replace('\\', '/')}"
"""
    modelfile_path = os.path.join(ADAPTER_OUTPUT_DIR, "Modelfile")
    with open(modelfile_path, "w", encoding="utf-8") as f:
        f.write(modelfile_content)

    test_model_name = "qwen2.5-7b-qlora-dryrun"
    print(f"Running `ollama create {test_model_name} -f {modelfile_path}`...")
    create_proc = subprocess.run(["ollama", "create", test_model_name, "-f", modelfile_path], capture_output=True, text=True)
    print(f"Ollama create exit code: {create_proc.returncode}")
    print(f"Ollama stdout:\n{create_proc.stdout.strip()}")
    if create_proc.stderr:
        print(f"Ollama stderr:\n{create_proc.stderr.strip()}")

    adapter_loaded_successfully = (create_proc.returncode == 0)

    summary_result = {
        "model_id": MODEL_ID,
        "num_steps": NUM_STEPS,
        "mean_time_per_step_sec": avg_step_time,
        "peak_vram_allocated_mb": peak_allocated_mb,
        "peak_vram_reserved_mb": peak_reserved_mb,
        "trainable_parameters": trainable_params,
        "total_parameters": all_params,
        "adapter_files": saved_files,
        "ollama_adapter_create_returncode": create_proc.returncode,
        "ollama_adapter_create_stdout": create_proc.stdout.strip(),
        "ollama_adapter_create_stderr": create_proc.stderr.strip(),
        "adapter_loaded_in_ollama": adapter_loaded_successfully,
    }

    results_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "results", "benchmarks"))
    os.makedirs(results_dir, exist_ok=True)
    summary_path = os.path.join(results_dir, "qlora_dryrun_qwen7b_results.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_result, f, indent=2)
    print(f"\nSaved dry run summary to {summary_path}")


if __name__ == "__main__":
    run_qlora_dry_run()

