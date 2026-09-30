"""Architectural adapter: walls and other plan lines drawn inside block definitions.

Whole plans are often inserted as one block. The scan stores up to a few hundred LINEs of each
definition (block coordinates, with their own layer); here they are placed in WCS as virtual
entities so they are classified like drawn lines. Only lines whose effective layer carries an
architectural word are expanded, one nesting level, never exploding or copying anything.
"""

from .name_profiles import tokens
from .opening_swings import block_transform

MAX_EXPANDED_LINES = 5000


def expand_block_lines(entities, vocabulary):
    """(virtual_entities, refs) for block references whose definition lines match the vocabulary.

    vocabulary: set of architectural tokens. Virtual handles are "<ref handle>/L<index>".
    """
    virtual, refs = [], {}
    for entity in entities:
        geometry = entity.get("geometry") or {}
        lines = (geometry.get("block_definition") or {}).get("lines") or []
        handle = str(entity.get("handle") or "")
        if not lines or not handle:
            continue
        transform = block_transform(geometry, uniform_only=False)
        if transform is None:
            continue
        place = transform[0]
        for index, line in enumerate(lines):
            layer = str(line.get("layer") or "0")
            effective = layer if layer != "0" else str(entity.get("layer") or "0")
            if not tokens(effective) & vocabulary:
                continue
            try:
                start, end = place(line["start"]), place(line["end"])
            except (KeyError, TypeError, IndexError):
                continue
            if len(virtual) >= MAX_EXPANDED_LINES:
                return virtual, refs
            virtual.append({"handle": f"{handle}/L{index}", "entity_type": "AcDbLine", "layer": effective,
                            "geometry": {"start": [start[0], start[1], 0.0], "end": [end[0], end[1], 0.0]},
                            "virtual_source": {"block_handle": handle, "block_name": geometry.get("block_name"),
                                               "definition_layer": layer}})
            refs[handle] = refs.get(handle, 0) + 1
    return virtual, refs
