import type { OrderingLanguage } from '../lib/api'

/**
 * The language buttons of the ordering page: only the languages the profile allows, each written in its own language,
 * big enough for a finger. Nothing is shown while there is only one language to choose from.
 */
export default function LanguageSwitcher({
  languages,
  current,
  onChange,
  size = 'md',
  variant = 'buttons',
}: {
  languages?: OrderingLanguage[]
  current: string
  onChange: (code: string) => void
  size?: 'md' | 'lg'
  /** 'menu': one drop-down (a phone's header has no room for a button per language). */
  variant?: 'buttons' | 'menu'
}) {
  if (!languages || languages.length < 2) return null
  if (variant === 'menu') {
    return (
      <select
        aria-label="Language"
        value={current}
        onChange={(event) => onChange(event.target.value)}
        className="shrink-0 whitespace-nowrap rounded-md border bg-background px-2 py-1.5 text-sm font-medium"
      >
        {languages.map((entry) => (
          <option key={entry.code} value={entry.code} lang={entry.code}>
            {entry.label}
          </option>
        ))}
      </select>
    )
  }
  const pad = size === 'lg' ? 'px-4 py-2 text-base' : 'px-2.5 py-1.5 text-sm'
  return (
    <div role="group" aria-label="Language" className="flex items-center gap-1.5">
      {languages.map((entry) => (
        <button
          key={entry.code}
          type="button"
          lang={entry.code}
          aria-pressed={entry.code === current}
          onClick={() => onChange(entry.code)}
          className={`rounded-md border font-medium ${pad} ${
            entry.code === current ? 'border-primary bg-primary text-primary-foreground' : 'text-muted-foreground'
          }`}
        >
          {entry.label}
        </button>
      ))}
    </div>
  )
}
