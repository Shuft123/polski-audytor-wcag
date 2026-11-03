@echo off
rem ===========================================================================
rem  Pokaz sprintu 1 - modul crawlera (osoba 1)
rem  Uruchomienie: dwuklik albo w terminalu:  scripts\demo_sprint1.bat
rem  Tryb bez pauz i bez otwierania okien (do sprawdzenia skryptu):
rem      set DEMO_AUTO=1 ^& scripts\demo_sprint1.bat
rem ===========================================================================
setlocal
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0.."

set PY=.venv\Scripts\python.exe
set OUT=demo-wyniki
set STRONA=https://pb.edu.pl/
set FOLDER=%OUT%\pb-edu-pl

if not exist "%PY%" (
    echo [BLAD] Brak srodowiska .venv. Zainstaluj projekt wedlug docs\crawler.md
    goto koniec
)

cls
echo ===========================================================================
echo   POLSKI AUDYTOR WCAG - sprint 1, modul crawlera
echo ===========================================================================
echo   1. Testy automatyczne
echo   2. Migawka strony na zywo (Playwright renderuje strone z JavaScriptem)
echo   3. Wynik: zrzut ekranu, DOM i metadane
echo   4. Etyka crawlowania: robots.txt
echo   5. Migawki testowe dla zespolu
echo ===========================================================================
call :pauza

rem ---------------------------------------------------------------------------
echo.
echo ===== KROK 1/5: Testy automatyczne =========================================
echo   Testy linkow, robots.txt, zapisu migawek i banerow cookies.
echo   Czesc testow uruchamia prawdziwa przegladarke na lokalnym serwerze.
echo.
"%PY%" -m pytest -q
call :pauza

rem ---------------------------------------------------------------------------
echo.
echo ===== KROK 2/5: Migawka strony na zywo =====================================
echo   Otwiera sie przegladarka: strona sie wczytuje, wykonuje JavaScript,
echo   jest przewijana (obrazki ladowane w trakcie), baner cookies jest
echo   zamykany przyciskiem "Odrzuc", na koniec zapis migawki.
echo.
"%PY%" -m audytor.crawler %STRONA% --out %OUT% --headed
if errorlevel 3 (
    echo.
    echo   Wbudowany Chromium nie wystartowal - ponawiam w przegladarce Edge...
    "%PY%" -m audytor.crawler %STRONA% --out %OUT% --headed --channel msedge
)
call :pauza

rem ---------------------------------------------------------------------------
echo.
echo ===== KROK 3/5: Co zapisala migawka ========================================
"%PY%" scripts\pokaz_migawke.py %FOLDER%
echo.
echo   Otwieram: zrzut calej strony, zrzut z banerem cookies i folder migawki.
if not defined DEMO_AUTO (
    if exist "%FOLDER%\screenshot.png" start "" "%FOLDER%\screenshot.png"
    if exist "%FOLDER%\screenshot-baner.png" start "" "%FOLDER%\screenshot-baner.png"
    start "" explorer "%FOLDER%"
)
call :pauza

rem ---------------------------------------------------------------------------
echo.
echo ===== KROK 4/5: Etyka crawlowania - robots.txt =============================
echo   Koszyk sklepu x-kom.pl jest zablokowany w robots.txt (Disallow).
echo   Crawler musi go POMINAC i nie wysylac do niego zapytan.
echo.
"%PY%" -m audytor.crawler https://www.x-kom.pl/koszyk --out %OUT%
call :pauza

rem ---------------------------------------------------------------------------
echo.
echo ===== KROK 5/5: Migawki testowe dla zespolu ================================
echo   5 roznych typow stron: uczelnia, miasto, administracja, sklep, gmina.
echo   Na nich pozostale osoby pracuja rownolegle (axe-core, modele AI).
echo   Format opisany w docs\kontrakt-danych.md, sekcja 1.
echo.
for /d %%D in (tests\data\snapshots\*) do (
    echo ---------------------------------------------------------------------------
    "%PY%" scripts\pokaz_migawke.py "%%D"
)
if not defined DEMO_AUTO start "" explorer "tests\data\snapshots"
echo.
echo ===========================================================================
echo   KONIEC POKAZU
echo   Wyniki z pokazu sa w folderze %OUT% (nie trafia do repozytorium).
echo ===========================================================================

:koniec
if not defined DEMO_AUTO pause
endlocal
exit /b 0

:pauza
echo.
if not defined DEMO_AUTO (
    echo   [Nacisnij dowolny klawisz, aby przejsc dalej...]
    pause >nul
)
exit /b 0
