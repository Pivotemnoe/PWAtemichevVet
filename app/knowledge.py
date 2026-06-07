from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parent / "data"
FOODS_FILE = DATA_DIR / "foods.json"
FAQ_FILE = DATA_DIR / "faq.json"
CARE_FILE = DATA_DIR / "care.json"

_FOODS_CACHE: list[dict[str, Any]] | None = None
_FAQ_CACHE: list[dict[str, Any]] | None = None
_CARE_CACHE: list[dict[str, Any]] | None = None

_STOP_WORDS = {
    "и",
    "или",
    "но",
    "что",
    "это",
    "как",
    "когда",
    "по",
    "про",
    "при",
    "для",
    "без",
    "со",
    "на",
    "в",
    "из",
    "от",
    "до",
    "у",
    "кошка",
    "кошки",
    "кот",
    "кота",
    "собака",
    "собаки",
    "питомец",
    "питомца",
}

_WORD_RE = re.compile(r"\w+", flags=re.UNICODE)
_COMPLEX_DISH_HINTS = {
    "борщ",
    "харчо",
    "суп",
    "гуляш",
    "котлета",
    "котлеты",
    "тефтели",
    "паста",
    "плов",
    "салат",
    "шаурма",
    "пюре",
    "каша",
    "рагу",
    "запеканка",
}


def _load_foods() -> list[dict[str, Any]]:
    global _FOODS_CACHE
    if _FOODS_CACHE is not None:
        return _FOODS_CACHE
    if not FOODS_FILE.exists():
        _FOODS_CACHE = []
        return _FOODS_CACHE
    with FOODS_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
    _FOODS_CACHE = data if isinstance(data, list) else []
    return _FOODS_CACHE


def _load_faq() -> list[dict[str, Any]]:
    global _FAQ_CACHE
    if _FAQ_CACHE is not None:
        return _FAQ_CACHE
    if not FAQ_FILE.exists():
        _FAQ_CACHE = []
        return _FAQ_CACHE
    with FAQ_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
    _FAQ_CACHE = data if isinstance(data, list) else []
    return _FAQ_CACHE


def _load_care() -> list[dict[str, Any]]:
    global _CARE_CACHE
    if _CARE_CACHE is not None:
        return _CARE_CACHE
    if not CARE_FILE.exists():
        _CARE_CACHE = []
        return _CARE_CACHE
    with CARE_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
    _CARE_CACHE = data if isinstance(data, list) else []
    return _CARE_CACHE


def _tokenize(text: str) -> list[str]:
    return _WORD_RE.findall((text or "").casefold())


def _content_tokens(text: str) -> set[str]:
    return {token for token in _tokenize(text) if token not in _STOP_WORDS}


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _score_food(query: str, item: dict[str, Any]) -> int:
    q = query.casefold().strip()
    if not q:
        return 0
    name = str(item.get("name") or "")
    category = str(item.get("category") or "")
    keywords = [str(value) for value in (item.get("keywords") or [])]
    haystack_main = name.casefold()
    haystack_extra = f"{category} {' '.join(keywords)}".casefold()

    score = 0
    if q == haystack_main:
        score += 20
    elif q in haystack_main:
        score += 8
    if q in haystack_extra:
        score += 5

    query_tokens = _content_tokens(q)
    item_tokens = _content_tokens(f"{name} {category} {' '.join(keywords)}")
    score += 3 * len(query_tokens & item_tokens)

    if score == 0:
        for qt in query_tokens:
            for it in item_tokens:
                if len(qt) >= 4 and len(it) >= 4 and _similar(qt, it) >= 0.82:
                    score += 1
                    break

    return score


def _plan_allowed(item: dict[str, Any], plan: str | None) -> bool:
    if not plan:
        return True
    allowed = item.get("for_plans") or []
    if not allowed:
        return True
    return str(plan).lower() in {str(value).lower() for value in allowed}


