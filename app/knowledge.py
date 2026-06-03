from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parent / "data"
FOODS_FILE = DATA_DIR / "foods.json"

_FOODS_CACHE: list[dict[str, Any]] | None = None

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
