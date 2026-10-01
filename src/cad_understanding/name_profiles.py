"""Layer / block name vocabularies for architectural candidates.

Built-in aliases cover English, Russian, Ukrainian, transliterated Russian and German
names; callers can add project-specific aliases. Matching is by whole tokens (so WALL does
not match WALLPAPER); a token is a run of letters, and CamelCase and digits/underscores/
dashes split names ("A-WALL_Ext", "АР_Стены", "DoorSwing"). A name match is only a hint and
never confirms an element.
"""

import re

_SPLIT = re.compile(r"[^\W\d_]+", re.UNICODE)
_CAMEL = re.compile(r"(?<=[a-zа-яіїєґё])(?=[A-ZА-ЯІЇЄҐЁ])")

BUILTIN_ALIASES = {
    "wall": {"wall", "walls", "стена", "стены", "стену", "стен", "стене", "стенами", "стіна", "стіни", "стін",
             "stena", "steny", "wand", "waende", "wände", "mur", "murs"},
    "door": {"door", "doors", "дверь", "двери", "дверей", "дверные", "дверной", "двері", "дверний",
             "dver", "dveri", "tur", "tür", "tuer", "porte", "portes"},
    "window": {"window", "windows", "glaz", "окно", "окна", "окон", "оконные", "оконный", "вікно", "вікна", "вікон",
               "okno", "okna", "fenster", "fenetre"},
    "opening": {"opening", "openings", "opng", "проем", "проём", "проемы", "проёмы", "проемов", "прорізи", "проріз",
                "отверстие", "отверстия", "отвір", "отвори", "proem", "proemy", "offnung", "öffnung"},
    "grid": {"grid", "grids", "axis", "axes", "ось", "оси", "осей", "сетка", "сетки", "осі", "сітка", "сітки",
             "os", "setka", "raster"},
    "column": {"column", "columns", "cols", "col", "колонна", "колонны", "колонн", "колона", "колони", "колон",
               "столб", "столбы", "kolonna", "kolonny", "stuetze", "stütze", "stuetzen", "poteau"},
    "slab_boundary": {"slab", "slabs", "deck", "плита", "плиты", "плит", "плите", "перекрытие", "перекрытия",
                      "перекриття", "plita", "plity", "perekrytie", "decke", "geschossdecke"},
    "room_boundary": {"room", "rooms", "помещение", "помещения", "помещений", "комната", "комнаты", "кімната",
                      "кімнати", "приміщення", "pomeshchenie", "komnata", "raum", "raeume", "räume"},
}

MAX_CUSTOM_ALIASES = 64
MAX_ALIAS_LENGTH = 40


def tokens(value):
    """Lower-case letter tokens of a name; CamelCase boundaries split, yo folds to ye.

    Xref-dependent names ("Wall Base|2_Arch_Plan_Text") use only the part after the last "|": the
    xref's file name says nothing about what a layer or block inside it holds.
    """
    text = _CAMEL.sub(" ", str(value).rsplit("|", 1)[-1]).casefold().replace("ё", "е")
    return set(_SPLIT.findall(text))


def _fold(alias):
    return str(alias).casefold().replace("ё", "е")


def validate_name_aliases(name_aliases):
    """None or {category: [alias, ...]} for known categories; raises ValueError otherwise."""
    if name_aliases is None:
        return
    if not isinstance(name_aliases, dict):
        raise ValueError("name_aliases must be an object {category: [aliases]}.")
    total = 0
    for category, aliases in name_aliases.items():
        if category not in BUILTIN_ALIASES:
            raise ValueError(f"name_aliases category must be one of {sorted(BUILTIN_ALIASES)}, got {category!r}.")
        if not isinstance(aliases, list) or not aliases:
            raise ValueError(f"name_aliases[{category!r}] must be a non-empty list of strings.")
        for alias in aliases:
            if not isinstance(alias, str) or not 1 <= len(alias) <= MAX_ALIAS_LENGTH or len(tokens(alias)) != 1 \
                    or tokens(alias) != {t for t in _SPLIT.findall(_fold(alias))}:
                raise ValueError("Each alias must be one word of letters (up to 40 characters).")
            total += 1
    if total > MAX_CUSTOM_ALIASES:
        raise ValueError(f"At most {MAX_CUSTOM_ALIASES} custom aliases are allowed.")


def build_rules(name_aliases=None):
    """Category -> alias set (built-in plus validated custom aliases, folded like tokens)."""
    validate_name_aliases(name_aliases)
    rules = {category: {_fold(a) for a in aliases} for category, aliases in BUILTIN_ALIASES.items()}
    for category, aliases in (name_aliases or {}).items():
        rules[category] |= {_fold(a) for a in aliases}
    return rules
