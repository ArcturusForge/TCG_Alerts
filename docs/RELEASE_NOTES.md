v0.6.1 also reads provider metadata explicitly as UTF-8, preserving names and game tags such as Pokémon during automatic updates.

TCG Alerts v0.6 adds automatic stable GitHub-release downloads for the app, pinned plugin updates, and on-demand FlareSolverr installation/update for blocked public product pages. Downloads require GitHub SHA-256 verification. The Windows app applies a staged update after closing and retains its previous executable. Plugin changes activate on restart and retain a previous installation.

The app and its plugins remain outside the collection database. Private GitHub repositories require read credentials via TCG_ALERTS_GITHUB_TOKEN. Browser-helper binaries are available for Windows/Linux x64; success depends on the target site and browser compatibility. Closing the app stops its helper. See README.md and docs/UPDATES.md for behavior and recovery details.
