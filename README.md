# TCG Alerts

A private desktop radar for sealed TCG prices and restocks. Built for a Windows PC first, with Linux source support. No hosted server, subscription or API keys are required. Source needs Python with Tk; Windows tray dependencies are included in the executable.

**Status: working v0.3 MVP, not yet a full-store aggregation service.** It monitors exact product URLs that you choose. It does not claim coverage of 150 stores, verified merchants, physical inventory or guaranteed restock detection.

## Start

Install Python 3.11 or later with Tcl/Tk support. On Windows, the standard python.org installer includes Tk. On Ubuntu, install `python3-tk`.

```sh
python -m pip install .
python run.py
```

For a standalone Windows executable, open the repository's **Actions → Desktop checks and executable**, select a successful run, and download **TCGAlerts-Windows**. Extract the ZIP and run `TCGAlerts.exe`. A Windows build must finish successfully before that artifact is available. The binary is unsigned.

To build locally on Windows:

```powershell
python -m pip install . pyinstaller==6.16.0
python -m PyInstaller --noconfirm --clean --onefile --windowed --name TCGAlerts run.py
```

The result is `dist/TCGAlerts.exe`. Build on the target operating system; a Linux build is not a Windows executable.

## Use

1. Choose **Track product** and paste an exact HTTPS product URL. For Shopify pages with multiple options, select the desired option in the shop and copy its `?variant=...` URL. Ambiguous variants are rejected with the available IDs in the error detail.
2. Add a target price and optionally a shipping amount. Targets are in the listing's reported currency. A blank shipping amount means unknown; `0` means free. A target includes shipping only when that amount is supplied.
3. Leave the app open. New watches are checked automatically; each successful listing is scheduled again in 15 minutes, with up to 30 seconds of jitter. **Check due now** wakes the worker but does not bypass cooldowns. Failed checks back off exponentially up to 24 hours.
4. Read alerts in the Alerts tab. The app rings its bell when an alert occurs; native Windows tray notifications are available. Closing exits by default; optional close-to-tray continues while the PC is awake. A sleeping PC cannot collect observations.
5. Compare stores by assigning identical products the same comparison group. Match language, set, edition, product type and quantity yourself. The table separates currencies, excludes failed/stale/paused listings, and leaves unknown delivered costs blank. It does not automatically normalize product names.

The **Discover** tab reads one collection page and extracts same-store Shopify-style product links. Only Packs' Riftbound collection is prefilled as a convenient starting URL, not an endorsement. Select a result to create a watch. This is not exhaustive catalog discovery: pagination and JavaScript-only listings are not followed.

## What works

- Shopify Ajax product variant prices/availability, with currency independently read from the public cart endpoint (GET only; nothing added to cart).
- Generic public product pages containing exactly one JSON-LD Product and one Offer.
- Persistent watchlist, pause/resume, exact-price threshold alerts, confirmed restock transitions and de-duplication.
- Price history chart/table, comparisons, local timestamps, last-check health and readable error details.
- CSV export (money in minor units), database backup and persistent storage outside the executable directory.
- Conservative robots checks, request spacing, response size limits, same-origin redirects, 429/503 cooldowns and Retry-After handling.

## Data and alert semantics

SQLite database: `%LOCALAPPDATA%\TCGAlerts\alerts.sqlite3` on Windows, `$XDG_DATA_HOME/TCGAlerts/alerts.sqlite3` or `~/.local/share/TCGAlerts/alerts.sqlite3` on Linux. Backups use SQLite's online backup API. Restore a backup by launching with `python run.py --database PATH_TO_BACKUP`; use a copy if you want to preserve the original backup.

Money uses integer minor units; this MVP is intended for two-decimal currencies such as AUD, USD and CAD. There is no FX conversion. Store shipping, import charges, discounts, coupon eligibility, tax differences and address restrictions are not calculated automatically.

A successful in-stock check meeting the target produces a price alert, including on the first check. It will not repeat until a later successful observation leaves the qualifying state. A restock alert requires a previously observed `out_of_stock` followed by `in_stock`. An initial successful check is never itself a restock. Preorders and unknown availability do not trigger either alert. An error preserves the last good price/stock and produces no observation or stock transition. History is observed listing data, not sales or market value.

Shopify `available` describes storefront purchase availability; merchants can allow overselling. Title-labelled preorders are marked separately, but an unlabelled preorder can still appear purchasable. Confirm fulfillment details at checkout. Generic unsupported pages, login/CAPTCHA walls, absent currencies and ambiguous offers are shown as check failures. No browser automation or anti-bot bypass is included.

## Development

```sh
python -m unittest discover -s tests -v
# Linux display test:
xvfb-run -a python tests/gui_smoke.py
# Windows display test:
python tests/gui_smoke.py
```

Network tests are mocked; unit tests never contact stores. Live Only Packs product/collection checks and official Riftbound/Cyberpunk publisher-page checks were performed during development. See [research and engineering decisions](docs/RESEARCH.md) and [roadmap](docs/ROADMAP.md).

Core modules: `core.py` (SQLite and transitions), `sources.py` (transport, adapters and discovery), `monitor.py` (serial background worker), `app.py` (Tk desktop interface). The tracking core does not depend on the GUI and can later power an always-on service.

## v0.2 — region, games, news and analytics

Use the **Game**, **Store country**, and **Store state / region** selectors above the tabs. For example: `Riftbound → Australia → Victoria`. Selecting an Australian state sets the country to Australia. Reset clears every watchlist filter. You can tag Riftbound, Cyberpunk and other games or enter custom game/country/region names in the watch editor.

