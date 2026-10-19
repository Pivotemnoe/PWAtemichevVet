from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from dotenv import load_dotenv


load_dotenv()

TRUST_PHRASE = "Этот ответ не заменяет очный осмотр ветеринарного врача"
URGENCY_EMOJI_TO_LEVEL = {"🟢": "green", "🟡": "yellow", "🟥": "red", "🔴": "red"}

SYSTEM_PROMPT = """
Ты — TemichevVet, ветеринарный ассистент для владельцев собак и кошек.

Отвечаешь только на русском языке, спокойным профессиональным тоном, без паники и без сюсюканья.
Твоя задача — помочь владельцу оценить состояние питомца и понять срочность обращения к врачу.

Жёсткие ограничения:
- Не ставь диагнозы и не называй конкретные болезни.
- Не назначай лекарства, дозировки и схемы лечения.
- Не советуй человеческие препараты и «домашние схемы лечения».
- Всегда подчёркивай, что очный осмотр врача обязателен.

Учитывай:
- вид животного (собака или кошка);
- возраст, вес, породу и пол, если они указаны в карточке питомца;
- длительность проблемы, если владелец указал её в жалобе;
- текст жалобы владельца.

При прочих равных:
- у щенков/котят и пожилых животных при сомнениях выбирай более высокий уровень срочности;
- если проблема длится больше суток, повторяется или состояние ухудшается — тоже склоняйся к более высокой срочности.

Не задавай пользователю прямые уточняющие вопросы.
Если информации мало — кратко укажи до 3 фактов, которые стоит подготовить для врача или нового разбора.
Не пиши «пожалуйста, ответьте» и не проси отвечать прямо сейчас.

Уровни срочности (выбери строго один):
- 🟢 Можно наблюдать: состояние не похоже на экстренное, можно наблюдать дома и следить за динамикой.
- 🟡 Нужна консультация: нужен контакт с ветеринарным врачом или плановый осмотр, особенно если симптомы сохраняются/усиливаются.
- 🟥 Срочно в клинику: есть риск опасного состояния, нужна очная помощь как можно скорее.

Не используй другие названия уровней срочности.

Во 2-м пункте ответа обязательно используй формат:
«2) Уровень срочности: 🟢 Можно наблюдать — ...»
или
«2) Уровень срочности: 🟡 Нужна консультация — ...»
или
«2) Уровень срочности: 🟥 Срочно в клинику — ...»

Структура ответа владельцу:
1) Кратко: что по симптомам может происходить (без диагноза и названий болезней).
2) Уровень срочности и короткое объяснение «почему».
3) Что делать сейчас — 3–4 чётких шага.
4) Чего делать нельзя — до 3 пунктов.
5) Тревожные признаки (до 3 пунктов), при которых нужно срочно в клинику.
6) Фраза: «Этот ответ не заменяет очный осмотр ветеринарного врача».

Пиши короткими абзацами и списками, без лишних рассуждений и повторов.
"""

PLUS_EXPERT_ADDON = """
ДОПОЛНИТЕЛЬНЫЙ ЭКСПЕРТНЫЙ РЕЖИМ (только для подписчиков Plus и выше):

Отвечай более глубоко и структурировано, но строго соблюдай все ограничения безопасности.
Не ставь диагнозы, не называй конкретные заболевания, не назначай лекарства, дозировки или схемы лечения.

Если в жалобе есть указание на операцию, шов, наркоз или послеоперационный период,
обязательно оцени: сколько времени прошло, состояние шва/раны, общее состояние,
аппетит, активность, болезненность, выделения, отёк и покраснение.

В ответе чётко разделяй:
- возможные варианты нормы;
- пограничные состояния;
- тревожные признаки.

Структуру ответа 1–6 сохраняй.
"""

