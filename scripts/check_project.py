from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


REQUIRED_FILES = (
    "README.md",
    ".env.example",
    "requirements.txt",
    "app/main.py",
    "app/db.py",
    "web/index.html",
    "web/styles.css",
    "web/app.js",
    "web/manifest.webmanifest",
    "web/sw.js",
    "web/assets/icon.svg",
    "scripts/max_poll.py",
)


class PublicDomGuard(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.template_depth = 0
        self.template_ids: set[str] = set()
        self.private_ids_outside_template: list[str] = []
        self.private_ids_anywhere: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        element_id = attr_map.get("id")
        if tag == "template":
            self.template_depth += 1
            if element_id:
                self.template_ids.add(element_id)
            return
        if element_id in {"dashboardView", "adminView", "logoutBtn", "workspace"}:
            self.private_ids_anywhere.append(element_id)
        if self.template_depth == 0 and element_id in {"dashboardView", "adminView"}:
            self.private_ids_outside_template.append(element_id)

    def handle_endtag(self, tag: str) -> None:
        if tag == "template" and self.template_depth > 0:
            self.template_depth -= 1


def check_public_dom_templates() -> None:
    html = (ROOT / "web/index.html").read_text(encoding="utf-8")
    parser = PublicDomGuard()
    parser.feed(html)

    forbidden_templates = {"dashboardTemplate", "adminTemplate"}
    forbidden_template_ids = sorted(forbidden_templates & parser.template_ids)
    if forbidden_template_ids:
        raise SystemExit(f"private templates must not be present in public HTML: {', '.join(forbidden_template_ids)}")
    if parser.private_ids_anywhere:
        ids = ", ".join(sorted(set(parser.private_ids_anywhere)))
        raise SystemExit(f"private view ids must not be present in public HTML: {ids}")

    forbidden_public_text = (
        "Личный кабинет",
        "Выберите действие",
        "Выйти",
        "Мои питомцы",
        "Напоминания",
        "История здоровья",
    )
    found_text = [text for text in forbidden_public_text if text in html]
    if found_text:
        raise SystemExit(f"private app text must not be present in public HTML: {', '.join(found_text)}")


def main() -> None:
    missing = [path for path in REQUIRED_FILES if not (ROOT / path).exists()]
    if missing:
        raise SystemExit(f"missing required files: {', '.join(missing)}")

    check_public_dom_templates()

    manifest = (ROOT / "web/manifest.webmanifest").read_text(encoding="utf-8")
    if "TemichevVet" not in manifest:
        raise SystemExit("manifest does not contain app name")

    js = (ROOT / "web/app.js").read_text(encoding="utf-8")
    for endpoint in (
        "/api/auth/email/start",
        "/api/auth/email/verify",
        "/api/auth/${provider}/start",
        "/api/auth/max/status",
    ):
        if endpoint not in js:
            raise SystemExit(f"frontend does not reference {endpoint}")

    print("pwa project check ok")


if __name__ == "__main__":
    main()
