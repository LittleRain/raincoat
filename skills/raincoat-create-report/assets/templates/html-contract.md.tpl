# HTML Contract

## Structure

- `.hero` title and period metadata
- `.nav` anchor navigation
- `.section` blocks in validated order
- `.metric-card`, `.chart-container`, `.table-wrap`, and `.conclusion` where declared
- `.footnote` source-data notes

## Assets

- Inline `assets/base-report.css` in the delivered HTML.
- Inline or locally package Chart.js and `assets/chart-defaults.js`.
- Do not require external CDN/network to render charts.

## Data

- Render counts and required metrics from `examples/expected-output-inventory.json`.
- Follow table schemas, WoW display rules, and empty-value policies from the normalized spec.
- Use declared evidence only for conclusions.
