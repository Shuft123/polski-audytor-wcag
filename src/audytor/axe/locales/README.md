# Tłumaczenia axe-core

`pl.json` – polskie komunikaty reguł axe-core, skopiowane bez zmian z pakietu npm
`axe-core@4.12.1` (`locales/pl.json`, licencja MPL-2.0, © Deque Systems, Inc.).

Przy aktualizacji `axe-playwright-python` (a więc i axe-core) warto podmienić plik na wersję
z tej samej wersji axe-core:

```
npm pack axe-core@<wersja> && tar xzf axe-core-<wersja>.tgz && cp package/locales/pl.json .
```
