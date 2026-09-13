"""Upload queued captures at transfer_seconds intervals, independently of capture."""
import sys

import run
from app.edge.__main__ import main


if __name__ == '__main__':
    import os
    os.chdir(run.root)
    main(['transfer', *sys.argv[1:]], expected_role='edge')
