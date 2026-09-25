import {
  ArrowRightLeft,
  Ban,
  CircleCheck,
  CircleDot,
  Eye,
  FileScan,
  Pencil,
  Plus,
  Replace,
  RotateCcw,
  Sparkles,
  Trash2,
  TriangleAlert,
  Undo2,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { VoucherAuditRead } from '#/lib/api/types'

/** Who or what an event came from, which sets its colour. */
export type EventTone = 'ai' | 'failure' | 'person' | 'system'

/** A run of headline text, emphasised when it names someone or something. */
export interface HeadlinePart {
  text: string
  strong?: boolean
}

/** One readable piece of what an event changed. */
export type SummaryItem =
  | {
      kind: 'category'
      before: Array<string> | null
      after: Array<string> | null
    }
  | { kind: 'account'; before: string | null; after: string | null }
  | { kind: 'confidence'; percent: number }
  | { kind: 'status'; before: string | null; after: string | null }
  | { kind: 'document-status'; before: string | null; after: string | null }
  | {
      kind: 'note'
      label: string
      text: string
      tone: 'neutral' | 'destructive'
    }
  | { kind: 'field'; label: string; before: string; after: string }

/** An audit row turned into something a person reads at a glance. */
export interface EventDescription {
  tone: EventTone
  icon: LucideIcon
  actorName: string
  headline: Array<HeadlinePart>
  summary: Array<SummaryItem>
}

type Change = { field: string; old: unknown; new: unknown }

type Sentence = (actor: string, subject: string) => Array<HeadlinePart>

interface ActionSpec {
  icon: LucideIcon
  sentence: Sentence
}

const AI_NAME = 'Steelyard AI'
const SYSTEM_NAME = 'Steelyard'
const UNKNOWN_PERSON = 'A team member'

const CATEGORY_FIELDS = ['level_1', 'level_2', 'level_3', 'level_4']
const HIDDEN_FIELDS = new Set(['spend_category_id', 'error_message'])

const FIELD_LABELS: Record<string, string> = {
  doc_status: 'Document status',
  invoice_number: 'Invoice number',
  document_invoice_number: 'Invoice number on the document',
  invoice_date: 'Invoice date',
  due_date: 'Due date',
  item_name: 'Item',
  unit_price: 'Unit price',
  vat_amount: 'VAT',
}

function actorDoes(verb: string): Sentence {
  return (actor, subject) => [
    { text: actor, strong: true },
    { text: ` ${verb} ` },
    { text: subject, strong: true },
  ]
}

function subjectWas(phrase: string): Sentence {
  return (_actor, subject) => [
    { text: subject, strong: true },
    { text: ` ${phrase}` },
  ]
}

const ACTIONS: Record<string, ActionSpec> = {
  ai_categorize: { icon: Sparkles, sentence: actorDoes('categorized') },
  edit: { icon: Pencil, sentence: actorDoes('corrected') },
  verify: { icon: CircleCheck, sentence: actorDoes('verified') },
  noop: { icon: Eye, sentence: actorDoes('reviewed') },
  reprocess_document: {
    icon: FileScan,
    sentence: actorDoes('re-read the document for'),
  },
  requeued_for_categorization: {
    icon: RotateCcw,
    sentence: subjectWas('was sent back for categorization'),
  },
  line_added: { icon: Plus, sentence: subjectWas('was added') },
  line_deleted: { icon: Trash2, sentence: subjectWas('was removed') },
  hard_reset: { icon: RotateCcw, sentence: actorDoes('reset') },
  spend_tree_reassigned: {
    icon: ArrowRightLeft,
    sentence: subjectWas('moved to a new spend tree'),
  },
  voucher_voided_in_erp: {
    icon: Ban,
    sentence: subjectWas('was voided in the ERP'),
  },
  withdrawn_by_erp: {
    icon: Undo2,
    sentence: subjectWas('was withdrawn by the ERP'),
  },
  superseded_by_extraction: {
    icon: Replace,
    sentence: subjectWas('was replaced by a new reading of the document'),
  },
}

const FALLBACK_ACTION: ActionSpec = {
  icon: CircleDot,
  sentence: actorDoes('changed'),
}

const FAILED_CATEGORIZATION: ActionSpec = {
  icon: TriangleAlert,
  sentence: actorDoes("couldn't categorize"),
}

function isEmpty(value: unknown): boolean {
  return value === null || value === undefined || value === ''
}

function asText(value: unknown): string | null {
  if (isEmpty(value)) {
    return null
  }
  return typeof value === 'string' ? value : JSON.stringify(value)
}

function humanise(field: string): string {
  const label = FIELD_LABELS[field] ?? field.replaceAll('_', ' ')
  return label.charAt(0).toUpperCase() + label.slice(1)
}

function isSystemActor(row: VoucherAuditRead): boolean {
  return !row.actor || row.actor === 'system'
}

function failedCategorization(row: VoucherAuditRead, changes: Array<Change>) {
  return (
    row.action === 'ai_categorize' &&
    changes.some(
      (change) => change.field === 'status' && change.new === 'ai_failed',
    )
  )
}

function toneOf(row: VoucherAuditRead, failed: boolean): EventTone {
  if (failed) {
    return 'failure'
  }
  if (row.action === 'ai_categorize') {
    return 'ai'
  }
  return isSystemActor(row) ? 'system' : 'person'
}

function actorNameOf(row: VoucherAuditRead): string {
  if (row.action === 'ai_categorize') {
    return AI_NAME
  }
  if (isSystemActor(row)) {
    return SYSTEM_NAME
  }
  return row.actor_name ?? UNKNOWN_PERSON
}

function categoryPath(
  byField: Map<string, Change>,
  side: 'old' | 'new',
): Array<string> | null {
  const levels = CATEGORY_FIELDS.map((field) =>
    asText(byField.get(field)?.[side]),
  ).filter((level): level is string => level !== null)
  return levels.length > 0 ? levels : null
}

function accountLabel(
  byField: Map<string, Change>,
  side: 'old' | 'new',
): string | null {
  const code = asText(byField.get('account_code')?.[side])
  const name = asText(byField.get('account_name')?.[side])
  if (code && name) {
    return `${code} · ${name}`
  }
  return code ?? name
}

function confidencePercent(value: unknown): number | null {
  const parsed = Number(value)
  if (isEmpty(value) || Number.isNaN(parsed)) {
    return null
  }
  return Math.round(parsed <= 1 ? parsed * 100 : parsed)
}

function summarise(
  changes: Array<Change>,
  action: string,
  failed: boolean,
): Array<SummaryItem> {
  const byField = new Map(changes.map((change) => [change.field, change]))
  const summary: Array<SummaryItem> = []

  if (CATEGORY_FIELDS.some((field) => byField.has(field))) {
    summary.push({
      kind: 'category',
      before: categoryPath(byField, 'old'),
      after: categoryPath(byField, 'new'),
    })
  }

  if (byField.has('account_code') || byField.has('account_name')) {
    summary.push({
      kind: 'account',
      before: accountLabel(byField, 'old'),
      after: accountLabel(byField, 'new'),
    })
  }

  const percent = confidencePercent(byField.get('confidence')?.new)
  if (percent !== null) {
    summary.push({ kind: 'confidence', percent })
  }

  const status = byField.get('status')
  if (status && action !== 'ai_categorize') {
    summary.push({
      kind: 'status',
      before: asText(status.old),
      after: asText(status.new),
    })
  }

  const docStatus = byField.get('doc_status')
  if (docStatus) {
    summary.push({
      kind: 'document-status',
      before: asText(docStatus.old),
      after: asText(docStatus.new),
    })
  }

  const reasoning = asText(byField.get('rationale')?.new)
  if (reasoning) {
    summary.push({
      kind: 'note',
      label: failed ? 'Why it failed' : 'Reasoning',
      text: reasoning,
      tone: failed ? 'destructive' : 'neutral',
    })
  }

  const error = asText(byField.get('error_message')?.new)
  if (error) {
    summary.push({
      kind: 'note',
      label: 'Error',
      text: error,
      tone: 'destructive',
    })
  }

  for (const change of changes) {
    if (isSpecialField(change.field)) {
      continue
    }
    summary.push({
      kind: 'field',
      label: humanise(change.field),
      before: asText(change.old) ?? '—',
      after: asText(change.new) ?? '—',
    })
  }

  return summary
}

function isSpecialField(field: string): boolean {
  return (
    CATEGORY_FIELDS.includes(field) ||
    HIDDEN_FIELDS.has(field) ||
    field.endsWith('_id') ||
    [
      'account_code',
      'account_name',
      'confidence',
      'status',
      'doc_status',
      'rationale',
    ].includes(field)
  )
}

/** Turn an audit row into a headline and a readable summary of what changed. */
export function describeEvent(row: VoucherAuditRead): EventDescription {
  const changes: Array<Change> = row.changes ?? []
  const failed = failedCategorization(row, changes)
  const spec = failed
    ? FAILED_CATEGORIZATION
    : (ACTIONS[row.action] ?? FALLBACK_ACTION)
  const actorName = actorNameOf(row)

  return {
    tone: toneOf(row, failed),
    icon: spec.icon,
    actorName,
    headline: spec.sentence(actorName, row.entity_label),
    summary: summarise(changes, row.action, failed),
  }
}
