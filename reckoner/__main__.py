"""`python -m reckoner` (and the PyInstaller entry point)."""
import sys

from reckoner.cli import main

if __name__ == "__main__":
    sys.exit(main())
