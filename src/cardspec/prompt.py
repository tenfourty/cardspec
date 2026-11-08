# Derived from json-render's prompt generation, rewritten in Python; see the NOTICE file.
"""Turn a catalogue into the instructions a model reads before it writes a card.

The text is generated from the same data that validates, so the two cannot disagree. It is
plain ASCII and the same every time for the same inputs.
"""

from __future__ import annotations

import json

from .catalogue import Catalogue, Profile
from .limits import Limits
from .links import LinkPolicy
from .schema import Opt


def catalogue_prompt(
    catalogue: Catalogue | None = None,
    *,
    profile: str | Profile | None = None,
    limits: Limits | None = None,
    links: LinkPolicy | None = None,
) -> str:
    """Instructions for writing a card in `catalogue`, for one surface `profile`.

    `limits` default to the profile's, else `Limits()`. With no picture hosts in `links` the
    Image element is left out and the text says so.
    """
    if catalogue is None:
        from .standard import CATALOGUE

        catalogue = CATALOGUE
    prof = catalogue.profile(profile) if isinstance(profile, str) else profile
    limits = limits or (prof.limits if prof else Limits())
    links = links or LinkPolicy()

    def offered(name: str) -> bool:
        if prof is not None and prof.elements is not None and name not in prof.elements:
            return False
        return not (name == "Image" and not links.pictures_allowed)

    names = [n for n in catalogue.elements if offered(n)]
    version = catalogue.versions[-1]
    root = catalogue.root
    out: list[str] = [
        f"Write a card as one JSON object. The card format is version {version}.",
        "",
        "How to write it",
        f'- The top-level object is a {root}: {{"type": "{root}", "v": {version}, "title": "...", '
        '"children": [ ... ]}.',
        '- Every element is an object with "type" and its props at the same level. An element '
        'that holds others has "children", a list of elements.',
        "- Unknown types, unknown keys and values of the wrong kind are refused, not ignored. "
        "You will get a list of issues; fix them and send the card again.",
        "",
        "Elements",
    ]
    for name in names:
        el = catalogue.elements[name]
        out += ["", f"{name}: {el.description}"]
        if el.props:
            out.append("Props:")
            for prop, spec in el.props.items():
                kind = spec.kind if isinstance(spec, Opt) else spec
                optional = " (optional)" if isinstance(spec, Opt) else ""
                out.append(f"- {prop}{optional}: {kind.describe(limits)}")
        if el.children is not None:
            allowed = [c for c in el.children.allowed if offered(c)]
            out.append("Children: " + ", ".join(allowed))
        else:
            out.append("Children: none")
        out += ["Example:", "```json", json.dumps(dict(el.example), indent=2), "```"]
    if catalogue.example is not None:
        out += ["", "A whole card", "```json", json.dumps(dict(catalogue.example), indent=2), "```"]
    out += ["", "Rules"]
    out += [f"- {rule}" for rule in catalogue.rules]
    out += [
        "",
        "Limits",
        f"- At most {limits.max_chars} characters of text in the whole card, {limits.max_elements} "
        f"elements, {limits.max_nesting} levels from the {root} down, and {limits.max_bytes} "
        "bytes of JSON.",
    ]
    for type_name, cap in limits.max_per_type.items():
        if offered(type_name):
            out.append(f"- At most {cap} {type_name} per card.")
    out += ["", "Pictures"]
    if "Image" in names:
        hosts = links.image_hosts
        if callable(hosts):
            out.append("- An Image address must be https and on a host the deployment allows.")
        else:
            out.append(
                "- An Image address must be https and on one of these hosts: "
                + ", ".join(sorted(hosts))
            )
    else:
        out.append("- There are no pictures here: do not add an image.")
    out.append("")
    return "\n".join(out)
