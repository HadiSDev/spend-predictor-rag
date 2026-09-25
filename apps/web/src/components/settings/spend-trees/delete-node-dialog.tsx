import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Button,
} from '#/components/ui'
import type { TreeNode } from '#/lib/api/spend-trees'

/** Confirms deleting a node, stating its cost first. */
export function DeleteNodeDialog({
  node,
  onOpenChange,
  onConfirm,
}: {
  node: TreeNode | null
  onOpenChange: (open: boolean) => void
  onConfirm: () => Promise<void>
}) {
  const childCount = node?.children.length ?? 0
  return (
    <AlertDialog open={node !== null} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete “{node?.name}”?</AlertDialogTitle>
          <AlertDialogDescription>
            {childCount > 0 ? (
              <>
                This category has {childCount} sub-categor
                {childCount === 1 ? 'y' : 'ies'}. Delete or move{' '}
                {childCount === 1 ? 'it' : 'them'} first.
              </>
            ) : (
              <>
                Invoice lines assigned to this category keep the category on
                record but will need reviewing.
              </>
            )}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            disabled={childCount > 0}
            onClick={() => void onConfirm()}
          >
            Delete
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
