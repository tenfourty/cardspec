# Derived from json-render's catalogue design, rewritten in Python; see the NOTICE file.
"""A catalogue is data: the elements a card may hold, what each takes, and the rules for a model.

Elements are described, not coded. The same description drives validation (`validate`), the
text a model reads (`catalogue_prompt`) and, in later releases, the string walker and the
renderers. A deployment can extend the standard catalogue or build its own.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from .limits import LIMIT_NAMES, Limits
from .schema import Children, Kind, Obj, Opt, PropsCheck

_NAME = re.compile(r"[A-Z][A-Za-z0-9]{0,19}")


@dataclass(frozen=True)
class Element:
    """One kind of element: its props, its children, a description and an example.

    `props` maps prop names to a kind (required) or `Opt(kind)`. `children` is None for a leaf.
    `example` is the element as a person writes it (the nested form: `type` and the props at
    the same level, `children` holding elements); a test proves every example validates.
    `check` is an optional cross-field check, run only when the props passed the kit.
    """

    name: str
    props: Mapping[str, Kind | Opt]
    description: str
    example: Mapping[str, Any]
    children: Children | None = None
    check: PropsCheck | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if not _NAME.fullmatch(self.name):
            raise ValueError(
                f"element name {self.name!r} must start with a capital letter and have at most "
                "20 letters or digits"
            )
        if not self.description.strip():
            raise ValueError(f"element {self.name} needs a description")
        if self.example.get("type") != self.name:
            raise ValueError(f'the example of {self.name} must have "type": "{self.name}"')
        object.__setattr__(self, "props", MappingProxyType(dict(self.props)))

    @property
    def schema(self) -> Obj:
        return Obj(self.props)

    def check_limits(self, limits: Limits) -> None:
        """Raise ValueError if the element names a limit that `Limits` does not have."""
        names = self.schema.limit_names()
        if self.children is not None and isinstance(self.children.max, str):
            names.append(self.children.max)
        for n in names:
            if n not in LIMIT_NAMES:
                raise ValueError(f"element {self.name} uses an unknown limit {n!r}")


@dataclass(frozen=True)
class Profile:
    """What one surface can show: the element types it takes (None means all) and its limits."""

    name: str
    elements: frozenset[str] | None
    limits: Limits


class Catalogue:
    """The elements, the root, the known format versions, the rules and the profiles."""

    def __init__(
        self,
        elements: Iterable[Element],
        *,
        root: str,
        versions: tuple[int, ...] = (1,),
        rules: tuple[str, ...] = (),
        profiles: Mapping[str, Mapping[str, Any]] | None = None,
        example: Mapping[str, Any] | None = None,
    ) -> None:
        items: dict[str, Element] = {}
        for el in elements:
            if el.name in items:
                raise ValueError(f"element {el.name} is defined twice")
            items[el.name] = el
        if root not in items:
            raise ValueError(f"the root element {root} is not in the catalogue")
        if not versions or any(isinstance(v, bool) or not isinstance(v, int) for v in versions):
            raise ValueError("versions must be a non-empty tuple of whole numbers")
        for el in items.values():
            el.check_limits(Limits())
            if el.children:
                for child in el.children.allowed:
                    if child not in items:
                        raise ValueError(f"{el.name} allows unknown child type {child}")
        self.elements: Mapping[str, Element] = MappingProxyType(items)
        self.root = root
        self.versions = tuple(versions)
        self.rules = tuple(rules)
        self.example = example
        specs: dict[str, dict[str, Any]] = {}
        for name, spec in (profiles or {}).items():
            elements_in = spec.get("elements")
            if elements_in is not None:
                missing = [e for e in elements_in if e not in items]
                if missing:
                    raise ValueError(f"profile {name} names unknown elements: {', '.join(missing)}")
                if root not in elements_in:
                    raise ValueError(f"profile {name} must keep the root element {root}")
            Limits().replace(**spec.get("limits", {}))  # fail now on a bad override
            specs[name] = dict(spec)
        self._profiles: Mapping[str, Mapping[str, Any]] = MappingProxyType(specs)

    @property
    def profiles(self) -> Mapping[str, Mapping[str, Any]]:
        return self._profiles

    def profile(self, name: str) -> Profile:
        """The named profile; raises KeyError for a name the catalogue does not have."""
        if name not in self._profiles:
            raise KeyError(f"unknown profile {name!r}; known: {', '.join(self._profiles)}")
        spec = self._profiles[name]
        els = spec.get("elements")
        return Profile(
            name,
            None if els is None else frozenset(els),
            Limits().replace(**spec.get("limits", {})),
        )

    def extend(
        self,
        *elements: Element,
        allow_in: tuple[str, ...] = (),
        rules: tuple[str, ...] = (),
    ) -> Catalogue:
        """A new catalogue with more elements. `allow_in` names the existing element types
        whose children may then include the new elements. The original is not changed."""
        new = {e.name for e in elements}
        for parent in allow_in:
            owner = self.elements.get(parent)
            if owner is None or owner.children is None:
                raise ValueError(f"{parent} cannot hold children, so it cannot be in allow_in")
        merged: list[Element] = []
        for el in self.elements.values():
            if el.name in allow_in and el.children is not None:
                allowed = el.children.allowed + tuple(
                    n for n in sorted(new) if n not in el.children.allowed
                )
                el = Element(
                    el.name,
                    el.props,
                    el.description,
                    el.example,
                    Children(allowed, el.children.max),
                    el.check,
                )
            merged.append(el)
        return Catalogue(
            [*merged, *elements],
            root=self.root,
            versions=self.versions,
            rules=self.rules + tuple(rules),
            profiles=self._profiles,
            example=self.example,
        )
