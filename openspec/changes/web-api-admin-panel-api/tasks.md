## 1. CORS

- [x] 1.1 Add `WEB_API_CORS_ORIGINS` to `web_api/config.py` (parse comma-separated
  list, trimmed; default empty)
- [x] 1.2 Add `CORSMiddleware` in `web_api/app.py` from the configured origins
  (allow credentials, standard methods/headers); no-op when empty
- [x] 1.3 Document `WEB_API_CORS_ORIGINS` in `.env.example` (dev localhost value)

## 2. Users

- [x] 2.1 Add `UserRead` schema (`id`, `email`, `name`, `role`, `is_system_admin`,
  `organization_id`) in `web_api/schemas.py`
- [x] 2.2 Add `web_api/routers/users.py`: `GET /api/v1/users/me` (via
  `current_user`) and `GET /api/v1/users` (org-scoped, paginated `Page[UserRead]`)
- [x] 2.3 Register the users router in `web_api/app.py`

## 3. Vendors

- [x] 3.1 Add `VendorRead` schema (`id`, `name`, `country_code`, `vat_number`,
  `description`) in `web_api/schemas.py`
- [x] 3.2 Add `web_api/routers/vendors.py`: `GET /api/v1/vendors` — distinct
  vendors referenced by the org's invoices (join `Invoice.vendor_id`), optional
  `q` on name/VAT, optional scoped `company_id`, paginated
- [x] 3.3 Register the vendors router in `web_api/app.py`

## 4. Tests

- [x] 4.1 `tests/web_api/test_users.py`: `/users/me` returns the caller's profile
  + role/system-admin; 401 without token; `/users` is org-scoped and paginated,
  no cross-tenant leakage
- [x] 4.2 `tests/web_api/test_vendors.py`: lists only the org's referenced
  vendors; `q` filters by name/VAT; foreign `company_id` → 404; empty scope → empty
- [x] 4.3 CORS: a request with an allowed `Origin` gets CORS headers; a
  non-configured origin does not (using a configured test app)
- [x] 4.4 `uv run pytest` — full suite green

## 5. Docs

- [x] 5.1 `CLAUDE.md`: add `/users/me`, `/users`, `/vendors` to the endpoint list
  and note CORS via `WEB_API_CORS_ORIGINS`
