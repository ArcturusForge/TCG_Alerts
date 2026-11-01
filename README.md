# TCG Alerts

A private desktop radar for sealed TCG prices and restocks. Built for a Windows PC first, with Linux source support. No hosted server, subscription, API keys or Python packages are required to run from source (Python with Tk is required).

**Status: working v0.1 MVP, not yet a full-store aggregation service.** It monitors exact product URLs that you choose. It does not claim coverage of 150 stores, verified merchants, physical inventory or guaranteed restock detection.

## Start

Install Python 3.11 or later with Tcl/Tk support. On Windows, the standard python.org installer includes Tk. On Ubuntu, install `python3-tk`.

```sh
python run.py
```

For a standalone Windows executable, open the repository's **Actions → Desktop checks and executable**, select a successful run, and download **TCGAlerts-Windows**. Extract the ZIP and run `TCGAlerts.exe`. A Windows build must finish successfully before that artifact is available. The binary is unsigned.

To build locally on Windows:

```powershell
python -m pip install pyinstaller==6.16.0
python -m PyInstaller --noconfirm --clean --onefile --windowed --name TCGAlerts run.py
```

The result is `dist/TCGAlerts.exe`. Build on the target operating system; a Linux build is not a Windows executable.

## Use

1. Choose **Track product** and paste an exact HTTPS product URL. For Shopify pages with multiple options, select the desired option in the shop and copy its `?variant=...` URL. Ambiguous variants are rejected with the available IDs in the error detail.
2. Add a target price and optionally a shipping amount. Targets are in the listing's reported currency. A blank shipping amount means unknown; `0` means free. A target includes shipping only when that amount is supplied.
3. Leave the app open. New watches are checked automatically; each successful listing is scheduled again in 15 minutes, with up to 30 seconds of jitter. **Check due now** wakes the worker but does not bypass cooldowns. Failed checks back off exponentially up to 24 hours.
4. Read alerts in the Alerts tab. The app rings its bell when an alert occurs; there are no external notifications yet. Closing the app stops monitoring. A sleeping PC cannot collect observations.
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

Network tests are mocked; unit tests never contact stores. A live Only Packs product check and collection discovery were performed during development. See [research and engineering decisions](docs/RESEARCH.md) and [roadmap](docs/ROADMAP.md).

Core modules: `core.py` (SQLite and transitions), `sources.py` (transport, adapters and discovery), `monitor.py` (serial background worker), `app.py` (Tk desktop interface). The tracking core does not depend on the GUI and can later power an always-on service.
