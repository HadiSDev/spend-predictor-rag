import { describe, expect, it, vi } from 'vitest'
import { QueryClient } from '@tanstack/react-query'
import { replaceIntegrationMutation } from './integrations'
import type { ApiClient } from './api-client'

describe('replaceIntegrationMutation', () => {
  it('posts to the integration replace path', async () => {
    const post = vi.fn().mockResolvedValue({ id: 'new-1', erp_type: 'billy' })
    const api = { post } as unknown as ApiClient

    const options = replaceIntegrationMutation(api, new QueryClient())
    await options.mutationFn!(
      {
        id: 'old-1',
        body: { erp_type: 'billy', label: 'Main', credentials: { access_token: 't' } },
      },
      {} as never,
    )

    expect(post).toHaveBeenCalledWith('/api/v1/erp-integrations/old-1/replace', {
      erp_type: 'billy',
      label: 'Main',
      credentials: { access_token: 't' },
    })
  })

  it('passes confirm through when the caller has acknowledged', async () => {
    const post = vi.fn().mockResolvedValue({ id: 'new-1' })
    const api = { post } as unknown as ApiClient

    const options = replaceIntegrationMutation(api, new QueryClient())
    await options.mutationFn!(
      {
        id: 'old-1',
        body: { erp_type: 'billy', credentials: {}, confirm: true },
      },
      {} as never,
    )

    expect(post.mock.calls[0][1].confirm).toBe(true)
  })
})
