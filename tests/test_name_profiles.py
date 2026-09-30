import pytest

from src.cad_understanding.architecture import build_architectural_report
from src.cad_understanding.name_profiles import build_rules, tokens, validate_name_aliases


def test_tokens_split_separators_camel_case_and_fold_cyrillic():
    assert tokens("A-WALL_Ext") == {"a", "wall", "ext"}
    assert tokens("DoorSwing01") == {"door", "swing"}
    assert tokens("АР_Стены") == {"ар", "стены"}
    assert tokens("ПРОЁМ") == {"проем"}


@pytest.mark.parametrize("name,category", [
    ("АР_Стены", "wall"), ("Двери-входные", "door"), ("Окна", "window"), ("Проёмы", "opening"),
    ("Колонны", "column"), ("Перекрытие", "slab_boundary"), ("Помещения", "room_boundary"),
    ("Оси", "grid"), ("Стіни", "wall"), ("Вікна", "window"), ("Steny", "wall"), ("Dveri", "door"),
    ("Wand", "wall"), ("A-DOOR", "door"), ("WallExt", "wall"), ("S-COLS", "column"),
])
def test_builtin_vocabularies_match_whole_words(name, category):
    assert tokens(name) & build_rules()[category], (name, category)


def test_whole_word_matching_avoids_substring_hits():
    rules = build_rules()
    for name in ("WALLPAPER", "COLOR", "Стенд", "Окно_Крашеное_Плитка"):
        hits = [c for c, words in rules.items() if tokens(name) & words]
        assert name == "Окно_Крашеное_Плитка" or hits == [], (name, hits)


def test_custom_aliases_are_validated_and_added():
    rules = build_rules({"wall": ["Мурус"], "door": ["ingresso"]})
    assert "мурус" in rules["wall"] and "ingresso" in rules["door"] and "wall" in rules["wall"]
    assert "мурус" not in build_rules()["wall"]
    for bad in ({"nonsense": ["x"]}, {"wall": []}, {"wall": ["two words"]}, {"wall": [""]},
                {"wall": ["x" * 41]}, {"wall": "wall"}, ["wall"], {"wall": [5]}):
        with pytest.raises(ValueError):
            validate_name_aliases(bad)
    with pytest.raises(ValueError):
        validate_name_aliases({"wall": [f"a{chr(97 + i % 26)}{chr(97 + i // 26)}" for i in range(65)]})
    validate_name_aliases(None)


def _ir(layer):
    return {"schema_version": "cad-ir/v2", "drawing": {"path": "a.dwg", "units": "mm"},
            "sections": {"entities": {"total": 1, "items": [
                {"handle": "A1", "entity_type": "AcDbLine", "layer": layer,
                 "geometry": {"start": [0, 0, 0], "end": [100, 0, 0]}}]}}}


def test_report_classifies_non_latin_layers_and_honours_custom_aliases():
    assert build_architectural_report(_ir("АР_Стены"))["candidates"][0]["category"] == "wall"
    assert build_architectural_report(_ir("MURUS-EXT"))["candidates"] == []
    report = build_architectural_report(_ir("MURUS-EXT"), name_aliases={"wall": ["murus"]})
    assert report["candidates"][0]["category"] == "wall"
    with pytest.raises(ValueError):
        build_architectural_report(_ir("X"), name_aliases={"bogus": ["x"]})
