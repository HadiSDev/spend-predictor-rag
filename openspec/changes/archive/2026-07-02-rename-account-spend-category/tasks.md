## 1. Rename the ORM entity

- [x] 1.1 Rename `src/web_api/db/models/account.py` → `spend_category.py`; class `Account` → `SpendCategory`, table `accounts` → `spend_categories`
- [x] 1.2 Fields: `level2`→`level_2` (required), `level3`→`level_3` (nullable); add `level_1` (nullable, Direct/Indirect) and `level_4` (nullable). Keep `account_code`, `account_name`, `description`
- [x] 1.3 Update `Company.accounts` → `Company.spend_categories` + `back_populates`; update `db/models/__init__.py` import + `__all__`

## 2. Global level-naming rename (`level[123]` → `level_[123]`)

- [x] 2.1 Chart/spend-tree source: `data/chart_of_accounts.csv` header; RAG indexer; `synthdata/{content,sampler,bundle,profiles,generate,score}.py` (incl. `level1_for`, `direct_level2`, `category_from_account`); `flow.py` candidate formatting
- [x] 2.2 Result namespace: `ai_api/models.py` (`CategorizedInvoice`/prediction `level1/2/3`), `sync/categorizer.py` (`Category`/`CategoryMatch` fields), `sync/runner.py` mapping + `spend_by_level2` key, `grounding.py`, `ledger.py`, `web_api/schemas.py`, `aggregation/engine.py`
- [x] 2.3 Mock ERP `category_level2` (`mock_erp/data/vendors.py`, `invoices.py`)

## 3. DB result-column renames + migrations

- [x] 3.1 `invoice_line.py`: `level1/2/3`→`level_1/2/3`, `gt_level1/2/3`→`gt_level_1/2/3`
- [x] 3.2 `erp_entry.py`: same rename (`level1/2/3`, `gt_level1/2/3`)
- [x] 3.3 `recommendation.py`: `category_level2/3`→`category_level_2/3`
- [x] 3.4 One Alembic migration (revision id ≤ 32 chars): rename table `accounts`→`spend_categories` + its `level2/3`→`level_2/3` + add `level_1`,`level_4`; rename `invoice_lines`/`erp_entries` level columns; rename `recommendations.category_level2/3`
- [x] 3.5 Run `uv run alembic upgrade head` (`DATABASE_URL=…@localhost:5433/…`); verify columns

## 4. Fixtures & data

- [x] 4.1 Rename `level1/2/3` keys in all `data/synthetic/*/labels.json` (100) and `data/synthetic/manifest.jsonl`

## 5. Spec

- [x] 5.1 Update `domain-model` spec: SpendCategory entity + `level_1..level_4`, remove "L1 never stored" rule, schema diagram `Company 1──N SpendCategory`

## 6. Tests & verification

- [x] 6.1 Apply the same `level[123]`→`level_[123]` rename across `tests/` (synthdata + core tests + `tests/web_api/conftest.py`)
- [x] 6.2 Add a test asserting `SpendCategory` persists `level_1` (Direct/Indirect) + optional `level_3`/`level_4`
- [x] 6.3 `uv run pytest` full suite green; confirm synthdata scoring + indexer paths still work with the new keys