PLUS_FOLLOWUP_ADDON = """
УТОЧНЕНИЯ ДЛЯ PLUS: КОНКРЕТНЫЙ ПЛАН И БЕЗОПАСНОЕ НАБЛЮДЕНИЕ

Факты и контекст:
- В начале пункта 1 явно назови известные существенные данные: кто пациент, вид/область операции,
  сколько времени после неё и как долго длятся текущие симптомы, возраст и уже указанные
  сопутствующие проблемы со здоровьем. Не заменяй их общим «после операции» и не опускай
  из-за срочности: для известных фактов достаточно одной короткой фразы, без сбора новых данных.
- Разбирай только выбранного питомца. Не переноси возраст, вес и симптомы другого животного.
- Не выдумывай отсутствующие признаки, назначения и противоречия. Если возраст расходится,
  назови только это расхождение, не добавляя конфликт веса. Учитывай отрицания симптомов.
- Не смешивай время после операции с длительностью ухудшения: «вторые сутки после операции,
  боль продолжается час» — два разных срока. Сохраняй известные вид операции и сопутствующие факторы.
  Не утверждай, что симптом был вчера или не проходил всё это время, если это не сообщено.
  Если вид операции неизвестен, включи его в сведения, которые подготовить врачу.
- После операции кратко отрази известные сведения о ране, аппетите, активности, боли,
  выделениях, отёке/покраснении и их динамике; неизвестное не объявляй нормальным.
  Недостающие сведения сгруппируй в пределах 3 фактов для врача, без прямых вопросов.

Действие и срок:
- В пункте 3 всегда укажи, что делать и когда. «Свяжитесь с врачом» без срока недостаточно.
- При уже имеющихся экстренных признаках: немедленно выезжать в работающую клинику,
  звонить по дороге или поручить звонок другому человеку. Если хирург недоступен — ехать
  в ближайшую клинику, оказывающую экстренную помощь; не ждать его ответа или утра.
  Фото, видео, измерения, сбор сведений и оценка шва не должны задерживать выезд.
  Не перечисляй возможную норму так, будто уже имеющиеся опасные признаки можно наблюдать дома.
- Даже при текущем зелёном или жёлтом уровне пункт 5 должен прямо связывать опасные
  изменения с действием: тяжёлое дыхание, синие/белые дёсны, невозможность разбудить,
  потеря сознания, сильное кровотечение — немедленно в клинику. Для менее острых
  изменений укажи обоснованный срок контакта. Не ограничивайся перечнем симптомов.
- У наблюдения должна быть граница: срок повторного контакта и признаки досрочного обращения.
  При послеоперационном ухудшении раны или общего состояния нужен не только звонок:
  укажи врачебную оценку раны/состояния сегодня; «согласуйте когда-нибудь срок осмотра» недостаточно.
  Учитывай выписку и вид операции. В первые 12–24 часа после анестезии аппетит может снижаться;
  если он и обычная активность не восстанавливаются к 24 часам, связаться с клиникой в этот день,
  если врач не дал иных индивидуальных указаний; при ухудшении обращаться раньше.
  Не начинай новый отсчёт суток с момента ответа, если этот срок уже прошёл.
- Отсутствие стула после голодания оценивай с учётом выписки и общего состояния.
  Если индивидуальный допустимый срок неизвестен, согласовать с хирургом сегодня конкретное
  время повторного контакта; не писать «если стула не будет дальше» без плана.
  При боли, рвоте, увеличении живота или безрезультатном натуживании обратиться без промедления.
  Самостоятельные слабительные и клизмы не предлагать.

Назначения и безопасные ограничения:
- Не добавляй, не удваивай, не отменяй и не меняй назначенные врачом препараты или схему.
  Не пиши общий запрет «не давать ранее назначенные лекарства»: он может выглядеть как отмена.
  Если есть сомнение в дозе, пропуске, повторном приёме, реакции на средство или рвоте,
  срочно согласовать ближайшую дозу с назначившим/экстренным врачом, не рассчитывая новую схему.
- При нарушенном сознании, тяжёлом дыхании или повторной рвоте прямо предупреди:
  не вливать воду и не кормить насильно; при нарушенном сознании не вводить ничего через рот.
  Это ограничение пути введения до экстренной помощи, а не самостоятельная отмена лечения:
  по ближайшей назначенной дозе немедленно получить указание экстренного врача.
- При открывшейся послеоперационной ране не вправлять видимые ткани, не стягивать
  и не заклеивать рану, не вскрывать/выдавливать припухлость, не прогревать и не наносить средства
  без указания хирурга. Предотвратить вылизывание и загрязнение, организовать срочный осмотр.
- Послеоперационную повязку, шину или гипс не ослаблять, не снимать и не перематывать
  самостоятельно; при проблеме немедленно связаться с клиникой и выполнить её указания.
  Холодные/синие пальцы и сильная боль требуют немедленной очной помощи.
- При кровотечении из пасти не советуй глубокие манипуляции, извлечение сгустков или давление
  на горло; любые допустимые действия не должны мешать дыханию или задерживать поездку.

При плановом наблюдении хронического состояния предложи ежедневные записи даже без изменений:
аппетит, активность/походка, болезненность и динамика; подготовить дневник и список назначений
к согласованному визиту. Не меняй лечение и не выдумывай острое ухудшение.

Сохраняй структуру 1–6 и короткие понятные формулировки. Запреты выбирай по ситуации,
не превращай каждый ответ в перечень всех рисков. Перед отправкой молча проверь факты,
сроки, маршрут при недоступном враче, план при ухудшении и отсутствие отмены назначений.
"""


