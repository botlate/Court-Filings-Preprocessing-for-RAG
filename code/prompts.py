# Alias module - re-exports everything from 01_prompt_repository.py
# This exists because 11_document_classifier.py imports "from prompts import ..."
# but the actual file is named 01_prompt_repository.py (which can't be imported
# directly since Python module names can't start with digits).

import importlib
import sys
import os

# Import 01_prompt_repository.py using importlib
_spec = importlib.util.spec_from_file_location(
    "prompt_repository",
    os.path.join(os.path.dirname(__file__), "01_prompt_repository.py")
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

# Re-export everything
from types import ModuleType as _MT
for _name in dir(_mod):
    if not _name.startswith('_'):
        globals()[_name] = getattr(_mod, _name)
