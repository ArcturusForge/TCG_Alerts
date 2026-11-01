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

## v0.2 additions

- Official news indexes checked: [Riftbound publisher news](https://playriftbound.com/en-us/news/) and [Cyberpunk publisher blog](https://cyberpunktcg.com/blog). Both provide visible article cards suitable for a bounded headline-only adapter; custom RSS/Atom is supported separately.
- [Cyberpunk Set Two announcement](https://cyberpunktcg.com/blog/set-2-announcement) illustrates why a publication date is not a launch date: an article can announce a future seasonal release window. The app stores publication dates only and links readers to the original article. It does not invent local launch dates or translate unspecified seasons into Australian dates.
- Merchant country/state are explicit user-entered tags. They do not claim delivery coverage or address verification. Existing watches are Unspecified rather than guessed from AUD pricing.
- Price analytics are per exact listing and observed time window. Activity charts count recorded check outcomes and browser open requests locally. We have no access to retailer analytics, sessions, unique visitors or sales; no estimated traffic is supplied as though it were measured.
- Upgrade validation covers additive v1→v2 migration, metadata filters, publication parsing, RSS/Atom safety, source caching, filtered analytics and empty chart states. Windows/Linux packaging includes both GUI and executable launch checks.


## v0.3 implementation and research snapshot

Location sources checked 1 November 2026: [Only Packs](https://onlypackstcg.com.au/pages/contact), [Plenty of Games FAQ](https://www.plentyofgames.com.au/pages/faq), [Final Boss](https://thefinalbosscollectables.com.au/pages/contact), [GUF](https://guf.com.au/pages/contact-us), [Tezza's](https://www.tezzasgames.com/), and [Techzone](https://techzonegeelong.com/). Plenty's FAQ discusses pickup; other starting pickup policies remain unknown. Each store has separate parser-support notes. No merchant trust badge or branch-level online inventory inference is made.

Calendar sources: [Cyberpunk production diary](https://cyberpunktcg.com/blog/production-update-1), [official event calendar](https://cyberpunktcg.com/calendar), [Riftbound 2026 Drawings](https://playriftbound.com/en-us/news/announcements/riftbounds-2026-drawings/), and [Cyberpunk Set Two](https://cyberpunktcg.com/blog/set-2-announcement). Exact dates, ranges and seasonal wording retain their differing precision and unspecified regional scope. Calendar entries are dated snapshots, with editable evidence rather than an automatic re-verification claim.

[Only Packs shipping policy](https://onlypackstcg.com.au/policies/shipping-policy) describes checkout-calculated shipping and promotions. We did not seed an unconditional rate from a product banner. User-entered country/postcode/currency estimates carry evidence and entered dates.

Native notifications follow [pystray's API](https://pystray.readthedocs.io/en/latest/usage.html). Callbacks queue commands to the Tk thread. Windows is supported; other platforms preserve a visible app. Lifecycle tests use a fake icon, while packaged Windows launch tests import the native backend. Neither claims to prove notification visibility under an individual user's OS settings.


## v0.4 implementation notes — 2 November 2026

The private artwork feature accepts user-supplied HTTPS image URLs or explicit local file selections. It bundles no third-party card artwork and performs no bulk catalog scraping. [Pillow's image documentation](https://pillow.readthedocs.io/en/stable/reference/Image.html) informed lazy-open/dimension checks, thumbnailing and malformed-image handling. Requests and decoded dimensions are bounded; ImageTk objects are created only on the GUI thread.

Deck estimates reuse existing watched singles URLs after explicit one-copy identity confirmation. Manual references, observed asking prices and fresh in-stock offers remain distinct. Reference subtotals expose priced-copy coverage; stale/failed/paused observations can contribute only a labelled reference, not a fresh purchase offer. Price/quantity arithmetic, currency isolation, import rollback, watch deletion, image decoding and the v3→v4 migration are covered by regression tests. The earlier provider research remains a dated design reference; no eBay or catalog API integration was silently added.
