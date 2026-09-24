import { defineConfig } from 'vite'
import { devtools } from '@tanstack/devtools-vite'

import { tanstackStart } from '@tanstack/react-start/plugin/vite'

import viteReact from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { nitro } from 'nitro/vite'

const config = defineConfig({
  resolve: { tsconfigPaths: true },
  build: {
    /**
     * Never inline a flag.
     *
     * Vite inlines any asset under 4 KB as a data URI, and almost every one of
     * `country-flag-icons`' 265 SVGs is under that — so the currency picker's
     * chunk came out at 240 KB of base-encoded artwork that every viewer
     * downloaded to render one 20px coin. Emitted as files they are fetched
     * lazily by the `<img loading="lazy">` in `CountryFlag`, so a viewer pays
     * only for the rows they actually see.
     *
     * A predicate rather than a global `assetsInlineLimit: 0`: inlining is the
     * right default for the handful of small icons elsewhere in the app, and
     * turning it off everywhere to fix one directory would trade this problem
     * for a pile of extra requests.
     */
    assetsInlineLimit: (filePath: string) =>
      filePath.includes('country-flag-icons') ? false : undefined,
  },
  plugins: [
    devtools(),
    nitro({ rollupConfig: { external: [/^@sentry\//] } }),
    tailwindcss(),
    tanstackStart(),
    viteReact(),
  ],
})

export default config
