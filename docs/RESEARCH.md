# Research and decisions — 1 November 2026 (Australia)

## Reference service

[TCG Sealed Alerts](https://tcgsealedalerts.com/) advertises cross-store sealed product comparisons, target-price SMS alerts, market views and preorder browsing. Its homepage currently advertises 774 US/Canadian stores. This is the service's own coverage claim, not independently audited merchant coverage. The useful behaviors to reproduce are finding a product, comparing equivalent listings, setting a target and seeing freshness. We do not copy its branding, datasets, implementation or merchant verification claims.

## Changes to the Gemini brief

| Brief assumption | Engineering decision |
|---|---|
| Next.js, backend service, Postgres, Redis and scraper containers | Start with Python/Tk and SQLite for a single PC. No SEO requirement in a desktop executable. Separate core supports a hosted service later. |
| Hourly scraping plus instant alerts | Alerts are evaluated on observations. Hourly polling permits nearly an hour of detection delay. MVP uses 15-minute polling while awake; this is not real time. |
| 150+ stores from the start | Prove exact-product adapters and store health first. A URL is not proof of adapter support. Expand coverage only with store validation. |
| Guess stock by absence of “sold out” | Require typed availability. Unknown and failed requests never become in-stock or sold-out observations. |
| Product title normalization | Do not silently merge pack, box, case, region or language editions. Exact variant IDs first; manually reviewed comparison groups next. |
| Shipping defaults to zero | Unknown shipping is unknown. User can enter a known amount or explicitly enter zero. |
| Listings schema doubles as history | Separate immutable successful observations and alert history. Failed checks are operational state. |
| Stores trusted by default | No unearned trust badge. Merchant vetting requires evidence and an explicit process. |
| Email and Telegram in first implementation | In-app alerts first. External delivery needs credentials, an outbox, retries, duplicate handling and configuration. |

## Primary implementation references

- [Shopify Ajax Product API](https://shopify.dev/docs/api/ajax/reference/product): public product-handle JSON, per-variant fields and presentment currency. Currency is checked through the locale's `cart.js`, because a dollar sign or Australian domain is insufficient evidence of AUD. GET requests do not change the cart.
- [Schema.org Offer](https://schema.org/Offer): explicit price, currency and availability. Aggregate/multiple offers are rejected by the generic adapter because a lowest price can belong to a different package.
- [Python Tk documentation](https://docs.python.org/3/library/tkinter.html): a native desktop toolkit bundled with standard Windows Python; worker events are queued to the main GUI thread.
- [PyInstaller manual](https://pyinstaller.org/en/stable/): bundles the app and interpreter; the build is OS-specific. GitHub Actions builds on Windows and Linux separately.
- [RFC 9309](https://www.rfc-editor.org/rfc/rfc9309.html): crawl permissions and failure handling. MVP denies access when robots cannot be verified, apart from missing 404/410 robots files. It is stricter than the RFC's allowance for other 4xx statuses. No anti-bot bypass or login automation.

## Australian probe

[Only Packs Riftbound collection](https://onlypackstcg.com.au/collections/riftbound) demonstrates why variants matter: Chinese Slim/Fat boxes and other editions appear alongside English-style listings. The [Vendetta booster box product page](https://onlypackstcg.com.au/products/riftbound-booster-box-vendetta) was checked via the implemented adapter: AUD 219.99, unavailable, Shopify variant `45959416971462`. This was a development observation, not an ongoing price guarantee. Shipping was not inferred as free from promotional text.

## Boundaries

Retailer support can break when templates, structured data, policies or endpoints change. Shopify availability does not establish physical stock; unlabelled preorder/overselling configurations need manual verification. No two-decimal currency conversion, merchant verification, investment valuation or guaranteed alert timing is claimed. A future 24/7 mode needs an always-on host or an awake PC and a deliberate background lifecycle.
