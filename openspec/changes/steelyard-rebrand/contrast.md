# Contrast check (task 4.3)

WCAG 2 contrast ratios for the Steelyard tokens, computed from the values in
`apps/web/src/styles.css`. Body text needs ≥ 4.5:1.

## Neutrals

| pair | light | dark |
|---|---|---|
| foreground on card | 19.80 | 18.42 |
| foreground on canvas | 18.16 | 19.80 |
| foreground on muted | 17.37 | 17.04 |
| muted-foreground on card / canvas / muted | 6.69 / 6.13 / 5.87 | 7.30 / 7.85 / 6.76 |
| subtle-foreground on card / canvas / muted | 5.33 / 4.89 / 4.68 | 5.70 / 6.12 / 5.27 |
| primary-foreground on primary | 19.80 | 19.80 |

`subtle-foreground` was first proposed at `#737373`. It failed on the canvas
(4.35) and on muted (4.16), so it is `#6b6b6b`.

## Status

Each status token is used two ways: as badge text over a 12–16% tint of
itself (`badge.tsx`), and as a solid fill under `*-foreground`. **The old
single values failed as badges in both themes.** Warning in light mode was
**1.94:1**, because an amber light enough to fill a button is too light to be
text on white. So each status gets a per-theme tone. The hue is kept and the
lightness is walked until both uses clear 4.5.

| status | old (both themes) | light: tone / badge / solid | dark: tone / badge / solid |
|---|---|---|---|
| success | `#3e9b4f` — badge 3.07 light | `#30783d` / 4.59 / 5.40 (white text) | `#3e9b4f` / 4.57 / 5.65 (ink text) |
| warning | `#e8a13a` — badge 1.94 light | `#905c11` / 4.52 / 5.64 (white text) | `#e8a13b` / 6.36 / 9.06 (ink text) |
| destructive | `#e5484d` — badge 3.35 light, solid 3.91 | `#cd1d23` / 4.53 / 5.51 (white text) | `#e7555a` / 4.52 / 5.52 (ink text) |
| info | `#2f6feb` — badge 3.91 light | `#1960e9` / 4.56 / 5.42 (white text) | `#4e85ee` / 4.50 / 5.56 (ink text) |

In dark mode the solid status fills take ink text rather than white. A tone
light enough to read as text on `#141414` is too light to carry white text.
