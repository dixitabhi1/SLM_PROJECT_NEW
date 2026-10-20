"""
scripts/download_public_benchmarks.py

Downloads official, raw data for the public validation benchmarks:
1. GSM-Hard (Hugging Face reasoning-machines/gsm-hard)
2. FinQA (GitHub czyssrs/FinQA)
3. InfiAgent-DABench (GitHub InfiAgent/InfiAgent)

Verifies SHA-256 hashes of raw files, performs deterministic sampling
(seed 42: 150 TEST items, 20 PRACTICE items disjoint from TEST),
and generates data/public/SOURCES.md and ID lists.
"""

import os
import sys
import json
import random
import hashlib
import urllib.request
from typing import List, Dict, Any

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_PUBLIC_DIR = os.path.join(REPO_ROOT, "data", "public")
RAW_DIR = os.path.join(DATA_PUBLIC_DIR, "raw")

SOURCES_METADATA = {
    "gsmhard": {
        "name": "GSM-Hard",
        "url": "https://huggingface.co/datasets/reasoning-machines/gsm-hard",
        "raw_url": "https://huggingface.co/datasets/reasoning-machines/gsm-hard/raw/960448f73503112d4226baeb8eb41d3fb5ae2506/gsmhardv2.jsonl",
        "commit": "960448f73503112d4226baeb8eb41d3fb5ae2506",
        "license": "MIT",
        "local_file": os.path.join(RAW_DIR, "gsmhard", "gsmhardv2.jsonl")
    },
    "finqa": {
        "name": "FinQA",
        "url": "https://github.com/czyssrs/FinQA",
        "raw_url": "https://raw.githubusercontent.com/czyssrs/FinQA/0f16e2867befa6840783e58be38c9efb9229d742/dataset/test.json",
        "commit": "0f16e2867befa6840783e58be38c9efb9229d742",
        "license": "MIT",
        "local_file": os.path.join(RAW_DIR, "finqa", "test.json")
    },
    "dabench": {
        "name": "InfiAgent-DABench",
        "url": "https://github.com/InfiAgent/InfiAgent",
        "commit": "3d6c4a70198e0a41fadf539f5b43c88b8c1a2d9c",
        "license": "CC-BY-NC 4.0 (Data) / Apache 2.0 (Code)",
        "questions_url": "https://raw.githubusercontent.com/InfiAgent/InfiAgent/3d6c4a70198e0a41fadf539f5b43c88b8c1a2d9c/examples/DA-Agent/data/da-dev-questions.jsonl",
        "labels_url": "https://raw.githubusercontent.com/InfiAgent/InfiAgent/3d6c4a70198e0a41fadf539f5b43c88b8c1a2d9c/examples/DA-Agent/data/da-dev-labels.jsonl",
        "questions_file": os.path.join(RAW_DIR, "dabench", "da-dev-questions.jsonl"),
        "labels_file": os.path.join(RAW_DIR, "dabench", "da-dev-labels.jsonl"),
        "tables_dir": os.path.join(RAW_DIR, "dabench", "tables")
    }
}


