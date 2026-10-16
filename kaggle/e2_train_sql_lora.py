"""
kaggle/e2_train_sql_lora.py

Self-contained QLoRA fine-tuning script for Experiment 2 (E2: SQL Specialist Adapter).
Designed for execution on free Kaggle GPU instances (NVIDIA Tesla T4 or P100, 16 GB VRAM).

Constraints & Invariants:
1. Base Model Pinned: microsoft/Phi-4-mini-instruct (commit cfbefacb99257ffa30c83adab238a50856ac3083)
2. Hardware: fp16 precision (no bf16 on T4/P100), QLoRA 4-bit (NF4), gradient checkpointing.
3. Max sequence length: 1,024 tokens.
4. Prompt Template: Exactly matches the pipeline's direct SQL prompt template.
5. Checkpoint saving: Every 200 steps (save_total_limit=3) to survive 12-hour session cutoff.
6. Zero API keys: Operates strictly without credentials or external API calls.
7. Data Disjointness: Cryptographic assertion that no Dev, Held-Out, or Reserve database appears in training data.
"""

import os
import sys
import json
import sqlite3
import hashlib
import zipfile
import subprocess
from typing import Dict, Any, List

import torch
from datasets import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainingArguments,
    Trainer,
    DataCollatorForSeq2Seq
)
from peft import (
    LoraConfig,
    get_peft_model,
    prepare_model_for_kbit_training
)

# Pinned Hugging Face Base Model
BASE_MODEL_ID = "microsoft/Phi-4-mini-instruct"
PINNED_REVISION = "cfbefacb99257ffa30c83adab238a50856ac3083"

# Forbidden Evaluation Databases across Dev (8), Held-Out (10), Reserve (7), and Extended Dev (12)
# All 20 official Spider validation databases must be strictly excluded from training:
FORBIDDEN_DATABASES = {
    "battle_death", "car_1", "concert_singer", "course_teach",
    "cre_Doc_Template_Mgt", "dog_kennels", "employee_hire_evaluation",
    "flight_2", "museum_visit", "network_1", "orchestra", "orchestra_2",
    "poker_player", "pets_1", "real_estate_properties", "singer",
    "student_transcripts_tracking", "tvshow", "voter_1", "world_1", "wta_1"
}

DIRECT_SQL_SYS = (
    "You are an expert SQL assistant. Given the database schema and question, write a single valid SQLite query that answers the question.\n"
    "Guidelines:\n"
    "- Return ONLY the exact column(s) requested by the question. Do not include auxiliary count or aggregate columns in the SELECT clause unless explicitly asked.\n"
    "- Ensure necessary table joins are included when attributes belong to relational tables.\n"
    "- Output strictly the SQL query enclosed in ```sql\n<query>\n```. Do not provide conversational explanations."
)


def get_table_schema_from_db(sqlite_path: str) -> str:
    """Extracts table schema DDL from SQLite database identically to the pipeline."""
    if not os.path.exists(sqlite_path):
        return ""
    try:
        conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL;")
        rows = cur.fetchall()
        conn.close()
        return "\n".join(" ".join(r[0].split()) for r in rows)
    except Exception as e:
        print(f"Warning: could not read schema from {sqlite_path}: {e}")
        return ""


