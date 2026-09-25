import * as React from 'react'
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useForm } from 'react-hook-form'
import {
  Button,
  CodeInput,
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
  CurrencyInput,
  DataTable,
  DatePicker,
  Dialog,
  DialogContent,
  DialogTitle,
  DialogTrigger,
  Drawer,
  DrawerContent,
  DrawerTitle,
  DrawerTrigger,
  Field,
  FieldControl,
  FieldLabel,
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  Input,
  LoadingScreen,
  NumberInput,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  ToastProvider,
  useToast,
} from './index'
import type { ColumnDef } from './index'

describe('Button', () => {
  it('renders variant-based classes from one component', () => {
    const { rerender } = render(<Button variant="primary">Go</Button>)
    expect(screen.getByRole('button', { name: 'Go' }).className).toContain(
      'bg-primary',
    )
    rerender(<Button variant="outline">Go</Button>)
    expect(screen.getByRole('button', { name: 'Go' }).className).toContain(
      'border',
    )
  })

  it('merges a caller className', () => {
    render(<Button className="w-full">X</Button>)
    expect(screen.getByRole('button', { name: 'X' }).className).toContain(
      'w-full',
    )
  })
})

describe('Field', () => {
  it('associates the label with the control', () => {
    render(
      <Field>
        <FieldLabel>Company name</FieldLabel>
        <FieldControl />
      </Field>,
    )
    expect(screen.getByLabelText('Company name')).toBeInstanceOf(
      HTMLInputElement,
    )
  })
})

