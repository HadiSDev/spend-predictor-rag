import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { SpendTreeEditor } from '#/components/settings/spend-tree-editor'
import { SpendTreesPanel } from '#/components/settings/spend-trees-panel'
import { canManageCompanies, useApi, usePrincipal } from '#/lib/auth'
import {
  createSpendCategoryMutation,
  archiveSpendTreeMutation,
  createSpendTreeMutation,
  deleteSpendTreeMutation,
  ensureDefaultSpendTreeMutation,
  deleteSpendCategoryMutation,
  importSpendTreeMutation,
  spendTreeQueryOptions,
  spendTreesQueryOptions,
  updateSpendCategoryMutation,
} from '#/lib/spend-trees'

/** Which tree is open, in the URL — so a tree is linkable like a voucher is. */
interface SpendTreeSearch {
  tree?: string
}

export const Route = createFileRoute('/_authed/settings/spend-trees')({
  component: SpendTreesSection,
  staticData: { title: 'Spend trees' },
  validateSearch: (search: Record<string, unknown>): SpendTreeSearch => ({
    tree: typeof search.tree === 'string' && search.tree ? search.tree : undefined,
  }),
})

function SpendTreesSection() {
  const api = useApi()
  const navigate = useNavigate({ from: Route.fullPath })
  const queryClient = useQueryClient()
  const canManage = canManageCompanies(usePrincipal())
  const { tree: openTreeId } = Route.useSearch()

  const trees = useQuery(spendTreesQueryOptions(api))
  const openTree = useQuery(spendTreeQueryOptions(api, openTreeId ?? null))

  const create = useMutation(createSpendTreeMutation(api, queryClient))
  const useDefault = useMutation(ensureDefaultSpendTreeMutation(api, queryClient))
  const removeTree = useMutation(deleteSpendTreeMutation(api, queryClient))
  const archiveTree = useMutation(archiveSpendTreeMutation(api, queryClient))
  const importCsv = useMutation(importSpendTreeMutation(api, queryClient))
  const addNode = useMutation(createSpendCategoryMutation(api, queryClient, openTreeId ?? ''))
  const updateNode = useMutation(updateSpendCategoryMutation(api, queryClient, openTreeId ?? ''))
  const deleteNode = useMutation(deleteSpendCategoryMutation(api, queryClient, openTreeId ?? ''))

  if (openTreeId) {
    return (
      <SpendTreeEditor
        tree={openTree.data}
        loading={openTree.isPending}
        canManage={canManage}
        onBack={() => navigate({ search: {} })}
        onAddNode={(body) => addNode.mutateAsync(body)}
        onUpdateNode={(id, body) => updateNode.mutateAsync({ id, body })}
        onDeleteNode={(id) => deleteNode.mutateAsync(id)}
      />
    )
  }

  return (
    <SpendTreesPanel
      trees={trees.data ?? []}
      loading={trees.isPending}
      error={trees.isError}
      canManage={canManage}
      onCreate={(body) => create.mutateAsync(body)}
      onUseDefault={() => useDefault.mutateAsync()}
      onDelete={(args) => removeTree.mutateAsync(args)}
      onArchive={(id) => archiveTree.mutateAsync(id)}
      onImport={(args) => importCsv.mutateAsync(args)}
      onOpenTree={(treeId) => navigate({ search: { tree: treeId } })}
    />
  )
}