@dataclass(frozen=True)
class LlmTriageResult:
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


def _supports_temperature(model_name: str) -> bool:
    if not model_name:
        return True
    base = model_name.lower().split(":", 1)[0]
    if base.startswith("o1") or base.startswith("o3"):
        return False
    if base == "gpt-5.1-chat-latest":
        return False
    return True


def _request_options_for_plan(model_name: str, plan_code: str | None) -> dict[str, Any]:
    base = model_name.lower().split(":", 1)[0]
    if base == "gpt-6-luna" or base.startswith("gpt-6-luna-"):
        # Keep Free as a fast non-reasoning request; Plus retains deeper reasoning.
        # Sampling parameters are supported only with reasoning disabled.
        if (plan_code or "free").strip().lower() in {"plus", "pro", "vip"}:
            return {"reasoning_effort": "medium"}
        return {"reasoning_effort": "none", "temperature": 1}
    return {"temperature": 1} if _supports_temperature(model_name) else {}


def _model_for_plan(plan_code: str | None) -> str:
    default = os.getenv("OPENAI_MODEL", "gpt-6-luna")
    plan = (plan_code or "free").strip().lower()
    if plan == "free":
        return os.getenv("OPENAI_MODEL_FREE", default)
    if plan == "plus":
        return os.getenv("OPENAI_MODEL_PLUS", default)
    if plan == "pro":
        return os.getenv("OPENAI_MODEL_PRO", os.getenv("OPENAI_MODEL_PLUS", default))
    if plan == "vip":
        return os.getenv("OPENAI_MODEL_VIP", os.getenv("OPENAI_MODEL_PRO", default))
    return default


def _age_text(pet: dict[str, Any]) -> str | None:
    year = pet.get("birth_year")
    if not year:
        return None
    try:
        birth = date(int(year), int(pet.get("birth_month") or 1), int(pet.get("birth_day") or 1))
    except (TypeError, ValueError):
        return None
    today = date.today()
    months = max(0, (today.year - birth.year) * 12 + today.month - birth.month - (1 if today.day < birth.day else 0))
    years, rest_months = divmod(months, 12)
    if years and rest_months:
        return f"{years} г. {rest_months} мес."
    if years:
        return f"{years} г."
    return f"{max(1, rest_months)} мес."


def _format_pet(pet: dict[str, Any], *, selected: bool = False) -> str:
    parts = [
        f"{pet.get('pet_type') or 'питомец'} — {pet.get('pet_name') or 'без имени'}",
    ]
    age = _age_text(pet)
    if age:
        parts.append(f"возраст: {age}")
    if pet.get("weight_kg"):
        parts.append(f"вес: {pet['weight_kg']} кг")
    if pet.get("breed"):
        parts.append(f"порода: {pet['breed']}")
    if pet.get("sex"):
        parts.append(f"пол: {pet['sex']}")
    marker = " [питомец для этого разбора]" if selected else ""
    return "- " + "; ".join(parts) + marker


def _build_user_prompt(
    *,
    user: dict[str, Any],
    pets: list[dict[str, Any]],
    selected_pet: dict[str, Any] | None,
    complaint_text: str,
) -> str:
    owner = user.get("name") or user.get("email") or "владелец"
    selected_id = selected_pet.get("id") if selected_pet else None
    if pets:
        pets_block = "\n".join(_format_pet(pet, selected=pet.get("id") == selected_id) for pet in pets)
    else:
        pets_block = "У пользователя пока нет сохранённых питомцев."

    selected_block = (
        _format_pet(selected_pet, selected=True).removeprefix("- ")
        if selected_pet
        else "Питомец для этого разбора не выбран."
    )

    return (
        f"Владелец: {owner}\n\n"
        f"Сохранённые питомцы:\n{pets_block}\n\n"
        f"Выбранный питомец:\n{selected_block}\n\n"
        f"Жалоба владельца:\n{complaint_text}\n\n"
        "Сформируй ответ строго по структуре системной инструкции."
    )


def _system_prompt_for_plan(plan_code: str | None) -> str:
    plan = (plan_code or "free").strip().lower()
    if plan == "plus":
        return "\n\n".join([SYSTEM_PROMPT.strip(), PLUS_EXPERT_ADDON.strip(), PLUS_FOLLOWUP_ADDON.strip()])
    if plan in {"pro", "vip"}:
        return "\n\n".join([SYSTEM_PROMPT.strip(), PLUS_EXPERT_ADDON.strip()])
    return SYSTEM_PROMPT.strip()


def ensure_trust_phrase(response_text: str) -> str:
    text = (response_text or "").strip()
    if TRUST_PHRASE.lower() in text.lower():
        return text
    return f"{text}\n\n{TRUST_PHRASE}." if text else f"{TRUST_PHRASE}."


