# Provider plugins (API v1)

The watchlist, deck ownership, pricing arithmetic, news feeds and charts are game-independent. Game tags accept arbitrary names. Riftbound has a built-in OpenRift catalogue; other games can use manual cards, local/URL artwork, compatible store listings, RSS feeds and installed catalogue providers. No deck-legality engine is implied.

Plugins live beside the active database under `plugins/<plugin-id>/plugin.json`. This directory is outside the executable. Settings → Game / store plugins installs JSON providers, opens the directory, enables/disables providers, reports errors and reloads them without rebuilding or restarting. New providers start disabled. Copy a Python provider's complete folder into that directory before reloading. A broken provider is isolated from the remaining providers. Disable a working plugin before replacing its files.

## JSON catalogue providers

Install `examples/plugins/tcgdex-pokemon/plugin.json` from the manager and enable it for Pokémon artwork/name search. It is a real public API integration, not a fictitious endpoint. Catalogue returns are limited to 40 candidates per search; larger catalogues are not mirrored. Results are cached for 24 hours, separated by provider, game and query. Offline results are labelled. Search provides candidates: the user chooses the correct printing; no card is silently matched by name.

Required keys: `api_version: 1`, unique lowercase `id`, `name`, `kind: "catalogue-json"`, `games` array, HTTPS `api_url`, and `fields` mapping with `id` and `name`. Optional `query_parameter` defaults to `q`; `game_parameter` passes the selected game; `results_path` is a dotted object/list path (empty means response root); `image_suffix` appends a fixed image rendition. Field paths can include numeric array indexes such as `images.0.url`.

Optional fields: `image_url`, `set_code`, `collector`, `printing`, `language`. Missing printing/language are `Other`, not inferred. Unknown artwork remains a readable placeholder. Prices in catalogue responses are ignored; store quotes and manual references keep their existing independent confirmation/currency rules. A provider returning a changed schema raises a readable error rather than inventing cards.

## Python providers

These run as local code with the same permissions as the app. Enable only trusted code. The manifest is inspected without executing `provider.py`; enabling executes it. Native dependencies must be distributed/configured by the provider author. Python packages installed into a separate system interpreter do not automatically appear inside a frozen executable. Pure Python/core-library providers work directly; heavyweight browser tools can run as separately installed sidecars, with their paths and prerequisites documented by the plugin.

```json
{
  "api_version": 1,
  "id": "my-store",
  "name": "My store reader",
  "kind": "python",
  "games": ["*"],
  "capabilities": ["store"],
  "hosts": ["shop.example.com"]
}
```

`provider.py` exports `create_plugin(context)` and returns an object. Context supplies `api_version` and a plugin-owned `data_dir`. Capability methods:

- `search_cards(game, query, client)` for `catalogue`: returns up to 40 dictionaries with `id`, `name` and optional catalogue fields above. Returns are normalized again by the host. No market prices are imported through this capability.
- `fetch_product(url, client)` for `store`: returns `tcg_alerts.core.Observation(title, integer_minor_unit_price, ISO_currency, stock, source, variant)` or `None` if not applicable. The host validates type and Observation fields, and labels its source with the plugin name. Exceptions become failed checks, retaining the last good price. Store routing requires an exact declared hostname. Overlapping enabled readers run in sorted folder order; disable conflicting readers.

Store readers receive the normal bounded HTTP client with robot permission checks, spacing, response limits and cooldowns. Catalogue readers receive a bounded API client: documented machine APIs are consumed under their API contract rather than treating their HTML-crawler robots rules as an API authorization contract. API providers remain responsible for the endpoint’s access terms and rate limits. Providers must preserve those source-access policies and avoid turning errors/challenge pages into price observations. Worker methods must not access Tk widgets. Providers should bound network calls and return promptly; they are trusted in-process code, not process-sandboxed or forcibly interruptible. Reload affects subsequent calls; an in-flight call may finish using the previous instance.

Game-specific deck validation, price-feed plugins, arbitrary UI panels and a plugin marketplace are future capabilities; v1 deliberately concentrates on card catalogues and product readers.

## Browser compatibility / blocked sources

Use a public JSON/API endpoint when it provides the exact product, currency and variant. For a genuinely JavaScript-rendered page, an optional browser sidecar can render the page before the store reader parses it. Playwright documents Chromium/Firefox/WebKit and requires its own package/browser installation. TLS/browser compatibility transports such as curl_cffi solve a different class of compatibility issues and do not supply a JavaScript engine. No such dependency, proxy rotation service or challenge solver is bundled in this release: the live tested stores worked through the normal adapter. Choose and test a transport against a concrete failing source before shipping one. A failed request must never generate a restock or price event.

References: [MO2 Python plugins](https://www.modorganizer.org/python-plugins-doc/writing-plugins.html), [OpenRift API](https://openrift.app/developers), [TCGdex cards](https://tcgdex.dev/rest/cards), [TCGdex assets](https://tcgdex.dev/assets), [Playwright library](https://playwright.dev/python/docs/library), [curl_cffi](https://curl-cffi.readthedocs.io/).


GitHub release updates and installation are now implemented in v0.6; see [UPDATES.md](UPDATES.md). Optional `cache_seconds` (0–86400) and provider version control the local catalogue cache. The Cyberpunk example uses exact-name lookup and a five-minute cache.
