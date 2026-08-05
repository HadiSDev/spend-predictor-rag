// Design-system primitives for the ERPSAA-themed admin panel.
// Import from '#/components/ui' (or '@/ui').

export { cn } from './cn'
export { ThemeProvider, useTheme, type Theme } from './theme-provider'

export { Button, buttonVariants, type ButtonProps } from './button'
export { IconButton, type IconButtonProps } from './icon-button'
export { Input, inputClassName } from './input'
export { NumberInput, type NumberInputProps } from './number-input'
export { Textarea } from './textarea'
export {
  Field,
  FieldLabel,
  FieldControl,
  FieldDescription,
  FieldError,
} from './field'
export {
  Form,
  FormField,
  FormItem,
  FormLabel,
  FormControl,
  FormDescription,
  FormMessage,
  useFormField,
} from './form'
export { Checkbox } from './checkbox'
export { RadioGroup, RadioItem } from './radio'
export { Switch } from './switch'
export {
  Select,
  SelectGroup,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  SelectGroupLabel,
  SelectSeparator,
} from './select'

export {
  Dialog,
  DialogTrigger,
  DialogClose,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
} from './dialog'
export {
  AlertDialog,
  AlertDialogTrigger,
  AlertDialogClose,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogFooter,
  AlertDialogTitle,
  AlertDialogDescription,
} from './alert-dialog'
export {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuGroup,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from './dropdown-menu'
export {
  Popover,
  PopoverTrigger,
  PopoverClose,
  PopoverContent,
  PopoverTitle,
  PopoverDescription,
} from './popover'
export { TooltipProvider, Tooltip, TooltipTrigger, TooltipContent } from './tooltip'
export { Tabs, TabsList, TabsTab, TabsPanel } from './tabs'
export { ToastProvider, useToast } from './toast'

export {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
  StatCard,
  type StatCardProps,
} from './card'
export { Badge, badgeVariants, type BadgeProps } from './badge'
export { Avatar, AvatarImage, AvatarFallback } from './avatar'
export { Separator } from './separator'
export { Skeleton } from './skeleton'
export { LoadingScreen, type LoadingScreenProps } from './loading-screen'
export { Progress, type ProgressProps } from './progress'
export {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  TableCaption,
} from './table'
export { Pagination, type PaginationProps } from './pagination'
export { DataTable, type ColumnDef, type DataTableProps } from './data-table'
export { Calendar, type CalendarProps } from './calendar'
export { DatePicker, type DatePickerProps } from './date-picker'

export {
  Sidebar,
  SidebarHeader,
  SidebarContent,
  SidebarFooter,
  SidebarNav,
  SidebarNavItem,
  sidebarNavItemClass,
  type SidebarNavItemProps,
} from './layout/sidebar'
export { Topbar, TopbarTitle, TopbarActions } from './layout/topbar'
export { AppShell, type AppShellProps } from './layout/app-shell'
