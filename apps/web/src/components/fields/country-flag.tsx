import { cn } from '#/components/ui'

const FLAGS = import.meta.glob('/node_modules/country-flag-icons/1x1/*.svg', {
  eager: true,
  import: 'default',
  query: '?url',
})

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

/** A country's flag, rendered as a round coin with a lettered fallback. */
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
        <img
          src={src}
          alt=""
          loading="lazy"
          className="size-full object-cover"
        />
      ) : (
        <span className="font-display text-[8px] leading-none font-semibold tracking-tight text-subtle-foreground">
          {country}
        </span>
      )}
    </span>
  )
}
