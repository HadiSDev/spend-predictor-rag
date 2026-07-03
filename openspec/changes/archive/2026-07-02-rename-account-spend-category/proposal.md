## Why

The spend-tree entity is named `Account`, which collides conceptually with
`ErpAccount` (the ERP's native chart of accounts) and reads ambiguously
everywhere it appears. It should be named **`SpendCategory`** — that is what it is:
a node in the company's own spend taxonomy. At the same time the tree's levels are
implicit and inconsistent: `level2`/`level3` are stored while **L1 (Direct/Indirect)
is inferred and never stored**, and there is no fourth tier. We want the category
to carry an explicit, stored **`level_1` … `level_4`**, with `level_1` holding the
Direct/Indirect classification.

## What Changes

- **BREAKING**: Rename the `Account` model → **`SpendCategory`** and its table
  `accounts` → `spend_categories`. The `Company.accounts` relationship becomes
  `Company.spend_categories`.
- Replace `level2`/`level3` with an explicit **`level_1`, `level_2`, `level_3`,
  `level_4`** path:
  - `level_1` — the **Direct/Indirect** classification, now **stored** (previously
    inferred and never persisted).
  - `level_2` — top category (required), was `level2`.
  - `level_3` — subcategory (optional), was `level3`.
  - `level_4` — new optional fourth tier (deepest labelled level).
- Keep `account_code`, `account_name`, and `description` as the leaf identity /
  embedding text (the categorizer writes the chosen leaf code onto invoice lines,
  so these stay).
- Update the RAG spend-tree indexer and any spend-tree producers to the new field
  names.
- Update the `domain-model` spec: the entity, the "L1 is never stored" rule, and
  the schema diagram.

## Capabilities

### New Capabilities
<!-- None. This renames/reshapes an existing entity; no new spec is introduced. -->

### Modified Capabilities
- `domain-model`: `Account` → `SpendCategory` (table `accounts` →
  `spend_categories`); `level2`/`level3` → stored `level_1`..`level_4` with
  `level_1` = Direct/Indirect; the "L1 never stored" key rule is removed.

## Impact

- **Domain / ORM**: `web_api/db/models/account.py` → `spend_category.py`
  (class + table + fields); `company.py` relationship; `db/models/__init__.py`
  export; a new Alembic migration (rename table, rename `level2`/`level3` →
  `level_2`/`level_3`, add `level_1`, `level_4`).
- **RAG** (`ai_api/rag/indexer.py`): spend-tree document rows currently keyed by
  `level2`/`level3`/`account_name` → new keys; retrieval string builder updated.
- **Categorizer / synthdata**: any spend-tree row producers (CSV/synthetic) that
  emit `level2`/`level3` → `level_1`..`level_4`. The deterministic categorizer's
  internal `_META` (keyed by code) is independent but its emitted `level1`/`level2`
  labels should align with the new naming where they feed `SpendCategory`.
- **Callers/tests**: imports of `Account`, `Company.accounts`, and any code
  reading `.level2`/`.level3`.
- **Out of scope**: changing `InvoiceLine`/`ErpEntry` categorization result columns
  (`level1`/`level2`/`level3`, `account_code`) — those are the *applied* result on
  a transaction, not the tree node, and are handled in a follow-up if desired.
