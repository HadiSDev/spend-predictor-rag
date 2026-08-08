import { cn } from '#/components/ui'

/**
 * A country's flag, rendered as a coin. Used by the currency picker and the
 * country picker alike — both choose a place, so both want the same mark.
 *
 * Round rather than rectangular for two reasons: this is money, and the flags
 * here range from 2:3 to 1:2, so a circle is what makes thirty-one of them read
 * as one set at 20px instead of thirty-one differently-shaped stickers.
 *
 * The artwork is vendored under `src/assets/flags` (see the README there), and
 * covers only the currency-issuing countries. The country list is all 249 of
 * them, so the lettered fallback below is the common case there, not the edge
 * case — it has to look deliberate, because most rows use it.
 *
 * Emoji flags were the obvious route and are the wrong one: Windows ships no
 * flag glyphs, so Chrome and Edge there render 🇩🇰 as two boxed capitals.
 */

// Resolved at build time, so a missing flag is a build-visible gap rather than
// a broken image at runtime.
const FLAGS = import.meta.glob('../../assets/flags/*.svg', {
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
