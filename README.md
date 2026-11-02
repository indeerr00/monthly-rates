# monthly-rates

Data relay for the **Monthly: Mortgage Calculator** iOS app.

A GitHub Action runs each weekday morning, pulls the Optimal Blue Mortgage Market
Indices from FRED, and writes `rates.json`. The app reads that one file:

```
https://raw.githubusercontent.com/indeerr00/monthly-rates/main/rates.json
```

This repo is public **only** so the app can read `rates.json` without
credentials. The FRED API key lives in the repo's `FRED_KEY` Actions secret and
never reaches the app or the published file.

## Why a relay

FRED's API requires a key. A key shipped inside an app binary can be extracted,
so the key stays here and the app only ever sees the finished JSON. It also means
the data source can change without shipping an app update.

## Series

| Feed id | FRED series | Index |
| --- | --- | --- |
| `30f` | `OBMMIC30YF` | 30-Year Fixed Rate Conforming Mortgage Index |
| `15f` | `OBMMIC15YF` | 15-Year Fixed Rate Conforming Mortgage Index |

Both are daily, in percent, not seasonally adjusted.

## Shape

```json
{
  "source": "Optimal Blue",
  "asOf": "2026-10-30",
  "cadence": "daily",
  "attribution": "Source: Optimal Blue Mortgage Market Indices (OBMMIC30YF, OBMMIC15YF), retrieved from FRED, Federal Reserve Bank of St. Louis.",
  "products": [
    {
      "id": "30f",
      "name": "30-year fixed",
      "term": 30,
      "current": 7.147,
      "previous": 7.147,
      "yearAgo": 6.17,
      "history": [{ "date": "2025-11-03", "value": 6.2 }],
      "rangeLow": 5.98,
      "rangeHigh": 7.4
    }
  ]
}
```

`history` is oldest → newest, up to 250 trading days. `rangeLow` / `rangeHigh`
are the 52-week low and high.

## Failure behaviour

`build_rates.py` exits non-zero without writing anything if FRED is unreachable,
the key is missing, or a series comes back with fewer than 30 usable
observations. The previous `rates.json` stays published and the Action shows as
failed. The app, in turn, keeps its last cached feed and falls back to a bundled
snapshot, so a broken run never empties the Rates tab.

## Running it by hand

Actions → **Refresh rates** → *Run workflow*. Locally:

```sh
FRED_KEY=your-key python build_rates.py
```

## Attribution

FRED marks these series *Copyrighted: Citation Required*. The citation above is
displayed on the app's Rates tab; keep it there.

Optimal Blue Mortgage Market Indices™ (OBMMI™) is a trademark of Optimal Blue.
