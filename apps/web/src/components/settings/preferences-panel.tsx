import { Monitor, Moon, Sun } from 'lucide-react'
import { RadioGroup, RadioItem, useTheme } from '#/components/ui'
import type { ThemePreference } from '#/components/ui'
import { SettingsCard } from './form'

const OPTIONS: Array<{ value: ThemePreference; label: string; icon: typeof Sun }> = [
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'dark', label: 'Dark', icon: Moon },
  { value: 'system', label: 'System', icon: Monitor },
]

/**
 * Application preferences. These are local to the browser, so they take effect
 * immediately and need no save button.
 */
export function PreferencesPanel() {
  const { preference, setTheme } = useTheme()

  return (
    <SettingsCard
      title="Preferences"
      description="Applies to this browser and takes effect immediately."
    >
      <fieldset className="flex flex-col gap-3">
        <legend className="mb-2 text-sm font-medium text-foreground">Theme</legend>
        <RadioGroup
          value={preference}
          onValueChange={(value) => setTheme(value as ThemePreference)}
          className="flex flex-wrap gap-2"
        >
          {OPTIONS.map(({ value, label, icon: Icon }) => (
            // The chip is the click target; the radio inside keeps keyboard
            // and screen-reader semantics for the group.
            <div
              key={value}
              onClick={() => setTheme(value)}
              className="flex cursor-pointer items-center gap-2 rounded-full border border-border px-4 py-2 text-sm transition-colors has-data-checked:border-foreground has-data-checked:font-medium has-data-checked:ring-1 has-data-checked:ring-foreground"
            >
              <RadioItem value={value} aria-label={label} />
              <Icon className="size-4 text-muted-foreground" />
              {label}
            </div>
          ))}
        </RadioGroup>
      </fieldset>
    </SettingsCard>
  )
}
