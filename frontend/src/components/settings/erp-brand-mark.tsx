import { cn } from '#/components/ui'

/**
 * A connector's mark, rendered as a rounded tile. Used by the ERP picker, where
 * choosing a system is the moment a customer decides whether we support their
 * accounting software — a row of logos answers that faster than a list of names.
 *
 * The artwork is vendored under `src/assets/erp` (see the README there) and
 * resolved by the `brand_slug` the catalog declares, never by connector name:
 * the front-end must not know any connector, or a new one would need a change
 * here to appear.
 *
 * Most connectors will have no artwork — we add a mark when we add a partner,
 * not when we add a connector — so the lettered fallback is the common case and
 * has to look deliberate rather than broken. Same reasoning as `country-flag`,
 * which faces 249 countries and 31 flags.
 */

// Resolved at build time, so a missing file is a build-visible gap rather than
// a broken image at runtime.
const MARKS: Record<string, string> = import.meta.glob(
  '../../assets/erp/*.svg',
  {
    eager: true,
    import: 'default',
    query: '?url',
  },
)

const BY_SLUG: Record<string, string> = Object.fromEntries(
  Object.entries(MARKS).map(([path, url]) => [
    path.slice(path.lastIndexOf('/') + 1, -'.svg'.length).toLowerCase(),
    url,
  ]),
)

export interface ErpBrandMarkProps {
  /** The catalog's `brand_slug`. Absent for a connector that declares none. */
  slug?: string | null
  /** The connector's label, used for the fallback's initial. */
  label: string
  className?: string
}

/**
 * Decorative: the label beside it carries the meaning, and repeating the
 * connector's name to a screen reader would only add noise between them.
 */
export function ErpBrandMark({ slug, label, className }: ErpBrandMarkProps) {
  const src = slug ? BY_SLUG[slug.toLowerCase()] : undefined

  return (
    <span
      aria-hidden
      data-testid="erp-brand-mark"
      data-variant={src ? 'artwork' : 'letter'}
      className={cn(
        'inline-grid size-10 shrink-0 place-items-center overflow-hidden rounded-xl',
        // The ring keeps a white-cornered mark from dissolving into a light
        // card, and gives the fallback the same silhouette as real artwork.
        'bg-muted ring-1 ring-black/10 ring-inset',
        className,
      )}
    >
      {src ? (
        <img src={src} alt="" loading="lazy" className="size-full" />
      ) : (
        <span className="font-display text-base leading-none font-semibold tracking-tight text-subtle-foreground">
          {label.trim().charAt(0).toUpperCase() || '?'}
        </span>
      )}
    </span>
  )
}
