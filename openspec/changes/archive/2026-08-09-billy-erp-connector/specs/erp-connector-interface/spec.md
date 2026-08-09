## ADDED Requirements

### Requirement: HTTP connectors share one base with a per-request auth hook

Connectors that talk to an ERP over HTTP SHALL derive from a shared
`HttpErpConnector` base that owns the HTTP client, header assembly, status-code
to exception mapping, retry, and binary fetch, so this logic exists once rather
than once per ERP.

- A subclass SHALL supply its authentication by implementing a hook returning
  the headers to send.
- That hook SHALL be evaluated **on every request**, not once at `authorize()`,
  so a connector whose token expires can refresh it without any change to the
  `ErpConnector` interface or to any caller.
- The base SHALL expose the HTTP client as an injectable attribute so tests can
  substitute a transport without patching internals or reaching the network.
- The abstract method signatures of `ErpConnector` SHALL be unchanged by this
  base.

#### Scenario: Auth headers are re-evaluated per request

- **WHEN** a connector performs two requests and its auth hook returns a
  different token the second time
- **THEN** the second request carries the second token

#### Scenario: Tests substitute the transport

- **WHEN** a test assigns a stub HTTP client to the connector before calling a
  fetch method
- **THEN** the connector uses it and issues no outbound network request

### Requirement: HTTP status codes map to the declared connector errors

The shared base SHALL translate ERP responses into the connector error
vocabulary consistently for every connector.

- HTTP 401 or 403 SHALL raise `ErpAuthError`.
- HTTP 429 SHALL raise `ErpRateLimitError`, carrying the retry delay when the
  ERP supplies one. It SHALL NOT be reported as `ErpDataError`: a caller must be
  able to tell "back off and retry" from "the ERP sent nonsense".
- HTTP 5xx and transport failures SHALL raise `ErpConnectionError`.
- Any other unexpected status SHALL raise `ErpDataError`.
- Before raising, the base SHALL retry a rate-limited or server-error response a
  bounded number of times with backoff. Once the bound is exhausted the error
  SHALL escape, and the sync runner's existing per-integration isolation records
  it against that integration alone.

#### Scenario: A rate-limited ERP raises the rate-limit error

- **WHEN** the ERP answers HTTP 429 on every attempt
- **THEN** `ErpRateLimitError` is raised after the bounded retries, not
  `ErpDataError`

#### Scenario: A transient server error is retried

- **WHEN** the ERP answers HTTP 503 once and then succeeds
- **THEN** the call returns the successful response and raises nothing

#### Scenario: An unreachable host is a connection error

- **WHEN** the HTTP request fails at the transport layer
- **THEN** `ErpConnectionError` is raised

### Requirement: Pagination is a declared strategy, not per-connector code

The connector layer SHALL provide pagination strategies that a connector selects
by declaration, so paging style is configuration rather than duplicated loops.

- The layer SHALL provide at least: page-number paging (a page index and size,
  stopping on a reported total), skip-pages paging (stopping on a
  next-page indicator), and cursor paging (following a next-link until absent).
- A connector SHALL declare which strategy it uses, and the shared base SHALL
  drive it and return the accumulated items.
- Switching a connector between strategies SHALL require no change to its field
  mapping code.

#### Scenario: A paged listing accumulates every item

- **WHEN** a connector using page-number paging lists a resource whose results
  span three pages
- **THEN** every item from all three pages is returned in one list

#### Scenario: Cursor paging stops when the link is absent

- **WHEN** a connector using cursor paging receives a page carrying no next-link
- **THEN** paging stops and no further request is made

### Requirement: A connector may filter by account after fetching

A connector whose ERP cannot filter entries by account SHALL apply the
`account_codes` selection itself after fetching: the filter is defined by its
**result**, not by where the filtering happens.

- The observable behaviour SHALL be identical either way: `None` returns all
  accounts, an empty set returns no entries, and a non-empty set returns only
  entries whose account is in it.
- An empty set SHALL short-circuit before any request, regardless of strategy.
- A connector that filters client-side SHALL document that it fetches the full
  ledger for the date window, because that cost is invisible in the signature.

#### Scenario: Client-side filtering is observably identical

- **WHEN** `fetch_entries(account_codes={"1350"})` is called on a connector that
  filters client-side
- **THEN** every returned entry has `erp_account_code == "1350"`, exactly as for
  a connector that filters at the ERP

#### Scenario: An empty selection issues no request

- **WHEN** `fetch_entries(account_codes=set())` is called on any connector
- **THEN** no entries are returned and no HTTP request is issued

### Requirement: A connector may declare brand metadata for its catalog entry

`ErpConnector` SHALL support optional class-level brand metadata alongside
`display_label`, so a client can present a connector recognisably without
knowing any connector by name.

- The metadata SHALL comprise a brand key for locating artwork, a short
  human-readable description of the ERP, and a link to its documentation.
- All three SHALL be optional. A connector declaring none SHALL produce exactly
  the catalog entry it produces today.
- The metadata SHALL be declarative class attributes, so registering a connector
  remains the whole of the wiring needed for it to appear in a client.

#### Scenario: A connector declaring brand metadata exposes it

- **WHEN** a connector declares a brand key, description and documentation link
- **THEN** the connector catalog carries all three for that connector

#### Scenario: A connector declaring none is unaffected

- **WHEN** a connector declares no brand metadata
- **THEN** its catalog entry carries its `erp_type`, label and credential fields
  as before, with the brand fields absent
