# Steelyard logo pack

The mark is **Counterweight**. The palette is **black `#0A0A0A` and white only**. The wordmark is Geist SemiBold, converted to outlines, so no font is needed to use these files.

## What's inside
| Folder | Files | Use |
|---|---|---|
| `svg/` | lockup + symbol (black / white), app icon (black / white) | Web, print, design tools. Always prefer SVG. |
| `png/` | lockup at 600 / 1200 / 2400 px wide, symbol at 256 / 512 / 1024, app icon 512 / 1024 | Docs, slides, email, anywhere SVG doesn't work |
| `favicon/` | favicon.svg, favicon.ico (16/32/48), 16–512 PNGs, apple-touch-icon.png | Website and web app |
| `social/` | avatar 800 (black / white), LinkedIn banner 1584×396, X header 1500×500, OG image 1200×630 | Profiles and link previews |

## Website `<head>`
```html
<link rel="icon" href="/favicon.ico" sizes="48x48">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta property="og:image" content="https://steelyard.com/og-image-1200x630.png">
<meta name="theme-color" content="#0A0A0A">
```

## Rules
- **Colours:** use the black version on light backgrounds and the white version on dark ones. Never use any other colour.
- **Clear space:** keep space around the logo at least the diameter of the large circle.
- **Minimum size:** 80 px wide for the lockup, 20 px for the symbol. Below 32 px, use the favicon version, which has a thicker arm.
- **Don't:** recolour it, add effects or gradients, tilt the arm (it is always level), stretch it, change the gap between mark and wordmark, or retype the wordmark.
