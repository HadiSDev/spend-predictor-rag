import { describe, expect, it } from 'vitest'
import { describeEvent } from './describe-event'
import type { VoucherAuditRead } from '#/lib/api/types'

function row(overrides: Partial<VoucherAuditRead> = {}): VoucherAuditRead {
  return {
    id: 'a1',
    entity_type: 'invoice_line',
    entity_id: 'l1',
    entity_label: 'Line 1',
    action: 'edit',
    actor: 'u1',
    actor_name: 'Hadi Salameh',
    changes: [],
    created_at: '2026-08-09T08:00:00Z',
    ...overrides,
  }
}

function headlineText(event: ReturnType<typeof describeEvent>): string {
  return event.headline.map((part) => part.text).join('')
}

const AI_CATEGORIZED = row({
  action: 'ai_categorize',
  actor: 'system',
  actor_name: null,
  changes: [
    { field: 'level_1', old: null, new: 'Indirect' },
    { field: 'level_2', old: null, new: 'Facilities & Office' },
    { field: 'level_3', old: null, new: 'Utilities' },
    { field: 'account_code', old: null, new: '6900' },
    { field: 'account_name', old: null, new: 'Utilities' },
    { field: 'confidence', old: null, new: '0.85' },
    { field: 'rationale', old: 'No description.', new: 'DSB is a utility.' },
    { field: 'spend_category_id', old: null, new: '290b9e8c-386d' },
    { field: 'status', old: 'uncategorized', new: 'ai_categorized' },
  ],
})

describe('describeEvent', () => {
  it('credits the AI and reads as a sentence for a categorization', () => {
    const event = describeEvent(AI_CATEGORIZED)
    expect(event.tone).toBe('ai')
    expect(headlineText(event)).toBe('Steelyard AI categorized Line 1')
  })

  it('collapses the three category levels into one path', () => {
    const [category] = describeEvent(AI_CATEGORIZED).summary.filter(
      (item) => item.kind === 'category',
    )
    expect(category).toEqual({
      kind: 'category',
      before: null,
      after: ['Indirect', 'Facilities & Office', 'Utilities'],
    })
  })

  it('pairs the account code with its name', () => {
    const summary = describeEvent(AI_CATEGORIZED).summary
    expect(summary).toContainEqual({
      kind: 'account',
      before: null,
      after: '6900 · Utilities',
    })
  })

  it('shows confidence as a whole percentage', () => {
    expect(describeEvent(AI_CATEGORIZED).summary).toContainEqual({
      kind: 'confidence',
      percent: 85,
    })
  })

  it('keeps only the new reasoning, not the one it replaced', () => {
    expect(describeEvent(AI_CATEGORIZED).summary).toContainEqual({
      kind: 'note',
      label: 'Reasoning',
      text: 'DSB is a utility.',
      tone: 'neutral',
    })
  })

  it('leaves the status out of a categorization, since the headline says it', () => {
    const kinds = describeEvent(AI_CATEGORIZED).summary.map((item) => item.kind)
    expect(kinds).not.toContain('status')
  })

  it('hides internal ids', () => {
    const labels = describeEvent(AI_CATEGORIZED)
      .summary.filter((item) => item.kind === 'field')
      .map((item) => item.label)
    expect(labels).not.toContain('Spend category id')
  })

  it('treats a categorization that ended in ai_failed as a failure', () => {
    const event = describeEvent(
      row({
        action: 'ai_categorize',
        actor: 'system',
        actor_name: null,
        changes: [
          { field: 'rationale', old: null, new: 'No description provided.' },
          { field: 'status', old: 'uncategorized', new: 'ai_failed' },
        ],
      }),
    )
    expect(event.tone).toBe('failure')
    expect(headlineText(event)).toBe("Steelyard AI couldn't categorize Line 1")
    expect(event.summary).toContainEqual({
      kind: 'note',
      label: 'Why it failed',
      text: 'No description provided.',
      tone: 'destructive',
    })
  })

  it('names the person behind a manual change', () => {
    const event = describeEvent(
      row({
        action: 'edit',
        changes: [{ field: 'level_2', old: 'Office', new: 'Furniture' }],
      }),
    )
    expect(event.tone).toBe('person')
    expect(event.actorName).toBe('Hadi Salameh')
    expect(headlineText(event)).toBe('Hadi Salameh corrected Line 1')
  })

  it('falls back to a neutral name when the person is unknown', () => {
    const event = describeEvent(row({ action: 'verify', actor_name: null }))
    expect(headlineText(event)).toBe('A team member verified Line 1')
  })

  it('describes a requeue as the system sending the line back', () => {
    const event = describeEvent(
      row({
        action: 'requeued_for_categorization',
        actor: 'system',
        actor_name: null,
        changes: [
          { field: 'status', old: 'ai_failed', new: 'uncategorized' },
          { field: 'error_message', old: 'Too vague.', new: null },
        ],
      }),
    )
    expect(event.tone).toBe('system')
    expect(headlineText(event)).toBe('Line 1 was sent back for categorization')
    expect(event.summary).toEqual([
      { kind: 'status', before: 'ai_failed', after: 'uncategorized' },
    ])
  })

  it('describes a document reprocess with the document status', () => {
    const event = describeEvent(
      row({
        action: 'reprocess_document',
        entity_type: 'invoice',
        entity_label: 'Invoice',
        changes: [{ field: 'doc_status', old: 'processed', new: 'pending' }],
      }),
    )
    expect(headlineText(event)).toBe(
      'Hadi Salameh re-read the document for Invoice',
    )
    expect(event.summary).toEqual([
      { kind: 'document-status', before: 'processed', after: 'pending' },
    ])
  })

  it('humanises the fields it has no special layout for', () => {
    const event = describeEvent(
      row({
        action: 'edit',
        entity_type: 'invoice',
        entity_label: 'Invoice',
        changes: [{ field: 'invoice_number', old: 'A-1', new: 'A-2' }],
      }),
    )
    expect(event.summary).toEqual([
      { kind: 'field', label: 'Invoice number', before: 'A-1', after: 'A-2' },
    ])
  })

  it('still reads for an action it does not know', () => {
    const event = describeEvent(row({ action: 'bulk_merge' }))
    expect(headlineText(event)).toBe('Hadi Salameh changed Line 1')
  })
})
