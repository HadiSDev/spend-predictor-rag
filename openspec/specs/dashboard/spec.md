# Dashboard Specification

## Purpose

A Streamlit dashboard that presents spend insights to the user. It connects to PostgreSQL and Qdrant to show categorized spend, vendor overlaps, and savings opportunities — all scoped to the user's company.

## Stack

- **Streamlit** (Python, single-page app)
- **PostgreSQL** via asyncpg for aggregation queries
- **Qdrant** for spend tree management (Settings tab)
- **Plotly** for charts (pie, bar, time-series)

No authentication for MVP — single-tenant dev mode. Auth added in Phase 3.

## Layout

```
Sidebar                           Main Area
┌─────────────────┐   ┌──────────────────────────────────────┐
│                 │   │                                        │
│  Company        │   │  Tab1  Tab2  Tab3  Tab4  Tab5         │
│  selector       │   │                                        │
│                 │   │  ┌──────────────────────────────────┐  │
│  [dropdown]     │   │  │                                  │  │
│                 │   │  │  Tab content (varies per tab)    │  │
│  Sync status    │   │  │                                  │  │
│  indicator      │   │  └──────────────────────────────────┘  │
│                 │   │                                        │
└─────────────────┘   └──────────────────────────────────────┘
```

### Sidebar

- **Company selector**: dropdown of companies the user can access (single option in MVP)
- **Sync status**: last sync timestamp + status badge (green/idle, yellow/syncing, red/error)
- **"Sync now"** button: triggers manual sync
- **Period selector**: trailing 3mo / 6mo / 12mo / all

## Tabs

### Tab 1: Overview

Purpose: At-a-glance spend health.

**Cards (top row)**:
- Total spend (selected period)
- # of vendors
- # of categories (L2)
- # of savings opportunities found

**Chart row**:
- Spend by L2 category (pie chart or horizontal bar)
- Spend trend (line chart, monthly over selected period)

**Bottom**:
- Top 3 savings opportunities (quick wins, highest confidence × savings)
- "View all" link to Savings tab

**SQL queries**:
```sql
-- Total spend
SELECT COALESCE(SUM(il.amount), 0) AS total
FROM invoice_lines il
WHERE il.company_id = $1
  AND il.status = 'categorized'
  AND il.invoice_date >= $2;

-- Spend by L2 category
SELECT il.level2, SUM(il.amount) AS total
FROM invoice_lines il
WHERE il.company_id = $1
  AND il.status = 'categorized'
  AND il.invoice_date >= $2
GROUP BY il.level2
ORDER BY total DESC;

-- Monthly spend trend
SELECT DATE_TRUNC('month', il.invoice_date) AS month, SUM(il.amount) AS total
FROM invoice_lines il
WHERE il.company_id = $1
  AND il.status = 'categorized'
  AND il.invoice_date >= $2
GROUP BY month
ORDER BY month;

-- Top savings quick wins
SELECT * FROM recommendations
WHERE company_id = $1 AND dismissed = false
ORDER BY (confidence * estimated_savings) DESC
LIMIT 3;

-- Vendor count, category count
SELECT COUNT(DISTINCT vendor_id), COUNT(DISTINCT level2)
FROM invoice_lines
WHERE company_id = $1 AND status = 'categorized' AND invoice_date >= $2;
```

### Tab 2: Vendors

Purpose: Understand who you're spending with and spot redundancy.

**Search/filter**: text search on vendor name, filter by L2 category

**Table columns**:
| Vendor | Category (L2) | Monthly Spend | Annual Spend | Txns | Redundancy Flags |
|---|---|---|---|---|---|
| Name | L2 | $X | $Y | N | ⚠️ "Also bought from Vendor B in same category" |

- Sorting by any column
- Click vendor → expand detail panel below table:
  - Spend trend for that vendor (mini line chart)
  - All invoice lines from that vendor (scrollable table)
  - Redundancy details: which other vendors overlap, overlap score, potential savings

**SQL**:
```sql
-- All vendors with aggregation
SELECT v.id, v.name, il.level2,
  SUM(il.amount) FILTER (WHERE il.invoice_date >= $2) AS period_spend,
  SUM(il.amount) AS annual_spend,
  COUNT(*) AS txn_count
FROM invoice_lines il
JOIN vendors v ON v.id = il.vendor_id
WHERE il.company_id = $1 AND il.status = 'categorized'
GROUP BY v.id, v.name, il.level2
ORDER BY period_spend DESC;

-- Redundancy flags for a vendor
SELECT r.* FROM recommendations r
WHERE r.company_id = $1
  AND r.rec_type = 'consolidation'
  AND r.current_vendor_id = $2
  AND r.dismissed = false;
```

