# Delivery roadmap

## v0.1 — implemented

Single-PC executable source, exact URL watches, Shopify variant and single-offer JSON-LD adapters, one-page collection discovery, persistent observations, price/restock transitions, comparison groups, history, backups, exports and Windows/Linux packaging workflow.

Release gate: unit tests, GUI smoke tests, live adapter probes and successful target-OS executable build. Do not call an artifact tested before the corresponding workflow succeeds.

## v0.2 — practical daily alerts

- Native notifications and system tray with explicit close/minimize behavior.
- Telegram/email optional settings, secrets stored through OS credential services, durable delivery outbox, retries and test notifications.
- Store-level health, configurable conservative intervals and durable per-host cooldowns.
- Variant picker in the add-product flow instead of requiring URL edits.
- Signed Windows installer and packaged executable launch test.

## v0.3 — useful Australian store coverage

- Confirm retailer permission and adapter behavior on an initial small Australian shortlist.
- Candidate stores: Only Packs, Plenty of Games, GUF, Tezza's, Final Boss, Grand J, J Toys, Techzone and Obsession. These names are candidates, not verified supported adapters.
- Store registry with evidence, region/currency, parser version and health; approved collection feeds/sitemaps and bounded pagination.
- Manual product-matching review: game, set, language, edition, package, pack count, region and GTIN/SKU evidence. Propose matches; do not auto-merge low-confidence titles.
- Shipping policies per destination, free-shipping thresholds and pickup availability. Keep unknowns visible.
- Fixture captures with actual permission and no personal data; adapter regression checks.

## Later — service scale

Only add Postgres, shared workers, queueing and accounts when several users or an always-on server justify them. The existing core is a starting point, not a promise of effortless scale. Introduce transactional alert delivery, migrations, retention/rollups, observability, access controls and a clear retailer contact process before broad unattended crawling. Browser fallback should be targeted and permitted rather than installed for every store.

Acceptance for each retailer: currency verified, correct selected variant, known sold-out/in-stock fixtures, preorder handling reviewed, rate-limit behavior verified, comparison identity checked, and honest freshness/error displays. No trading or checkout automation is planned.
