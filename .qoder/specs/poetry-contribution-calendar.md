# Plan: Poetry Weekly Heatmap (Year Contribution Calendar)

## Overview
Add a GitHub-style contribution heatmap below the search bar on the homepage, displaying 52 weeks of poetry publishing activity for the year. Color intensity reflects weekly poem count (5 levels based on teal theme). Activity weeks are shown in a distinct bright color (full replace, not overlay). Supports year switching via dropdown. Hover tooltip only, no click interaction. Visible to guests.

---

## Files to Modify

| File | Change |
|------|--------|
| `src/main.py` | Add `/api/poems/weekly-stats` public API endpoint |
| `src/static/index.html` | Insert heatmap container after search bar (line 60) |
| `src/static/style.css` | Add heatmap styles with responsive layout |
| `src/static/app.js` | Add `loadWeeklyHeatmap()` + `renderWeeklyHeatmap()` functions, integrate into `showSection('home')` |

---

## 1. Backend API (`src/main.py`)

### New endpoint: `GET /api/poems/weekly-stats?year=2026`

- Add to `PUBLIC_DATA_WHITELIST` (line ~70): `'/api/poems/weekly-stats'`
- Use `@api_route('/api/poems/weekly-stats', methods=['GET'])`
- **Logic**: Stream `db_poems.iter_records()` and `db_activities.iter_records()`, compute week number from `date` field, aggregate counts per week
- **Week calculation** (MicroPython compatible):
  ```
  day_of_year = sum(days_in_months[:month]) + day
  week = min((day_of_year - 1) // 7 + 1, 52)
  ```
- **Response format**:
  ```json
  {
    "year": 2026,
    "weeks": [0, 3, 0, 1, ...],  // 52 elements: poem count per week
    "act_weeks": [5, 12, 30]     // week numbers that have activities
  }
  ```
  Use compact arrays instead of objects to minimize response size (~200 bytes).
- Call `gc.collect()` after computation.

---

## 2. Frontend HTML (`src/static/index.html`)

Insert after `</div>` of search-container (line 60), before search-results-section:

```html
<!-- Poetry Weekly Heatmap -->
<div class="weekly-heatmap-container" id="weekly-heatmap-container">
    <div class="heatmap-header">
        <h4 class="heatmap-title">Year Poetry Weekly</h4>
        <select id="heatmap-year-select" onchange="loadWeeklyHeatmap()"></select>
    </div>
    <div class="heatmap-grid" id="weekly-heatmap"></div>
    <div class="heatmap-legend">
        <!-- 6 legend items: level-0 through level-4 + activity -->
    </div>
</div>
```

---

## 3. Frontend CSS (`src/static/style.css`)

### Color Levels (5 levels based on --accent #008080 teal)
| Level | Condition | Color | Description |
|-------|-----------|-------|-------------|
| 0 | 0 poems | `#e9ecef` | Empty (light gray) |
| 1 | 1-2 poems | `#b2d8d8` | Light teal |
| 2 | 3-5 poems | `#66b2b2` | Medium teal |
| 3 | 6-10 poems | `#008080` | Standard teal (--accent) |
| 4 | 11+ poems | `#005555` | Deep teal |
| activity | has activity | `#e6a817` | Bright amber/gold (full replace, NOT overlay) |

### Layout
- Container: card style (card-bg, radius, shadow, border)
- Grid: `display: grid; grid-template-columns: repeat(52, 1fr); gap: 3px;`
- Week cell: `aspect-ratio: 1/1; border-radius: 3px;`
- Tooltip: CSS `::after` with `data-tooltip` attribute
- Legend: flex row centered below grid

### Responsive
- **PC (>=1280px)**: 52 columns auto-sized
- **Tablet (768-1279px)**: 52 columns `minmax(8px, 1fr)`
- **Mobile (<768px)**: fixed cell width `10px`, container `overflow-x: auto` for horizontal scroll

---

## 4. Frontend JS (`src/static/app.js`)

### `loadWeeklyHeatmap()`
- Get year from `#heatmap-year-select` or default to `new Date().getFullYear()`
- `fetch(API_BASE + '/poems/weekly-stats?year=' + year)`
- Call `renderWeeklyHeatmap(data)`

### `renderWeeklyHeatmap(data)`
- Populate year selector (current year down to current-2, 3 years total) if not yet populated
- Build `actSet = new Set(data.act_weeks)` for O(1) lookup
- For each of 52 weeks, create a div with:
  - If `actSet.has(weekNum)`: class `activity` (bright amber, full replace)
  - Else: class `level-N` based on poem count thresholds
  - `data-tooltip` attribute: "Week N: X poems" or "Week N: X poems [Activity]"
- `container.innerHTML = cells.join('')`

### Integration
- In `showSection()` (line ~1069), inside `if(id === 'home')` block, add call to `loadWeeklyHeatmap()`
- The heatmap container visibility follows same logic as search-container (always visible on home for guests)

---

## 5. Verification

1. After implementation, start the dev server and navigate to homepage
2. Verify the heatmap renders below search bar with 52 week cells
3. Verify hover tooltip shows correct week number and poem count
4. Verify activity weeks display in amber color (full replace)
5. Verify year dropdown switches data correctly
6. Verify responsive behavior: mobile horizontal scroll, tablet/PC auto-fit
7. Verify guest access: log out and confirm heatmap still loads
8. Test with empty data (new year with no poems) - all cells should be level-0 gray
