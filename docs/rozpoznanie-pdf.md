# Rozpoznanie: audyt dostępności dokumentów PDF (pikepdf, veraPDF)

Notatka ze sprintu 2 (osoba 2, F6/F7). Cel: ocenić, czym sprawdzać dostępność dokumentów PDF linkowanych na
stronach (crawler zbiera je już w `meta.json` → `links.documents`) i jak wpiąć to w nasz przebieg skanu.
Prototyp: `scripts/rozpoznanie_pdf.py`. To rozpoznanie – **nie** moduł produkcyjny.

## Wnioski w skrócie

1. **Dwie warstwy.** Szybkie sprawdzenia w Pythonie przez **pikepdf** dla każdego PDF-a (ułamek sekundy,
   bez Javy, działa w CI) plus **veraPDF** jako opcjonalny, pełny walidator PDF/UA (106 reguł maszynowych),
   uruchamiany jako osobna usługa w docker-compose.
2. **Prototyp na pikepdf zgadza się z veraPDF w 17 z 20 plików** z oficjalnego korpusu testowego veraPDF
   dla sprawdzanych reguł. Rozbieżności wynikają ze świadomego uproszczenia – opis niżej.
3. **Żadne z tych narzędzi nie oceni sensu:** czy alt opisuje obrazek, czy kolejność czytania ma sens,
   czy nagłówki oddają strukturę. To zostaje dla AI (osoby 3 i 4) i audytora – tak jak na stronach WWW.
4. **Do decyzji zespołu przed implementacją:** gdzie w modelu danych żyje dokument PDF (propozycja niżej)
   i w którym sprincie robimy F25/F26.

## Narzędzia

### pikepdf
- Biblioteka Pythona oparta na QPDF; gotowe paczki (wheels) na Windows, Linux i macOS – `pip install pikepdf`,
  bez dodatkowych programów. Licencja MPL-2.0. W teście: wersja 10.16.
- Daje dostęp do „surowej” struktury PDF: katalog dokumentu (`/Lang`, `/MarkInfo`, `/ViewerPreferences`),
  drzewo struktury (`/StructTreeRoot` – tagi `H1`, `P`, `Figure`, `Table`…), metadane XMP (`dc:title`,
  `pdfuaid:part`), zawartość stron (operatory tekstu i obrazów).
- **Nie ma wbudowanej walidacji** – każdą regułę piszemy sami. Dobre do kilkunastu najważniejszych sprawdzeń,
  nie do pełnej zgodności z PDF/UA.
- Czas: ok. 0,1 s na plik testowy (proces Pythona razem ze startem).

### veraPDF
- Otwarty walidator PDF/A i PDF/UA rozwijany przez konsorcjum veraPDF; implementuje maszynowo sprawdzalne
  wymagania PDF/UA-1, PDF/UA-2 i WTPDF jako tzw. profile walidacji. Dla PDF/UA wykonuje **tylko** sprawdzenia
  maszynowe (Matterhorn Protocol rozróżnia sprawdzenia maszynowe i wymagające człowieka).
- Profil PDF/UA-1 ma **106 reguł** (policzone w `PDFUA-1.xml` z repozytorium veraPDF-validation-profiles).
- Dostępny jako CLI, GUI, REST API i obraz Docker; wersja 1.30 wyszła w kwietniu 2026. Raport w XML, JSON albo HTML.
- Wymaga Javy (JVM). Do naszego obrazu workera dochodzi wtedy Java – lepiej osobna usługa w docker-compose
  (REST) niż Java w tym samym obrazie co Playwright.
- Nie udało się go uruchomić w środowisku rozpoznania (brak dostępu do serwera z paczkami), więc porównanie
  oparte jest na korpusie testowym veraPDF: pliki `*-pass-*` / `*-fail-*` z opisanym oczekiwanym wynikiem.

### Inne, odrzucone na teraz
- **PAC** (PDF Accessibility Checker) – popularny wśród audytorów, ale to przede wszystkim aplikacja okienkowa,
  nie do automatyzacji w workerze. Przydatny audytorowi do ręcznej weryfikacji.
- **pdfua** (PyPI) – gotowy zestaw sprawdzeń na pikepdf; autorzy deklarują 12 sprawdzeń pokrywających 16 ze
  106 reguł PDF/UA-1. Mały i młody projekt – raczej inspiracja niż zależność.
- **cpdf** – ma eksperymentalny weryfikator Matterhorn; licencja AGPL albo płatna – do sprawdzenia, jeśli wrócimy do tematu.

## Eksperyment: prototyp na pikepdf vs korpus veraPDF

`scripts/rozpoznanie_pdf.py` sprawdza 9 rzeczy. Dla 7 z nich korpus veraPDF ma pliki testowe:

| Sprawdzenie | Reguła PDF/UA-1 | WCAG 2.1 (technika PDF) | Zgodność z korpusem |
|---|---|---|---|
| dokument otagowany (`StructTreeRoot`, `Marked`) | 7.1-11 | 1.3.1 (PDF1, PDF9) | 1/1 |
| brak `Suspects` | 7.1-4 | 1.3.1 | 2/2 |
| metadane XMP | 7.1-8 | – | 2/2 |
| tytuł dokumentu (`dc:title`) | 7.1-9 | 2.4.2 (PDF18) | 2/2 |
| przeglądarka pokazuje tytuł (`DisplayDocTitle`) | 7.1-10 | 2.4.2 (PDF18) | 3/3 |
| język dokumentu (`/Lang` w katalogu) | 7.2-34 (część) | 3.1.1 (PDF16) | **2/5** |
| ilustracje (`Figure`) mają alt | 7.3-1 | 1.1.1 (PDF1) | 5/5 |
| identyfikator PDF/UA w XMP | 5-1 | – | brak plików w pobranej części |
| strony z tekstem, nie sam skan | – | 1.1.1, 1.4.5 (PDF7) | brak plików w korpusie |
| **razem** | | | **17/20** |

Czego nauczył eksperyment:
- **Język:** reguła PDF/UA 7.2-34 wymaga, żeby język był *ustalony* dla każdego tekstu – może być ustawiony
  na elementach struktury (np. `<P Lang="en-US">`), a nie w katalogu dokumentu. Nasze sprawdzenie patrzy tylko na
  katalog – to odpowiada technice WCAG PDF16 (3.1.1), ale jest surowsze niż PDF/UA. Wniosek: wynik „brak języka
  w katalogu” zapisywać jako `do_weryfikacji`, nie `blad`, albo przejść po drzewie struktury.
- **Alt:** pusty `Alt=""` przy ilustracji to błąd, ale pusty `ActualText` veraPDF akceptuje – pierwsza wersja
  prototypu przepuszczała pusty alt. Szczegóły reguł warto brać wprost z profilu veraPDF, a nie z pamięci.
- Proste sprawdzenia katalogu (tagi, tytuł, metadane) są jednoznaczne i zgodne w 100%.

Powtórzenie eksperymentu:
```
git clone --depth 1 --filter=blob:none --sparse https://github.com/veraPDF/veraPDF-corpus.git
cd veraPDF-corpus && git sparse-checkout set "PDF_UA-1/7.1 General" "PDF_UA-1/7.2 Text" "PDF_UA-1/7.3 Graphics"
python scripts/rozpoznanie_pdf.py --korpus PDF_UA-1
python scripts/rozpoznanie_pdf.py jakis-dokument.pdf      # raport JSON dla jednego pliku
```

## Czego automat nie sprawdzi
- czy alt ilustracji opisuje jej treść (jak na stronach – ocena AI, F9),
- czy kolejność czytania i tagi nagłówków odpowiadają wyglądowi dokumentu,
- czy tabele mają sensowne nagłówki, a skan ma poprawny OCR,
- kontrastu tekstu (wymaga renderowania stron – np. przez Playwright/pdf.js albo `pdftoppm`, osobny temat).

## Propozycja wpięcia w projekt (do decyzji)
1. **Pobieranie:** worker bierze adresy z `links.documents` (tylko PDF, ta sama witryna, robots.txt,
   limit np. 20 MB i 10 dokumentów na skan), pobiera je przez `urllib` z tym samym ograniczaniem tempa
   (`audytor.skan.Ogranicznik`).
2. **Szybkie sprawdzenia (pikepdf)** w nowym module `audytor.pdf` – wyniki jako `Problem`:
   `zrodlo: "heurystyka"`, `regula: "pdf-…"` (np. `pdf-brak-tagow`, `pdf-brak-tytulu`, `pdf-alt-ilustracji`),
   `url_podstrony` = adres PDF-a, `selektor` = ścieżka w drzewie struktury albo `strona 3`.
   Jednoznaczne (brak tagów, brak tytułu) – `blad`; reszta – `do_weryfikacji`.
3. **veraPDF (opcjonalnie)** jako usługa `verapdf` w docker-compose wołana przez REST; wyniki jako
   `regula: "pdfua-7.1-9"` itd. Włączane parametrem skanu, bo dokłada czas i zależność od Javy.
4. **Model danych:** dokument PDF zapisywać jako wiersz `podstrona` z nową kolumną `typ` (`strona` | `dokument`)
   – reszta (problemy, `blad`, API) działa bez zmian. Wymaga migracji 0003.

Szacunek: pkt 1–2 to ok. jeden sprint dla jednej osoby (z testami na korpusie veraPDF), pkt 3 – dodatkowo
ok. 2–3 dni z osobą 6 (docker-compose, CI).

## Źródła
- veraPDF – walidacja PDF/A i PDF/UA, profile: https://docs.verapdf.org/validation/
- veraPDF – wiersz poleceń: https://docs.verapdf.org/cli/validation
- veraPDF – informacje o projekcie: https://verapdf.org/home/
- Profil PDF/UA-1 i korpus testowy: https://github.com/veraPDF/veraPDF-validation-profiles, https://github.com/veraPDF/veraPDF-corpus
- Matterhorn Protocol (PDF Association): https://pdfa.org/download-area/accessibility/MatterhornProtocol_1-02.pdf
- Technika WCAG PDF16 (język dokumentu): https://www.w3.org/WAI/WCAG21/Techniques/pdf/PDF16
- pdfua (PyPI): https://pypi.org/project/pdfua/
- pikepdf: https://pikepdf.readthedocs.io/
