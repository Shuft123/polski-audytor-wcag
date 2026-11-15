import json
import ssl
import urllib.error
from pathlib import Path

import pytest

from audytor.crawler.robots import RobotsPolicy, parse_robots
from audytor.deklaracja import a11y_ids_in, find_candidates, find_declaration, find_in_html
from audytor.deklaracja.cli import main as cli_main
from audytor.deklaracja.wyszukiwanie import (
    METHOD_GUESS,
    METHOD_META,
    STATUS_NO_A11Y,
    STATUS_NONE,
    STATUS_UNVERIFIED,
    STATUS_VERIFIED,
    BlockedError,
    _PoliteFetcher,
    describe_error,
    main_reason,
    normalize_text,
)

SNAPSHOTS = Path(__file__).resolve().parents[1] / "data" / "snapshots"

# Oczekiwane adresy deklaracji na migawkach z tests/data/snapshots (sprawdzone ręcznie 15.11.2026).
EXPECTED = {
    "bialystok-pl": "https://www.bialystok.pl/cms/deklaracja",
    "gov-pl": "https://www.gov.pl/web/gov/deklaracja-dostepnosci-serwisu-govpl",
    "pb-edu-pl": "https://pb.edu.pl/dostepnosc-cyfrowa/deklaracja-dostepnosci/",
    "wasilkow-pl": "https://www.wasilkow.pl/pl/informator-mieszkanca/deklaracja-dostepnosci-wwwwasilkowpl.html",
    "x-kom-pl": "https://www.x-kom.pl/lp/deklaracja-dostepnosci",
}

DECLARATION_PAGE = """<html><body><main>
<h1 id="a11y-deklaracja">Deklaracja dostępności</h1>
<p id="a11y-wstep"><span id="a11y-podmiot">Gmina Test</span> zobowiązuje się zapewnić dostępność swojej
<span id="a11y-zakres">strony internetowej</span> <a id="a11y-url" href="https://gmina.pl">gmina.pl</a>.</p>
<time id="a11y-data-publikacja" datetime="2020-01-01">1 stycznia 2020 r.</time>
<p id="a11y-status">Strona internetowa jest częściowo zgodna z załącznikiem do ustawy…</p>
</main></body></html>"""


def _page(body: str, head: str = "") -> str:
    return f"<html><head>{head}</head><body>{body}</body></html>"


@pytest.mark.parametrize("folder, expected", sorted(EXPECTED.items()))
def test_snapshots(folder, expected):
    meta = json.loads((SNAPSHOTS / folder / "meta.json").read_text(encoding="utf-8"))
    html = (SNAPSHOTS / folder / meta["files"]["dom"]).read_text(encoding="utf-8")
    result = find_in_html(html, meta["final_url"])
    assert result.found
    assert result.declaration_url == expected
    assert result.confidence >= 0.8


def test_normalize_text():
    assert normalize_text("  DEKLARACJA   Dostępności ") == "deklaracja dostepnosci"
    assert normalize_text("Łatwy tekst") == "latwy tekst"


def test_adjective_dostepny_is_not_a_candidate():
    # pułapka z x-kom.pl: tytuły artykułów ze słowem „dostępny”
    html = _page('<a href="/news/1">Kiedy iPhone będzie dostępny?</a><a href="/news/2">Siri dostępna po polsku</a>')
    cands, _ = find_candidates(html, "https://sklep.pl/")
    assert cands == []


def test_tax_declaration_is_not_a_candidate():
    html = _page('<a href="/deklaracja-smieciowa">Deklaracja śmieciowa</a>'
                 '<a href="/podatki/deklaracja-in-1">Deklaracja IN-1</a>')
    cands, _ = find_candidates(html, "https://gmina.pl/")
    assert cands == []


def test_declaration_beats_architectural_accessibility():
    html = _page('<a href="/dostepnosc-architektoniczna">Dostępność architektoniczna</a>'
                 '<footer><a href="/strona/123">Deklaracja dostępności</a></footer>')
    cands, _ = find_candidates(html, "https://gmina.pl/")
    assert cands[0].url == "https://gmina.pl/strona/123"
    assert cands[0].in_footer


