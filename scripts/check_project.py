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
    "docs/DB_SCHEMA.md",
    "scripts/max_poll.py",
    "scripts/setup_max_webhook.py",
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
    forbidden_artifacts = (
        "<h2 id=\"legalModalTitle\">Документ</h2>",
        ">×</button>",
    )
    found_artifacts = [text for text in forbidden_artifacts if text in html]
    if found_artifacts:
        raise SystemExit("public HTML contains technical modal artifacts")
    for modal_id in ("authDialog", "legalModal"):
        if f'id="{modal_id}" hidden aria-hidden="true"' not in html:
            raise SystemExit(f"{modal_id} must be hidden from public accessibility tree by default")


def check_public_seo() -> None:
    html = (ROOT / "web/index.html").read_text(encoding="utf-8")
    required = {
        "public title": "<title>TemichevVet — оценка срочности симптомов у собак и кошек</title>",
        "meta description": 'name="description"',
        "canonical": '<link rel="canonical" href="https://temichevvet.ru/"',
        "og title": 'property="og:title"',
        "og image": 'property="og:image"',
        "webapplication json-ld": '"@type": "WebApplication"',
        "organization json-ld": '"@type": "Organization"',
        "person json-ld": '"@type": "Person"',
    }
    missing = [label for label, needle in required.items() if needle not in html]
    if missing:
        raise SystemExit(f"public SEO metadata missing: {', '.join(missing)}")


def main() -> None:
    missing = [path for path in REQUIRED_FILES if not (ROOT / path).exists()]
    if missing:
        raise SystemExit(f"missing required files: {', '.join(missing)}")

    check_public_dom_templates()
    check_public_seo()

    manifest = (ROOT / "web/manifest.webmanifest").read_text(encoding="utf-8")
    if "TemichevVet" not in manifest:
        raise SystemExit("manifest does not contain app name")

    js = (ROOT / "web/app.js").read_text(encoding="utf-8")
    if 'localStorage.setItem("tvv_token"' in js or "localStorage.setItem('tvv_token'" in js:
        raise SystemExit("user auth token must not be written to localStorage")
    if "tvv_admin_token" in js:
        raise SystemExit("admin auth token must not be stored or read from localStorage")
    for key in ("tvv_telegram_login_state", "tvv_telegram_login_url", "tvv_max_login_state", "tvv_max_login_url"):
        if f'localStorage.setItem("{key}"' in js or f"localStorage.setItem('{key}'" in js:
            raise SystemExit(f"messenger login challenge must not be written to localStorage: {key}")

    for endpoint in (
        "/api/auth/email/start",
        "/api/auth/email/verify",
        "/api/auth/${provider}/start",
        "/api/auth/max/status",
        "/api/auth/max/init",
    ):
        if endpoint not in js:
            raise SystemExit(f"frontend does not reference {endpoint}")

    backend = (ROOT / "app/main.py").read_text(encoding="utf-8")
    for legal_path in (
        "/privacy",
        "/consent",
        "/terms",
        "/offer",
        "/medical-disclaimer",
        "/cookies",
        "/contacts",
    ):
        if f'@app.get("{legal_path}"' not in backend:
            raise SystemExit(f"backend does not expose standalone legal route {legal_path}")

    sw = (ROOT / "web/sw.js").read_text(encoding="utf-8")
    for private_path in ('"/api/"', '"/admin"', '"/app"', '"/review-login"'):
        if private_path not in sw:
            raise SystemExit(f"service worker private cache guard misses {private_path}")

    print("pwa project check ok")


if __name__ == "__main__":
    main()
