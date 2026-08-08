# Flags

4:3 flag SVGs for the currencies offered in `src/lib/currencies.ts`, one file per
ISO 3166-1 alpha-2 code (plus `eu.svg` for the euro).

Vendored from [lipis/flag-icons](https://github.com/lipis/flag-icons) (MIT),
stripped of XML declarations, comments and ids. About 24 KB for all 31, so Vite
inlines most of them as data URIs.

They are vendored rather than installed because these are the only flags the app
needs, and rather than drawn by hand because an approximated national flag is
worse than no flag. `mx.svg` is the one exception: the real file is 85 KB of
coat-of-arms that renders as a smudge at 20 px, so it ships as the plain
tricolour.

Adding a currency to `CURRENCIES` means adding its flag here under the same
country code — `country-flag.tsx` resolves the file by code and falls back to a
lettered chip when there is none.
