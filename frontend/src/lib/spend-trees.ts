import { queryOptions } from '@tanstack/react-query'
import type { QueryClient, UseMutationOptions } from '@tanstack/react-query'
import type { ApiClient } from './api-client'
import type {
  SpendCategoryCreate,
  SpendCategoryRead,
  SpendCategoryUpdate,
  SpendTreeCreate,
  SpendTreeDeleteResult,
  SpendTreeDetailRead,
  SpendTreeImportResult,
  SpendTreeRead,
  SpendTreeUpdate,
} from './types'

export function spendTreesKey() {
  return ['spend-trees'] as const
}

export function spendTreeKey(treeId: string) {
  return ['spend-trees', treeId] as const
}

/** The organization's spend trees (`GET /spend-trees`). Readable by any member. */
export function spendTreesQueryOptions(api: ApiClient, includeArchived = false) {
  return queryOptions({
    queryKey: [...spendTreesKey(), { includeArchived }] as const,
    queryFn: () =>
      api.get<Array<SpendTreeRead>>(
        `/api/v1/spend-trees${includeArchived ? '?include_archived=true' : ''}`,
      ),
  })
}

/**
 * One tree with every node (`GET /spend-trees/{id}`).
 *
 * The whole tree in one request on purpose: it is hundreds of nodes at most,
 * and both the selector's column navigation and its search are instant only if
 * the client already holds it. Paginating it would make picking a category a
 * sequence of round-trips.
 */
export function spendTreeQueryOptions(api: ApiClient, treeId: string | null) {
  return queryOptions({
    queryKey: spendTreeKey(treeId ?? 'none'),
    queryFn: () => api.get<SpendTreeDetailRead>(`/api/v1/spend-trees/${treeId}`),
    enabled: treeId !== null,
  })
}

/**
 * Materialize the organization's copy of the default template
 * (`POST /spend-trees/default`). Idempotent — returns the existing copy when
 * there is one.
 *
 * Needed because copy-on-first-use is otherwise triggered only by creating a
 * company, which leaves an organization that predates spend trees unable to
 * obtain the default at all.
 */
export function ensureDefaultSpendTreeMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<SpendTreeDetailRead, Error, void> {
  return {
    mutationFn: () => api.post<SpendTreeDetailRead>('/api/v1/spend-trees/default'),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: spendTreesKey() }),
  }
}

export function createSpendTreeMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<SpendTreeDetailRead, Error, SpendTreeCreate> {
  return {
    mutationFn: (body) => api.post<SpendTreeDetailRead>('/api/v1/spend-trees', body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: spendTreesKey() }),
  }
}

export function updateSpendTreeMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<SpendTreeRead, Error, { id: string; body: SpendTreeUpdate }> {
  return {
    mutationFn: ({ id, body }) => api.patch<SpendTreeRead>(`/api/v1/spend-trees/${id}`, body),
    onSuccess: (_result, { id }) => {
      void queryClient.invalidateQueries({ queryKey: spendTreesKey() })
      void queryClient.invalidateQueries({ queryKey: spendTreeKey(id) })
    },
  }
}

export function archiveSpendTreeMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<SpendTreeRead, Error, string> {
  return {
    mutationFn: (id) => api.post<SpendTreeRead>(`/api/v1/spend-trees/${id}/archive`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: spendTreesKey() }),
  }
}

/**
 * Delete a tree and its nodes (`DELETE /spend-trees/{id}`).
 *
 * A hard delete, unlike a company's soft deactivation: a tree owns no financial
 * record — an `InvoiceLine` keeps its stored levels whatever happens to the node
 * it pointed at. Two `409`s to tell apart: a company still assigned (reassign
 * first), and categorized lines pointing into it (retry with `confirm`).
 */
export function deleteSpendTreeMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<SpendTreeDeleteResult, Error, { id: string; confirm?: boolean }> {
  return {
    mutationFn: ({ id, confirm }) =>
      api.del<SpendTreeDeleteResult>(
        `/api/v1/spend-trees/${id}${confirm ? '?confirm=true' : ''}`,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: spendTreesKey() })
      // Deleting a tree clears the pointer on every line that used it.
      void queryClient.invalidateQueries({ queryKey: ['invoice-lines'] })
      void queryClient.invalidateQueries({ queryKey: ['erp-entries'] })
    },
  }
}

