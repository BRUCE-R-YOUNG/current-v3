import contextlib
import os
from pathlib import Path

def service_root(config_path: Path) -> Path:
    root = config_path.resolve().parent / 'runtime' / config_path.stem
    root.mkdir(parents=True, exist_ok=True)
    return root

@contextlib.contextmanager
def service_lock(root: Path, name: str):
    with (root / f'{name}.lock').open('a+b') as lock:
        lock.seek(0)
        lock.write(b'0')
        lock.flush()
        lock.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == 'nt':
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