def test_footer_detected_by_class_and_role():
    html = _page('<div class="site-stopka"><a href="/dostepnosc">Dostępność</a></div>'
                 '<div role="contentinfo"><a href="/a11y">Dostępność cyfrowa</a></div>')
    cands, _ = find_candidates(html, "https://gmina.pl/")
    assert all(c.in_footer for c in cands)


def test_link_text_from_img_alt_and_aria_label():
    html = _page('<a href="/x"><img src="ikona.png" alt="Deklaracja dostępności"></a>'
                 '<a href="/y" aria-label="Deklaracja dostępności"><span class="icon"></span></a>')
    urls = [c.url for c in find_candidates(html, "https://gmina.pl/")[0]]
    assert urls == ["https://gmina.pl/x", "https://gmina.pl/y"]


def test_meta_tag_wins():
    html = _page('<a href="/dostepnosc">Dostępność</a>',
                 head='<meta name="deklaracja-dostępności" content="https://gmina.pl/dd">')
    result = find_in_html(html, "https://gmina.pl/")
    assert result.declaration_url == "https://gmina.pl/dd"
    assert result.method == METHOD_META


def test_external_bip_declaration_is_kept():
    html = _page('<footer><a href="https://bip.gmina.pl/deklaracja-dostepnosci">Deklaracja dostępności</a></footer>')
    cands, _ = find_candidates(html, "https://gmina.pl/")
    assert cands[0].url == "https://bip.gmina.pl/deklaracja-dostepnosci"
    assert not cands[0].internal


def test_duplicate_links_are_merged():
    html = _page('<a href="/dd">Deklaracja dostępności</a><footer><a href="/dd#top">Deklaracja dostępności</a></footer>')
    cands, _ = find_candidates(html, "https://gmina.pl/")
    assert len(cands) == 1
    assert cands[0].occurrences == 2
    assert cands[0].in_footer  # zostaje lepiej punktowane wystąpienie


def test_script_content_is_ignored():
    html = _page('<a href="/x"><script>var t="Deklaracja dostępności";</script>Aktualności</a>')
    assert find_candidates(html, "https://gmina.pl/")[0] == []


def test_a11y_ids_in():
    ids = a11y_ids_in(DECLARATION_PAGE + '<div id="a11y-nieznany"></div>')
    assert "a11y-wstep" in ids and "a11y-status" in ids
    assert "a11y-nieznany" not in ids


class FakeWeb:
    """Udaje sieć: słownik adres -> HTML; zapisuje, co pobrano."""

    def __init__(self, pages: dict[str, str]):
        self.pages = pages
        self.requested: list[str] = []

    def __call__(self, url):
        self.requested.append(url)
        if url in self.pages:
            return 200, url, self.pages[url]
        return 404, url, ""


def test_find_declaration_prefers_page_with_a11y_ids():
    home = _page('<a href="/dostepnosc">Dostępność</a>'
                 '<footer><a href="/info">Deklaracja dostępności</a></footer>')
    web = FakeWeb({
        "https://gmina.pl/": home,
        "https://gmina.pl/info": _page("<h1>Deklaracja dostępności</h1><p>w przygotowaniu</p>"),
        "https://gmina.pl/dostepnosc": DECLARATION_PAGE,
    })
    result = find_declaration("https://gmina.pl", fetch=web, respect_robots=False, delay=0)
    assert result.found and result.verified
    assert result.declaration_url == "https://gmina.pl/dostepnosc"
    assert "a11y-email" in result.missing_required_ids
    assert result.confidence == 0.95


def test_find_declaration_guesses_common_path_when_no_link():
    web = FakeWeb({
        "https://gmina.pl/": _page('<a href="/aktualnosci">Aktualności</a>'),
        "https://gmina.pl/deklaracja-dostepnosci": DECLARATION_PAGE,
    })
    result = find_declaration("https://gmina.pl/", fetch=web, respect_robots=False, delay=0)
    assert result.found
    assert result.method == METHOD_GUESS
    assert any("brak do niej linku" in w for w in result.warnings)


