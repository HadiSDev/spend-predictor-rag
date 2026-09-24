import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from '@testing-library/react'
import { Tabs, TabsList, TabsTab } from './index'

/**
 * Base UI renders several components as a native `<button>` by default and, in
 * development, warns when the `render` prop replaces that with something else.
 * The warning is worth heeding rather than silencing: the element still carries
 * the button role, so it is announced as a button but does not behave like one.
 *
 * The Settings tabs deliberately render as links, because they navigate and a
 * real anchor is what makes middle-click and open-in-new-tab work.
 * `nativeButton={false}` is how that intent is declared.
 *
 * A menu item is not affected: Base UI accepts a real `<a href>` there without
 * complaint, which is why the account menu's Settings link needs nothing.
 *
 * These tests pin the mechanism, not the call site: that lives in a route file
 * (`routes/_authed/settings.tsx`) whose `Link` needs a router, and this project
 * has no router test setup to render it in.
 */
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
    call.some((arg: unknown) => typeof arg === 'string' && NATIVE_BUTTON_WARNING.test(arg)),
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
          <TabsTab value="/settings" nativeButton={false} render={<a href="/settings" />}>
            Profile
          </TabsTab>
        </TabsList>
      </Tabs>,
    )

    expect(complained()).toBe(false)
  })
})
