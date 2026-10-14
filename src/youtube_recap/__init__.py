"""youtube-recap: an MCP server that searches YouTube and returns transcripts to summarize."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("youtube-recap")
except PackageNotFoundError:  # running from a source tree without installing
    __version__ = "0.0.0"

__all__ = ["__version__"]
