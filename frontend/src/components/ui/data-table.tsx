import * as React from 'react'
import {
  type ColumnDef,
  type RowData,
  type SortingState,
  flexRender,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table'
import { ChevronDown, ChevronsUpDown, ChevronUp } from 'lucide-react'
import { cn } from './cn'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from './table'
import { Pagination } from './pagination'

// Per-column presentation carried on the TanStack `meta` field.
declare module '@tanstack/react-table' {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData extends RowData, TValue> {
    align?: 'left' | 'right' | 'center'
    className?: string
  }
}

export type { ColumnDef } from '@tanstack/react-table'

const alignClass = { left: 'text-left', right: 'text-right', center: 'text-center' } as const

export interface DataTableProps<TData> {
  columns: Array<ColumnDef<TData, any>>
  data: Array<TData>
  pageSize?: number
  emptyMessage?: React.ReactNode
  getRowId?: (row: TData, index: number) => string
  className?: string
}

/** A sortable + paginated table powered by TanStack Table over the styled
 * `Table` primitives. Columns are standard TanStack `ColumnDef`s; carry
 * `meta: { align, className }` for cell presentation. */
export function DataTable<TData>({
  columns,
  data,
  pageSize = 10,
  emptyMessage = 'No results.',
  getRowId,
  className,
}: DataTableProps<TData>) {
  const [sorting, setSorting] = React.useState<SortingState>([])

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize } },
    getRowId,
  })

  const rows = table.getRowModel().rows
  const pageCount = table.getPageCount()

  return (
    <div className={cn('flex flex-col gap-4', className)}>
      <Table>
        <TableHeader>
          {table.getHeaderGroups().map((group) => (
            <TableRow key={group.id}>
              {group.headers.map((header) => {
                const meta = header.column.columnDef.meta
                const canSort = header.column.getCanSort()
                const sorted = header.column.getIsSorted()
                return (
                  <TableHead key={header.id} className={cn(meta?.align && alignClass[meta.align], meta?.className)}>
                    {header.isPlaceholder ? null : canSort ? (
                      <button
                        type="button"
                        onClick={header.column.getToggleSortingHandler()}
                        className="inline-flex items-center gap-1 font-medium outline-none hover:text-foreground focus-visible:text-foreground"
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {sorted === 'asc' ? (
                          <ChevronUp className="size-3.5" />
                        ) : sorted === 'desc' ? (
                          <ChevronDown className="size-3.5" />
                        ) : (
                          <ChevronsUpDown className="size-3.5 opacity-50" />
                        )}
                      </button>
                    ) : (
                      flexRender(header.column.columnDef.header, header.getContext())
                    )}
                  </TableHead>
                )
              })}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {rows.length === 0 ? (
            <TableRow>
              <TableCell colSpan={columns.length} className="h-24 text-center text-muted-foreground">
                {emptyMessage}
              </TableCell>
            </TableRow>
          ) : (
            rows.map((row) => (
              <TableRow key={row.id}>
                {row.getVisibleCells().map((cell) => {
                  const meta = cell.column.columnDef.meta
                  return (
                    <TableCell key={cell.id} className={cn(meta?.align && alignClass[meta.align], meta?.className)}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  )
                })}
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
      {pageCount > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            {data.length} {data.length === 1 ? 'row' : 'rows'}
          </p>
          <Pagination
            page={table.getState().pagination.pageIndex + 1}
            pageCount={pageCount}
            onPageChange={(p) => table.setPageIndex(p - 1)}
          />
        </div>
      )}
    </div>
  )
}
