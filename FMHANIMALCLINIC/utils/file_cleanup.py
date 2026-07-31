"""Helpers for safe media file cleanup on model updates/deletes."""

import logging

logger = logging.getLogger(__name__)


def safely_delete_field_file(field_file):
    """Delete a FieldFile from storage, ignoring missing-file errors."""
    if not field_file:
        return

    name = getattr(field_file, 'name', None)
    storage = getattr(field_file, 'storage', None)

    if not name or storage is None:
        return

    try:
        if storage.exists(name):
            storage.delete(name)
    except FileNotFoundError:
        # Already missing on disk; DB cleanup should still proceed.
        return
    except OSError:
        # Covers common filesystem race conditions and missing file paths.
        return
    except Exception:  # pylint: disable=broad-exception-caught
        logger.warning('Failed to delete file from storage: %s', name, exc_info=True)
