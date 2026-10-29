"""Generic CV registry helpers; specifications stay inside the criteria."""

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from inspect import isabstract
from types import MappingProxyType
from typing import Any

from .criterion_base import CriterionBase


@dataclass(frozen=True)
class CVRegistration:
    """Reference an implementation without repeating its metadata."""

    criterion_class: type[CriterionBase]

    @property
    def criterion_id(self) -> str:
        return self.criterion_class.criterion_id

    @property
    def implementation_id(self) -> str:
        return self.criterion_class.method_id

    @property
    def requires_subject_region(self) -> bool:
        return self.criterion_class.input_requirements()["reliable_subject_region"]

    def create(self, settings: dict[str, Any] | None = None) -> CriterionBase:
        """Reuse the criterion constructor's settings validation."""
        return self.criterion_class(settings)

    def validate_measurements(self, required: Sequence[str]) -> None:
        """Check requested native measurement names; subsets are allowed."""
        if not isinstance(required, (list, tuple)) or any(
            not isinstance(name, str) or not name.strip() for name in required
        ):
            raise TypeError("required_measurements must be a list/tuple of names.")
        if len(required) != len(set(required)):
            raise ValueError("required_measurements must not contain duplicates.")
        unknown = set(required) - set(self.criterion_class.measurement_specs())
        if unknown:
            raise ValueError(
                f"{self.implementation_id}: unsupported measurements: "
                f"{', '.join(sorted(unknown))}"
            )

    def describe(self, *, include_defaults: bool = True) -> dict[str, Any]:
        """Delegate the catalog description to the implementation itself."""
        return self.criterion_class.describe(include_defaults=include_defaults)


class CVRegistry(Mapping[str, CVRegistration]):
    """Read-only mapping from implementation IDs to registered classes."""

    def __init__(self, criterion_classes: Sequence[type[CriterionBase]]):
        entries = {}
        for criterion_class in criterion_classes:
            if (
                not isinstance(criterion_class, type)
                or not issubclass(criterion_class, CriterionBase)
                or isabstract(criterion_class)
            ):
                raise TypeError("Register a concrete CriterionBase subclass.")
            for field in ("criterion_id", "method_id", "method_version"):
                value = getattr(criterion_class, field, None)
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"{criterion_class.__name__}: invalid {field}.")
            registration = CVRegistration(criterion_class)
            key = registration.implementation_id
            if key in entries:
                raise ValueError(f"Duplicate implementation_id: {key}")
            entries[key] = registration
        self._entries = MappingProxyType(entries)

    def __getitem__(self, key: str) -> CVRegistration:
        return self._entries[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def get_registration(
        self,
        criterion_id: str,
        implementation_id: str | None = None,
        *,
        registry: Mapping[str, CVRegistration] | None = None,
    ) -> CVRegistration:
        """Resolve a criterion; require a method choice when several support it."""
        entries = self if registry is None else registry
        if not isinstance(criterion_id, str) or not criterion_id.strip():
            raise ValueError("criterion_id must be a nonempty string.")
        if implementation_id is not None:
            if not isinstance(implementation_id, str) or not implementation_id.strip():
                raise ValueError("implementation_id must be a nonempty string.")
            if implementation_id not in entries:
                raise ValueError(f"Unsupported CV implementation: {implementation_id}")
            entry = entries[implementation_id]
            if entry.criterion_id != criterion_id:
                raise ValueError(
                    f"{implementation_id} does not support {criterion_id}."
                )
            return entry
        matches = [
            entry for entry in entries.values() if entry.criterion_id == criterion_id
        ]
        if not matches:
            raise ValueError(f"Unsupported CV criterion: {criterion_id}")
        if len(matches) != 1:
            raise ValueError(f"{criterion_id}: select an explicit implementation_id.")
        return matches[0]

    def get_catalog(
        self,
        *,
        include_defaults: bool = True,
        registry: Mapping[str, CVRegistration] | None = None,
    ) -> list[dict[str, Any]]:
        """Collect descriptions without constructing criteria or analyzing images."""
        entries = self if registry is None else registry
        return [
            entry.describe(include_defaults=include_defaults)
            for entry in entries.values()
        ]
