import { cn } from '#/components/ui'

const MARKS: Record<string, string> = import.meta.glob(
  '../../../assets/erp/*.svg',
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
  /** The catalog's `brand_slug`, absent when the connector declares none. */
  slug?: string | null
  /** The connector's label, used for the fallback's initial. */
  label: string
  className?: string
}

/** Decorative connector mark tile with a lettered fallback. */
export function ErpBrandMark({ slug, label, className }: ErpBrandMarkProps) {
  const src = slug ? BY_SLUG[slug.toLowerCase()] : undefined

  return (
    <span
      aria-hidden
      data-testid="erp-brand-mark"
      data-variant={src ? 'artwork' : 'letter'}
      className={cn(
        'inline-grid size-10 shrink-0 place-items-center overflow-hidden rounded-xl',
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
