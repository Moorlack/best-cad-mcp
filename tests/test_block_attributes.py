from types import SimpleNamespace

from src.cad_understanding.block_attributes import (
    capture_block_attributes, summarize_block_attributes,
)


def attr(handle="A1", tag="LABEL", text="Glass", invisible=False):
    return SimpleNamespace(Handle=handle, TagString=tag, TextString=text, Invisible=invisible)


def block(refs=(), constants=()):
    return SimpleNamespace(GetAttributes=lambda: refs, GetConstantAttributes=lambda: constants)


def entity(handle, captured):
    return {"handle": handle, "entity_type": "AcDbBlockReference",
            "geometry": {"block_attributes": captured}}


def test_repeated_tags_empty_text_and_constant_provenance_preserved():
    result = capture_block_attributes(block((attr(), attr("A2", text="", invisible=True)), (attr("C1"),)))
    assert result["status"] == "complete"
    assert [a["tag"] for a in result["items"]] == ["LABEL"] * 3
    assert [a["handle"] for a in result["items"]] == ["A1", "A2", "C1"]
    assert result["items"][1]["text"] == ""
    assert result["items"][1]["invisible"] is True
    assert result["items"][2]["kind"] == "constant_definition"


def test_empty_arrays_are_complete_but_unknown_collections_are_not():
    assert capture_block_attributes(block())["status"] == "complete"
    result = capture_block_attributes(block(None))
    assert result["status"] == "partial"
    assert result["groups"]["reference"]["read_failed"] is True
    assert result["groups"]["reference"]["available"] is None


def test_failed_reference_read_still_captures_constants():
    def fail():
        raise RuntimeError("COM unavailable")
    result = capture_block_attributes(SimpleNamespace(GetAttributes=fail,
                                                      GetConstantAttributes=lambda: (attr("C1"),)))
    assert result["status"] == "partial"
    assert result["items"][0]["handle"] == "C1"


def test_failed_property_does_not_erase_other_attributes_or_invent_visibility():
    result = capture_block_attributes(block((SimpleNamespace(Handle="bad"), attr())))
    assert result["status"] == "partial"
    assert result["items"][0]["invisible"] is None
    assert result["items"][0]["unavailable_fields"] == ["tag", "text", "invisible"]
    assert result["items"][1]["text"] == "Glass"


def test_limits_are_explicit_and_constants_have_independent_budget():
    result = capture_block_attributes(block(tuple(attr(text="x" * 1100) for _ in range(65)), (attr("C1"),)))
    assert result["status"] == "partial"
    assert result["groups"]["reference"] == {
        "available": 65, "included": 64, "truncated": True, "read_failed": False}
    assert len(result["items"]) == 65
    assert len(result["items"][0]["text"]) == 1024
    assert result["items"][0]["truncated_fields"] == ["text"]
    assert result["items"][-1]["handle"] == "C1"


def test_report_limits_and_missing_capture_are_explicit():
    captured = capture_block_attributes(block(tuple(attr() for _ in range(64))))
    entities = [entity(str(i), captured) for i in range(4)]
    entities.append({"handle": "old", "entity_type": "AcDbBlockReference", "geometry": {}})
    result = summarize_block_attributes(entities)
    assert result["available_in_cache"] == 256
    assert result["included"] == 200
    assert result["truncated"] is True
    assert result["not_captured_block_handles"] == ["old"]
    result["items"][0]["text"] = "changed"
    assert captured["items"][0]["text"] == "Glass"


def test_ambiguous_block_handles_do_not_produce_misattributed_annotations():
    captured = capture_block_attributes(block((attr(),)))
    result = summarize_block_attributes([entity("B1", captured), entity("B1", captured),
                                         entity("", captured)])
    assert result["items"] == []