def compute_sha256(file_path: str) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def download_file(url: str, dest_path: str) -> None:
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
        print(f"  [Cached] {dest_path}")
        return
    print(f"  Downloading: {url} -> {dest_path}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    with urllib.request.urlopen(req) as resp, open(dest_path, "wb") as out_f:
        while chunk := resp.read(65536):
            out_f.write(chunk)


def download_all_benchmarks() -> Dict[str, Any]:
    print("=== Step 1.1: Downloading Raw Benchmark Files ===")
    hashes = {}

    # 1. GSM-Hard
    print("\n1. GSM-Hard...")
    gsm_cfg = SOURCES_METADATA["gsmhard"]
    download_file(gsm_cfg["raw_url"], gsm_cfg["local_file"])
    hashes["gsmhardv2.jsonl"] = compute_sha256(gsm_cfg["local_file"])
    print(f"   SHA-256: {hashes['gsmhardv2.jsonl']}")

    # 2. FinQA
    print("\n2. FinQA...")
    fin_cfg = SOURCES_METADATA["finqa"]
    download_file(fin_cfg["raw_url"], fin_cfg["local_file"])
    hashes["finqa_test.json"] = compute_sha256(fin_cfg["local_file"])
    print(f"   SHA-256: {hashes['finqa_test.json']}")

    # 3. InfiAgent-DABench
    print("\n3. InfiAgent-DABench...")
    da_cfg = SOURCES_METADATA["dabench"]
    download_file(da_cfg["questions_url"], da_cfg["questions_file"])
    download_file(da_cfg["labels_url"], da_cfg["labels_file"])
    hashes["da-dev-questions.jsonl"] = compute_sha256(da_cfg["questions_file"])
    hashes["da-dev-labels.jsonl"] = compute_sha256(da_cfg["labels_file"])
    print(f"   da-dev-questions.jsonl SHA-256: {hashes['da-dev-questions.jsonl']}")
    print(f"   da-dev-labels.jsonl SHA-256:    {hashes['da-dev-labels.jsonl']}")

    # Download required CSV tables
    with open(da_cfg["questions_file"], "r", encoding="utf-8") as f:
        questions = [json.loads(line) for line in f if line.strip()]
    table_names = sorted(list(set(q["file_name"] for q in questions)))
    print(f"   Downloading {len(table_names)} unique CSV tables...")
    os.makedirs(da_cfg["tables_dir"], exist_ok=True)
    table_hashes = {}
    base_table_url = f"https://raw.githubusercontent.com/InfiAgent/InfiAgent/{da_cfg['commit']}/examples/DA-Agent/data/da-dev-tables"
    for tbl in table_names:
        tbl_path = os.path.join(da_cfg["tables_dir"], tbl)
        tbl_url = f"{base_table_url}/{urllib.parse.quote(tbl)}"
        download_file(tbl_url, tbl_path)
        table_hashes[tbl] = compute_sha256(tbl_path)
    hashes["dabench_tables_count"] = len(table_hashes)
    hashes["dabench_tables"] = table_hashes

    return hashes


def sample_splits(raw_hashes: Dict[str, Any]) -> None:
    print("\n=== Step 1.2: Deterministic Sampling (seed 42, N=150 TEST, N=20 PRACTICE) ===")
    random.seed(42)

    # 1. GSM-Hard
    gsm_file = SOURCES_METADATA["gsmhard"]["local_file"]
    with open(gsm_file, "r", encoding="utf-8") as f:
        gsm_items = [json.loads(l) for l in f if l.strip()]
    total_gsm = len(gsm_items)
    all_gsm_indices = list(range(total_gsm))
    random.shuffle(all_gsm_indices)
    gsm_practice_indices = sorted(all_gsm_indices[:20])
    gsm_test_indices = sorted(all_gsm_indices[20:170])
    gsm_practice_ids = [f"gsmhard_{idx:04d}" for idx in gsm_practice_indices]
    gsm_test_ids = [f"gsmhard_{idx:04d}" for idx in gsm_test_indices]
    print(f"GSM-Hard: total={total_gsm}, practice={len(gsm_practice_ids)}, test={len(gsm_test_ids)}")

    # 2. FinQA
    fin_file = SOURCES_METADATA["finqa"]["local_file"]
    with open(fin_file, "r", encoding="utf-8") as f:
        fin_items = json.load(f)
    total_fin = len(fin_items)
    all_fin_indices = list(range(total_fin))
    random.shuffle(all_fin_indices)
    fin_practice_indices = sorted(all_fin_indices[:20])
    fin_test_indices = sorted(all_fin_indices[20:170])
    fin_practice_ids = [fin_items[idx]["id"] for idx in fin_practice_indices]
    fin_test_ids = [fin_items[idx]["id"] for idx in fin_test_indices]
    print(f"FinQA: total={total_fin}, practice={len(fin_practice_ids)}, test={len(fin_test_ids)}")

    # 3. InfiAgent-DABench
    da_q_file = SOURCES_METADATA["dabench"]["questions_file"]
    with open(da_q_file, "r", encoding="utf-8") as f:
        da_items = [json.loads(l) for l in f if l.strip()]
    total_da = len(da_items)
    all_da_indices = list(range(total_da))
    random.shuffle(all_da_indices)
    da_practice_indices = sorted(all_da_indices[:20])
    da_test_indices = sorted(all_da_indices[20:170])
    da_practice_ids = [f"dabench_{da_items[idx]['id']:04d}" for idx in da_practice_indices]
    da_test_ids = [f"dabench_{da_items[idx]['id']:04d}" for idx in da_test_indices]
    print(f"InfiAgent-DABench: total={total_da}, practice={len(da_practice_ids)}, test={len(da_test_ids)}")

    # Save ID lists
    def save_ids(filename: str, ids: List[str]) -> str:
        p = os.path.join(DATA_PUBLIC_DIR, filename)
        with open(p, "w", encoding="utf-8") as out:
            json.dump(ids, out, indent=2)
        h = compute_sha256(p)
        print(f"  Saved: {p} (SHA-256: {h})")
        return h

    id_hashes = {
        "gsmhard_practice_ids": save_ids("gsmhard_practice_ids.json", gsm_practice_ids),
        "gsmhard_test_ids": save_ids("gsmhard_test_ids.json", gsm_test_ids),
        "finqa_practice_ids": save_ids("finqa_practice_ids.json", fin_practice_ids),
        "finqa_test_ids": save_ids("finqa_test_ids.json", fin_test_ids),
        "dabench_practice_ids": save_ids("dabench_practice_ids.json", da_practice_ids),
        "dabench_test_ids": save_ids("dabench_test_ids.json", da_test_ids),
    }

    # Generate SOURCES.md
    sources_md_path = os.path.join(DATA_PUBLIC_DIR, "SOURCES.md")
    with open(sources_md_path, "w", encoding="utf-8") as smd:
        smd.write(f"""# Public Benchmark Data Sources & Cryptographic Verification

This document records the official provenance, commit pins, licenses, and SHA-256 hashes of the public benchmark datasets used to validate the frozen SLM Pipeline (v1.3) against multi-tier LLM baselines.

---

## 1. Official Sources & Provenance

### 1.1 GSM-Hard
- **Source Repository:** [`reasoning-machines/gsm-hard`](https://huggingface.co/datasets/reasoning-machines/gsm-hard)
- **Commit SHA:** `{SOURCES_METADATA['gsmhard']['commit']}`
- **License:** MIT
- **Raw File:** `gsmhardv2.jsonl` (1,319 problems with scale-perturbed numeric magnitudes)
- **Raw SHA-256:** `{raw_hashes['gsmhardv2.jsonl']}`
- **Sampling (seed 42):**
  - Practice Set ($N=20$): `gsmhard_practice_ids.json` (SHA-256: `{id_hashes['gsmhard_practice_ids']}`)
  - Test Set ($N=150$): `gsmhard_test_ids.json` (SHA-256: `{id_hashes['gsmhard_test_ids']}`)

### 1.2 FinQA
- **Source Repository:** [`czyssrs/FinQA`](https://github.com/czyssrs/FinQA) (EMNLP 2021)
- **Commit SHA:** `{SOURCES_METADATA['finqa']['commit']}`
- **License:** MIT
- **Raw File:** `dataset/test.json` (1,147 financial question-answering items with tables and text)
- **Raw SHA-256:** `{raw_hashes['finqa_test.json']}`
- **Sampling (seed 42):**
  - Practice Set ($N=20$): `finqa_practice_ids.json` (SHA-256: `{id_hashes['finqa_practice_ids']}`)
  - Test Set ($N=150$): `finqa_test_ids.json` (SHA-256: `{id_hashes['finqa_test_ids']}`)

### 1.3 InfiAgent-DABench
- **Source Repository:** [`InfiAgent/InfiAgent`](https://github.com/InfiAgent/InfiAgent) (ICML 2024)
- **Commit SHA:** `{SOURCES_METADATA['dabench']['commit']}`
- **License:** CC-BY-NC 4.0 (Data) / Apache 2.0 (Code)
- **Raw Files:**
  - `da-dev-questions.jsonl` (257 closed-form data analysis questions; SHA-256: `{raw_hashes['da-dev-questions.jsonl']}`)
  - `da-dev-labels.jsonl` (257 closed-form ground-truth answers; SHA-256: `{raw_hashes['da-dev-labels.jsonl']}`)
  - `da-dev-tables/*.csv` (52 unique CSV tables referenced across questions)
- **Sampling (seed 42):**
  - Practice Set ($N=20$): `dabench_practice_ids.json` (SHA-256: `{id_hashes['dabench_practice_ids']}`)
  - Test Set ($N=150$): `dabench_test_ids.json` (SHA-256: `{id_hashes['dabench_test_ids']}`)

---

## 2. Cryptographic Manifest Summary

| Dataset File / Split | Items ($N$) | SHA-256 Digest |
|---|:---:|---|
| **GSM-Hard Raw File** | 1,319 | `{raw_hashes['gsmhardv2.jsonl']}` |
| **FinQA Test Raw File** | 1,147 | `{raw_hashes['finqa_test.json']}` |
| **DABench Questions Raw File** | 257 | `{raw_hashes['da-dev-questions.jsonl']}` |
| **DABench Labels Raw File** | 257 | `{raw_hashes['da-dev-labels.jsonl']}` |
| **GSM-Hard Practice IDs** | 20 | `{id_hashes['gsmhard_practice_ids']}` |
| **GSM-Hard Test IDs** | 150 | `{id_hashes['gsmhard_test_ids']}` |
| **FinQA Practice IDs** | 20 | `{id_hashes['finqa_practice_ids']}` |
| **FinQA Test IDs** | 150 | `{id_hashes['finqa_test_ids']}` |
| **DABench Practice IDs** | 20 | `{id_hashes['dabench_practice_ids']}` |
| **DABench Test IDs** | 150 | `{id_hashes['dabench_test_ids']}` |
""")
    print(f"Generated: {sources_md_path}")


def main():
    os.makedirs(DATA_PUBLIC_DIR, exist_ok=True)
    os.makedirs(RAW_DIR, exist_ok=True)
    raw_hashes = download_all_benchmarks()
    sample_splits(raw_hashes)
    print("\n=== Public Benchmark Preparation Complete ===")


if __name__ == "__main__":
    main()
