import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from '@testing-library/react'
import { Tabs, TabsList, TabsTab } from '#/components/ui'

const NATIVE_BUTTON_WARNING = /native <button>/i

let consoleError: ReturnType<typeof vi.spyOn>
let consoleWarn: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
  consoleWarn = vi.spyOn(console, 'warn').mockImplementation(() => {})
})

afterEach(() => {
  consoleError.mockRestore()
  consoleWarn.mockRestore()
})

function complained(): boolean {
  return [...consoleError.mock.calls, ...consoleWarn.mock.calls].some((call) =>
    call.some(
      (arg: unknown) =>
        typeof arg === 'string' && NATIVE_BUTTON_WARNING.test(arg),
    ),
  )
}

describe('a tab that navigates', () => {
  it('warns when rendered as a link without saying so', () => {
    render(
      <Tabs value="/settings">
        <TabsList>
          <TabsTab value="/settings" render={<a href="/settings" />}>
            Profile
          </TabsTab>
        </TabsList>
      </Tabs>,
    )

    expect(complained()).toBe(true)
  })

  it('is silent once declared as not a native button', () => {
    render(
      <Tabs value="/settings">
        <TabsList>
          <TabsTab
            value="/settings"
            nativeButton={false}
            render={<a href="/settings" />}
          >
            Profile
          </TabsTab>
        </TabsList>
      </Tabs>,
    )

    expect(complained()).toBe(false)
  })
})