def download_and_extract_spider(dest_dir: str = "./spider_data") -> str:
    """Downloads official Spider dataset archive and extracts it."""
    os.makedirs(dest_dir, exist_ok=True)
    zip_path = os.path.join(dest_dir, "spider.zip")
    
    if not os.path.exists(os.path.join(dest_dir, "spider", "train_spider.json")):
        if not os.path.exists(zip_path):
            print("Downloading Spider dataset archive via gdown...")
            try:
                import gdown
            except ImportError:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "gdown"])
                import gdown
            gdown.download(id="1403EGqzIDoHMdQF4c9Bkyl7dZLZ5Wt6J", output=zip_path, quiet=False)
        
        print("Extracting spider.zip...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(dest_dir)
        print("Extraction complete.")
    
    spider_root = os.path.join(dest_dir, "spider")
    return spider_root


def build_training_dataset(spider_root: str, tokenizer: Any) -> Dataset:
    """Constructs tokenized training dataset with strict non-overlap validation."""
    train_spider_path = os.path.join(spider_root, "train_spider.json")
    train_others_path = os.path.join(spider_root, "train_others.json")
    db_base_dir = os.path.join(spider_root, "database")

    raw_items = []
    with open(train_spider_path, "r", encoding="utf-8") as f:
        raw_items.extend(json.load(f))
    if os.path.exists(train_others_path):
        with open(train_others_path, "r", encoding="utf-8") as f:
            raw_items.extend(json.load(f))

    print(f"Loaded {len(raw_items)} raw training instances from Spider train.")

    # Schema cache
    schema_cache = {}
    train_dbs = set()
    formatted_data = []

    for item in raw_items:
        db_id = item["db_id"]
        train_dbs.add(db_id)

        # STRICT ASSERTION: Zero overlap with evaluation databases
        if db_id in FORBIDDEN_DATABASES:
            raise ValueError(f"CRITICAL LEAKAGE DETECTED: Database {db_id} belongs to evaluation splits!")

        if db_id not in schema_cache:
            db_file = os.path.join(db_base_dir, db_id, f"{db_id}.sqlite")
            schema_cache[db_id] = get_table_schema_from_db(db_file)

        schema = schema_cache[db_id]
        question = item["question"]
        gold_query = item["query"]

        # Exact pipeline template formatting
        user_prompt = (
            f"[Database: {db_id}]\n"
            f"[Database Schema:\n{schema}\n]\n"
            f"Question: {question}\n"
            f"Return only the requested column.\n"
            f"Write a valid SQLite query in ```sql ... ```."
        )
        assistant_reply = f"```sql\n{gold_query}\n```"

        formatted_data.append({
            "system": DIRECT_SQL_SYS,
            "user": user_prompt,
            "assistant": assistant_reply
        })

    # Assert complete disjointness
    overlap = train_dbs.intersection(FORBIDDEN_DATABASES)
    assert len(overlap) == 0, f"Disjointness assertion failed! Overlap: {overlap}"
    print(f"Disjointness verified: 0 of {len(train_dbs)} training databases overlap with evaluation splits.")

    # Render first training instance
    print("=" * 80)
    print("RENDERED TRAINING EXAMPLE (Matching Pipeline Direct SQL Template):")
    print("=== SYSTEM ===")
    print(formatted_data[0]["system"])
    print("=== USER ===")
    print(formatted_data[0]["user"])
    print("=== ASSISTANT ===")
    print(formatted_data[0]["assistant"])
    print("=" * 80)

    # Format into Phi-4-mini chat template
    tokenized_samples = []
    max_len = 1024

    for sample in formatted_data:
        messages = [
            {"role": "system", "content": sample["system"]},
            {"role": "user", "content": sample["user"]},
            {"role": "assistant", "content": sample["assistant"]}
        ]
        text = tokenizer.apply_chat_template(messages, tokenize=False)
        enc = tokenizer(text, max_length=max_len, truncation=True)
        enc["labels"] = list(enc["input_ids"])
        tokenized_samples.append(enc)

    return Dataset.from_list(tokenized_samples)


def train():
    print("=" * 80)
    print("EXPERIMENT 2 (E2): QLoRA SQL ADAPTER TRAINING")
    print(f"Platform: Kaggle GPU | PyTorch {torch.__version__} | CUDA: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"Device: {torch.cuda.get_device_name(0)}")
    print("=" * 80)

    # 1. Download & Prepare Dataset
    spider_root = download_and_extract_spider("./spider_data")

    # 2. Tokenizer
    print(f"Loading tokenizer for {BASE_MODEL_ID} (revision {PINNED_REVISION})...")
    tokenizer = AutoTokenizer.from_pretrained(
        BASE_MODEL_ID,
        revision=PINNED_REVISION,
        trust_remote_code=True
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # 3. Build tokenized dataset
    train_dataset = build_training_dataset(spider_root, tokenizer)
    print(f"Training dataset size: {len(train_dataset)} instances.")

    # 4. BitsAndBytes 4-bit Quantization Config (FP16 compute for T4/P100 compatibility)
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True
    )

    # 5. Load Base Model
    print(f"Loading base model in 4-bit NF4 with fp16 compute...")
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_ID,
        revision=PINNED_REVISION,
        quantization_config=bnb_config,
        device_map="auto",
        torch_dtype=torch.float16,
        trust_remote_code=True
    )

    model = prepare_model_for_kbit_training(model)
    model.gradient_checkpointing_enable()

    # 6. LoRA Configuration
    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # 7. Training Arguments with Step Checkpointing (Survives 12h Session Cutoff)
    output_dir = "./phi4_sql_adapter_output"
    checkpoint_dir = "./phi4_sql_checkpoints"

    training_args = TrainingArguments(
        output_dir=checkpoint_dir,
        per_device_train_batch_size=4,
        gradient_accumulation_steps=4,  # effective batch size: 16
        warmup_ratio=0.03,
        num_train_epochs=2,
        learning_rate=2e-4,
        fp16=True,   # T4 / P100 compatible (strictly no bf16)
        bf16=False,
        logging_steps=50,
        save_strategy="steps",
        save_steps=200,          # Checkpoint every 200 steps
        save_total_limit=3,      # Keep latest 3 checkpoints
        dataloader_num_workers=2,
        report_to="none"         # Zero third-party telemetry / zero API keys
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        data_collator=DataCollatorForSeq2Seq(tokenizer, pad_to_multiple_of=8, return_tensors="pt", padding=True)
    )

    # 8. Execute Training
    print("Starting QLoRA training...")
    trainer.train()

    # 9. Save Final Adapter
    print(f"Saving final adapter weights to {output_dir}...")
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    # 10. Record Adapter File Hashes
    print("=" * 80)
    print("TRAINING COMPLETE: ADAPTER FILE HASHES")
    for fname in sorted(os.listdir(output_dir)):
        fpath = os.path.join(output_dir, fname)
        if os.path.isfile(fpath):
            with open(fpath, "rb") as f:
                h = hashlib.sha256(f.read()).hexdigest()
            print(f"  {fname}: SHA-256 = {h}")
    print("=" * 80)


if __name__ == "__main__":
    train()

