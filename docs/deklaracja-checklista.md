# Checklista wymogów deklaracji dostępności

Autor: Maciej Klepacki (osoba 5) · sprint 1 · stan prawny na 15.11.2026
Wersja maszynowa (do walidatora F18): `src/audytor/deklaracja/wymagania.py` – zmieniamy oba pliki razem.

## Źródła

| Dokument | Co z niego wynika |
|---|---|
| Ustawa z dnia 4 kwietnia 2019 r. o dostępności cyfrowej stron internetowych i aplikacji mobilnych podmiotów publicznych (t.j. Dz.U. 2023 poz. 82, zm. poz. 511) | **art. 10** – obowiązek sporządzenia i publikacji deklaracji, **art. 11** – przegląd i aktualizacja, **art. 18** – procedura żądania i skargi, **art. 19** – kary |
| Decyzja wykonawcza Komisji (UE) 2018/1523 | wzorcowe oświadczenie w sprawie dostępności (art. 10 ustawy odsyła do tego wzoru) |
| „Warunki techniczne publikacji oraz struktura dokumentu elektronicznego deklaracji dostępności”, **wersja 2.0 z 31.07.2024** (Ministerstwo Cyfryzacji, BIP MC, art. 12 pkt 7 ustawy) | identyfikatory `a11y-*`, nagłówki, formuły, format dat – **to jest podstawa walidatora** |

Uwaga: część stron ma deklaracje według starszej wersji warunków (2019/2020, np. `a11y-osoba`, `a11y-deklaracja`, daty tylko `rrrr-mm-dd`). Walidator powinien je rozpoznawać i zgłaszać „nieaktualną strukturę”, a nie traktować jak brak deklaracji.

## A. Czy deklaracja w ogóle jest (F17)

| # | Wymóg | Źródło | Jak sprawdzamy automatycznie |
|---|---|---|---|
| A1 | Deklaracja istnieje dla każdej strony internetowej podmiotu (także BIP) i dla każdej wersji językowej | art. 10 | Wyszukiwanie linku na stronie głównej (`audytor.deklaracja`) |
| A2 | Link do deklaracji jest łatwo dostępny z każdego miejsca nawigacji, np. w stopce | art. 10, warunki tech. | Kandydat w `<footer>` / `role=contentinfo` / klasa „footer/stopka”; ostrzeżenie, gdy deklaracja jest tylko pod typowym adresem |
| A3 | Deklaracja jest stroną HTML, nie PDF/DOCX | warunki tech. | Typ odpowiedzi i rozszerzenie adresu |
| A4 | Deklaracja sama jest dostępna cyfrowo (nawet gdy strona nie jest) | warunki tech. | axe-core na stronie deklaracji (moduł osoby 2) |
| A5 | *(dobra praktyka)* meta tag `<meta name="deklaracja-dostępności" content="URL">` na podstronach | warunki tech. | Parser meta tagu – najpewniejszy sygnał |

## B. Identyfikatory `a11y-*` (wersja 2.0)

Każdy identyfikator może wystąpić tylko raz, bez polskich znaków, nie tłumaczy się ich w innych wersjach językowych.

| Identyfikator | Treść | Status |
|---|---|---|
| `a11y-wstep` | cała treść oświadczenia wstępnego | obowiązkowy |
| `a11y-podmiot` | nazwa podmiotu publicznego | obowiązkowy |
| `a11y-zakres` | „strona internetowa” albo „aplikacja mobilna” | obowiązkowy |
| `a11y-url` | adres strony / miejsce pobrania aplikacji | obowiązkowy |
| `a11y-data-publikacja` | data publikacji strony / wydania aplikacji | obowiązkowy |
| `a11y-data-aktualizacja` | data ostatniej istotnej aktualizacji | obowiązkowy |
| `a11y-status` | cały akapit ze stanem zgodności | obowiązkowy |
| `a11y-ocena` | ocena nadmiernych kosztów lub link do niej | gdy powołuje się na nadmierne koszty |
| `a11y-data-sporzadzenie` | data sporządzenia pierwszej deklaracji | obowiązkowy |
| `a11y-data-przeglad` | data ostatniego przeglądu | obowiązkowy od pierwszego przeglądu |
| `a11y-kontakt` | osoba albo komórka do kontaktu | obowiązkowy |
| `a11y-email` | e-mail do kontaktu | obowiązkowy |
| `a11y-telefon` | telefon do kontaktu | obowiązkowy |
| `a11y-procedura` | `section` „Obsługa wniosków i skarg…” | obowiązkowy |
| `a11y-aplikacje` | `section` „Aplikacje mobilne” | gdy podmiot ma aplikacje |
| `a11y-architektura` | `section` „Dostępność architektoniczna” | obowiązkowy |
| `a11y-architektura-url` | link do opisu dostępności architektonicznej | opcjonalny |
| `a11y-komunikacja` | `section` „Dostępność komunikacyjno-informacyjna” | obowiązkowy |

## C. Struktura i nagłówki (odwzorowane wiernie)

