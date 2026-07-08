import * as React from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { useForm } from 'react-hook-form'
import {
  BarChart3,
  Bell,
  FileText,
  LayoutDashboard,
  Moon,
  Settings,
  Sun,
  Users,
} from 'lucide-react'
import {
  AlertDialog,
  AlertDialogClose,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
  AppShell,
  Avatar,
  AvatarFallback,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Checkbox,
  type ColumnDef,
  DataTable,
  DatePicker,
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Field,
  FieldControl,
  FieldLabel,
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  IconButton,
  Input,
  NumberInput,
  Popover,
  PopoverContent,
  PopoverDescription,
  PopoverTitle,
  PopoverTrigger,
  Progress,
  RadioGroup,
  RadioItem,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Separator,
  Sidebar,
  SidebarContent,
  SidebarHeader,
  SidebarNav,
  SidebarNavItem,
  Skeleton,
  StatCard,
  Switch,
  Tabs,
  TabsList,
  TabsPanel,
  TabsTab,
  Textarea,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
  Topbar,
  TopbarActions,
  TopbarTitle,
  useTheme,
  useToast,
} from '#/components/ui'

export const Route = createFileRoute('/ui')({ component: UiShowcase })

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card className="p-6">
      <h2 className="mb-4 font-display text-base font-medium tracking-tight">{title}</h2>
      <div className="flex flex-wrap items-start gap-4">{children}</div>
    </Card>
  )
}

type Row = { supplier: string; category: string; amount: number; status: string }
const ROWS: Array<Row> = [
  { supplier: 'NordicCloud ApS', category: 'Technology', amount: 12500, status: 'verified' },
  { supplier: 'Acme Legal', category: 'Professional Services', amount: 4200, status: 'ai_categorized' },
  { supplier: 'PrintCo', category: 'Office Supplies', amount: 320, status: 'uncategorized' },
  { supplier: 'BuildRight', category: 'Facilities', amount: 8800, status: 'verified' },
  { supplier: 'DataFeed Inc', category: 'Technology', amount: 1500, status: 'ai_categorized' },
]
const COLUMNS: Array<ColumnDef<Row>> = [
  { accessorKey: 'supplier', header: 'Supplier' },
  { accessorKey: 'category', header: 'Category' },
  {
    accessorKey: 'amount',
    header: 'Amount',
    meta: { align: 'right' },
    cell: ({ getValue }) => <span className="tabular-nums">{getValue<number>().toLocaleString()} kr</span>,
  },
  {
    accessorKey: 'status',
    header: 'Status',
    enableSorting: false,
    cell: ({ getValue }) => {
      const status = getValue<string>()
      return (
        <Badge variant={status === 'verified' ? 'success' : status === 'ai_categorized' ? 'info' : 'default'}>
          {status}
        </Badge>
      )
    },
  },
]

type VendorForm = { vendor: string; email: string }

