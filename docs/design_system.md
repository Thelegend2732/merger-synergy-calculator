# Design system

How the app is made to look and behave like a professional financial tool (Bloomberg Terminal, Capital IQ,
Stripe and Mercury dashboards were the references). Everything below is implemented in
`.streamlit/config.toml` (theme) and `ui/theme.py` (icon vocabulary, CSS layer, branded blocks).

## Principles

1. **Answer first.** Every tab opens with a dashboard card: the verdict banner and four to five KPI tiles.
   Inputs, tables and charts come after. A reader gets the conclusion without scrolling.
2. **One icon per concept.** Icons come from Material Symbols Rounded (the set Streamlit ships, so nothing is
   downloaded) and are looked up by concept, never by name, through `ICONS` in `ui/theme.py`. The same concept
   always gets the same icon: enterprise value is always `apartment`, leverage is always `speed`.
3. **Colour is semantic.** Navy for neutral figures and totals, green for accretive / comfortable, red for
   dilutive / breached, amber for the watch zone, grey for auxiliary series. Decorative colour is not used.
4. **Numbers line up.** Inter with tabular figures everywhere a number appears (metrics, tables, tiles), so
   columns of KPIs can be compared at a glance.
5. **Native first.** Streamlit widgets wherever one exists (metrics with `border=True` and `icon=`, expanders
   with icons, badges, progress bars). HTML is limited to four presentational blocks Streamlit has no element
   for: the header band, section titles, the verdict banner and the compact KPI tile.

## Icon vocabulary

| Area | Concept | Material Symbol |
|---|---|---|
| Navigation | DCF Valuation | `query_stats` |
| | Comps & Football Field | `stacked_bar_chart` |
| | Capital Structure & Risk | `account_balance` |
| | Transaction Summary | `receipt_long` |
| | Projections & Sensitivity | `grid_on` |
| | Monte Carlo Risk | `scatter_plot` |
| Sidebar | Deal case / preset | `folder_open` |
| | Excel pitchbook | `description` |
| | Analysis settings | `settings` |
| | Deal inputs | `tune` |
| | Acquirer | `domain` |
| | Target | `my_location` |
| | Consideration | `payments` |
| | Synergies | `hub` |
| | Purchase price allocation | `inventory_2` |
| | Synergy phasing | `timeline` |
| KPIs | Enterprise value | `apartment` |
| | Equity value / split | `pie_chart` |
| | Per-share value / price | `paid`, `sell` |
| | Market price | `show_chart` |
| | EPS | `functions` |
| | Premium | `trending_up` |
| | Ownership | `groups` |
| | Breakeven | `balance` |
| | Cash | `savings` |
| | Debt | `credit_card` |
| | Interest / rate | `request_quote`, `percent` |
| | Leverage | `speed` |
| | Probability | `casino` |
| | Downside | `south` |
| States | Accretive | `trending_up` |
| | Dilutive | `trending_down` |
| | OK / warning / error / info | `check_circle`, `warning`, `error`, `info` |
| Content | Table | `table_chart` |
| | Chart | `insights` |
| | Methodology | `menu_book` |

Streamlit renders an icon in any label with the `:material/<name>:` directive; `ui.theme.icon("ev")` returns
that string for a concept key. Inside HTML blocks the font is used directly (class `msc-ico`).

## Typography and shape

| Token | Value |
|---|---|
| UI font | Inter 400 / 500 / 600 / 700 (Google Fonts, declared in `config.toml`) |
| Code font | JetBrains Mono |
| Base size | 15 px |
| Headings | h1 1.75 rem · h2 1.35 rem · h3 1.15 rem, weight 600-700 |
| Metric value | 1.65 rem, weight 600, tabular figures |
| Radius | 10 px (8 px for buttons) |
| Borders | `#dde3ec`; data frames `#e3e8f0` with a `#eef2f7` header |
| Background | page `#f6f8fb`, cards and sidebar `#ffffff` |

## Colour tokens

| Token | Hex | Used for |
|---|---|---|
| Navy | `#1f4e79` | primary, totals, neutral bars, section icon squares |
| Green | `#2e9e5b` | accretive, comfortable leverage, positive deltas |
| Red | `#d64545` | dilutive, leverage breach, negative deltas |
| Amber | `#e0a030` | watch zone, precedent transactions |
| Grey | `#8a8f98` | auxiliary series, 52-week range, unavailable |
| Text | `#1b2a41` | body copy |

The same hex values live in `engine/constants.py`, so charts and UI never drift apart.

## Layout blocks (`ui/theme.py`)

- `render_header(title, subtitle, chips)`: navy gradient band with the logo mark and live status chips
  (loaded case, analysis year and EPS basis, verdict). Rendered at the end of the run so the chips reflect
  the model.
- `section(icon_key, title, caption)`: icon in a tinted square, bold title, grey caption. Every card starts
  with one (`card_title` delegates to it).
- `hero(state, label, value, sub)`: the verdict banner (green / red / neutral) used for the EPS verdict,
  the Monte Carlo probability, the leverage check and the deal base price.
- `metric(col, label, value, icon_key, **kwargs)`: `st.metric` with a border and an icon, the KPI tile.
- `kpi(label, value, icon_key)`: compact HTML tile for narrow columns.

## Sidebar

The sidebar reads top-down as a workflow: **Deal case** (load or import) → **Excel pitchbook** (export) →
**Analysis settings** (year, EPS basis: the two switches that change every tab) → **Deal inputs**, grouped
in expanders with icons. PPA and phasing are collapsed by default because they are rarely changed.