describe('Dialog', () => {
  it('opens from the trigger and closes on Escape', async () => {
    render(
      <Dialog>
        <DialogTrigger render={<Button>Open</Button>} />
        <DialogContent>
          <DialogTitle>Verify line</DialogTitle>
        </DialogContent>
      </Dialog>,
    )
    expect(screen.queryByText('Verify line')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Open' }))
    expect(await screen.findByText('Verify line')).toBeTruthy()
    fireEvent.keyDown(document.activeElement ?? document.body, {
      key: 'Escape',
    })
    await waitFor(() => expect(screen.queryByText('Verify line')).toBeNull())
  })
})

describe('Drawer', () => {
  it('opens from its anchored side, moves focus inside, and closes on Escape', async () => {
    render(
      <Drawer>
        <DrawerTrigger render={<Button>Open panel</Button>} />
        <DrawerContent side="right">
          <DrawerTitle>Entry detail</DrawerTitle>
        </DrawerContent>
      </Drawer>,
    )
    expect(screen.queryByText('Entry detail')).toBeNull()

    const trigger = screen.getByRole('button', { name: 'Open panel' })
    fireEvent.click(trigger)
    const panel = await screen.findByText('Entry detail')
    expect(panel.closest('[class*="right-0"]')).toBeTruthy()
    await waitFor(() => expect(document.activeElement).not.toBe(trigger))

    fireEvent.keyDown(document.activeElement ?? document.body, {
      key: 'Escape',
    })
    await waitFor(() => expect(screen.queryByText('Entry detail')).toBeNull())
    await waitFor(() => expect(document.activeElement).toBe(trigger))
  })

  it('dismisses via its close control', async () => {
    render(
      <Drawer>
        <DrawerTrigger render={<Button>Open panel</Button>} />
        <DrawerContent>
          <DrawerTitle>Entry detail</DrawerTitle>
        </DrawerContent>
      </Drawer>,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Open panel' }))
    await screen.findByText('Entry detail')
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    await waitFor(() => expect(screen.queryByText('Entry detail')).toBeNull())
  })

  it('renders a wide drawer when asked for one', () => {
    render(
      <Drawer open>
        <DrawerContent size="wide" aria-label="Wide panel">
          <p>content</p>
        </DrawerContent>
      </Drawer>,
    )
    const panel = screen.getByLabelText('Wide panel')
    expect(panel.className).toContain('max-w-[1100px]')
    expect(panel.className).not.toContain('max-w-md')
  })
})

type Row = { name: string; amount: number }
const columns: Array<ColumnDef<Row>> = [
  { accessorKey: 'name', header: 'Name' },
  { accessorKey: 'amount', header: 'Amount' },
]
const rows: Array<Row> = [
  { name: 'Charlie', amount: 30 },
  { name: 'Alice', amount: 10 },
  { name: 'Bob', amount: 20 },
]

describe('DataTable', () => {
  it('sorts by a column and paginates', async () => {
    render(
      <DataTable
        columns={columns}
        data={rows}
        getRowId={(r) => r.name}
        pageSize={2}
      />,
    )

    let cells = screen.getAllByRole('cell')
    expect(cells[0].textContent).toBe('Charlie')

    fireEvent.click(screen.getByRole('button', { name: /Name/ }))
    cells = screen.getAllByRole('cell')
    expect(cells[0].textContent).toBe('Alice')

    fireEvent.click(screen.getByRole('button', { name: 'Next page' }))
    cells = screen.getAllByRole('cell')
    expect(cells[0].textContent).toBe('Charlie')
  })
})

function ToastDemo() {
  const toast = useToast()
  return <Button onClick={() => toast.add({ title: 'Saved' })}>Notify</Button>
}

describe('Toast', () => {
  it('shows a toast when added', async () => {
    render(
      <ToastProvider>
        <ToastDemo />
      </ToastProvider>,
    )
    expect(screen.queryByText('Saved')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Notify' }))
    expect(await screen.findByText('Saved')).toBeTruthy()
  })
})

describe('NumberInput', () => {
  it('formats the value with separators, decimals and a prefix', () => {
    render(
      <NumberInput
        value={1234567.5}
        thousandSeparator=","
        decimalScale={2}
        fixedDecimalScale
        prefix="kr "
        readOnly
      />,
    )
    expect(screen.getByDisplayValue('kr 1,234,567.50')).toBeTruthy()
  })
})

describe('CurrencyInput', () => {
  it('formats a stored decimal string for its currency', () => {
    render(
      <CurrencyInput
        currency="DKK"
        value="1234.50000"
        onChange={() => {}}
        readOnly
      />,
    )
    expect(screen.getByDisplayValue(/1,234\.50/)).toBeTruthy()
  })

  it('hands the caller a number, never the formatted string', () => {
    const onChange = vi.fn()
    render(<CurrencyInput currency="DKK" value={null} onChange={onChange} />)

    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: '1234.5' },
    })

    expect(onChange).toHaveBeenCalled()
    expect(typeof onChange.mock.lastCall?.[0]).toBe('number')
    expect(onChange.mock.lastCall?.[0]).toBe(1234.5)
  })

  it('reports an empty field as null rather than zero', () => {
    const onChange = vi.fn()
    render(<CurrencyInput currency="DKK" value={12} onChange={onChange} />)

    fireEvent.change(screen.getByRole('textbox'), { target: { value: '' } })

    expect(onChange).toHaveBeenLastCalledWith(null)
  })

  it('never reports NaN, whatever is typed', () => {
    const onChange = vi.fn()
    render(<CurrencyInput currency="DKK" value={null} onChange={onChange} />)

    for (const typed of ['1,5', 'abc', '.', '-', '1.2.3']) {
      fireEvent.change(screen.getByRole('textbox'), {
        target: { value: typed },
      })
    }

    for (const call of onChange.mock.calls) {
      expect(Number.isNaN(call[0])).toBe(false)
    }
  })

  it('renders a plain number when the invoice states no currency', () => {
    render(
      <CurrencyInput
        currency={null}
        value={1234.5}
        onChange={() => {}}
        readOnly
      />,
    )
    expect(screen.getByDisplayValue('1,234.50')).toBeTruthy()
  })

  it('keeps a negative, because a credit note reduces spend', () => {
    const onChange = vi.fn()
    render(<CurrencyInput currency="DKK" value={null} onChange={onChange} />)

    fireEvent.change(screen.getByRole('textbox'), { target: { value: '-50' } })

    expect(onChange).toHaveBeenLastCalledWith(-50)
  })

  it('right-aligns with tabular figures, so a column can be scanned', () => {
    render(
      <CurrencyInput currency="DKK" value={1} onChange={() => {}} readOnly />,
    )
    const input = screen.getByRole('textbox')
    expect(input.className).toContain('text-right')
    expect(input.className).toContain('tabular-nums')
  })
})

