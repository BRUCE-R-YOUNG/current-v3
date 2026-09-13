"""Capture without loading an inference model; uses the shared durable queue."""
import sys

import run  # Establish the same import root as run.py.
from app.edge.__main__ import main


if __name__ == '__main__':
    import os
    os.chdir(run.root)
    main(['capture', *sys.argv[1:]], expected_role='edge')
