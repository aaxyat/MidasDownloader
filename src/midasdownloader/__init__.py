"""MidasDownloader - Batch Admit Card Downloader Package."""

from .cli import app

def main() -> None:
    """Entrypoint for the CLI script."""
    app()

__all__ = ["app", "main"]
