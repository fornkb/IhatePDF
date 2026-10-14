"""Protect source files and publish outputs atomically."""

from collections.abc import Callable, Iterable
from pathlib import Path
import os
import tempfile


def validate_outputs(outputs: Iterable[Path], inputs: Iterable[Path], force: bool = False) -> None:
    sources = {p.resolve() for p in inputs}
    seen: set[Path] = set()
    for output in outputs:
        resolved = output.resolve()
        if resolved in sources:
            raise ValueError(f"Output would overwrite an input: {output}. Choose a different path.")
        if resolved in seen:
            raise ValueError(f"Multiple outputs have the same path: {output}.")
        seen.add(resolved)
        if output.is_symlink():
            raise ValueError(f"Refusing to write through a symbolic link: {output}.")
        if output.exists() and not output.is_file():
            raise ValueError(f"Output is not a regular file: {output}.")
        if output.exists() and not force:
            raise ValueError(f"Output already exists: {output}.")


def atomic_write(output: Path, writer: Callable[[Path], None], *, force: bool = False) -> None:
    """Stage alongside destination, then publish without exposing partial files."""
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".ihatepdf-", suffix=output.suffix, dir=output.parent)
    os.close(fd)
    staged = Path(name)
    try:
        writer(staged)
        if force:
            os.replace(staged, output)
        elif os.name == "nt":
            # On Windows rename is atomic and refuses an existing destination.
            # This also works on OneDrive folders that prohibit hard links.
            os.rename(staged, output)
        else:
            # Hard-link publication is atomic and fails if another writer won the race.
            os.link(staged, output)
    finally:
        staged.unlink(missing_ok=True)

