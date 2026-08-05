import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useForm } from 'react-hook-form'
import {
  Button,
  type ColumnDef,
  DataTable,
  DatePicker,
  Dialog,
  DialogContent,
  DialogTitle,
  DialogTrigger,
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
