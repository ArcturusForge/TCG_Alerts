# v0.5 validation record

Local validation combines unit tests, headless GUI checks and a small explicit live-source sample. Live observations are dated evidence, not promises about current stock, broad retailer coverage or ongoing API stability. No live data is seeded as a watch or deck price in a user's database.

Live checks (2 November 2026, Melbourne):

- OpenRift `/api/v1/search?q=Orianna&limit=2`: JSON catalogue and actual card artwork returned successfully. Artwork selections expose printing/set/language rather than automatic name-only matching. Riftcodex was investigated but timed out; it is not the shipped default.
- Pokémon TCGdex external JSON provider: Pikachu search returned 40 bounded candidates and the first card artwork loaded. This exercised the same public JSON-provider path available to installed plugins.
- Only Packs Riftbound collection: six product links discovered. One Chinese Spiritforged Slim display returned a valid Shopify AUD observation. This does not establish English-card availability.
- GUF Riftbound collection: 18 links discovered. Vendetta display correctly demanded branch selection; the explicitly selected Werribee variant returned a valid AUD out-of-stock observation. Branches were not pooled.
- Riftbound publisher index: nine headlines; all nine images associated by exact article URL with the index's embedded JSON after its HTML images proved to be placeholders.
- Cyberpunk publisher index: seven headlines; all seven provided artwork in the article tiles.

Checks cover request/parse paths and actual catalogue/image retrieval. Unit tests use fixtures for deterministic prices and unknown-price handling. GUI smoke includes the first-use guide, both deck views, keyboard tile selection, asynchronous local images, image failure/stale response paths, virtualized long decks, deck charts and a smaller window. Windows/package checks remain CI gates; a Linux capture alone is not proof of Windows layout or notifications.

Sources: https://openrift.app/developers · https://onlypackstcg.com.au/collections/riftbound · https://guf.com.au/collections/riftbound · https://playriftbound.com/en-us/news/ · https://cyberpunktcg.com/blog
