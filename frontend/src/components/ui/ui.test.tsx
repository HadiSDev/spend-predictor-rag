import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useForm } from 'react-hook-form'
import {
  Button,
  type ColumnDef,
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
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

describe('Button', () => {
  it('renders variant-based classes from one component', () => {
    const { rerender } = render(<Button variant="primary">Go</Button>)
    expect(screen.getByRole('button', { name: 'Go' }).className).toContain('bg-primary')
    rerender(<Button variant="outline">Go</Button>)
    expect(screen.getByRole('button', { name: 'Go' }).className).toContain('border')
  })

  it('merges a caller className', () => {
    render(<Button className="w-full">X</Button>)
    expect(screen.getByRole('button', { name: 'X' }).className).toContain('w-full')
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
    // getByLabelText only succeeds when the label is programmatically linked.
    expect(screen.getByLabelText('Company name')).toBeInstanceOf(HTMLInputElement)
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
    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' })
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
    // Anchored right, not centred like Dialog.
    expect(panel.closest('[class*="right-0"]')).toBeTruthy()
    // Focus is trapped inside the panel, not left on the trigger behind it.
    await waitFor(() => expect(document.activeElement).not.toBe(trigger))

    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' })
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
    // The default drawer is max-w-md; the split layout needs room for a PDF
    // beside a field list.
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
    render(<DataTable columns={columns} data={rows} getRowId={(r) => r.name} pageSize={2} />)

    // pageSize 2 → first page has 2 of 3 rows in original order.
    let cells = screen.getAllByRole('cell')
    expect(cells[0].textContent).toBe('Charlie')

    // Sort by Name asc → Alice first.
    fireEvent.click(screen.getByRole('button', { name: /Name/ }))
    cells = screen.getAllByRole('cell')
    expect(cells[0].textContent).toBe('Alice')

    // Page 2 shows the 3rd sorted row (Charlie).
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

    // Label is programmatically associated with the control.
    const control = screen.getByLabelText('Vendor name')
    expect(control).toBeInstanceOf(HTMLInputElement)

    // Submitting empty surfaces the rule's message and blocks onValid.
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Vendor name is required')).toBeTruthy()
    expect(onValid).not.toHaveBeenCalled()
    expect(control.getAttribute('aria-invalid')).toBe('true')

    // Filling a value clears the error and lets the submit through.
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
})

describe('DatePicker', () => {
  it('opens the calendar and reports the selected date', async () => {
    const onChange = vi.fn()
    render(<DatePicker onChange={onChange} defaultMonth={new Date(2025, 0, 1)} />)

    fireEvent.click(screen.getByRole('button', { name: /Pick a date/ }))
    // The calendar grid appears in the popover.
    const day = await screen.findByText('15')
    fireEvent.click(day)

    expect(onChange).toHaveBeenCalledTimes(1)
    const picked = onChange.mock.calls[0][0] as Date
    expect(picked.getDate()).toBe(15)
    expect(picked.getMonth()).toBe(0)
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

/** Opens the popup the way a pointer does — Base UI listens below `click`. */
function openCombobox(): HTMLInputElement {
  const input: HTMLInputElement = screen.getByRole('combobox', { name: 'Fruit' })
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

    await waitFor(() => expect(screen.queryByRole('option', { name: 'Apple' })).toBeNull())
    expect(screen.getByRole('option', { name: 'Blueberry' })).toBeTruthy()
    expect(screen.queryByRole('option', { name: 'Banana' })).toBeNull()
  })

  it('reports the selected value once and closes the popup', async () => {
    const onValueChange = vi.fn()
    render(<ComboboxDemo onValueChange={onValueChange} />)
    const input = openCombobox()

    fireEvent.click(await screen.findByRole('option', { name: 'Cherry' }))

    await waitFor(() => expect(screen.queryByRole('option', { name: 'Cherry' })).toBeNull())
    expect(onValueChange).toHaveBeenCalledTimes(1)
    expect(onValueChange.mock.calls[0][0]).toBe('Cherry')
    expect(input.value).toBe('Cherry')
  })

  it('selects with the keyboard and closes on Escape without changing the value', async () => {
    const onValueChange = vi.fn()
    render(<ComboboxDemo onValueChange={onValueChange} />)
    const input = openCombobox()
    await screen.findByRole('option', { name: 'Apple' })

    // Escape closes without selecting.
    fireEvent.keyDown(input, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('option', { name: 'Apple' })).toBeNull())
    expect(onValueChange).not.toHaveBeenCalled()

    // Arrow down highlights the first option, Enter selects it.
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

  // Without the chevron the control is indistinguishable from a plain Input,
  // and a user has no reason to click it expecting a list — it shipped that way
  // once already, unnoticed, because nothing asserted it.
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
    // The input keeps room for it, so the text never sits under the adornment.
    expect(screen.getByRole('combobox', { name: 'Fruit' }).className).toContain('pl-10')
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
    // Resolving by role + accessible name proves the label is linked to the input.
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
    // SelectValue always passes a function child, so Base UI never consults the
    // root's own `items` — the mapping has to be handed to SelectValue itself.
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
