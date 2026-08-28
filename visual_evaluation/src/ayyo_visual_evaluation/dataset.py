"""Bounded recorded visual sources with no implicit persistence."""

from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import stat
from types import MappingProxyType
from typing import Mapping, Protocol

from .errors import VisualDatasetError
from .models import (
    MAX_DATASET_BYTES,
    VisualEvaluationDatasetManifest,
    VisualEvaluationInput,
    VisualEvaluationSample,
)


class VisualRecordedSource(Protocol):
    """Narrow transport-neutral loader boundary for one manifest sample."""

    def load(
        self,
        dataset: VisualEvaluationDatasetManifest,
        sample: VisualEvaluationSample,
    ) -> VisualEvaluationInput: ...


def _validate_membership(
    dataset: VisualEvaluationDatasetManifest,
    sample: VisualEvaluationSample,
) -> None:
    if type(dataset) is not VisualEvaluationDatasetManifest:
        raise VisualDatasetError("recorded source requires a typed dataset manifest")
    if type(sample) is not VisualEvaluationSample:
        raise VisualDatasetError("recorded source requires a typed sample")
    matching = tuple(item for item in dataset.samples if item.sample_id == sample.sample_id)
    if len(matching) != 1 or matching[0] != sample:
        raise VisualDatasetError(
            "sample is absent from or conflicts with the immutable dataset manifest"
        )


def _checked_input(sample: VisualEvaluationSample, payload: bytes) -> VisualEvaluationInput:
    if len(payload) != sample.asset_size_bytes:
        raise VisualDatasetError("recorded sample byte count does not match its manifest")
    if sha256(payload).hexdigest() != sample.asset_sha256:
        raise VisualDatasetError("recorded sample digest does not match its manifest")
    try:
        return VisualEvaluationInput(sample=sample, rgb8=payload)
    except ValueError as error:
        raise VisualDatasetError("recorded sample input contract is malformed") from error


class InMemoryVisualRecordedSource:
    """Immutable bounded test/embedding source keyed by asset reference."""

    __slots__ = ("_assets", "_total_bytes")

    def __init__(self, assets: Mapping[str, bytes]) -> None:
        if not isinstance(assets, Mapping) or not assets:
            raise VisualDatasetError("in-memory visual assets must be a nonempty mapping")
        copied: dict[str, bytes] = {}
        total = 0
        for key, value in assets.items():
            if type(key) is not str or type(value) is not bytes or not value:
                raise VisualDatasetError(
                    "in-memory visual assets require exact text keys and immutable bytes"
                )
            if key in copied:
                raise VisualDatasetError("in-memory asset references must be unique")
            total += len(value)
            if total > MAX_DATASET_BYTES:
                raise VisualDatasetError("in-memory assets exceed their aggregate bound")
            copied[key] = bytes(value)
        self._assets = MappingProxyType(copied)
        self._total_bytes = total

    @property
    def total_bytes(self) -> int:
        return self._total_bytes

    def load(
        self,
        dataset: VisualEvaluationDatasetManifest,
        sample: VisualEvaluationSample,
    ) -> VisualEvaluationInput:
        _validate_membership(dataset, sample)
        payload = self._assets.get(sample.asset_reference)
        if payload is None:
            raise VisualDatasetError("recorded sample asset is missing")
        return _checked_input(sample, payload)


class RootedRawRgb8VisualSource:
    """Read exact raw-rgb8 fixture files beneath one configured root.

    Directory components and the final file are opened relative to directory
    descriptors with ``O_NOFOLLOW``. No image decoder, archive, or compression
    library is involved.
    """

    __slots__ = ("_root",)

    def __init__(self, root: str | os.PathLike[str]) -> None:
        path = Path(root)
        if path.is_symlink():
            raise VisualDatasetError("evaluation root cannot be a symbolic link")
        try:
            resolved = path.resolve(strict=True)
        except OSError as error:
            raise VisualDatasetError("evaluation root does not exist") from error
        if not resolved.is_dir():
            raise VisualDatasetError("evaluation root must be a directory")
        self._root = resolved

    @property
    def root(self) -> Path:
        return self._root

    def _read(self, sample: VisualEvaluationSample) -> bytes:
        components = sample.asset_reference.split("/")
        directory_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY
        file_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
        if hasattr(os, "O_NOFOLLOW"):
            directory_flags |= os.O_NOFOLLOW
        descriptors: list[int] = []
        try:
            current = os.open(self._root, directory_flags)
            descriptors.append(current)
            for component in components[:-1]:
                current = os.open(component, directory_flags, dir_fd=current)
                descriptors.append(current)
            file_descriptor = os.open(components[-1], file_flags, dir_fd=current)
            descriptors.append(file_descriptor)
            metadata = os.fstat(file_descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise VisualDatasetError("recorded asset must be a regular file")
            if metadata.st_size != sample.asset_size_bytes:
                raise VisualDatasetError(
                    "recorded asset size does not match its immutable manifest"
                )
            chunks: list[bytes] = []
            remaining = sample.asset_size_bytes + 1
            while remaining:
                chunk = os.read(file_descriptor, min(remaining, 64 * 1_024))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            payload = b"".join(chunks)
            if len(payload) != sample.asset_size_bytes:
                raise VisualDatasetError(
                    "recorded asset changed size while it was being read"
                )
            return payload
        except VisualDatasetError:
            raise
        except OSError as error:
            raise VisualDatasetError(
                "recorded asset is missing, inaccessible, or crosses a symlink"
            ) from error
        finally:
            for descriptor in reversed(descriptors):
                try:
                    os.close(descriptor)
                except OSError:
                    pass

    def load(
        self,
        dataset: VisualEvaluationDatasetManifest,
        sample: VisualEvaluationSample,
    ) -> VisualEvaluationInput:
        _validate_membership(dataset, sample)
        return _checked_input(sample, self._read(sample))
