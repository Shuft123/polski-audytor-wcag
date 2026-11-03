"""Wykrywanie i zamykanie banerów zgody na cookies.

Zasada: baner zamykamy przyciskiem ODRZUCENIA albo "tylko niezbędne" (nigdy "akceptuj
wszystkie"), a przed zamknięciem zapisujemy zrzut okna z banerem – sam baner też podlega
audytowi dostępności. Gdy nie da się go zamknąć, migawka powstaje z banerem i z ostrzeżeniem.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Frame, Page

# Teksty przycisków (po normalizacji: małe litery, pojedyncze spacje, bez kropki na końcu).
# Kolejność ma znaczenie: najpierw "odrzuć", potem "tylko niezbędne".
REJECT_PATTERNS: list[str] = [
    r"^odrzu(ć|c)( wszystk(ie|o))?( (pliki )?(cookies?|ciasteczka))?$",
    r"^odrzucam( wszystk(ie|o)| niewymagane| opcjonalne| dodatkowe)?$",
    r"^odrzu(ć|c) (niewymagane|opcjonalne|dodatkowe|pozostałe)( (pliki )?(cookies?|ciasteczka))?$",
    r"^nie (zgadzam się|akceptuję|wyrażam zgody)$",
    r"^odm(ów|awiam)( zgody)?$",
    r"^(reject|decline|deny|refuse)( all)?( cookies)?$",
    r"^(tylko|wyłącznie) (niezbędne|wymagane|konieczne|podstawowe)( (pliki )?(cookies?|ciasteczka))?$",
    r"^(akceptuj(ę)?|zezwól na|zgoda na|zgadzam się na|użyj|używaj) (tylko |wyłącznie )?"
    r"(niezbędne|wymagane|konieczne)( (pliki )?(cookies?|ciasteczka))?$",
    r"^(only |use )?(necessary|essential)( cookies)?( only)?$",
    r"^(accept|allow) (only )?(necessary|essential)( cookies)?( only)?$",
]

# Przyciski "odrzuć" popularnych systemów zgód (CMP).
KNOWN_REJECT_SELECTORS: list[str] = [
    "#onetrust-reject-all-handler",                 # OneTrust
    "#CybotCookiebotDialogBodyButtonDecline",       # Cookiebot
    "#didomi-notice-disagree-button",               # Didomi
    ".cky-btn-reject",                              # CookieYes
    ".cmplz-btn.cmplz-deny",                        # Complianz
    ".iubenda-cs-reject-btn",                       # iubenda
    ".cm-btn-decline",                              # Klaro
    ".cc-deny",                                     # Osano / cookieconsent
    "#cookiescript_reject",                         # CookieScript
    "button[data-testid='uc-deny-all-button']",     # Usercentrics
    ".fc-cta-do-not-consent",                       # Google Funding Choices
]

# Słowa, po których rozpoznajemy, że przycisk należy do banera zgody (szukane w przodkach).
CONTEXT_KEYWORDS = ["cookie", "ciastecz", "prywatnoś", "zgod", "privacy", "consent", "rodo"]
# Słowa, po których rozpoznajemy sam baner (element fixed/sticky/dialog).
BANNER_KEYWORDS = ["cookie", "ciastecz"]

MARKER_ATTR = "data-audytor-cookie"

_COMPILED = [re.compile(p, re.IGNORECASE) for p in REJECT_PATTERNS]


def normalize_label(text: str | None) -> str:
    """Tak samo jak w JS: małe litery, pojedyncze spacje, bez kropek/wykrzykników na końcu."""
    text = re.sub(r"\s+", " ", (text or "").lower()).strip()
    return re.sub(r"[.!…:]+$", "", text).strip()


def is_reject_label(text: str | None) -> bool:
    """Czy napis przycisku oznacza odrzucenie / tylko niezbędne cookies."""
    label = normalize_label(text)
    return bool(label) and len(label) <= 60 and any(p.search(label) for p in _COMPILED)


_FIND_BUTTON_JS = """
({patterns, selectors, keywords, marker}) => {
  const norm = s => (s || '').toLowerCase().replace(/\\s+/g, ' ').trim().replace(/[.!…:]+$/, '').trim();
  const visible = el => {
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return false;
    const st = getComputedStyle(el);
    return st.visibility !== 'hidden' && st.display !== 'none' && parseFloat(st.opacity || '1') > 0.05;
  };
  const inConsentContext = el => {
    let n = el;
    for (let i = 0; i < 10 && n; i++, n = n.parentElement) {
      const t = (n.innerText || '').toLowerCase();
      if (t.length < 6000 && keywords.some(k => t.includes(k))) return true;
    }
    return false;
  };
  const mark = (el, how, text) => { el.setAttribute(marker, '1'); return {how, text}; };

  for (const sel of selectors) {
    for (const el of document.querySelectorAll(sel)) {
      if (visible(el)) return mark(el, 'selector', norm(el.innerText || el.value) || sel);
    }
  }
  const candidates = Array.from(document.querySelectorAll(
    'button, a, [role="button"], input[type="button"], input[type="submit"]'));
  for (const p of patterns) {
    const re = new RegExp(p, 'i');
    for (const el of candidates) {
      const t = norm(el.innerText || el.value || el.getAttribute('aria-label'));
      if (!t || t.length > 60 || !re.test(t)) continue;
      if (visible(el) && inConsentContext(el)) return mark(el, 'text', t);
    }
  }
  return null;
}
"""

_DETECT_BANNER_JS = """
(keywords) => {
  for (const el of document.querySelectorAll('body *')) {
    const st = getComputedStyle(el);
    const overlay = st.position === 'fixed' || st.position === 'sticky'
      || el.getAttribute('role') === 'dialog' || el.getAttribute('role') === 'alertdialog'
      || el.tagName === 'DIALOG';
    if (!overlay || st.display === 'none' || st.visibility === 'hidden') continue;
    const r = el.getBoundingClientRect();
    if (r.width * r.height < 20000) continue;          // pomijamy małe ikonki "ustawienia cookies"
    const t = (el.innerText || '').toLowerCase();
    if (t.length < 6000 && keywords.some(k => t.includes(k))) return true;
  }
  return false;
}
"""


@dataclass
class CookieBannerResult:
    detected: bool = False
    dismissed: bool = False
    method: str | None = None          # "selector" | "text"
    button_text: str | None = None
    frame_url: str | None = None       # gdy baner był w iframe
    screenshot: bytes | None = None    # widok okna z banerem, przed zamknięciem
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "checked": True,
            "detected": self.detected,
            "dismissed": self.dismissed,
            "method": self.method,
            "button_text": self.button_text,
            "frame_url": self.frame_url,
        }


def _frames(page: Page) -> list[Frame]:
    main = page.main_frame
    return [main] + [f for f in page.frames if f is not main]


def _safe_eval(frame: Frame, script: str, arg) -> object:
    try:
        return frame.evaluate(script, arg)
    except PlaywrightError:
        return None  # ramka zniknęła / cross-origin bez dostępu itd.


def banner_visible(page: Page) -> bool:
    return any(_safe_eval(f, _DETECT_BANNER_JS, BANNER_KEYWORDS) for f in _frames(page))


def _find_reject_button(page: Page, args: dict) -> tuple[Frame | None, dict | None]:
    for frame in _frames(page):
        hit = _safe_eval(frame, _FIND_BUTTON_JS, args)
        if hit:
            return frame, hit
    return None, None


def handle_cookie_banner(
    page: Page,
    screenshot_kwargs: dict,
    wait_for_banner_ms: int = 2000,
    poll_ms: int = 500,
    wait_after_ms: int = 800,
) -> CookieBannerResult:
    """Wykrywa baner zgody, robi zrzut okna z banerem i zamyka go przyciskiem odrzucenia.

    Część banerów pojawia się z opóźnieniem (np. x-kom ok. 2 s), dlatego przez
    `wait_for_banner_ms` ponawiamy wyszukiwanie co `poll_ms`.
    """
    result = CookieBannerResult()
    args = {
        "patterns": REJECT_PATTERNS,
        "selectors": KNOWN_REJECT_SELECTORS,
        "keywords": CONTEXT_KEYWORDS,
        "marker": MARKER_ATTR,
    }

    deadline = time.monotonic() + wait_for_banner_ms / 1000
    while True:
        found_frame, found = _find_reject_button(page, args)
        visible = bool(found) or banner_visible(page)
        if visible or time.monotonic() >= deadline:
            break
        page.wait_for_timeout(poll_ms)

    result.detected = visible
    if not result.detected:
        return result

    try:
        result.screenshot = page.screenshot(full_page=False, **screenshot_kwargs)
    except PlaywrightError as exc:
        result.warnings.append(f"Nie udało się zapisać zrzutu banera cookies: {exc.message.splitlines()[0]}")

    if not found or found_frame is None:
        result.warnings.append(
            "Wykryto baner cookies, ale nie znaleziono przycisku odrzucenia – migawka zawiera baner"
        )
        return result

    result.method = found["how"]
    result.button_text = found["text"]
    if found_frame is not page.main_frame:
        result.frame_url = found_frame.url

    selector = f"[{MARKER_ATTR}='1']"
    try:
        found_frame.click(selector, timeout=5000)
    except PlaywrightError as exc:
        result.warnings.append(f"Nie udało się kliknąć „{result.button_text}”: {exc.message.splitlines()[0]}")
        _safe_eval(found_frame, f"() => document.querySelectorAll(\"{selector}\").forEach(e => e.removeAttribute('{MARKER_ATTR}'))", None)
        return result

    # Część banerów przeładowuje stronę po wyborze.
    try:
        page.wait_for_load_state("load", timeout=5000)
    except PlaywrightError:
        pass
    page.wait_for_timeout(wait_after_ms)
    # Znacznik nie może zostać w zapisanym DOM-ie.
    for frame in _frames(page):
        _safe_eval(frame, f"() => document.querySelectorAll(\"{selector}\").forEach(e => e.removeAttribute('{MARKER_ATTR}'))", None)

    if banner_visible(page):
        result.warnings.append(
            f"Kliknięto „{result.button_text}”, ale baner cookies nadal jest widoczny"
        )
    else:
        result.dismissed = True
    return result