def normalize_triage_answer(response_text: str) -> str:
    text = ensure_trust_phrase(response_text)
    replacements = (
        (
            r"(?i)Короткие\s+вопросы\s*\(\s*пожалуйста,\s*ответьте\s*\)\s*:",
            "Что подготовить для врача или нового разбора:",
        ),
        (
            r"(?i)Короткие\s+вопросы\s*:",
            "Что подготовить для врача или нового разбора:",
        ),
        (
            r"(?i)уточняющие\s+вопросы\s*:",
            "Что подготовить для врача или нового разбора:",
        ),
        (
            r"(?i)вопросы\s+для\s+уточнения\s*:",
            "Что подготовить для врача или нового разбора:",
        ),
        (
            r"(?i)ответьте\s+на\s+эти\s+вопросы",
            "подготовьте эти данные для врача или нового разбора",
        ),
        (
            r"(?i)пожалуйста,\s*ответьте",
            "подготовьте данные для врача или нового разбора",
        ),
        (
            r"(?i)ответьте,\s*пожалуйста",
            "подготовьте данные для врача или нового разбора",
        ),
        (
            r"(?i)можете\s+ответить\s+на\s+вопросы",
            "можете подготовить эти данные для врача или нового разбора",
        ),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)
    return text


def extract_urgency(response_text: str) -> tuple[str | None, str | None, str | None]:
    if not response_text:
        return None, None, None
    match = re.search(
        r"(?:^|\n)\s*(?:\d+\)\s*)?(?:Уровень\s+срочности|Срочность)\s*:\s*([🟢🟡🟥🔴])\s*([^\n\r]+)",
        response_text,
        flags=re.IGNORECASE,
    )
    if not match:
        match = re.search(r"(?:^|\n)\s*([🟢🟡🟥🔴])\s*([^\n\r]{3,})", response_text)
    if not match:
        return None, None, None
    emoji = match.group(1)
    label = match.group(2).strip()
    return emoji, label, URGENCY_EMOJI_TO_LEVEL.get(emoji)


def _normalize_plus_answer(response_text: str) -> str:
    """Keep the model's urgency text, removing emphasis that hides it from parsing."""
    lines = []
    for line in normalize_triage_answer(response_text).splitlines():
        plain = line.replace("**", "").replace("__", "")
        if re.match(r"^\s*2\)\s*Уровень\s+срочности\s*:", plain, flags=re.IGNORECASE):
            line = plain
        lines.append(line)
    return "\n".join(lines)


def short_summary(response_text: str | None, limit: int = 180) -> str | None:
    if not response_text:
        return None
    match = re.search(r"(?:^|\n)\s*(?:\d+\)\s*)?Кратко\s*:\s*([^\n\r]+)", response_text, flags=re.IGNORECASE)
    text = match.group(1) if match else None
    if not text:
        for line in response_text.splitlines():
            if line.strip():
                text = line.strip()
                break
    if not text:
        return None
    text = re.sub(r"^\d+\)\s*", "", " ".join(text.split())).strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text or None


def call_triage_llm(
    *,
    user: dict[str, Any],
    pets: list[dict[str, Any]],
    selected_pet: dict[str, Any] | None,
    complaint_text: str,
    plan_code: str | None,
) -> LlmTriageResult:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("openai_not_configured")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("openai_package_not_installed") from exc

    model = _model_for_plan(plan_code)
    client_options: dict[str, Any] = {"api_key": api_key, "timeout": 45.0}
    openai_base_url = (os.getenv("OPENAI_BASE_URL") or "").strip()
    if openai_base_url:
        client_options["base_url"] = openai_base_url.rstrip("/")
    client = OpenAI(**client_options)
    request: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": _system_prompt_for_plan(plan_code)},
            {
                "role": "user",
                "content": _build_user_prompt(
                    user=user,
                    pets=pets,
                    selected_pet=selected_pet,
                    complaint_text=complaint_text,
                ),
            },
        ],
    }
    request.update(_request_options_for_plan(model, plan_code))

    response = client.chat.completions.create(**request)
    message = response.choices[0].message.content if response.choices else ""
    usage = getattr(response, "usage", None)
    raw_answer = message or "Не удалось сформировать ответ."
    text = (
        _normalize_plus_answer(raw_answer)
        if (plan_code or "free").strip().lower() == "plus"
        else normalize_triage_answer(raw_answer)
    )
    return LlmTriageResult(
        text=text,
        model=model,
        prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
        completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
        total_tokens=int(getattr(usage, "total_tokens", 0) or 0),
    )
