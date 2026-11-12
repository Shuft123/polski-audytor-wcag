# Moduł AI – ocena tekstu alternatywnego (F9, kryterium 1.1.1)

Notatka ze sprintu 1. Osoba 3: Tomasz Chodorowski.

Pliki:
- notebook z modułem i ewaluacją: [`notebooks/F9_ocena_alt_colab.ipynb`](../notebooks/F9_ocena_alt_colab.ipynb) (Google Colab, GPU T4)
- zestaw testowy: [`tests/data/alt/alt_testy.jsonl`](../tests/data/alt/alt_testy.jsonl)
- wyniki wersji v3: [`docs/wyniki/alt_wyniki_v3.csv`](wyniki/alt_wyniki_v3.csv)

## Model i uruchomienie
- **Model:** Bielik-11B-v3.0-Instruct (SpeakLeash), kwantyzacja Q4_K_M (~6,7 GB).
- **Uruchomienie:** Ollama na Google Colab (GPU T4, 15 GB VRAM), API zgodne z OpenAI, `temperature=0.1`.
- **Wymienny backend:** zmiana `base_url` i nazwy modelu przełącza na lokalną Ollamę, PLGrid LLM Lab, CloudFerro Sherlock lub model komercyjny (przyda się w F16).

## Interfejs modułu
```python
ocen_alt(alt, kontekst="", src="", w_linku=False, obraz_opis=None) -> WynikAlt
# WynikAlt: werdykt (ok | blad | do_weryfikacji), kategoria, pewnosc, uzasadnienie,
#           zrodlo (reguła | ai), kryterium ("1.1.1")
```
- `alt=None` oznacza brak atrybutu (zawsze błąd), a `alt=""` pusty alt (może być poprawny).
- `obraz_opis` jest przygotowany na wynik modelu wizyjnego (osoba 4).

## Architektura oceny
1. **Reguły (bez modelu):** brak atrybutu alt, alt będący nazwą pliku, słowa-wypełniacze („zdjęcie”, „grafika”) oraz nazwa ikony w linku/przycisku („lupa”, która trafia do weryfikacji).
2. **Model:** dostaje tylko przypadki, których reguły nie rozstrzygają. Zwraca kategorię problemu (np. `zbyt_ogolny`, `wyglad_zamiast_funkcji`), a werdykt wylicza kod.

## Wyniki
Zestaw: 18 przykładów (4 rozstrzygnięte regułami, 14 przez model). 4 z nich dodano po strojeniu promptu, więc model ich wcześniej nie widział.

| Wersja promptu | Trafność AI | Pominięte problemy | Fałszywe alarmy |
|---|---|---|---|
| v1 – bazowy | 86% (6/7) | 1 („Lupa” uznana za OK) | 0 |
| v2 – kategoria „wygląd zamiast funkcji” | 80% (8/10) | 0 | 2 (zbyt agresywna) |
| v3 – pytanie kontrolne + przykłady poprawnych altów | 100% (14/14) | 0 | 0 |

- **Wykrywanie problemów (v3):** 11/11, 0 fałszywych alarmów, identyczne werdykty w 2 przebiegach.
- **Jedyna niezgodność:** „Lupa” dostaje `do_weryfikacji` zamiast `blad`. To zamierzone, bo reguła ikon tylko sygnalizuje problem człowiekowi.
- **Pomyłki w trakcie strojenia:** w v1 opis wyglądu ikony uznawany za opis funkcji, w v2 odwrotnie: poprawne alty bez czasownika uznawane za błąd.

## Wydajność i koszt
- **Czas:** 3,7–6,3 s (średnio ~4,2–4,7 s) na obraz oceniany przez model.
  - Strona z 30 obrazami zajmuje ≈ 2–2,5 min.
  - Strona główna x-kom.pl (337 obrazów) zajęłaby ≈ 25 min bez filtrowania. Konieczne jest więc odsiewanie regułami, pomijanie pustych altów w linkach z tekstem i cache (F15).
- **Koszt:** Colab jest darmowy, ale sesja wygasa, więc nie nadaje się jako stały backend. Docelowo: PLGrid LLM Lab, CloudFerro Sherlock lub własny GPU.
- **Sprzęt:** Q4_K_M ~6,7 GB VRAM, Q8_0 ~12 GB VRAM.

## Wnioski i ryzyka
- **Pewność zwracana przez model jest bezużyteczna w obecnej formie:** model zwrócił `1.0` we wszystkich 14 przypadkach. Próg „pewność < 0,6 → do weryfikacji” nigdy nie zadziała. Do F15 trzeba ustalić inne źródło pewności (np. zgodność kilku odpowiedzi).
- **Zestaw testowy jest syntetyczny.** 100% oznacza „prompt działa na przypadkach wzorcowych”, a nie skuteczność na prawdziwych stronach. Następny krok to oznaczenie altów z migawek zespołu (`tests/data/snapshots`). W migawkach są m.in.:
  - nazwy plików jako alt („Wasilków-029.jpg”);
  - opis wyglądu ikony w linku („Ikona z przekreślonym uchem…”);
  - obrazy tekstu w linkach;
  - 51 pustych altów w linkach na gov.pl.
- **Bez opisu obrazu nie da się ocenić, czy alt pasuje do obrazu.** Potrzebna jest integracja z modelem wizyjnym (osoba 4).
- **Każda zmiana promptu wymaga pełnej ewaluacji z kontrprzykładami**, bo v2 „przestrzeliła”.
- **Brak atrybutu (`None`) i pusty alt (`""`) muszą być rozróżnialne** w kontrakcie danych i w bazie. CSV gubi tę różnicę.

## Do uzgodnienia
- **Z osobą 2 (model danych):** mapowanie pól `werdykt` → `status`, `pewnosc` → `poziom_pewnosci`, `kryterium` → `kryterium_wcag`. Moduł musi też dostarczać `selektor`, `fragment_html` i `url_podstrony`, więc potrzebny jest ekstraktor obrazów z migawki.
- **Z osobą 1 (crawler):** element nadrzędny obrazu (`a`, `button`, `figure`) i tekst linku.
- **Następny sprint:** przeniesienie modułu z notebooka do `src/audytor/ai/` z testami jednostkowymi.
