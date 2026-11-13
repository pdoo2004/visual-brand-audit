
"""Deduplicate downloaded images before analysis."""

import hashlib
from collections.abc import Iterable
from typing import TypeVar

T = TypeVar("T")


def unique_downloads(images: Iterable[T]) -> tuple[list[T], list[T]]:
    """Return (unique_images, duplicates) using file content hashes."""
    seen_hashes: set[str] = set()
    unique: list[T] = []
    duplicates: list[T] = []

    for item in images:
        with item.path.open("rb") as file:
            digest = hashlib.file_digest(file, "sha256").hexdigest()

        if digest in seen_hashes:
            duplicates.append(item)
        else:
            seen_hashes.add(digest)
            unique.append(item)

    return unique, duplicates
