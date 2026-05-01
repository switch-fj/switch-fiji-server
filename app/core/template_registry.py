from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.logger import setup_logger

logger = setup_logger(__name__)


class TemplateRegistry:
    """Resolves template and static file directories and mounts static assets on the FastAPI app."""

    ROOT_DIR = Path(__file__).resolve().parent.parent

    def __init__(
        self,
        templates_full_path: Optional[Path] = None,
        static_dir: Optional[Path] = None,
    ):
        """Initialise directory paths for templates and static files.

        Args:
            templates_full_path: Absolute path to the templates directory. Defaults to <root>/templates.
            static_dir: Absolute path to the static files directory. Defaults to <root>/static.
        """
        if templates_full_path:
            self.TEMPLATES_DIR = templates_full_path
        else:
            self.TEMPLATES_DIR = Path(self.ROOT_DIR, "templates")

        if static_dir:
            self.STATIC_DIR = static_dir
        else:
            self.STATIC_DIR = Path(self.ROOT_DIR, "static")

    # Mount static folder
    def mount_static(
        self,
        app: FastAPI,
        path: Optional[str] = "/static",
        name: Optional[str] = "static",
    ):
        """Mount the static files directory onto the FastAPI app if it exists.

        Args:
            app: The FastAPI application instance to mount static files on.
            path: The URL path prefix for static files. Defaults to "/static".
            name: The route name for the static files mount. Defaults to "static".

        Returns:
            None
        """
        if self.STATIC_DIR.exists():
            logger.info("Static files mounted at /static")
            app.mount(path=path, app=StaticFiles(directory=str(self.STATIC_DIR)), name=name)
            return

        logger.error("Error mounting static files.")
