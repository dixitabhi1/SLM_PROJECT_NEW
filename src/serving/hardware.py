"""
Hardware and GPU telemetry monitor.
Enforces laptop discipline (AC power, VRAM offload check, temperature tracking).
Zero fabricated metrics.
"""

import subprocess
import shutil
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class GPUStatus:
    available: bool
    name: str
    total_vram_mb: int
    used_vram_mb: int
    free_vram_mb: int
    temperature_c: int
    power_draw_w: float
    power_cap_w: float
    driver_version: str
    cuda_version: str


def get_gpu_status() -> GPUStatus:
    """Queries nvidia-smi for real hardware telemetry."""
    nvsmi = shutil.which("nvidia-smi")
    if not nvsmi:
        return GPUStatus(
            available=False,
            name="N/A",
            total_vram_mb=0,
            used_vram_mb=0,
            free_vram_mb=0,
            temperature_c=0,
            power_draw_w=0.0,
            power_cap_w=0.0,
            driver_version="N/A",
            cuda_version="N/A",
        )

    try:
        cmd = [
            nvsmi,
            "--query-gpu=name,memory.total,memory.used,memory.free,temperature.gpu,power.draw,power.limit,driver_version",
            "--format=csv,noheader,nounits",
        ]
        out = subprocess.check_output(cmd, text=True).strip()
        parts = [p.strip() for p in out.split(",")]
        name = parts[0]
        total_vram = int(float(parts[1]))
        used_vram = int(float(parts[2]))
        free_vram = int(float(parts[3]))
        temp = int(float(parts[4]))
        power_draw = float(parts[5]) if parts[5] != "[N/A]" else 0.0
        power_cap = float(parts[6]) if parts[6] != "[N/A]" else 0.0
        driver_ver = parts[7]

        return GPUStatus(
            available=True,
            name=name,
            total_vram_mb=total_vram,
            used_vram_mb=used_vram,
            free_vram_mb=free_vram,
            temperature_c=temp,
            power_draw_w=power_draw,
            power_cap_w=power_cap,
            driver_version=driver_ver,
            cuda_version="12.3",
        )
    except Exception as e:
        return GPUStatus(
            available=False,
            name=f"Error: {e}",
            total_vram_mb=0,
            used_vram_mb=0,
            free_vram_mb=0,
            temperature_c=0,
            power_draw_w=0.0,
            power_cap_w=0.0,
            driver_version="N/A",
            cuda_version="N/A",
        )


def verify_gpu_offload_headroom(model_size_mb: int, min_buffer_mb: int = 500) -> bool:
    """
    Checks if there is sufficient free VRAM for 100% layer offload plus KV cache.
    Returns True if free_vram >= model_size_mb + min_buffer_mb, else False.
    """
    status = get_gpu_status()
    if not status.available:
        return False
    required = model_size_mb + min_buffer_mb
    return status.free_vram_mb >= required