function FormDemo() {
  const toast = useToast()
  const form = useForm<VendorForm>({ defaultValues: { vendor: '', email: '' } })

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit((values) => toast.add({ title: `Saved ${values.vendor}` }))}
        className="grid w-full gap-4 sm:grid-cols-2"
      >
        <FormField
          control={form.control}
          name="vendor"
          rules={{ required: 'Vendor name is required' }}
          render={({ field }) => (
            <FormItem>
              <FormLabel>Vendor name</FormLabel>
              <FormControl>
                <Input placeholder="Acme A/S" {...field} />
              </FormControl>
              <FormDescription>The supplier's legal name.</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="email"
          rules={{
            required: 'Email is required',
            pattern: { value: /^[^@\s]+@[^@\s]+\.[^@\s]+$/, message: 'Enter a valid email' },
          }}
          render={({ field }) => (
            <FormItem>
              <FormLabel>Billing email</FormLabel>
              <FormControl>
                <Input type="email" placeholder="billing@acme.dk" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <div className="sm:col-span-2">
          <Button type="submit">Save vendor</Button>
        </div>
      </form>
    </Form>
  )
}

function UiShowcase() {
  const { theme, toggleTheme } = useTheme()
  const toast = useToast()
  const [date, setDate] = React.useState<Date | undefined>()
  const [amount, setAmount] = React.useState<string>('12500')

  return (
    <AppShell
      sidebar={
        <Sidebar>
          <SidebarHeader>
            <div className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground">
              <BarChart3 className="size-4" />
            </div>
            <span className="font-display text-lg font-semibold tracking-tight">Spendly</span>
          </SidebarHeader>
          <SidebarContent>
            <SidebarNav>
              <SidebarNavItem icon={<LayoutDashboard />} active>
                Dashboard
              </SidebarNavItem>
              <SidebarNavItem icon={<FileText />}>Invoices</SidebarNavItem>
              <SidebarNavItem icon={<Users />}>Vendors</SidebarNavItem>
              <SidebarNavItem icon={<Settings />}>Settings</SidebarNavItem>
            </SidebarNav>
          </SidebarContent>
        </Sidebar>
      }
      header={
        <Topbar>
          <TopbarTitle>UI Library</TopbarTitle>
          <TopbarActions>
            <IconButton aria-label="Notifications" variant="ghost">
              <Bell />
            </IconButton>
            <IconButton aria-label="Toggle theme" variant="outline" onClick={toggleTheme}>
              {theme === 'dark' ? <Sun /> : <Moon />}
            </IconButton>
            <Avatar>
              <AvatarFallback>HS</AvatarFallback>
            </Avatar>
          </TopbarActions>
        </Topbar>
      }
    >
      <div className="flex flex-col gap-6">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <StatCard icon={<BarChart3 />} label="Total product insights" value="758,925" />
          <StatCard icon={<FileText />} label="Total revenue in 2025" value="$958,925" />
          <StatCard icon={<Users />} label="Active vendors" value="1,204" />
        </div>

        <Section title="Buttons">
          <Button>Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="outline">Outline</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="destructive">Destructive</Button>
          <Button variant="inverted">Inverted</Button>
          <Button size="sm">Small</Button>
          <Button size="lg">Large</Button>
          <Button disabled>Disabled</Button>
        </Section>

        <Section title="Badges">
          <Badge>Default</Badge>
          <Badge variant="primary">Primary</Badge>
          <Badge variant="outline">Outline</Badge>
          <Badge variant="success">Verified</Badge>
          <Badge variant="info">AI</Badge>
          <Badge variant="warning">Pending</Badge>
          <Badge variant="destructive">Failed</Badge>
        </Section>

        <Section title="Form controls">
          <div className="grid w-full gap-4 sm:grid-cols-2">
            <Field>
              <FieldLabel>Company name</FieldLabel>
              <FieldControl placeholder="Acme A/S" />
            </Field>
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium">Category</label>
              <Select defaultValue="Technology">
                <SelectTrigger>
                  <SelectValue placeholder="Pick a category" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Technology">Technology</SelectItem>
                  <SelectItem value="Facilities">Facilities</SelectItem>
                  <SelectItem value="Professional Services">Professional Services</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Input placeholder="Plain input" />
            <Textarea placeholder="Notes…" />
          </div>
          <div className="flex flex-wrap items-center gap-6">
            <label className="flex items-center gap-2 text-sm">
              <Checkbox defaultChecked /> Accept
            </label>
            <label className="flex items-center gap-2 text-sm">
              <Switch defaultChecked /> Sync enabled
            </label>
            <RadioGroup defaultValue="a" className="flex-row gap-4">
              <label className="flex items-center gap-2 text-sm">
                <RadioItem value="a" /> Monthly
              </label>
              <label className="flex items-center gap-2 text-sm">
                <RadioItem value="b" /> Yearly
              </label>
            </RadioGroup>
          </div>
        </Section>

        <Section title="Number & date">
          <div className="grid w-full gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium">Amount</label>
              <NumberInput
                value={amount}
                onValueChange={(v) => setAmount(v.value)}
                thousandSeparator=","
                decimalScale={2}
                fixedDecimalScale
                prefix="kr "
                placeholder="kr 0.00"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium">Invoice date</label>
              <DatePicker value={date} onChange={setDate} />
            </div>
          </div>
        </Section>

        <Section title="Form (react-hook-form)">
          <FormDemo />
        </Section>

        <Section title="Overlays">
          <Dialog>
            <DialogTrigger render={<Button variant="outline">Open dialog</Button>} />
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Verify categorization</DialogTitle>
                <DialogDescription>Confirm the AI-assigned category for this line.</DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <DialogClose render={<Button variant="ghost">Cancel</Button>} />
                <Button>Verify</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          <AlertDialog>
            <AlertDialogTrigger render={<Button variant="destructive">Delete</Button>} />
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Deactivate company?</AlertDialogTitle>
                <AlertDialogDescription>
                  This soft-deactivates the company. Financial data is retained.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogClose render={<Button variant="ghost">Cancel</Button>} />
                <AlertDialogClose render={<Button variant="destructive">Deactivate</Button>} />
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>

          <DropdownMenu>
            <DropdownMenuTrigger render={<Button variant="outline">Actions</Button>} />
            <DropdownMenuContent>
              <DropdownMenuItem>
                <FileText /> View invoice
              </DropdownMenuItem>
              <DropdownMenuItem>
                <Users /> Reassign vendor
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem>Delete</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <Popover>
            <PopoverTrigger render={<Button variant="outline">Popover</Button>} />
            <PopoverContent>
              <PopoverTitle>Filter</PopoverTitle>
              <PopoverDescription>Narrow the results by status or period.</PopoverDescription>
            </PopoverContent>
          </Popover>

          <Tooltip>
            <TooltipTrigger render={<Button variant="ghost">Hover me</Button>} />
            <TooltipContent>Tooltips explain things</TooltipContent>
          </Tooltip>

          <Button variant="secondary" onClick={() => toast.add({ title: 'Saved', description: 'Your changes are in.' })}>
            Show toast
          </Button>
        </Section>

        <Section title="Tabs">
          <Tabs defaultValue="overview" className="w-full">
            <TabsList>
              <TabsTab value="overview">Overview</TabsTab>
              <TabsTab value="activity">Activity</TabsTab>
              <TabsTab value="settings">Settings</TabsTab>
            </TabsList>
            <TabsPanel value="overview" className="text-sm text-muted-foreground">
              Overview panel content.
            </TabsPanel>
            <TabsPanel value="activity" className="text-sm text-muted-foreground">
              Activity panel content.
            </TabsPanel>
            <TabsPanel value="settings" className="text-sm text-muted-foreground">
              Settings panel content.
            </TabsPanel>
          </Tabs>
        </Section>

        <Section title="Feedback & display">
          <div className="w-full max-w-sm">
            <Progress value={64} showValue label="Categorization progress" />
          </div>
          <Separator />
          <div className="flex w-full flex-col gap-2">
            <Skeleton className="h-4 w-48" />
            <Skeleton className="h-4 w-32" />
          </div>
        </Section>

        <Card>
          <CardHeader>
            <CardTitle>Recent spend</CardTitle>
            <CardDescription>Sortable, paginated data table.</CardDescription>
          </CardHeader>
          <CardContent>
            <DataTable columns={COLUMNS} data={ROWS} getRowId={(r) => r.supplier} pageSize={4} />
          </CardContent>
        </Card>
      </div>
    </AppShell>
  )
}
