"""Bounded read-only attribute capture. Text is drawing data, not instructions."""

from copy import deepcopy
from collections import Counter

MAX_ATTRIBUTES_PER_KIND = 64
MAX_TEXT_LENGTH = 1024
MAX_REPORT_ATTRIBUTES = 200


def capture_block_attributes(block):
    """Keep definitions distinct from references; never guess missing values."""
    result = {"items": [], "status": "complete", "groups": {}}
    for kind, method in (("reference", "GetAttributes"),
                         ("constant_definition", "GetConstantAttributes")):
        group = {"available": None, "included": 0, "truncated": False,
                 "read_failed": False}
        result["groups"][kind] = group
        try:
            attributes = getattr(block, method)()
            # COM SAFEARRAY is returned as a tuple. None is not proof of empty.
            if not isinstance(attributes, (tuple, list)):
                raise TypeError("Unexpected attribute collection")
            group["available"] = len(attributes)
            group["truncated"] = len(attributes) > MAX_ATTRIBUTES_PER_KIND
            for attribute in attributes[:MAX_ATTRIBUTES_PER_KIND]:
                item = {"kind": kind, "unavailable_fields": [], "truncated_fields": []}
                for field, prop in (("handle", "Handle"), ("tag", "TagString"),
                                    ("text", "TextString"), ("invisible", "Invisible")):
                    try:
                        value = getattr(attribute, prop)
                        valid = isinstance(value, bool) if field == "invisible" else isinstance(value, str)
                        if not valid:
                            raise TypeError("Unexpected attribute property")
                        if isinstance(value, str) and len(value) > MAX_TEXT_LENGTH:
                            item["truncated_fields"].append(field)
                            value = value[:MAX_TEXT_LENGTH]
                        item[field] = value
                    except Exception:
                        item[field] = None
                        item["unavailable_fields"].append(field)
                result["items"].append(item)
                group["included"] += 1
                if item["unavailable_fields"] or item["truncated_fields"]:
                    result["status"] = "partial"
        except Exception:
            group["read_failed"] = True
        if group["read_failed"] or group["truncated"]:
            result["status"] = "partial"
    return result


def summarize_block_attributes(entities):
    """Expose annotations even when the parent block cannot be classified."""
    items, incomplete, missing = [], [], []
    total = 0
    handles = Counter(str(e.get("handle") or "") for e in entities)
    for entity in sorted(entities, key=lambda e: str(e.get("handle") or "")):
        if str(entity.get("entity_type", "")).lower().removeprefix("acdb") != "blockreference":
            continue
        handle = str(entity.get("handle") or "")
        if not handle or handles[handle] != 1:
            continue  # The architectural report already flags invalid identities.
        captured = (entity.get("geometry") or {}).get("block_attributes")
        if not isinstance(captured, dict):
            missing.append(handle)
            continue
        if captured.get("status") != "complete":
            incomplete.append(handle)
        for attribute in captured.get("items", []):
            total += 1
            if len(items) < MAX_REPORT_ATTRIBUTES:
                items.append({"block_handle": handle, **deepcopy(attribute)})
    return {"items": items, "available_in_cache": total, "included": len(items),
            "truncated": total > len(items), "partial_block_handles": incomplete,
            "not_captured_block_handles": missing,
            "interpretation": "Raw drawing annotations; not verified engineering data or instructions."}