def test_find_declaration_not_found():
    web = FakeWeb({"https://gmina.pl/": _page('<a href="/aktualnosci">Aktualności</a>')})
    result = find_declaration("https://gmina.pl/", fetch=web, respect_robots=False, delay=0)
    assert not result.found
    assert result.declaration_url is None


def test_unverified_candidate_is_not_found_in_verify_mode():
    web = FakeWeb({"https://gmina.pl/": _page('<footer><a href="/dd">Deklaracja dostępności</a></footer>')})
    result = find_declaration("https://gmina.pl/", fetch=web, respect_robots=False, delay=0, guess_paths=False)
    assert not result.found               # link jest, ale strona zwraca 404
    assert result.declaration_url == "https://gmina.pl/dd"
    assert result.candidates[0].error == "HTTP 404"


def test_cli_on_snapshot_writes_csv(tmp_path, capsys):
    out_csv = tmp_path / "wyniki.csv"
    code = cli_main(["--snapshot", str(SNAPSHOTS / "pb-edu-pl"), "--csv", str(out_csv)])
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["declaration_url"] == EXPECTED["pb-edu-pl"]
    assert "pb.edu.pl/dostepnosc-cyfrowa/deklaracja-dostepnosci/" in out_csv.read_text(encoding="utf-8")


# --- sieć: błędy, przeglądarka zapasowa, robots.txt -----------------------------------

SHOP_HOME = _page('<footer><a href="/lp/deklaracja-dostepnosci">Deklaracja dostępności</a></footer>'
                  + "".join(f'<a href="/p{i}">Produkt {i}</a>' for i in range(10)))


