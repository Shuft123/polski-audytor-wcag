import pytest

from audytor.crawler.links import classify_links, is_internal, normalize_url

PAGE = "https://www.przyklad.pl/aktualnosci/"


@pytest.mark.parametrize(
    "href, expected",
    [
        ("/kontakt", "https://www.przyklad.pl/kontakt"),
        ("galeria", "https://www.przyklad.pl/aktualnosci/galeria"),
        ("../o-nas#zespol", "https://www.przyklad.pl/o-nas"),
        ("HTTPS://WWW.Przyklad.PL:443/A?x=1#y", "https://www.przyklad.pl/A?x=1"),
        ("http://przyklad.pl:80", "http://przyklad.pl/"),
        ("https://przyklad.pl:8443/x", "https://przyklad.pl:8443/x"),
        ("  /spacje  ", "https://www.przyklad.pl/spacje"),
    ],
)
def test_normalize_url_resolves_and_cleans(href, expected):
    assert normalize_url(href, base=PAGE) == expected


@pytest.mark.parametrize(
    "href",
    ["mailto:urzad@przyklad.pl", "tel:+48123456789", "javascript:void(0)", "data:text/html,x",
     "ftp://przyklad.pl/plik", "", "   ", None, "http://[nieprawidlowy"],
)
def test_normalize_url_rejects_non_web(href):
    assert normalize_url(href, base=PAGE) is None


def test_is_internal_ignores_www_but_not_subdomains():
    assert is_internal("https://przyklad.pl/a", PAGE)
    assert is_internal("http://www.przyklad.pl/b", PAGE)
    assert not is_internal("https://bip.przyklad.pl/", PAGE)
    assert not is_internal("https://przyklad.com/", PAGE)


def test_classify_links_splits_dedups_and_keeps_order():
    hrefs = [
        "/kontakt",
        "https://www.przyklad.pl/kontakt#mapa",   # duplikat po usunięciu fragmentu
        PAGE,                                     # link do samej siebie
        "/pliki/deklaracja.PDF",
        "/img/logo.png",                          # obrazek – pomijany
        "https://facebook.com/przyklad",
        "https://facebook.com/przyklad",          # zewnętrzny duplikat
        "https://bip.przyklad.pl/",               # poddomena = zewnętrzny
        "mailto:urzad@przyklad.pl",
        "/o-nas",
    ]
    result = classify_links(hrefs, PAGE)
    assert result.pages == ["https://www.przyklad.pl/kontakt", "https://www.przyklad.pl/o-nas"]
    assert result.documents == ["https://www.przyklad.pl/pliki/deklaracja.PDF"]
    assert result.external_count == 2


def test_classify_links_empty():
    result = classify_links([], PAGE)
    assert result.pages == [] and result.documents == [] and result.external_count == 0
