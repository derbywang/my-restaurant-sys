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
}: {
  languages?: OrderingLanguage[]
  current: string
  onChange: (code: string) => void
  size?: 'md' | 'lg'
}) {
  if (!languages || languages.length < 2) return null
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