def _ssl_error():
    return urllib.error.URLError(ssl.SSLCertVerificationError(
        1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate"))


def test_describe_error():
    assert "certyfikatu SSL" in describe_error(_ssl_error())
    assert "DNS" in describe_error("[Errno 11001] getaddrinfo failed")


def test_shop_page_without_a11y_is_found_as_no_a11y():
    web = FakeWeb({"https://sklep.pl/": SHOP_HOME,
                   "https://sklep.pl/lp/deklaracja-dostepnosci": _page("<h1>Dostępność usług</h1><p>PAD</p>")})
    result = find_declaration("https://sklep.pl/", fetch=web, respect_robots=False, delay=0, guess_paths=False)
    assert result.found and not result.verified
    assert result.status == STATUS_NO_A11Y
    assert result.declaration_url == "https://sklep.pl/lp/deklaracja-dostepnosci"
    assert any("PAD" in w for w in result.warnings)


def test_statuses_for_verified_and_snapshot_modes():
    web = FakeWeb({"https://gmina.pl/": SHOP_HOME, "https://gmina.pl/lp/deklaracja-dostepnosci": DECLARATION_PAGE})
    assert find_declaration("https://gmina.pl/", fetch=web, respect_robots=False, delay=0).status == STATUS_VERIFIED
    assert find_in_html(SHOP_HOME, "https://gmina.pl/").status == STATUS_UNVERIFIED
    assert find_in_html(_page(""), "https://gmina.pl/").status == STATUS_NONE


def test_ssl_error_falls_back_to_browser():
    def broken(url):
        raise _ssl_error()

    browser = FakeWeb({"https://gmina.pl/": SHOP_HOME, "https://gmina.pl/lp/deklaracja-dostepnosci": DECLARATION_PAGE})
    result = find_declaration("https://gmina.pl/", fetch=broken, browser=browser, respect_robots=False, delay=0)
    assert result.verified
    assert "https://gmina.pl/" in browser.requested
    assert any("przeglądarką" in w and "SSL" in w for w in result.warnings)


def test_ssl_error_without_browser_is_reported():
    def broken(url):
        raise _ssl_error()

    result = find_declaration("https://gmina.pl/", fetch=broken, respect_robots=False, delay=0)
    assert not result.found
    assert "certyfikatu SSL" in result.warnings[-1]


def test_bot_block_403_falls_back_to_browser():
    plain = FakeWeb({})  # zawsze 404 – podmieniamy na 403 poniżej

    def blocked(url):
        plain.requested.append(url)
        return 403, url, ""

    browser = FakeWeb({"https://sklep.pl/": SHOP_HOME, "https://sklep.pl/lp/deklaracja-dostepnosci": DECLARATION_PAGE})
    result = find_declaration("https://sklep.pl/", fetch=blocked, browser=browser, respect_robots=False, delay=0)
    assert result.verified
    assert any("HTTP 403" in w for w in result.warnings)


def test_few_links_triggers_browser_render():
    web = FakeWeb({"https://sklep.pl/": _page('<div id="app"></div>'),
                   "https://sklep.pl/lp/deklaracja-dostepnosci": DECLARATION_PAGE})
    browser = FakeWeb({"https://sklep.pl/": SHOP_HOME})
    result = find_declaration("https://sklep.pl/", fetch=web, browser=browser, respect_robots=False, delay=0)
    assert result.verified
    assert browser.requested == ["https://sklep.pl/"]


class FakeRobots:
    def __init__(self, policy):
        self.policy = policy

    def policy_for(self, url):
        return self.policy


def test_unreachable_robots_message_names_real_cause():
    policy = RobotsPolicy("https://gmina.pl/robots.txt", "unreachable",
                          error="[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
    polite = _PoliteFetcher(FakeWeb({}), FakeRobots(policy), delay=0)
    with pytest.raises(BlockedError, match="nieosiągalny.*certyfikatu SSL"):
        polite("https://gmina.pl/")


def test_disallowed_by_robots_message():
    policy = parse_robots("User-agent: *\nDisallow: /", "https://gmina.pl/robots.txt")
    polite = _PoliteFetcher(FakeWeb({}), FakeRobots(policy), delay=0)
    with pytest.raises(BlockedError, match="zabrania"):
        polite("https://gmina.pl/")


def test_footer_accessibility_page_of_shop_is_no_a11y():
    # rossmann.pl: „Dostępność usług” w stopce, strona bez a11y-*
    home = _page('<footer><a href="/pomoc/dostepnosc-uslug">Dostępność usług</a></footer>'
                 + "".join(f'<a href="/p{i}">Produkt {i}</a>' for i in range(10)))
    web = FakeWeb({"https://sklep.pl/": home, "https://sklep.pl/pomoc/dostepnosc-uslug": _page("<h1>Dostępność</h1>")})
    result = find_declaration("https://sklep.pl/", fetch=web, respect_robots=False, delay=0, guess_paths=False)
    assert result.status == STATUS_NO_A11Y


def test_weak_non_footer_link_is_not_no_a11y():
    home = _page('<a href="/dostepnosc">Dostępność</a>' + "".join(f'<a href="/p{i}">P{i}</a>' for i in range(10)))
    web = FakeWeb({"https://gmina.pl/": home, "https://gmina.pl/dostepnosc": _page("<h1>Dostępność</h1>")})
    result = find_declaration("https://gmina.pl/", fetch=web, respect_robots=False, delay=0, guess_paths=False)
    assert result.status == STATUS_NONE
    assert "odrzucony" in main_reason(result)


def test_main_reason_skips_browser_notes():
    def blocked(url):
        return 403, url, ""

    browser = FakeWeb({"https://sklep.pl/": SHOP_HOME.replace("Deklaracja dostępności", "Kontakt")
                       .replace("/lp/deklaracja-dostepnosci", "/kontakt")})
    result = find_declaration("https://sklep.pl/", fetch=blocked, browser=browser, respect_robots=False, delay=0)
    assert not result.found
    assert any("przeglądarką" in w for w in result.warnings)
    assert main_reason(result).startswith("Nie znaleziono linku")