def _species_allowed(item: dict[str, Any], species: str | None) -> bool:
    if not species:
        return True
    allowed = item.get("species") or []
    if not allowed:
        return True
    normalized = str(species).casefold()
    aliases = {
        "кошка": "cat",
        "кот": "cat",
        "cat": "cat",
        "собака": "dog",
        "пёс": "dog",
        "пес": "dog",
        "dog": "dog",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized in {aliases.get(str(value).casefold(), str(value).casefold()) for value in allowed}


def _score_text_record(query: str, item: dict[str, Any], fields: tuple[str, ...]) -> int:
    q = query.casefold().strip()
    if not q:
        return 1
    text_parts: list[str] = []
    for field in fields:
        value = item.get(field)
        if isinstance(value, list):
            text_parts.extend(str(part) for part in value)
        elif value:
            text_parts.append(str(value))
    haystack = " ".join(text_parts).casefold()
    score = 0
    if q in haystack:
        score += 8
    query_tokens = _content_tokens(q)
    item_tokens = _content_tokens(haystack)
    score += 3 * len(query_tokens & item_tokens)
    if score == 0:
        for qt in query_tokens:
            for it in item_tokens:
                if len(qt) >= 4 and len(it) >= 4 and _similar(qt, it) >= 0.82:
                    score += 1
                    break
    return score


def _find_records(
    items: list[dict[str, Any]],
    query: str,
    *,
    plan: str | None = None,
    species: str | None = None,
    limit: int = 6,
    fields: tuple[str, ...],
) -> list[dict[str, Any]]:
    scored: list[tuple[int, dict[str, Any]]] = []
    for item in items:
        if not _plan_allowed(item, plan) or not _species_allowed(item, species):
            continue
        score = _score_text_record(query, item, fields)
        if score > 0:
            scored.append((score, item))
    scored.sort(key=lambda row: row[0], reverse=True)
    return [item for _, item in scored[:limit]]


def find_food(query: str, *, limit: int = 5) -> list[dict[str, Any]]:
    scored: list[tuple[int, dict[str, Any]]] = []
    for item in _load_foods():
        score = _score_food(query, item)
        if score > 0:
            scored.append((score, item))
    scored.sort(key=lambda row: row[0], reverse=True)
    return [item for _, item in scored[:limit]]


def is_complex_dish_query(query: str) -> bool:
    tokens = set(_content_tokens(query))
    return bool(tokens & _COMPLEX_DISH_HINTS)


def food_to_public(item: dict[str, Any]) -> dict[str, Any]:
    why = item.get("why") if isinstance(item.get("why"), dict) else {}
    return {
        "name": item.get("name") or "",
        "allowed": bool(item.get("allowed")),
        "category": item.get("category") or "",
        "toxicity": why.get("toxicity") or "",
        "effects": why.get("effects") or "",
        "risk_level": why.get("risk_level") or "",
        "how_much_is_dangerous": item.get("how_much_is_dangerous") or "",
        "advice": item.get("advice") or "",
    }


def faq_to_public(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or "",
        "question": item.get("question") or "",
        "short_answer": item.get("short_answer") or "",
        "detailed_answer": item.get("detailed_answer") or "",
        "category": item.get("category") or "",
        "species": item.get("species") or [],
        "tags": item.get("tags") or [],
    }


def care_to_public(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or "",
        "title": item.get("title") or "",
        "summary": item.get("summary") or "",
        "details": item.get("details") or "",
        "steps": item.get("steps") or [],
        "warning": item.get("warning") or "",
        "category": item.get("category") or "",
        "species": item.get("species") or [],
        "tags": item.get("tags") or [],
    }


def find_faq(
    query: str = "",
    *,
    plan: str | None = None,
    species: str | None = None,
    limit: int = 6,
) -> list[dict[str, Any]]:
    return [
        faq_to_public(item)
        for item in _find_records(
            _load_faq(),
            query,
            plan=plan,
            species=species,
            limit=limit,
            fields=("question", "short_answer", "detailed_answer", "category", "keywords", "tags"),
        )
    ]


def find_care(
    query: str = "",
    *,
    plan: str | None = None,
    species: str | None = None,
    limit: int = 6,
) -> list[dict[str, Any]]:
    return [
        care_to_public(item)
        for item in _find_records(
            _load_care(),
            query,
            plan=plan,
            species=species,
            limit=limit,
            fields=("title", "summary", "details", "category", "keywords", "tags"),
        )
    ]


def check_food(query: str, ingredients: str | None = None) -> dict[str, Any]:
    query = (query or "").strip()
    ingredients = (ingredients or "").strip()
    if not query:
        return {"status": "empty", "message": "Введите продукт или блюдо."}

    matches = find_food(query, limit=3)
    if matches:
        item = food_to_public(matches[0])
        return {
            "status": "found",
            "item": item,
            "message": render_food_result(item),
            "suggestions": [food_to_public(match) for match in matches[1:]],
        }

    if ingredients:
        ingredient_results = [food_to_public(item) for part in ingredients.split(",") for item in find_food(part.strip(), limit=1)]
        dangerous = [item for item in ingredient_results if not item["allowed"]]
        if dangerous:
            names = ", ".join(item["name"] for item in dangerous[:5])
            return {
                "status": "ingredients_checked",
                "message": (
                    f"Лучше не давать: в составе есть рискованные ингредиенты: {names}.\n\n"
                    "Для питомцев безопаснее отдельные простые продукты без соли, специй, лука, чеснока, соусов и жареного жира."
                ),
                "items": ingredient_results,
            }
        if ingredient_results:
            return {
                "status": "ingredients_checked",
                "message": (
                    "По известным ингредиентам явных запрещённых продуктов не найдено. "
                    "Но готовые блюда всё равно лучше давать только без соли, специй, соусов и жарки."
                ),
                "items": ingredient_results,
            }

    if is_complex_dish_query(query):
        return {
            "status": "need_ingredients",
            "message": (
                "Похоже, это готовое блюдо. Напишите состав через запятую: например, мясо, рис, лук, соль. "
                "Я проверю ингредиенты и отмечу опасные добавки."
            ),
        }

    return {
        "status": "not_found",
        "message": (
            "Я не нашёл это как отдельный продукт в базе. Если это блюдо, напишите его состав через запятую. "
            "Если это отдельный продукт, попробуйте другое название или близкий вариант."
        ),
    }


def render_food_result(item: dict[str, Any]) -> str:
    prefix = "✅ Можно" if item["allowed"] else "⛔ Нельзя"
    return (
        f"{prefix}: {item['name']}\n"
        f"Категория: {item['category'] or 'не указана'}\n"
        f"Токсичность: {item['toxicity'] or 'не указана'}\n"
        f"Почему это важно: {item['effects'] or 'нет данных'}\n"
        f"Уровень риска: {item['risk_level'] or 'не указан'}\n"
        f"Опасное количество: {item['how_much_is_dangerous'] or 'нет данных'}\n"
        f"Совет: {item['advice'] or 'нет данных'}"
    )
