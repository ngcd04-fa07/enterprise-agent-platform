import sys
from pathlib import Path

# Ensures api_client (and server, if ever imported) resolve regardless of
# how pytest's rootdir/import-mode machinery behaves — don't rely on the
# editable install's .pth entry alone.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
