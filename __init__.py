"""Independent CRUN integration for ComfyUI. No provider calls at import time."""

from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
from .crun.version import VERSION as __version__

WEB_DIRECTORY = "./web"

try:
    from server import PromptServer
except ImportError:
    PromptServer = None  # Offline tests and source inspection do not need Comfy.

if PromptServer is not None and getattr(PromptServer, "instance", None) is not None:
    from .crun.server import register_routes

    register_routes(PromptServer.instance.routes)

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY", "__version__"]
