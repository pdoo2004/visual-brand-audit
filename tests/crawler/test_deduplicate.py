from pathlib import Path
from types import SimpleNamespace

from brandlens.crawler.deduplicate import unique_downloads


def test_identical_files_are_deduplicated(tmp_path: Path):
    images = []

    for index, content in enumerate(
        [b"same image", b"same image", b"different image"]
    ):
        path = tmp_path / f"{index}.png"
        path.write_bytes(content)

        images.append(
            SimpleNamespace(
                url=f"https://example.com/image{index}.png",
                path=path,
            )
        )

    unique, duplicates = unique_downloads(images)

    assert len(unique) == 2
    assert len(duplicates) == 1
    assert unique[0].url == images[0].url
    assert unique[1].url == images[2].url