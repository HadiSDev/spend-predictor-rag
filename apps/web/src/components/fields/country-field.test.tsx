import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { CountryField } from './country-field'

function renderField(value = '') {
  const onChange = vi.fn()
  render(<CountryField value={value} onChange={onChange} />)
  return {
    onChange,
    input: screen.getByRole<HTMLInputElement>('combobox', { name: 'Country' }),
  }
}

describe('CountryField', () => {
  it('shows the country a stored code names', () => {
    const { input } = renderField('DK')

    expect(input.value).toBe('DK — Denmark')
  })

  it('resolves a code saved by the free-text field it replaced', () => {
    const { input } = renderField('dk')

    expect(input.value).toBe('DK — Denmark')
  })

  it('surfaces a code that names no country instead of blanking it', () => {
    const { input } = renderField('ZZ')

    expect(input.value).toBe('Unknown code: ZZ')
  })

  it('emits the canonical uppercase code when a country is picked', async () => {
    const { onChange, input } = renderField()

    fireEvent.click(input)
    fireEvent.change(input, { target: { value: 'sweden' } })
    fireEvent.click(await screen.findByRole('option', { name: 'SE — Sweden' }))

    expect(onChange).toHaveBeenCalledWith('SE')
  })

  it('finds a country by code as readily as by name', async () => {
    const { input } = renderField()

    fireEvent.click(input)
    fireEvent.change(input, { target: { value: 'NL' } })

    expect(
      await screen.findByRole('option', { name: 'NL — Netherlands' }),
    ).toBeTruthy()
  })

  it('finds an accented name typed without the accent', async () => {
    const { input } = renderField()

    fireEvent.click(input)
    fireEvent.change(input, { target: { value: 'curacao' } })

    expect(
      await screen.findByRole('option', { name: 'CW — Curaçao' }),
    ).toBeTruthy()
  })

  it('offers the whole list, not just the currency-issuing countries', async () => {
    const { input } = renderField()

    fireEvent.click(input)
    fireEvent.change(input, { target: { value: 'kenya' } })

    expect(
      await screen.findByRole('option', { name: 'KE — Kenya' }),
    ).toBeTruthy()
  })
})
