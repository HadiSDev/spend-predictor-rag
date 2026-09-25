import { ChevronDown, ChevronRight, Pencil, Plus, Trash2 } from 'lucide-react'
import { Badge, IconButton } from '#/components/ui'
import type { TreeNode } from '#/lib/api/spend-trees'

export interface NodeRowProps {
  node: TreeNode
  maxDepth: number
  canManage: boolean
  expanded: Set<string>
  onToggle: (id: string) => void
  onAdd: (node: TreeNode) => void
  onEdit: (node: TreeNode) => void
  onDelete: (node: TreeNode) => void
}

export function NodeRow({
  node,
  maxDepth,
  canManage,
  expanded,
  onToggle,
  onAdd,
  onEdit,
  onDelete,
}: NodeRowProps) {
  const open = expanded.has(node.id)
  const hasChildren = node.children.length > 0
  const atMaxDepth = node.depth >= maxDepth

  return (
    <li>
      <div
        className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-muted/50"
        style={{ paddingLeft: `${0.5 + (node.depth - 1) * 1.25}rem` }}
      >
        {hasChildren ? (
          <button
            type="button"
            onClick={() => onToggle(node.id)}
            aria-label={open ? `Collapse ${node.name}` : `Expand ${node.name}`}
            aria-expanded={open}
            className="rounded p-0.5 text-muted-foreground hover:text-foreground"
          >
            {open ? (
              <ChevronDown className="size-4" />
            ) : (
              <ChevronRight className="size-4" />
            )}
          </button>
        ) : (
          <span className="size-5" aria-hidden />
        )}

        <span className="min-w-0 flex-1">
          <span className="text-sm text-foreground">{node.name}</span>
          {node.code ? (
            <Badge variant="outline" className="ml-2">
              {node.code}
            </Badge>
          ) : null}
          {node.description ? (
            <span className="ml-2 truncate text-xs text-muted-foreground">
              {node.description}
            </span>
          ) : null}
        </span>

        <span className="flex shrink-0 items-center gap-1">
          <IconButton
            aria-label={`Add a category under ${node.name}`}
            disabled={!canManage || atMaxDepth}
            title={
              atMaxDepth
                ? `This tree is ${maxDepth} levels deep — its deepest categories cannot have children.`
                : canManage
                  ? undefined
                  : 'Requires an admin or moderator role'
            }
            onClick={() => onAdd(node)}
          >
            <Plus className="size-4" />
          </IconButton>
          <IconButton
            aria-label={`Edit ${node.name}`}
            disabled={!canManage}
            onClick={() => onEdit(node)}
          >
            <Pencil className="size-4" />
          </IconButton>
          <IconButton
            aria-label={`Delete ${node.name}`}
            disabled={!canManage}
            onClick={() => onDelete(node)}
          >
            <Trash2 className="size-4" />
          </IconButton>
        </span>
      </div>

      {open && hasChildren ? (
        <ul>
          {node.children.map((child) => (
            <NodeRow
              key={child.id}
              node={child}
              maxDepth={maxDepth}
              canManage={canManage}
              expanded={expanded}
              onToggle={onToggle}
              onAdd={onAdd}
              onEdit={onEdit}
              onDelete={onDelete}
            />
          ))}
        </ul>
      ) : null}
    </li>
  )
}
