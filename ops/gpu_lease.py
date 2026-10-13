"""Project GPU lease, optionally coordinating read-only with an existing shared lease."""
from contextlib import contextmanager
from pathlib import Path
import fcntl,os

@contextmanager
def gpu_lease(root=None):
    root=Path(root or Path(__file__).resolve().parents[1]).resolve()
    requested=os.getenv("MODELOPS_GPU_LEASE")
    shared=Path(requested) if requested else Path("/data/VLA-Forge/Evidence/M05/gpu.lock")
    if requested and not shared.is_file():raise ValueError("Configured shared GPU lease is unavailable")
    if shared.is_file():lock=shared.open("r")
    else:
        own=root/"Evidence/v1/gpu.lock";own.parent.mkdir(parents=True,exist_ok=True)
        lock=own.open("a")
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield
    finally:lock.close()
