import pytest

from audytor.crawler.cookies import is_reject_label, normalize_label


@pytest.mark.parametrize(
    "label",
    [
        "Odrzuć",                      # gov.pl
        "Odrzuć wszystkie",
        "ODRZUĆ WSZYSTKIE.",
        "Odrzucam niewymagane",        # x-kom
        "Akceptuję wymagane",          # bialystok.pl
        "Tylko niezbędne",
        "Zezwól na niezbędne pliki cookies",
        "Odrzuć opcjonalne cookies",
        "Nie zgadzam się",
        "Odmów",
        "Reject all",
        "Decline",
        "Only necessary",
        "Accept necessary cookies only",
        "  Odrzuć \n  wszystkie  ",
    ],
)
def test_reject_labels_are_recognized(label):
    assert is_reject_label(label)


@pytest.mark.parametrize(
    "label",
    [
        "Akceptuję wszystkie",         # nigdy nie klikamy zgody na wszystko
        "Zezwól na wszystkie",
        "Akceptuję",
        "Accept all",
        "Ustawienia cookies",
        "Spersonalizuj",
        "Zgoda",
        "Odrzuć zmiany w formularzu i wróć do strony głównej serwisu",  # zbyt długi, inny kontekst
        "",
        None,
    ],
)
def test_other_labels_are_not_rejects(label):
    assert not is_reject_label(label)


def test_normalize_label():
    assert normalize_label("  Odrzuć\n\tWSZYSTKIE! ") == "odrzuć wszystkie"
