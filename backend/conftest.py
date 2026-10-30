"""En tests, l'extraction reste dans le pool local : les monkeypatches de `analyser` restent observables."""
import os

os.environ.setdefault("PIECES_EXTRACTION_PROCESSUS", "0")
