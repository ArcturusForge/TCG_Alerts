# Deck builder and live cost tracker — proposed next milestone

The requested extension is a deck manager with a priced bill of materials. This document is a researched design; v0.3 does not yet implement the deck builder or claim automated eBay sold-data access.

## Useful first workflow

Import/paste a quantity-and-name deck list, resolve each row to an exact card identity, choose acceptable printings and enter quantities owned. Display each card's needed/owned/missing quantities, observed unit price, line subtotal, source, currency, availability and last update. Save independent versions of decks and export a shopping list.

Keep these totals distinct:

- **Full deck reference value:** requested quantity × a selected reference price for each resolved card.
- **Missing-card item cost:** max(0, required − owned) × a current suitable listing's unit price.
- **Delivered purchase estimate:** item basket plus known per-store shipping and fees, when an actual allocation of cards to stores is available. Do not add per-card shipping as though every copy ships separately, or imply the cheapest individual listings form the cheapest delivered basket.
- **Unpriced/unavailable coverage:** count missing rows/copies explicitly. Show priced subtotals with coverage; an unknown card must never contribute zero to an asserted complete total.

Different cards, currencies, standard/foil/showcase versions, languages, conditions and graded/raw copies stay separate. For collecting, exact printings matter; for gameplay, an explicit cheapest-acceptable-printing mode can be useful. A purchase offer is not a sold-price reference. Listing availability alone does not prove the seller has the required number of copies.

A practical initial build can reuse explicit singles URLs in the existing monitor, with a verified one-copy listing identity. Ordinary monitoring refreshes are timestamped observations, not an instantaneous market feed. This works before an external card catalog/artwork integration is enabled. Ownership should eventually come from a collection ledger with shared-card allocation; per-deck owned counters must not pretend the same physical copy is available in several simultaneously reserved decks.

## eBay sold references

Use recent comparable sold transactions as one reference source, with time window, sample size, median and observed range. Exclude mismatched editions, graded copies, lots, proxies, wrong condition/language and duplicate transactions. Shipping, sale currency and per-copy lot normalization need explicit handling. Best Offer results with an undisclosed accepted amount must not become a purported exact sale price. A lone last sale should remain a single observation rather than a reliable market average.

The official [Marketplace Insights overview](https://www.edp.ebay.com/api-docs/buy/marketplace-insights/static/overview.html) describes sold-history data and limited-release access. The official [marketplace support page](https://developer.ebay.com/api-docs/buy/ref-marketplace-supported.html) says that this API is restricted and not open to new users. Marketplace support for Australia does not grant access. Do not promise this as a freely available automatic integration. Start with user-entered evidence/authorized imports or a provider with a suitable agreement; add an approved adapter if access becomes available. Current asking prices are not a substitute labelled as completed sales.

## Card data and art

The authoritative [Riot Riftbound digital tools policy](https://developer.riotgames.com/docs/riftbound) encourages deck managers but sets app-specific authorization/API and asset-source requirements. Use authorized Riot assets through an approved integration; availability on TCG Arena or another website does not establish permission to redistribute them. We can build the deck-list, ownership and pricing features without bundling artwork while provider access is resolved. Do not submit applications or contact providers without user direction.

[TCG Arena's documentation](https://documentation.tcg-arena.fr/) describes a configurable game/card-data file format. It is a useful format/interoperability reference, not evidence of a blanket content licence or a commercial pricing feed. [NetDeck's developer page](https://netdeck.gg/for-developers) currently advertises Cyberpunk-compatible website embeds but marks direct API access as coming soon. An HTML embed does not automatically solve a native desktop catalog integration.

[OpenRift's developer documentation](https://openrift.app/developers) offers a potential Riftbound catalog/price adapter, subject to its terms and the underlying game's asset requirements. It documents daily pricing updates and differing marketplace metrics/language coverage. Review those semantics before using any numbers as an AUD/NM/English card price. Keep provider identifiers, provenance, refresh times and currency attached to every quote.

## Implementation order

1. Decks, quantities, sections, owned/missing counts, exact printing identifiers and plain-list/CSV import/export.
2. Explicit monitored singles links and source-aware price breakdowns, preserving unknowns and freshness.
3. Authorized catalog/artwork adapters and card search with cached provider data under agreed terms.
4. Price-history and budget alerts, costliest-card breakdowns and version-to-version deck cost changes.
5. Basket-aware buying suggestions using quantity availability, shipping thresholds and permitted sellers; distinguish candidate estimates from a proven optimum.

Each game's deck-construction checks need an independently verified rule definition/version. Do not claim legality from a shared generic card count. A deck manager is not an automated gameplay simulator.
