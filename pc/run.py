"""PC receiver and learning entry point, also usable from the distribution."""
import os
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
root = here if (here / 'app').is_dir() else here.parent
sys.path.insert(0, str(root))

if __name__ == '__main__':
    os.chdir(root)
    from app.edge.__main__ import main
    main(expected_role='server')
