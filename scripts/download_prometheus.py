"""Downloads prometheus-eval/prometheus-7b-v2.0-GGUF (Q4_K_M) and computes its SHA-256."""
import os
import hashlib
from huggingface_hub import hf_hub_download

REPO_ID = "prometheus-eval/prometheus-7b-v2.0-GGUF"
FILENAME = "prometheus-7b-v2.0.Q4_K_M.gguf"
LOCAL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")

def compute_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()

def main():
    os.makedirs(LOCAL_DIR, exist_ok=True)
    target_path = os.path.join(LOCAL_DIR, FILENAME)
    print(f"Downloading {FILENAME} from {REPO_ID} to {target_path}...")
    downloaded_path = hf_hub_download(
        repo_id=REPO_ID,
        filename=FILENAME,
        local_dir=LOCAL_DIR
    )
    print(f"Downloaded to: {downloaded_path}")
    print("Computing SHA-256 checksum...")
    sha = compute_sha256(downloaded_path)
    size_bytes = os.path.getsize(downloaded_path)
    print(f"File: {downloaded_path}")
    print(f"Size: {size_bytes} bytes ({size_bytes / (1024**3):.2f} GiB)")
    print(f"SHA-256: {sha}")

if __name__ == "__main__":
    main()

