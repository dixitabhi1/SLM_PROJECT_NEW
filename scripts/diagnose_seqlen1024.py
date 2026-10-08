import os
import sys
import time
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

MODEL_NAME = "microsoft/Phi-4-mini-instruct"

def run_test(seq_len=1024, grad_ckpt=True, targets="all-linear"):
    print("=" * 60)
    print(f"DIAGNOSTIC TEST: seq_len={seq_len}, grad_ckpt={grad_ckpt}, targets={targets}")
    print("=" * 60)

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
        use_gradient_checkpointing=grad_ckpt,
    )
    if grad_ckpt:
        model.gradient_checkpointing_enable()

    target_mod = "all-linear" if targets == "all-linear" else ["q_proj", "v_proj"]
    peft_config = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=target_mod,
    )
    model = get_peft_model(model, peft_config)
    model.print_trainable_parameters()

    dummy_input_ids = torch.randint(100, 5000, (1, seq_len), device="cuda:0")
    dummy_labels = dummy_input_ids.clone()

    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
    torch.cuda.reset_peak_memory_stats()

    print("Running forward + backward...")
    t0 = time.perf_counter()
    outputs = model(input_ids=dummy_input_ids, labels=dummy_labels)
    loss = outputs.loss
    print(f"Forward pass completed in {time.perf_counter() - t0:.2f}s, Loss: {loss.item():.4f}")
    print(f"Allocated: {torch.cuda.memory_allocated() / (1024*1024):.1f} MiB, Max: {torch.cuda.max_memory_allocated() / (1024*1024):.1f} MiB")

    t1 = time.perf_counter()
    loss.backward()
    optimizer.step()
    print(f"Backward pass completed in {time.perf_counter() - t1:.2f}s")
    print(f"Peak CUDA Allocated: {torch.cuda.max_memory_allocated() / (1024*1024):.1f} MiB")

if __name__ == "__main__":
    seq_len = int(sys.argv[1]) if len(sys.argv) > 1 else 1024
    grad_ckpt = sys.argv[2].lower() == "true" if len(sys.argv) > 2 else True
    targets = sys.argv[3] if len(sys.argv) > 3 else "all-linear"
    run_test(seq_len=seq_len, grad_ckpt=grad_ckpt, targets=targets)