These are **store location tags you supply**, not shipping eligibility or a verified address directory. An Australian currency, domain or product language does not establish where a store is based. Existing v0.1 watches migrate as Unspecified; edit their tags to include them in location/game filters. The upgrade preserves watches, observations and alerts. Country/state/game filters apply to counters, watchlists, comparisons, alert history and analytics. Search/status filters apply to the watchlist. Monitoring continues for all enabled watches even when hidden by a view filter. CSV export remains a full watchlist export and includes the new tags.

### News board

The **News** tab reads headline links and publication dates from the official Riftbound and Cyberpunk news pages. It refreshes due sources hourly while the app is open and caches headlines for offline use. Failed sources retain their cached items and show an error in **Manage sources**. A refresh button respects cooldowns. This reads the visible publisher index page, not their entire archive.

Filter by game above and by topic inside the board. Topic tags come from headline keywords and can be imperfect. **Publication dates are not release dates.** No article publication date is promoted to a product release date, and seasonal windows such as “Spring” are not translated into Australian dates. Open the source story for release details and territory. These publisher indexes have global/unspecified regional scope; store-country filters deliberately do not hide them.

Use **Manage sources / add RSS** to add RSS or Atom feeds for other games, new TCG announcements or a general news publisher. Supply a name, HTTPS feed URL and source-level game tag. Custom feeds are user sources; they are not verified official publishers. You can pause/resume any source. Only headline, link, publication date and keyword topic are stored; article text is not republished. There is no promise of coverage of every new TCG or all announcements.

### Analytics

The **Analytics** tab offers 7/30/90-day windows and three charts with hover values and an **Inspect plotted data** table:

- **Item price:** actual observation timestamps for one selected exact listing, in its own currency. Includes sold-out and preorder price observations; excludes shipping. Low, last observed price and first-to-last change describe this observed sample, not market returns. Gaps between observations do not prove what happened while the app was asleep.
- **Checks per UTC day:** successful versus failed listing checks for current tagged watches in the selected country/state/game scope. The success rate is successful attempts divided by all recorded successful/failed attempts. It is not availability or uptime. First/last UTC days can be partial.
- **Store-link opens per UTC day:** browser open requests made through this installation's Open store action, where the browser accepted the request. It does not establish that a retailer page loaded, or represent retailer visitors, unique people, product demand, sales or general market traffic.

Activity recording begins with v0.2; existing observations are not converted into invented historical activity. Current tags determine historical activity scope; deleted-watch activity is excluded. Each evidence series uses at most the latest 10,000 rows in the window, with a cap warning. Retailer visitor traffic requires an independently supplied or licensed source and is currently unavailable. No analytics is transmitted to us.


## v0.3: stores, variants, native alerts, calendar and delivered cost

**Stores** starts with six curated Australian entries focused on Victoria: Only Packs, Plenty of Games, The Final Boss Collectables, GUF, Tezza's Games and Techzone Geelong. Each has a location source/check date and independent adapter-support note. Location evidence is not merchant certification or a guarantee of parser support, authenticity or stock. GUF's online stock is not assigned to individual branches. Open store/source/catalog, add/edit entries, or explicitly apply a directory location to linked watches. New known-store watches inherit country/state only when both are Unspecified. Existing tags are preserved during upgrade.

In a new watch dialog, **Pick Shopify variant** loads exact options, reported price/currency and availability. Choose explicitly; no cheapest/default option is assumed. The selected URL includes the exact variant ID. A fresh check occurs after saving. Existing watches do not change variant, preserving their history; add another watch instead. **Delivery & units** edits pack count, fixed shipping country/postcode and listing pickup eligibility.

**Settings & data** includes native Windows notifications, a test button, Minimize to tray, Exit, and opt-in close-to-tray. The tray menu can show the app, wake due checks or exit. Closing exits by default. A window hides only when its tray icon is ready; failure keeps explicit minimize visible. Windows settings determine notification visibility. Linux remains windowed with in-app alerts. Sleeping PCs do not monitor. Email/Telegram and native Linux/macOS tray support are not included.

**Calendar** starts with four source-linked entries: Cyberpunk Welcome to Night City retail release/prerelease weekend, Riftbound Gift of the Rift, and Cyberpunk Set Two's announced seasonal window. This is a dated research snapshot, not an automatically re-verified comprehensive feed. Each entry has game/type, region, status, precision, source, checked date and notes. Add/edit releases, local events, promos or prereleases. Day/Range are exact dates; Window/TBA have no invented dates. A confirmed announcement can still have an approximate window. Seasonal wording is not translated into an assumed Australian date. Game filtering applies; calendar region is independent of store geography. Export visible exact dates as all-day `.ics` events. Window/TBA/cancelled entries are skipped and counted. There are no release reminders or time-of-day conversions.

**Compare** estimates the cost of one listed unit per row, with destination country/postcode and Delivery/Pickup mode. Per-pack cost requires a user-verified pack count and known item-plus-shipping total. No pack count is guessed from title or price. Enter a fixed quote for an exact postcode or add sourced store rules under Stores → Shipping rules. Exact-postcode rules override country-wide rules; matching fixed listing quotes take precedence. Rates are currency-specific with no FX conversion. A free-threshold-only rule leaves shipping unknown below the threshold. No starting shipping rates are guessed from promotional banners.

Legacy blank-postcode quotes apply only with a blank Compare postcode. They never become destination-specific quotes automatically. Pickup requires an explicit listing/store policy and remains an estimate requiring item eligibility/readiness confirmation. Extras, duties and basket discounts are not calculated. Compare destination rules do not redefine alert targets: those still use item price plus the watch's entered fixed shipping, if present. Database upgrade is additive and preserves observations, alerts and prior metadata.

The deck-builder idea and researched data-source boundaries are specified in [DECK_BUILDER.md](docs/DECK_BUILDER.md). It is a proposed next milestone, not part of this executable.
