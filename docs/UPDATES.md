# Updates and browser helper

Settings → Updates / browser helper controls background checks. The app checks stable GitHub releases on startup and every six hours while open; no scheduler or server is required. Draft/prerelease/non-semantic versions are not installed. App downloads and plugin downloads can be toggled separately. A failed check leaves the installed version intact and reports an error here.

## App release channel

The source is `ArcturusForge/TCG_Alerts`, stable `vMAJOR.MINOR.PATCH` tags. CI builds/tests both desktops and, only after both succeed on main, publishes versioned GitHub Releases with `TCGAlerts-Windows.zip`, `TCGAlerts-Linux.zip` and individually installable plugin ZIPs. Existing versions are never silently overwritten. Actions artifacts remain available for development builds; automatic updates use Releases, not expiring artifact URLs.

Every binary download requires the GitHub asset's SHA-256 digest and exact declared size. HTTPS release redirects strip credentials when changing host. ZIP/tar paths, links, duplicates, member counts and expanded sizes are checked before installing into a new version directory. This verifies downloaded bytes against GitHub metadata; it is not code signing or an independent publisher signature.

The packaged Windows app stages new releases while running. Closing it hands off to a separate PowerShell process, waits for exit, verifies the staged executable, runs its packaged smoke test, retains `TCGAlerts.exe.previous`, replaces the executable and reopens the same database. Failed launch probes do not replace the current app. Copy/launch failures after replacement restore the previous executable. Result details are written to `updates/apply-result.txt`. Writable installation directories are required; access failure leaves the staged download for a later retry. The user database is never replaced by an app update. A pre-update SQLite backup is saved under updates/ before scheduling replacement; use it if a future migration makes the database incompatible with a rollback executable.

Source launches and Linux builds download/stage an update; use **Restart into downloaded update** to launch its executable. They do not rewrite a git checkout or replace an arbitrary Linux installation. Disable automatic app downloads to keep updates manual. A failed check does not discard an already staged update. There is no claim that a smoke check detects every later runtime fault; the previous executable is retained for manual recovery.

This repository is public. App releases, the bundled provider release ZIPs and the public browser-helper releases can be checked and downloaded without a GitHub token. No extra update configuration is required after installing v0.6.1.

`TCG_ALERTS_GITHUB_TOKEN` remains optional for higher API rate limits or private third-party provider repositories; those private repositories require read access. No account token is embedded in the app, release files, logs or repository. Publishing still uses the repository Actions token's contents-write permission in the gated release job.

## Plugin updates

Use **Game / store plugins → Install from GitHub** and specify the repository and exact ZIP asset. An installed manifest pins its source:

```json
"version": "0.6.0",
"update": {
  "repository": "ArcturusForge/TCG_Alerts",
  "asset": "TCGAlerts-plugin-netdeck-cyberpunk.zip"
}
```

New installations start disabled. The updater verifies the asset, plugin id, API compatibility, version and unchanged repository/asset/kind/games/capabilities/hosts before replacing the provider directory. Scope changes require a manual installation instead of being silently granted. Existing `data/` is preserved; `.previous` retains a rollback installation. Updated Python code activates on restart (or explicit Reload). A plugin failing to load after replacement falls back to its previous installation when present. That failed version is remembered so automatic checks wait for a different release rather than repeatedly reinstalling the broken one. A rollback restores files, not arbitrary side effects of trusted Python code.

The shipped Pokémon TCGdex and Cyberpunk NetDeck manifests pin this channel. Cyberpunk uses the public embed SDK's exact-name lookup, not a fuzzy full-catalogue browser. For example, `Rebecca: Having a Moment` was returned in a live check. Artwork uses provider-supplied signed URLs and can expire; loaded previews stay cached, and running the lookup again obtains a current URL. Catalogue caches are separated by provider/version/game/query; the Cyberpunk lookup refreshes after five minutes. Prices are never imported through this card-identity endpoint.

## Browser helper

FlareSolverr is downloaded on demand from **FlareSolverr/FlareSolverr**'s official stable GitHub releases, using the same checksum/archive checks. Windows and Linux x64 binaries are supported. First download is roughly 250–400 MB. It runs on a randomly chosen **127.0.0.1** port; no service is exposed to the network. The app starts it only when needed, serializes rendering calls, drops GitHub credentials from its environment, uses temporary browser requests, and stops its process tree when closing. It does not import the user's normal browser profile.

After the initial installation, automatic checks update the helper too. A new helper must pass its local readiness check before its current pointer changes; failed startup retains the prior selection. The two selected helper versions are kept; older helper directories are removed when possible. The installation may need OS libraries, and success depends on the remote challenge and current browser compatibility.

Normal adapters remain first choice. The helper is a fallback for a product-page HTTP 403 or a recognizable browser challenge after robots permission has been checked. Robots failures/disallow rules and HTTP 429/503 cooldowns are not overridden. Only successful same-store HTML is accepted; challenge text and failed renderings never become prices or restock transitions. No login, cart write, credential replay, proxy service or paid CAPTCHA solver is configured. Vendor behavior can change; the helper is not a guarantee of access to every retailer.

## Remaining integrations

Sold-price feeds and wider market traffic still need suitable data access; no sales or external visitor history is invented. Automatic calendar verification and game-specific legality engines remain separate features. The new deck missing-card budget alert uses existing verified links: it requires fresh in-stock same-currency unit asks covering every missing copy, excludes shipping, marks quantities unverified and deduplicates qualifying transitions.

References: https://docs.github.com/en/rest/releases/releases · https://github.com/FlareSolverr/FlareSolverr · https://netdeck.gg/embed.js · https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html
