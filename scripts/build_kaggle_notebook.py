import json

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
        "source": [
            "# Paste or upload e2_train_sql_lora.py and execute\n",
            "%run e2_train_sql_lora.py\n"
        ]
    },
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "## Convert LoRA Adapter to GGUF Format\n",
            "After training completes, convert the saved adapter to GGUF using llama.cpp:"
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
            "with open('phi4-mini-sql-lora.gguf', 'rb') as f:\n",
            "    print('GGUF SHA-256:', hashlib.sha256(f.read()).hexdigest())\n"
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

print("Kaggle notebook generated at kaggle/e2_train_sql_lora.ipynb")