export interface ImportVariables {
  treeId: string
  content: string
  mode: 'merge' | 'replace'
  /** Acknowledges that the import removes categories lines are assigned to. */
  confirm?: boolean
}

/**
 * Load a CSV into a tree (`POST /spend-trees/{id}/import`).
 *
 * Two distinct failures the caller must tell apart, both surfaced as thrown
 * errors carrying the server's `detail`: a `422` means the file did not
 * validate and nothing was written (`detail.errors` names the offending lines);
 * a `409` means the import is valid but would orphan categorized lines, and
 * succeeds unchanged once `confirm` is set.
 */
export function importSpendTreeMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<SpendTreeImportResult, Error, ImportVariables> {
  return {
    mutationFn: ({ treeId, content, mode, confirm }) =>
      api.post<SpendTreeImportResult>(
        `/api/v1/spend-trees/${treeId}/import?mode=${mode}${confirm ? '&confirm=true' : ''}`,
        { content },
      ),
    onSuccess: (_result, { treeId }) => {
      void queryClient.invalidateQueries({ queryKey: spendTreesKey() })
      void queryClient.invalidateQueries({ queryKey: spendTreeKey(treeId) })
    },
  }
}

export function createSpendCategoryMutation(
  api: ApiClient,
  queryClient: QueryClient,
  treeId: string,
): UseMutationOptions<SpendCategoryRead, Error, SpendCategoryCreate> {
  return {
    mutationFn: (body) =>
      api.post<SpendCategoryRead>(`/api/v1/spend-trees/${treeId}/nodes`, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: spendTreeKey(treeId) })
      void queryClient.invalidateQueries({ queryKey: spendTreesKey() })
    },
  }
}

/**
 * Edit one node (`PATCH /spend-tree-nodes/{id}`).
 *
 * Always invalidates rather than patching the cached node in place: a rename
 * rewrites every descendant's materialized path server-side, so the one row
 * that comes back is not the whole of what changed.
 */
export function updateSpendCategoryMutation(
  api: ApiClient,
  queryClient: QueryClient,
  treeId: string,
): UseMutationOptions<SpendCategoryRead, Error, { id: string; body: SpendCategoryUpdate }> {
  return {
    mutationFn: ({ id, body }) =>
      api.patch<SpendCategoryRead>(`/api/v1/spend-tree-nodes/${id}`, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: spendTreeKey(treeId) }),
  }
}

export function deleteSpendCategoryMutation(
  api: ApiClient,
  queryClient: QueryClient,
  treeId: string,
): UseMutationOptions<SpendTreeDeleteResult, Error, string> {
  return {
    mutationFn: (id) => api.del<SpendTreeDeleteResult>(`/api/v1/spend-tree-nodes/${id}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: spendTreeKey(treeId) })
      void queryClient.invalidateQueries({ queryKey: spendTreesKey() })
    },
  }
}

// -- Shaping a flat node list into a tree ------------------------------------

/** A node with its children attached, for rendering. */
export interface TreeNode extends SpendCategoryRead {
  children: Array<TreeNode>
}

/**
 * Build the hierarchy from the server's flat, shallowest-first list.
 *
 * One pass: the server's ordering guarantees a parent is seen before any child,
 * so no second pass or recursive sort is needed.
 */
export function buildTree(nodes: Array<SpendCategoryRead>): Array<TreeNode> {
  const byId = new Map<string, TreeNode>()
  const roots: Array<TreeNode> = []

  for (const node of nodes) {
    byId.set(node.id, { ...node, children: [] })
  }
  for (const node of nodes) {
    const shaped = byId.get(node.id)!
    const parent = node.parent_id ? byId.get(node.parent_id) : undefined
    if (parent) parent.children.push(shaped)
    else roots.push(shaped)
  }
  return roots
}

/** A node's full path, trailing levels dropped. */
export function nodePath(node: SpendCategoryRead): Array<string> {
  return [node.level_1, node.level_2, node.level_3, node.level_4].filter(
    (value): value is string => value !== null && value !== '',
  )
}

/** A node's path as display text — what a chosen category reads as. */
export function formatPath(node: SpendCategoryRead, separator = ' › '): string {
  return nodePath(node).join(separator)
}

/** The children of `parentId` (or the roots when null), in the server's order. */
export function childrenOf(
  nodes: Array<SpendCategoryRead>,
  parentId: string | null,
): Array<SpendCategoryRead> {
  return nodes.filter((node) => node.parent_id === parentId)
}
