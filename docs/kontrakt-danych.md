# Kontrakt danych między modułami

Dokument zawiera ustalony format wymiany danych, dzięki czemu moduł crawlera, modele AI, backend i raporty mogą ze sobą bezkolizyjnie rozmawiać. [Termin: do 02.11.2026]

## 1. Format migawki strony (Crawler -> Reszta)
Osoba 1 do 3.11 dostarcza migawki stron do pracy dla reszty zespołu.
- Gdzie będą zapisywane? (np. folder `tests/data/`)
- Co zawiera migawka? (Zapisany DOM / zrzut całej strony / metadane)

## 2. Format pojedynczego wyniku z audytu
Zgodnie z wymaganiami MVP (Model danych v1), każdy wykryty problem (zarówno z axe-core, jak i AI) musi mieć wspólny format przed zapisem do bazy.
Wstępne pola do JSONa (do przedyskutowania):
- `url_podstrony`: string
- `zrodlo`: string ("axe" lub "ai")
- `kryterium_wcag`: string
- `waga`: string/int
- `selektor`: string
- `fragment_html`: string
- `poziom_pewnosci`: float (dla AI)
- `status`: string ("blad", "do weryfikacji", itp.)
