import { cn } from '#/components/ui'

/**
 * A country's flag, rendered as a coin. Used by the currency picker and the
 * country picker alike — both choose a place, so both want the same mark.
 *
 * Round rather than rectangular for two reasons: this is money, and the flags
 * here range from 2:3 to 1:2, so a circle is what makes thirty-one of them read
 * as one set at 20px instead of thirty-one differently-shaped stickers.
 *
 * The artwork comes from `country-flag-icons` (MIT): 265 flags, ISO 3166-1 plus
 * `EU`, so every currency the picker offers can show one. It replaced 31
 * hand-vendored files, six of which were broken — the vendoring pass stripped
 * ids, and `cn`, `eu`, `hk`, `in`, `kr` and `nz` place their stars and emblems
 * through `<use xlink:href="#…">`, so those references dangled and the flags
 * painted as bare fields of colour. A maintained package cannot rot that way,
 * and adding a currency no longer means drawing anything.
 *
 * The **1x1** set, not 3x2: these render as circles, and a square source loses
 * far less to the crop than a 3:2 one.
 *
 * Emoji flags were the obvious route and are the wrong one: Windows ships no
 * flag glyphs, so Chrome and Edge there render 🇩🇰 as two boxed capitals.
 */

// As URLs, so Vite emits one asset per flag and the browser fetches only the
// ones actually shown. Inlining all 265 as strings would put ~500 KB of
// decorative SVG in the bundle to render one 20px coin.
const FLAGS = import.meta.glob('/node_modules/country-flag-icons/1x1/*.svg', {
  eager: true,
  import: 'default',
  query: '?url',
}) as Record<string, string>

const BY_COUNTRY: Record<string, string> = Object.fromEntries(
  Object.entries(FLAGS).map(([path, url]) => [
    path.slice(path.lastIndexOf('/') + 1, -'.svg'.length).toUpperCase(),
    url,
  ]),
)

export interface CountryFlagProps {
  /** ISO 3166-1 alpha-2, or `EU`. */
  country: string
  className?: string
}

/**
 * Decorative: the code and name beside it carry the meaning, and repeating the
 * country to a screen reader would only add noise between them.
 */
export function CountryFlag({ country, className }: CountryFlagProps) {
  const src = BY_COUNTRY[country.toUpperCase()]

  return (
    <span
      aria-hidden
      className={cn(
        'inline-grid size-5 shrink-0 place-items-center overflow-hidden rounded-full',
        'bg-muted ring-1 ring-black/10 ring-inset',
        className,
      )}
    >
      {src ? (
        // `cover` crops a 4:3 flag at the sides, which is where flags carry the
        // least: a Nordic cross keeps its cross and a canton stays in frame.
        <img src={src} alt="" loading="lazy" className="size-full object-cover" />
      ) : (
        <span className="font-display text-[8px] leading-none font-semibold tracking-tight text-subtle-foreground">
          {country}
        </span>
      )}
    </span>
  )
}
