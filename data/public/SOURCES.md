# Public Benchmark Data Sources & Cryptographic Verification

This document records the official provenance, commit pins, licenses, and SHA-256 hashes of the public benchmark datasets used to validate the frozen SLM Pipeline (v1.3) against multi-tier LLM baselines.

---

## 1. Official Sources & Provenance

### 1.1 GSM-Hard
- **Source Repository:** [`reasoning-machines/gsm-hard`](https://huggingface.co/datasets/reasoning-machines/gsm-hard)
- **Commit SHA:** `960448f73503112d4226baeb8eb41d3fb5ae2506`
- **License:** MIT
- **Raw File:** `gsmhardv2.jsonl` (1,319 problems with scale-perturbed numeric magnitudes)
- **Raw SHA-256:** `2032b0188a49ac0ec38cbe1e695e7d62d6dddc44bbb64f920728aca710e9ddef`
- **Sampling (seed 42):**
  - Practice Set ($N=20$): `gsmhard_practice_ids.json` (SHA-256: `9949a69d644eeb5015b60d757547d6d7ab63305a4b22c24013055ede71e038ba`)
  - Test Set ($N=150$): `gsmhard_test_ids.json` (SHA-256: `d4efb6fe44099d842a86860a0326db58bfe0f8782c6fc242735daaad99e9b905`)

### 1.2 FinQA
- **Source Repository:** [`czyssrs/FinQA`](https://github.com/czyssrs/FinQA) (EMNLP 2021)
- **Commit SHA:** `0f16e2867befa6840783e58be38c9efb9229d742`
- **License:** MIT
- **Raw File:** `dataset/test.json` (1,147 financial question-answering items with tables and text)
- **Raw SHA-256:** `831dbfb2e785dbc227f895ce3f24046433467aec67b09db2bd6ac7692a8a30dc`
- **Sampling (seed 42):**
  - Practice Set ($N=20$): `finqa_practice_ids.json` (SHA-256: `543e8ed061419cd2833d24506ee2cda5ffdddf1f317807a559c2c46a89f82557`)
  - Test Set ($N=150$): `finqa_test_ids.json` (SHA-256: `8fe47f47510a320ffeace8158e138a8c4b42983e03f96d54658ff650b794afab`)

### 1.3 InfiAgent-DABench
- **Source Repository:** [`InfiAgent/InfiAgent`](https://github.com/InfiAgent/InfiAgent) (ICML 2024)
- **Commit SHA:** `3d6c4a70198e0a41fadf539f5b43c88b8c1a2d9c`
- **License:** CC-BY-NC 4.0 (Data) / Apache 2.0 (Code)
- **Raw Files:**
  - `da-dev-questions.jsonl` (257 closed-form data analysis questions; SHA-256: `49ae783b20ecb60449ce1443c524e89f8ca8353a04e05e4d14a055b7a6f06126`)
  - `da-dev-labels.jsonl` (257 closed-form ground-truth answers; SHA-256: `83b8fb8133c1794fcb6b42435e9cce124d22f68b71e2eedb37c973e40b5a18c2`)
  - `da-dev-tables/*.csv` (52 unique CSV tables referenced across questions)
- **Sampling (seed 42):**
  - Practice Set ($N=20$): `dabench_practice_ids.json` (SHA-256: `ace1675a3bf0c9ba399488f4cbd300b44ca5491463d8de2d12ade405b77e28b0`)
  - Test Set ($N=150$): `dabench_test_ids.json` (SHA-256: `890f1c5eecdc78c5e9738948cbc1a9c77416a11da7e89d816341a883a1172922`)

---

## 2. Cryptographic Manifest Summary

| Dataset File / Split | Items ($N$) | SHA-256 Digest |
|---|:---:|---|
| **GSM-Hard Raw File** | 1,319 | `2032b0188a49ac0ec38cbe1e695e7d62d6dddc44bbb64f920728aca710e9ddef` |
| **FinQA Test Raw File** | 1,147 | `831dbfb2e785dbc227f895ce3f24046433467aec67b09db2bd6ac7692a8a30dc` |
| **DABench Questions Raw File** | 257 | `49ae783b20ecb60449ce1443c524e89f8ca8353a04e05e4d14a055b7a6f06126` |
| **DABench Labels Raw File** | 257 | `83b8fb8133c1794fcb6b42435e9cce124d22f68b71e2eedb37c973e40b5a18c2` |
| **GSM-Hard Practice IDs** | 20 | `9949a69d644eeb5015b60d757547d6d7ab63305a4b22c24013055ede71e038ba` |
| **GSM-Hard Test IDs** | 150 | `d4efb6fe44099d842a86860a0326db58bfe0f8782c6fc242735daaad99e9b905` |
| **FinQA Practice IDs** | 20 | `543e8ed061419cd2833d24506ee2cda5ffdddf1f317807a559c2c46a89f82557` |
| **FinQA Test IDs** | 150 | `8fe47f47510a320ffeace8158e138a8c4b42983e03f96d54658ff650b794afab` |
| **DABench Practice IDs** | 20 | `ace1675a3bf0c9ba399488f4cbd300b44ca5491463d8de2d12ade405b77e28b0` |
| **DABench Test IDs** | 150 | `890f1c5eecdc78c5e9738948cbc1a9c77416a11da7e89d816341a883a1172922` |