function CodeHost({
  length,
  onComplete,
  disabled,
  initial = '',
}: {
  length?: number
  onComplete?: (code: string) => void
  disabled?: boolean
  initial?: string
}) {
  const [code, setCode] = React.useState(initial)
  return (
    <>
      <label htmlFor="code">Verification code</label>
      <CodeInput
        id="code"
        value={code}
        onChange={setCode}
        onComplete={onComplete}
        length={length}
        disabled={disabled}
      />
    </>
  )
}

const cells = () => document.querySelectorAll('[data-slot="code-input-cell"]')
const cellText = () => Array.from(cells()).map((cell) => cell.textContent)

describe('CodeInput', () => {
  it('renders one cell per digit, at the requested length', () => {
    const { unmount } = render(<CodeHost />)
    expect(cells().length).toBe(6)
    unmount()

    render(<CodeHost length={4} />)
    expect(cells().length).toBe(4)
  })

  it('fills only its own cells for a value shorter than the length', () => {
    render(<CodeHost initial="12" />)
    expect(cellText()).toEqual(['1', '2', '', '', '', ''])
  })

  it('is empty with no placeholder digit', () => {
    render(<CodeHost />)
    expect(cellText().join('')).toBe('')
  })

  it('reports the accumulated code as one string, not per cell', () => {
    render(<CodeHost />)
    const field = screen.getByLabelText<HTMLInputElement>('Verification code')

    fireEvent.change(field, { target: { value: '1' } })
    fireEvent.change(field, { target: { value: '12' } })
    fireEvent.change(field, { target: { value: '123' } })

    expect(field.value).toBe('123')
    expect(cellText()).toEqual(['1', '2', '3', '', '', ''])
  })

  it('rejects a non-digit without changing the code', () => {
    render(<CodeHost initial="12" />)
    const field = screen.getByLabelText<HTMLInputElement>('Verification code')

    fireEvent.change(field, { target: { value: '12a' } })

    expect(field.value).toBe('12')
    expect(cellText()).toEqual(['1', '2', '', '', '', ''])
  })

  it('clears the last digit on Backspace', () => {
    render(<CodeHost initial="123" />)
    const field = screen.getByLabelText<HTMLInputElement>('Verification code')

    fireEvent.keyDown(field, { key: 'Backspace' })
    expect(field.value).toBe('12')

    fireEvent.keyDown(field, { key: 'Backspace' })
    fireEvent.keyDown(field, { key: 'Backspace' })
    expect(field.value).toBe('')

    fireEvent.keyDown(field, { key: 'Backspace' })
    expect(field.value).toBe('')
  })

  it('does not move the entry point on an arrow key', () => {
    render(<CodeHost initial="123" />)
    const field = screen.getByLabelText<HTMLInputElement>('Verification code')

    fireEvent.keyDown(field, { key: 'ArrowLeft' })
    fireEvent.keyDown(field, { key: 'ArrowRight' })

    expect(field.value).toBe('123')
    expect(cellText()).toEqual(['1', '2', '3', '', '', ''])
  })

  it('distributes a pasted code across the cells, grouped or not', () => {
    const { unmount } = render(<CodeHost />)
    fireEvent.change(screen.getByLabelText('Verification code'), {
      target: { value: '123456' },
    })
    expect(cellText()).toEqual(['1', '2', '3', '4', '5', '6'])
    unmount()

    render(<CodeHost />)
    fireEvent.change(screen.getByLabelText('Verification code'), {
      target: { value: '123 456' },
    })
    expect(cellText()).toEqual(['1', '2', '3', '4', '5', '6'])
  })

  it('discards pasted digits beyond the last cell', () => {
    render(<CodeHost />)
    const field = screen.getByLabelText<HTMLInputElement>('Verification code')

    fireEvent.change(field, { target: { value: '1234567890' } })

    expect(field.value).toBe('123456')
    expect(cellText()).toEqual(['1', '2', '3', '4', '5', '6'])
  })

  it('reports completion once, on the transition into a complete code', () => {
    const onComplete = vi.fn()
    render(<CodeHost initial="12345" onComplete={onComplete} />)
    const field = screen.getByLabelText<HTMLInputElement>('Verification code')

    expect(onComplete).not.toHaveBeenCalled()

    fireEvent.change(field, { target: { value: '123456' } })
    expect(onComplete).toHaveBeenCalledTimes(1)
    expect(onComplete).toHaveBeenCalledWith('123456')

    fireEvent.focus(field)
    fireEvent.blur(field)
    expect(onComplete).toHaveBeenCalledTimes(1)
  })

  it('reports completion for a code that arrives in one paste', () => {
    const onComplete = vi.fn()
    render(<CodeHost onComplete={onComplete} />)

    fireEvent.change(screen.getByLabelText('Verification code'), {
      target: { value: '654321' },
    })

    expect(onComplete).toHaveBeenCalledTimes(1)
    expect(onComplete).toHaveBeenCalledWith('654321')
  })

  it('reports completion again after the code is broken and remade', () => {
    const onComplete = vi.fn()
    render(<CodeHost initial="123456" onComplete={onComplete} />)
    const field = screen.getByLabelText<HTMLInputElement>('Verification code')
    expect(onComplete).toHaveBeenCalledTimes(1)

    fireEvent.keyDown(field, { key: 'Backspace' })
    fireEvent.change(field, { target: { value: '123459' } })

    expect(onComplete).toHaveBeenCalledTimes(2)
    expect(onComplete).toHaveBeenLastCalledWith('123459')
  })

  it('is one labelled tab stop offering one-time-code autofill', () => {
    render(<CodeHost />)
    const field = screen.getByLabelText<HTMLInputElement>('Verification code')

    expect(field.getAttribute('autocomplete')).toBe('one-time-code')
    expect(field.getAttribute('inputmode')).toBe('numeric')
    expect(document.querySelectorAll('input').length).toBe(1)
    expect(field.tabIndex).toBe(0)
  })

  it('blocks entry when disabled', () => {
    render(<CodeHost disabled initial="12" />)
    const field = screen.getByLabelText<HTMLInputElement>('Verification code')

    expect(field.disabled).toBe(true)
    fireEvent.change(field, { target: { value: '123' } })
    expect(cellText()).toEqual(['1', '2', '', '', '', ''])
  })
})