| # | Nagłówek | Wymagany | Uwagi |
|---|---|---|---|
| C1 | Deklaracja dostępności | tak | h1 (albo h2, jeśli tak wynika z hierarchii strony) |
| C2 | Stan dostępności cyfrowej | tak | h2 |
| C3 | Niedostępne treści | przy stanie „częściowo zgodna”/„niezgodna” | podsekcje h3: Niezgodność z załącznikiem / Treści nieobjęte przepisami / Nadmierne koszty |
| C4 | Przygotowanie deklaracji dostępności | tak | w przykładach MC: „… i jej aktualizacja” – akceptujemy oba |
| C5 | Udogodnienia, ograniczenia i inne informacje | nie | |
| C6 | Skróty klawiszowe | gdy są niestandardowe skróty | |
| C7 | Informacje zwrotne i dane kontaktowe | tak | |
| C8 | Obsługa wniosków i skarg związanych z dostępnością | tak | `section#a11y-procedura` |
| C9 | Pozostałe informacje | tak | podsekcje h3 poniżej |
| C10 | Aplikacje mobilne | gdy są aplikacje | `section#a11y-aplikacje` |
| C11 | Dostępność architektoniczna | tak | `section#a11y-architektura` |
| C12 | Dostępność komunikacyjno-informacyjna | tak | `section#a11y-komunikacja` |
| C13 | Hierarchia nagłówków zachowana (sekcje niżej niż tytuł) | tak | wspólne z kryterium WCAG 1.3.1 |

## D. Treść

| # | Wymóg | Jak sprawdzić |
|---|---|---|
| D1 | Oświadczenie wstępne wg wzoru: „[podmiot] zobowiązuje się zapewnić dostępność swojej [strony internetowej / aplikacji mobilnej] zgodnie z ustawą z dnia 4 kwietnia 2019 r. …” | dopasowanie formuły po normalizacji spacji |
| D2 | Stan zgodności – dokładnie jedna z trzech formuł: „jest **w pełni zgodna** / **częściowo zgodna** / **niezgodna** z załącznikiem do ustawy…” | regex; częściowa/niezgodna ⇒ musi być lista niezgodności (C3) |
| D3 | Przy „częściowo zgodna”/„niezgodna”: wymienione niezgodności, wyłączenia (art. 3) i ewentualne nadmierne koszty z wynikami oceny (art. 8 ust. 3–4, `a11y-ocena`) | obecność listy pod C3; **F19**: porównanie z wynikami skanu |
| D4 | Daty w `<time datetime="rrrr-mm-dd">` z tekstem „5 lutego 2020 r.”; publikacja i aktualizacja obowiązkowe (gdy brak aktualizacji – te same daty) | parser `time`, poprawność daty, aktualizacja ≥ publikacja |
| D5 | Data przeglądu nie starsza niż 31 marca bieżącego roku (art. 11: przegląd co roku do 31.03) | `a11y-data-przeglad` vs data skanu; po 31.03 – przegląd z bieżącego roku |
| D6 | Sposób przygotowania: samoocena albo badanie podmiotu zewnętrznego (wtedy nazwa podmiotu i link do raportu/streszczenia) | słowa kluczowe w sekcji C4 |
| D7 | Kontakt: osoba lub komórka, e-mail (`mailto:`), telefon | format e-mail i telefonu |
| D8 | Procedura (art. 18): prawo do żądania dostępności lub alternatywnego dostępu; termin **7 dni**, wydłużenie najpóźniej do **2 miesięcy**; prawo do skargi; **link do Rzecznika Praw Obywatelskich** (obowiązkowy) | słowa kluczowe + link do `rpo.gov.pl` / `bip.brpo.gov.pl` |
| D9 | Dostępność architektoniczna siedziby głównej: adres, wejścia, korytarze/schody/windy, pochylnie/pętle indukcyjne, parking dla osób z niepełnosprawnościami, wejście z psem asystującym, tłumacz PJM (albo link `a11y-architektura-url`) | słowa kluczowe w sekcji (pełna ocena – ręczna/AI, „do weryfikacji”) |
| D10 | Dostępność komunikacyjno-informacyjna: czy można skorzystać z tłumacza PJM w kontakcie elektronicznym; dobra praktyka – linki do ETR i PJM, pętla indukcyjna | słowa kluczowe |
| D11 | Deklaracja strony zawiera link do deklaracji każdej aplikacji mobilnej podmiotu | linki w C10 |

## E. Kary (kontekst do raportu)

Art. 19: do 5000 zł za brak deklaracji albo brak wymaganych elementów (gdy powtórzy się w dwóch kolejnych monitoringach), do 10 000 zł za uporczywe niezapewnianie dostępności. W raporcie podajemy to jako informację, nie jako ocenę prawną.

## F. Podmioty prywatne (sklepy)

Sklepy nie są podmiotami publicznymi, więc nie muszą mieć deklaracji w rozumieniu ustawy z 2019 r. Od 28.06.2025 obowiązuje je ustawa z dnia 26 kwietnia 2024 r. o zapewnianiu spełniania wymagań dostępności niektórych produktów i usług (tzw. PAD) – publikują wtedy *informację o spełnianiu wymagań dostępności* (często nazwaną „Deklaracja dostępności” albo „Dostępność”, np. x-kom.pl: `/lp/deklaracja-dostepnosci`). Detektor F17 je znajduje; walidator F18 **nie** powinien oceniać ich według warunków technicznych dla podmiotów publicznych – tylko odnotować typ.

## Co sprawdza już kod (sprint 1/2), a co zostaje na F18

- **Gotowe:** A1, A2, A5 (wyszukiwanie + meta tag), wstępnie B (lista znalezionych i brakujących obowiązkowych `a11y-*`).
- **F18 (sprint 3–4):** B w całości (unikalność, `section` przy procedurze/architekturze/komunikacji), C, D1–D2, D4–D5, D7–D8, A3.
- **„Do weryfikacji” / AI:** D3, D6, D9, D10 (treść opisowa).
- **F19 (sprint 8):** D3 vs wyniki skanu (deklaruje zgodność, a skan znajduje błędy).
