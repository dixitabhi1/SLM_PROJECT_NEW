import json
import os

with open("kaggle/e2_train_sql_lora.py", "r", encoding="utf-8") as f:
    code_lines = [line + "\n" for line in f.read().splitlines()]

cells = [
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "# Experiment 2 (E2): Kaggle SQL Specialist Adapter Training\n",
            "\n",
            "**Model:** `microsoft/Phi-4-mini-instruct` (commit `cfbefacb99257ffa30c83adab238a50856ac3083`)\n",
            "**Hardware:** NVIDIA Tesla T4 or P100 (16 GB VRAM, `fp16=True`, `bf16=False`)\n",
            "**Task:** Text-to-SQL QLoRA Fine-Tuning on Spider Train\n",
            "**Data Integrity:** 0% overlap with Dev, Held-Out, or Reserve evaluation databases\n",
            "**Checkpoints:** Saved every 200 steps (max 3) to survive 12-hour session timeout"
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "!pip install -q transformers peft bitsandbytes datasets accelerate gdown\n"
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "import torch\n",
            "print(f'PyTorch: {torch.__version__}')\n",
            "print(f'CUDA Available: {torch.cuda.is_available()}')\n",
            "if torch.cuda.is_available():\n",
            "    print(f'Device: {torch.cuda.get_device_name(0)}')\n",
            "    vram = torch.cuda.get_device_properties(0).total_memory / (1024**3)\n",
            "    print(f'VRAM: {vram:.2f} GB')\n"
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": code_lines
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "## Zip Adapter Weights for Easy 1-Click Download\n",
            "Zips `./phi4_sql_adapter_output` into `e2_sql_adapter.zip` for download."
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "!zip -r e2_sql_adapter.zip ./phi4_sql_adapter_output\n",
            "import hashlib\n",
            "with open('e2_sql_adapter.zip', 'rb') as f:\n",
            "    print('e2_sql_adapter.zip SHA-256:', hashlib.sha256(f.read()).hexdigest())\n"
        ]
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "## (Optional) Convert LoRA Adapter to GGUF Format on Kaggle\n",
            "Converts the saved adapter to GGUF using llama.cpp directly on Kaggle:"
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "!git clone https://github.com/ggerganov/llama.cpp.git\n",
            "!python llama.cpp/convert_lora_to_gguf.py --base-model-id microsoft/Phi-4-mini-instruct ./phi4_sql_adapter_output --outtype f16 --outfile phi4-mini-sql-lora.gguf\n",
            "import hashlib\n",
            "import os\n",
            "if os.path.exists('phi4-mini-sql-lora.gguf'):\n",
            "    with open('phi4-mini-sql-lora.gguf', 'rb') as f:\n",
            "        print('GGUF SHA-256:', hashlib.sha256(f.read()).hexdigest())\n"
        ]
    }
]

nb = {
    "cells": cells,
    "metadata": {
        "accelerator": "GPU",
        "gpuClass": "standard",
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3"
        },
        "language_info": {
            "name": "python",
            "version": "3.10.12"
        }
    },
    "nbformat": 4,
    "nbformat_minor": 4
}

with open("kaggle/e2_train_sql_lora.ipynb", "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=2)

print("Self-contained Kaggle notebook successfully generated at kaggle/e2_train_sql_lora.ipynb")
