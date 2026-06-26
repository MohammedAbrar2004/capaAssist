"""Single structured logger for the whole service. Import get_logger() —
never call print() for diagnostics, and never instantiate a second logger
with a different name.
"""

import logging
import sys

_LOGGER_NAME = "capa_ai"
_configured = False


def get_logger(child: str | None = None) -> logging.Logger:
    global _configured
    if not _configured:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        root = logging.getLogger(_LOGGER_NAME)
        root.setLevel(logging.INFO)
        root.addHandler(handler)
        root.propagate = False
        _configured = True

    name = f"{_LOGGER_NAME}.{child}" if child else _LOGGER_NAME
    return logging.getLogger(name)
