# ERP marks

One square SVG per connector, named after the `brand_slug` its catalog entry
declares (`GET /api/v1/erp-types`). `erp-brand-mark.tsx` resolves the file by
that slug and falls back to a lettered tile when there is none — so a connector
registered without artwork still renders, and adding artwork later needs no code
change.

Each is a **self-contained tile**: the rounded background is part of the file, so
the mark carries its own brand colour rather than inheriting the app's. That is
deliberate — these read as app icons, and a row of them is what tells a customer
at a glance whether we support their accounting system. It also means they look
the same in light and dark mode, which is what a brand mark should do.

Drawn at a 64×64 viewBox with a 14px corner radius so all of them read as one
set at 40px.

## Provenance

| File        | Source                                                                    | Notes                                                                                                                                                                                                     |
| ----------- | ------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `billy.svg` | `https://www.billy.dk/assets/new_identity/logos/billy-by-shine_white.svg` | Billy's own mark. Only the **symbol** is used — the "billy by Shine" wordmark beside it in the source file is illegible at 40px. Placed on Billy's `#002E33`, the brand colour their site uses behind it. |
| `mock.svg`  | Drawn here                                                                | The Debug ERP is ours, so its mark is too: a shell prompt on slate, to read as a development tool rather than a product a customer could buy.                                                             |

Third-party marks are used **nominatively** — to identify which system an
integration connects to, which is ordinary for an integrations page — and are not
modified beyond cropping to the symbol and placing it on the vendor's own colour.
If a vendor asks us to stop, the fallback tile already covers their absence:
delete the file and nothing breaks.
