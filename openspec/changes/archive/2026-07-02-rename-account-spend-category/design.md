## Context

`Account` ([account.py](../../../src/web_api/db/models/account.py)) is the company
spend-tree node: `company_id`, `account_code`, `account_name`, `level2`, `level3`,
`description`. `Company.accounts` is its relationship. The RAG indexer
([indexer.py](../../../src/ai_api/rag/indexer.py)) builds retrieval documents from
spend-tree rows keyed by `level2`/`level3`/`account_name`/`description`. The
deterministic categorizer emits `level1` (Direct/Indirect) and `level2`/`level3`
onto transactions, but L1 is never stored on the tree node — the domain-model spec
states "L1 (Direct/Indirect) is never stored."

The name `Account` collides with `ErpAccount` (the ERP's native chart of
accounts), and the level structure is implicit. This change renames the entity to
`SpendCategory` and makes the level path explicit and stored.

## Goals / Non-Goals

**Goals:**
- Rename `Account` → `SpendCategory`, table `accounts` → `spend_categories`,
  relationship `Company.accounts` → `Company.spend_categories`.
- Replace `level2`/`level3` with stored `level_1`, `level_2`, `level_3`, `level_4`,
  where `level_1` = Direct/Indirect.
- Keep `account_code`/`account_name`/`description` (leaf identity + embedding).
- Update the indexer and any spend-tree producers to the new field names.

**Non-Goals:**
- No change to the *applied* categorization result columns on `InvoiceLine` /
  `ErpEntry` (`level1`/`level2`/`level3`, `account_code`). Those describe a
  transaction's assigned category, not the tree node.
- No new categorization behavior; `level_1` is stored but this change does not add
  logic to populate it beyond migrating existing data.
- No customer API/UI changes.

## Decisions

### D1 — `SpendCategory` keeps a leaf identity alongside the four levels
The node carries both the labelled path (`level_1`..`level_4`) and
`account_code`/`account_name`/`description`.
- *Why:* the categorizer writes the chosen leaf **code** onto invoice lines
  (`InvoiceLine.account_code`), and the indexer embeds `account_name` +
  `description`. Dropping them would break categorization output and retrieval.
- *Alternative rejected:* fold `account_name` into `level_4`. Cleaner on paper but
  loses the stable leaf code/name the rest of the pipeline references; deferred as
  an open question rather than done blindly here.

### D2 — `level_1` = Direct/Indirect, stored and nullable
`level_1` is a stored text column holding "Direct" or "Indirect" (nullable until
classified). This supersedes the "L1 never stored" rule.
- *Why:* the user wants the property present on the node. Nullable keeps migration
  backfill-free and lets unclassified trees load.
- *Note:* populating `level_1` for existing rows is out of scope — it can be
  derived later (the categorizer already knows Direct/Indirect per code, e.g. COGS
  = Direct). Migration leaves it null.

### D3 — Field migration mapping
`level2` → `level_2`, `level3` → `level_3`; add `level_1` (null), add `level_4`
(null). `level_2` stays required; `level_3`/`level_4` nullable.
- *Why:* least-lossy, mechanical. No data is dropped.

### D4 — Table + entity rename via an explicit migration
Alembic migration renames table `accounts` → `spend_categories`, renames the two
level columns, and adds the two new ones. Revision id kept ≤ 32 chars (to fit
`alembic_version.version_num`, per the prior migration's lesson).
- *Why:* a rename is a real DDL operation; SQLModel `create_all` alone won't
  migrate an existing DB.

### D5 — Update indexer/producers to new keys
The indexer's row access (`r["level2"]`, `r["level3"]`) and retrieval-string
builder move to `level_1`..`level_4`. Any synthetic/CSV spend-tree producers emit
the new keys. The retrieval string can optionally include `level_1` (Direct/
Indirect) for richer context, but at minimum keeps `level_2 > … > account_name`.

## Risks / Trade-offs

- **Wide rename touches many call sites** → the ORM coupling is small
  (`Company.accounts`, `__init__` export, indexer); a repo-wide grep for
  `Account`, `.accounts`, `.level2`/`.level3` bounds the work. Tests catch misses.
- **`Account` vs `ErpAccount` grep noise** → search carefully; `ErpAccount`,
  `account_code`, `native_account_code`, `AccountResponse` must NOT be renamed.
- **Redundancy between `level_4` and `account_name`** → kept both for safety;
  flagged as an open question rather than silently merged.
- **Migration on a live DB** → rename + add columns is additive/lossless; existing
  `level2`/`level3` data is preserved under the new names; `level_1`/`level_4` null.
- **`InvoiceLine.level1/2/3` naming now differs from `SpendCategory.level_1..4`**
  (underscore vs not) → intentional: one is the tree node, the other the applied
  result. Documented; a later change can align them if desired.

## Migration Plan

1. Rename the model file/class and fields; update `Company` relationship and the
   models `__init__` export.
2. Update the indexer and spend-tree producers to the new field names.
3. Generate one Alembic migration: rename table + `level2`/`level3` columns, add
   `level_1`/`level_4`. Revision id ≤ 32 chars.
4. `uv run alembic upgrade head` against Postgres (`DATABASE_URL=…@localhost:5433/…`).
5. Run `uv run pytest`; fix any references surfaced by the rename.
- **Rollback:** reverse migration (rename back, drop the two new columns) and
  revert code. Lossless.

## Open Questions

- Should `account_name` be merged into `level_4` (single leaf label) rather than
  kept as a separate field? Kept separate here to avoid breaking the categorizer's
  leaf reference — confirm if you'd prefer the merge.
- Should existing rows' `level_1` be backfilled with Direct/Indirect now (derivable
  from the leaf code) or left null until re-categorization? Left null in this change.
- Should the transaction-side result columns (`InvoiceLine.level1..3`) be renamed to
  match `level_1..4` for consistency? Deferred as a separate change.