function VendorForm({ onValid }: { onValid: (v: { vendor: string }) => void }) {
  const form = useForm<{ vendor: string }>({ defaultValues: { vendor: '' } })
  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onValid)}>
        <FormField
          control={form.control}
          name="vendor"
          rules={{ required: 'Vendor name is required' }}
          render={({ field }) => (
            <FormItem>
              <FormLabel>Vendor name</FormLabel>
              <FormControl>
                <Input {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <Button type="submit">Save</Button>
      </form>
    </Form>
  )
}

describe('Form', () => {
  it('shows the RHF validation error, links the label, then submits when valid', async () => {
    const onValid = vi.fn()
    render(<VendorForm onValid={onValid} />)

    const control = screen.getByLabelText('Vendor name')
    expect(control).toBeInstanceOf(HTMLInputElement)

    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Vendor name is required')).toBeTruthy()
    expect(onValid).not.toHaveBeenCalled()
    expect(control.getAttribute('aria-invalid')).toBe('true')

    fireEvent.change(control, { target: { value: 'Acme A/S' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(onValid).toHaveBeenCalledTimes(1))
    expect(onValid.mock.calls[0][0].vendor).toBe('Acme A/S')
    expect(screen.queryByText('Vendor name is required')).toBeNull()
  })
})

describe('LoadingScreen', () => {
  it('exposes a status role and the message for assistive tech', () => {
    render(<LoadingScreen message="Preparing your workspace…" />)
    const status = screen.getByRole('status')
    expect(status).toBeTruthy()
    expect(status.textContent).toContain('Preparing your workspace…')
  })

  it('shows the Steelyard lockup, rendered rather than typed', () => {
    const { container } = render(<LoadingScreen />)
    expect(
      screen.getByRole('img', { name: 'Steelyard' }).tagName.toLowerCase(),
    ).toBe('svg')
    expect(container.textContent).not.toMatch(/steelyard/i)
  })
})

describe('DatePicker', () => {
  it('opens the calendar and reports the selected date', async () => {
    const onChange = vi.fn()
    render(
      <DatePicker onChange={onChange} defaultMonth={new Date(2025, 0, 1)} />,
    )

    fireEvent.click(screen.getByRole('button', { name: /Pick a date/ }))
    const day = await screen.findByText('15')
    fireEvent.click(day)

    expect(onChange).toHaveBeenCalledTimes(1)
    const picked = onChange.mock.calls[0][0] as Date
    expect(picked.getDate()).toBe(15)
    expect(picked.getMonth()).toBe(0)
  })

  it('wears the same field shape as the selects it sits beside', () => {
    render(
      <>
        <DatePicker />
        <Select value="">
          <SelectTrigger aria-label="Company">
            <SelectValue placeholder="All companies" />
          </SelectTrigger>
        </Select>
      </>,
    )

    const trigger = screen.getByRole('button', { name: /Pick a date/ })
    for (const shared of ['rounded-md', 'h-10', 'border-input', 'bg-card']) {
      expect(trigger.className).toContain(shared)
      expect(
        screen.getByRole('combobox', { name: 'Company' }).className,
      ).toContain(shared)
    }
    expect(trigger.className).not.toContain('rounded-full')
  })
})

const FRUITS = ['Apple', 'Banana', 'Blueberry', 'Cherry']

function ComboboxDemo({
  onValueChange,
  loading,
}: {
  onValueChange?: (value: string | null) => void
  loading?: boolean
}) {
  return (
    <Combobox items={FRUITS} onValueChange={onValueChange}>
      <ComboboxInput aria-label="Fruit" placeholder="Search fruit" />
      <ComboboxContent loading={loading}>
        <ComboboxEmpty>No fruit found.</ComboboxEmpty>
        <ComboboxList>
          {(item: string) => (
            <ComboboxItem key={item} value={item}>
              {item}
            </ComboboxItem>
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  )
}

function openCombobox(): HTMLInputElement {
  const input: HTMLInputElement = screen.getByRole('combobox', {
    name: 'Fruit',
  })
  input.focus()
  fireEvent.pointerDown(input, { pointerType: 'mouse' })
  fireEvent.mouseDown(input)
  fireEvent.mouseUp(input)
  fireEvent.click(input)
  return input
}

describe('Combobox', () => {
  it('filters the options as the user types, case-insensitively', async () => {
    render(<ComboboxDemo />)
    const input = openCombobox()
    expect(await screen.findByRole('option', { name: 'Apple' })).toBeTruthy()

    fireEvent.change(input, { target: { value: 'bl' } })

    await waitFor(() =>
      expect(screen.queryByRole('option', { name: 'Apple' })).toBeNull(),
    )
    expect(screen.getByRole('option', { name: 'Blueberry' })).toBeTruthy()
    expect(screen.queryByRole('option', { name: 'Banana' })).toBeNull()
  })

  it('reports the selected value once and closes the popup', async () => {
    const onValueChange = vi.fn()
    render(<ComboboxDemo onValueChange={onValueChange} />)
    const input = openCombobox()

    fireEvent.click(await screen.findByRole('option', { name: 'Cherry' }))

    await waitFor(() =>
      expect(screen.queryByRole('option', { name: 'Cherry' })).toBeNull(),
    )
    expect(onValueChange).toHaveBeenCalledTimes(1)
    expect(onValueChange.mock.calls[0][0]).toBe('Cherry')
    expect(input.value).toBe('Cherry')
  })

  it('selects with the keyboard and closes on Escape without changing the value', async () => {
    const onValueChange = vi.fn()
    render(<ComboboxDemo onValueChange={onValueChange} />)
    const input = openCombobox()
    await screen.findByRole('option', { name: 'Apple' })

    fireEvent.keyDown(input, { key: 'Escape' })
    await waitFor(() =>
      expect(screen.queryByRole('option', { name: 'Apple' })).toBeNull(),
    )
    expect(onValueChange).not.toHaveBeenCalled()

    fireEvent.keyDown(input, { key: 'ArrowDown' })
    await screen.findByRole('option', { name: 'Apple' })
    fireEvent.keyDown(input, { key: 'Enter' })

    await waitFor(() => expect(onValueChange).toHaveBeenCalledTimes(1))
    expect(onValueChange.mock.calls[0][0]).toBe('Apple')
  })

  it('shows the empty state when nothing matches', async () => {
    render(<ComboboxDemo />)
    const input = openCombobox()
    await screen.findByRole('option', { name: 'Apple' })

    fireEvent.change(input, { target: { value: 'zzz' } })

    expect(await screen.findByText('No fruit found.')).toBeTruthy()
    expect(screen.queryAllByRole('option')).toHaveLength(0)
  })

  it('marks itself as opening a list', () => {
    const { container } = render(<ComboboxDemo />)

    expect(container.querySelector('svg.lucide-chevron-down')).toBeTruthy()
  })

  it('drops the chevron when the input lives inside the popup', () => {
    const { container } = render(
      <Combobox items={FRUITS}>
        <ComboboxInput aria-label="Fruit" hideIcon />
      </Combobox>,
    )

    expect(container.querySelector('svg.lucide-chevron-down')).toBeNull()
  })

  it('renders a start adornment without covering the input', () => {
    render(
      <Combobox items={FRUITS}>
        <ComboboxInput aria-label="Fruit" startAdornment={<span>DK</span>} />
      </Combobox>,
    )

    const adornment = screen.getByText('DK')
    expect(adornment.parentElement?.className).toContain('pointer-events-none')
    expect(screen.getByRole('combobox', { name: 'Fruit' }).className).toContain(
      'pl-10',
    )
  })

  it('shows a loading indication instead of the list while items load', async () => {
    render(<ComboboxDemo loading />)
    openCombobox()

    const status = await screen.findByRole('status')
    expect(status.textContent).toContain('Loading…')
    expect(screen.queryAllByRole('option')).toHaveLength(0)
    expect(screen.queryByText('No fruit found.')).toBeNull()
  })

  it('associates the input with a surrounding Field label', () => {
    render(
      <Field>
        <FieldLabel>Vendor</FieldLabel>
        <Combobox items={FRUITS}>
          <ComboboxInput />
        </Combobox>
      </Field>,
    )
    const control = screen.getByRole('combobox', { name: 'Vendor' })
    expect(control).toBeInstanceOf(HTMLInputElement)
  })
})

describe('Select', () => {
  const ROLES = [
    { value: 'org:admin', label: 'Admin' },
    { value: 'org:member', label: 'Member' },
  ]

  function renderSelect(items?: typeof ROLES) {
    render(
      <Select items={ROLES} value="org:member">
        <SelectTrigger aria-label="Role">
          <SelectValue items={items} />
        </SelectTrigger>
        <SelectContent>
          {ROLES.map((role) => (
            <SelectItem key={role.value} value={role.value}>
              {role.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>,
    )
    return screen.getByLabelText('Role')
  }

  it('shows the item label rather than the raw value when given items', () => {
    expect(renderSelect(ROLES).textContent).toBe('Member')
  })

  it('falls back to the raw value when no items are given', () => {
    expect(renderSelect(undefined).textContent).toBe('org:member')
  })

  it('shows the placeholder when nothing is selected', () => {
    render(
      <Select items={ROLES} value="">
        <SelectTrigger aria-label="Role">
          <SelectValue items={ROLES} placeholder="Choose a role" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="org:admin">Admin</SelectItem>
        </SelectContent>
      </Select>,
    )
    expect(screen.getByLabelText('Role').textContent).toBe('Choose a role')
  })
})
