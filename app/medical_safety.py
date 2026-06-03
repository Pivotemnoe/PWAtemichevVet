from __future__ import annotations

import re
from dataclasses import dataclass


URGENCY_LABELS = {
    "green": "Можно наблюдать",
    "yellow": "Нужна консультация",
    "red": "Срочно в клинику",
}


@dataclass(frozen=True)
class RedFlagResult:
    matched: tuple[str, ...]

    @property
    def has_red_flags(self) -> bool:
        return bool(self.matched)


RED_FLAG_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "судороги",
        (
            r"\bсудорог\w*\b",
            r"\bконвульси\w*\b",
            r"\bприпад\w*\b",
            r"\bэпилепт\w*\s+приступ\w*\b",
        ),
    ),
    (
        "тяжёлое дыхание",
        (
            r"\bтяж[её]ло\s+дыш\w*\b",
            r"\bплохо\s+дыш\w*\b",
            r"\bзатрудн[её]нн\w*\s+дыхани\w*\b",
            r"\bодышк\w*\b",
            r"\bне\s+может\s+дыш\w*\b",
            r"\bзадых\w*\b",
            r"\bдыш\w*\s+с\s+открыт\w*\s+ртом\b",
            r"\bсин\w*\s+(?:язык|десн\w*)\b",
        ),
    ),
    (
        "кровь или кровотечение",
        (
            r"\bкров[ьи]\b",
            r"\bкровит\b",
            r"\bкровотеч\w*\b",
            r"\bкровав\w*\b",
            r"\bс\s+кровью\b",
        ),
    ),
    (
        "подозрение на отравление",
        (
            r"\bотрав\w*\b",
            r"\bяд\b",
            r"\bкрыси\w*\s+яд\b",
            r"\bантифриз\b",
            r"\bизониазид\b",
            r"\bксилит\w*\b",
            r"\bсъел\w*\s+(?:таблет\w*|лекарств\w*|яд|отрав\w*)\b",
        ),
    ),
    (
        "потеря сознания",
        (
            r"\bбез\s+сознани\w*\b",
            r"\bпотер\w*\s+сознани\w*\b",
            r"\bобморок\w*\b",
            r"\bне\s+реагиру\w*\b",
            r"\bне\s+приходит\s+в\s+себя\b",
            r"\bотключил\w*\b",
        ),
    ),
)

NEGATED_PATTERNS: dict[str, tuple[str, ...]] = {
    "судороги": (r"\bбез\s+судорог\w*\b", r"\bсудорог\w*\s+нет\b"),
    "тяжёлое дыхание": (r"\bдыш\w*\s+нормально\b", r"\bбез\s+(?:одышк\w*|проблем\s+с\s+дыхани\w*)\b"),
    "кровь или кровотечение": (r"\bбез\s+кров[ьи]\b", r"\bкров[ьи]\s+нет\b"),
    "подозрение на отравление": (r"\bне\s+отрав\w*\b", r"\bотравлени\w*\s+нет\b"),
    "потеря сознания": (r"\bв\s+сознани\w*\b", r"\bбез\s+потер[ьи]\s+сознани\w*\b"),
}


def detect_red_flags(text: str | None) -> RedFlagResult:
    normalized = " ".join(str(text or "").casefold().split())
    if not normalized:
        return RedFlagResult(matched=())

    matched: list[str] = []
    for label, patterns in RED_FLAG_PATTERNS:
        if any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in NEGATED_PATTERNS.get(label, ())):
            continue
        if any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in patterns):
            matched.append(label)
    return RedFlagResult(matched=tuple(dict.fromkeys(matched)))


def render_red_flag_response(result: RedFlagResult) -> str:
    symptoms = ", ".join(result.matched) if result.matched else "красные симптомы"
    return (
        "🟥 Срочно в клинику\n\n"
        f"По описанию есть красные симптомы: {symptoms}.\n\n"
        "В такой ситуации не ждите онлайн-разбора. Свяжитесь с ветеринарной клиникой и везите питомца "
        "на очный осмотр как можно скорее.\n\n"
        "Что сделать сейчас:\n"
        "• держите питомца спокойно, без активных нагрузок;\n"
        "• не давайте человеческие лекарства и не начинайте лечение самостоятельно;\n"
        "• если есть подозрение на отравление, возьмите с собой упаковку или название вещества;\n"
        "• если есть кровь, судороги, потеря сознания или тяжёлое дыхание, сообщите об этом клинике сразу.\n\n"
        "Этот ответ не заменяет очный осмотр ветеринарного врача."
    )