### Tab 3: Categories

Purpose: Drill into where money goes.

**Tree view** or **expandable table**:

```
Level 1: Direct ($X, Y%)               ← top-level aggregation
  Level 2: Technology ($X, Y%)          ← L2 categories
    Level 3: Cloud Infrastructure ($Z)  ← L3 if present
      Account 6010: Cloud Hosting ($W)  ← leaf account_name
  Level 2: Facilities & Office
    ...
```

- Expand/collapse per node
- Click leaf account → show all transactions in that account

**Pie chart**: L2 breakdown (same as Overview but interactive — click slice to filter)

**Vendors per category table**: for a selected L2, show vendors, spend, redundancy count

**SQL**:
```sql
-- Hierarchical spend
SELECT level1, level2, level3, account_code, account_name,
  SUM(amount) AS total
FROM invoice_lines
WHERE company_id = $1 AND status = 'categorized' AND invoice_date >= $2
GROUP BY ROLLUP (level1, level2, level3, account_code, account_name);
```

### Tab 4: Savings

Purpose: Ranked list of opportunities to take action on.

**Cards or table**, sorted by savings potential × confidence:

| # | Type | Category | Current Vendor | Annual Spend | Potential Savings | Confidence | Action |
|---|---|---|---|---|---|---|---|
| 1 | Consolidation | Cloud Infra | Vendor A | $48K | $7.2K (15%) | 0.85 | Dismiss |
| 2 | Alternative | Office Supplies | Vendor B | $12K | $1.8K (15%) | 0.60 | Dismiss |
| 3 | Bulk Signal | Legal | Vendor C | $36K | $3.6K (10%) | 0.50 | Dismiss |

- Dismiss button → sets `dismissed = true`, hides from default view
- "Show dismissed" toggle at top
- **Total addressable savings** card at top: sum of all non-dismissed `estimated_savings`

**Color coding by confidence**:
- ≥0.8: green (high confidence)
- 0.5–0.8: yellow (medium)
- <0.5: red (low — may still be useful)

**SQL**:
```sql
SELECT * FROM recommendations
WHERE company_id = $1 AND dismissed = false
ORDER BY (confidence * estimated_savings) DESC;
```

### Tab 5: Settings

Purpose: Configure the company.

**Spend Tree section**:
- Current accounts count: "Your spend tree has N accounts across M categories"
- "Upload new spend tree" → file uploader (CSV)
- Show upload history (from `files` table where `file_type = 'spend_tree_csv'`)
- Warning: "Uploading a new tree won't re-categorize old data unless you trigger re-categorization"

**Data section**:
- Sync status + last sync time
- "Sync now" button (calls `sync.runner.run_sync()`)
- Invoice count: "N invoices, M lines categorized"

**Demo section** (MVP only):
- "Generate synthetic data" button — generates a fresh synthetic tenant with N vendors, M months
- Danger zone: "Reset all data" — deletes and regenerates

**No ERP connection UI yet** (coming in Phase 4).

## Data Flow

```
Page load:
  1. Read company_id from query params or default ("default")
  2. Render sidebar with company selector + sync status
  3. Render active tab

Tab switch:
  4. Re-run SQL queries for the active tab with current period filter
  5. Cache results with @st.cache_data (TTL: 60s)

Sync:
  6. User clicks "Sync now"
  7. Call sync.runner.run_sync(company_id) in a thread
  8. Show spinner, refresh on completion

Synthetic data:
  9. User clicks "Generate synthetic data"
  10. Call sync.runner.run_synthetic(company_id) 
  11. Show progress, redirect to Overview
```

## Stub Implementation

Current `app.py` is a placeholder with empty tabs. Phase 1 build order:

1. Wire up PostgreSQL connection in `app.py` (asyncpg pool, loaded once)
2. Build Overview tab (cards + spend by category pie + trend line)
3. Build Settings tab (synthetic data generation trigger)
4. Build Vendors tab (table + redundancy flags)
5. Build Categories tab (hierarchical drill-down)
6. Build Savings tab (ranked list + dismiss action)
7. Add period selector, company selector, sync status to sidebar

## Open Questions

- [ ] Should the dashboard auto-refresh (poll every N seconds) or be manual-refresh only?
- [ ] Do we need a full-text search on vendor names or is a simple filter enough?
- [ ] Export (CSV download of any table) — add to which tab?
- [ ] Should the Savings tab allow "actioned" status in addition to dismissed (for tracking real impact)?
