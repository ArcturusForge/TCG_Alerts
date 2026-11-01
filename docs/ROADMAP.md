# Delivery roadmap

## v0.2 — implemented

- Windows/Linux desktop packaging and launch checks.
- Exact-product watchlists, background Shopify/JSON-LD checks, alerts, history, comparison groups, backups and CSV exports.
- Country/state/game metadata and filters, with an additive upgrade from v0.1.
- Cached official Riftbound/Cyberpunk publisher headlines, source health and custom RSS/Atom feeds.
- Per-listing observed-price charts and local check/link-open activity charts, with evidence inspection.

These views do not establish merchant verification, national delivery coverage, physical stock, comprehensive market pricing or retailer visitor traffic.

## Recommended next priorities

1. **Verified Australian store registry and variant picker.** Make useful watches easier to create and prevent pack/box/case/language mismatches. Candidate retailers include Only Packs, Plenty of Games, GUF, Tezza's, Final Boss, Grand J, J Toys, Techzone and Obsession; these are candidates, not an asserted support list.
2. **Native notifications and system tray.** Alerts should be useful while another application is in front. Add explicit close/minimize behavior and optional Telegram/email only with credentials, delivery retries and an outbox.
3. **Release calendar.** Store source URL, region, date precision, confirmed/tentative status and last-verified timestamp. A seasonal announcement stays a window until an exact date is confirmed.
4. **Delivered-cost comparison.** Add destination/postcode, pickup availability, shipping thresholds and explicit pack-count/unit-price metadata. Unknown shipping remains unknown.
5. **Saved filtered views and bulk tags.** Useful as store coverage grows. Store-level metadata should propagate to its listings with a clear override rule.
6. **Sourced demand indicators.** Keep search interest, local clicks, retailer visits, sales volume and stock changes separate. Add a metric only when a legitimate named source is available.

## Retailer coverage acceptance

Check currency, exact selected variant, known sold-out/in-stock examples, preorder behavior, request policies/rate limits, comparison identity, freshness and failure displays. Preserve permitted parser fixtures without personal data. Add bounded approved feeds/sitemaps and pagination before broad catalog discovery. No login, CAPTCHA bypass or checkout automation.

## Service scale

Add Postgres, shared workers, queues and accounts only when multiple users or an always-on service justify them. Before broad unattended crawling, add database migrations, transactional external alert delivery, retention, observability, access controls and a retailer contact process. Monitoring on a PC still requires that PC to be awake and the app running.
