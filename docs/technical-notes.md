# COMP5339 Assignment 2

EV Charging Data Streaming and Analysis. Group: TUT06-AssignmentGroup-08.

This package implements synthetic data generation, ordered MQTT publishing, subscription, DuckDB storage and a live Flask map dashboard. The instructor generator is unchanged. Charger coordinates and identifiers come from Assignment 1; September 2026 AEMO NSW1 prices calibrate the simulation. Charging sessions, telemetry and customer tariffs are synthetic.

## Display metadata enrichment (26 October 2026)

The dashboard now fills missing display metadata from the existing Assignment 1 augmentation tables. Original nonempty charger names/addresses and normalized location plug data take precedence. Missing names fall back to Open Charge Map, then OpenStreetMap; missing addresses can use Open Charge Map, and missing plug types can use OpenStreetMap. Augmentation is eligible only when both `match_status = 'Matched'` and `match_level = 'Location'`. Operator-only, rejected and out-of-threshold candidates are excluded. Remaining gaps display the device ID or `Not recorded`.

`sql/charger_display.sql` defines the repeatable `charger_display` view; the app creates it automatically at startup and joins it at device grain. The API includes `name_source`, `address_source` and `plug_types_source`, and both marker popups and the detail pane show metadata provenance. Plug types are still location-level information. Device IDs, coordinates, modelled connector capacity, generated events and charging analytics retain their existing definitions. Generator input/output CSVs are not rewritten for this display-only change.

On the packaged 432-device snapshot, available names increase from 1 to 203 (181 OCM and 21 additional OSM fallbacks); available plug types increase from 181 to 264 (83 OSM fallbacks). The earlier enrichment validation used a 6,466-event baseline; its historical evidence is retained separately from the final database. Start the application normally; no separate migration command or dataset regeneration is needed.

```bash
python -m unittest discover -s tests -v
python scripts/validate_enrichment.py
```

The current suite contains five enrichment regressions plus three publisher-timing regressions. `docs/enrichment_validation.json` records snapshot/API checks, and `docs/enrichment_tests.txt` records the eight-test run. `docs/enriched_mqtt_validation.json` records a new isolated MQTT check after enrichment. See `docs/enrichment_changes.md` for design and report-update notes.

## Publisher timing update (26 October 2026)

The publisher now uses high-resolution `perf_counter_ns()` deadlines. Each subsequent message waits a full configured interval after the preceding broker PUBACK; the deadline is rechecked after every sleep. JSON encoding is completed before waiting. This avoids short intervals caused by coarse Windows Python 3.12 `monotonic()` ticks. The default minimum remains 0.1 seconds; pacing is deliberately conservative, so transport/acknowledgment overhead adds to total replay time.

Run the focused regressions and an isolated real-MQTT check from the project root:

```bash
python -m unittest discover -s tests -v
python scripts/validate_mqtt_pacing.py
```

Use your virtual environment's Python executable in place of `python`. The integration check uses temporary databases and independent loopback ports, sends the complete 412-event demo plus 10 duplicate events, and checks high-resolution publication intervals, committed metrics and duplicate handling. Its evidence is in `docs/publisher_timing_validation.json`; the new unit-test output is in `docs/publisher_timing_tests.txt`. These are new timing-fix checks, distinct from the earlier development checks described elsewhere in this README. No additional packages are required.

## Installation and startup (full-network replay)

### 1. Open the correct project folder

Extract the submission ZIP, then open **COMP5339_Assignment2** in VS Code. Open Terminal → New Terminal. The terminal's working directory must contain `run.py` and `requirements.txt`.

Python executes this project; do not use VS Code's Run Python File button, because the launcher requires command-line arguments.

### 2. First-time setup on each computer

Install `uv` if it is not already available: https://docs.astral.sh/uv/getting-started/installation/ . Then run these commands from the project folder:

```bash
uv venv --python 3.12
uv pip install --python .venv/bin/python -r requirements.txt
```

These commands create `.venv` and install the runtime dependencies. No environment activation is needed when using the explicit Python path below.

Each person using a separate computer or newly extracted project folder must perform this setup. Do not copy someone else's `.venv`: it contains machine-specific paths and packages. On subsequent runs in this same folder, skip installation while `.venv` remains available. If `requirements.txt` changes, repeat the dependency installation command.

### 3. Terminal 1: start the broker, subscriber and dashboard

```bash
.venv/bin/python run.py serve --fresh
```

Wait until the terminal prints:

```text
Dashboard ready: http://127.0.0.1:8050 (Ctrl+C stops services)
```

**Keep terminal 1 running.** This command starts the local MQTT broker, receives messages, writes them to DuckDB and serves the dashboard. Ports 1883 and 8050 must be available.

`--fresh` creates a new timestamped database under `database/`, using the Assignment 1 baseline. It preserves existing databases, including the supplied `database/ev_stream.duckdb`. Each startup with `--fresh` begins with no received events; an initially empty map is expected.

### 4. Terminal 2: publish the complete event stream

In VS Code select Terminal → New Terminal again. Ensure this second terminal is also in **the same COMP5339_Assignment2 folder**, then run:

```bash
.venv/bin/python run.py publish
```

Both terminals must run together: terminal 1 receives, stores and displays the data; terminal 2 sends it. Do not stop terminal 1 to run the publishing command. There is no need to activate the environment in either terminal.

The publisher sends `data/events.jsonl`: all 46,084 events in event-time order, at least 0.1 seconds apart. Initial price events cover all 432 devices at 430 locations; allow approximately 45 seconds plus processing overhead for these initial events. Some map markers overlap because devices share coordinates. Complete replay requires at least 76.8 minutes plus overhead; you can inspect the dashboard while replay continues.

### 5. Open and use the dashboard

Open http://127.0.0.1:8050 in a browser. Leave both terminals running while observing live updates. Select All operators to see the full network. Click a marker to inspect details and charging-session curves. The dashboard polls every second.

The simulation uses real Assignment 1 locations and real AEMO wholesale input; the charging activity and customer prices are synthetic, not real-world live occupancy.

### 6. Stop and restart

To stop early, press **Control+C in terminal 2**, then **Control+C in terminal 1**. If publishing has already finished, stop terminal 1 only. Closing the browser alone does not stop the services.

Next time, open two terminals in the same project folder and repeat steps 3–5. Installation is not required again. Each `serve --fresh` starts a new replay database and therefore needs the publisher to populate it. Replaying identical events into the same database does not duplicate analytical totals.

### Windows equivalents

On Windows, the virtual environment's executable is `.venv\Scripts\python.exe`. First-time setup:

```powershell
uv venv --python 3.12
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
```

Terminal 1:

```powershell
.venv\Scripts\python.exe run.py serve --fresh
```

Terminal 2:

```powershell
.venv\Scripts\python.exe run.py publish
```

### Troubleshooting

- **`.venv/bin/python` not found:** run the first-time setup in this folder; on Windows use the Windows path above.
- **`run.py` or `requirements.txt` not found:** switch to the extracted `COMP5339_Assignment2` folder.
- **Port already in use / database locked:** stop an earlier running instance before starting another. Only one app process may own a given DuckDB file.
- **Empty map after startup:** start the publisher in terminal 2, keep terminal 1 running, and check the operator filter.
- **Missing basemap tiles:** OpenStreetMap tiles require internet access; frontend libraries are included locally.

The supplied database is checkpointed and contains 46,084 events, 5,288 completed sessions, 0 active sessions and 133,981.800 kWh, covering 432 devices; watermark 2026-09-02 01:42:38+10:00. Run serve to inspect this final state. Use serve --fresh plus publish, or demo --fresh --limit 300 --delay 0.5, to demonstrate new arrivals. Replaying identical events into the completed database does not change totals.

## Regenerate the supplied dataset

The generator input and real monthly AEMO cache are included. Run:

```bash
.venv/bin/python run.py generate
```

This uses all 432 devices, start date 2026-09-01, one day, seed 5339 and five-minute telemetry. It recreates the four generated CSVs and both ordered JSONL streams. The existing DuckDB database is not cleared. If the AEMO cache is missing, the instructor generator downloads the real input; there is no fabricated wholesale-price fallback.

To rebuild the station mapping from the unchanged Assignment 1 baseline into a NEW database path:

```bash
PYTHONPATH=src .venv/bin/python -m evstream.prepare --db database/new_baseline.duckdb
```

The preparation command refuses to overwrite an existing database. On Windows PowerShell, set `$env:PYTHONPATH="src"` before the `.venv\Scripts\python.exe -m evstream.prepare` command. Normal launcher commands do not need PYTHONPATH setup.

## Project structure and outputs

| Path | Purpose |
| --- | --- |
| run.py | Launch services, replay messages and regenerate data |
| requirements.txt | Required runtime Python packages |
| src/evstream/prepare.py | Assignment 1 device-to-station mapping and baseline database copy |
| src/evstream/events.py | Typed CSV-to-JSON conversion, price filtering and ordering |
| src/evstream/publisher.py | MQTT QoS 1 publishing with minimum pacing |
| src/evstream/broker.py | Local MQTT broker |
| src/evstream/app.py | MQTT subscriber and Flask HTTP application |
| src/evstream/store.py | Validation, transactional storage and analytical queries |
| src/evstream/common.py, __init__.py | Shared paths and package support |
| static/ | Dashboard HTML/JavaScript and vendored Leaflet/Chart.js assets and licenses |
| sql/stream_schema.sql | Additive stream DDL, indexes and analytical views |
| sql/charger_display.sql | Display view with verified location-match fallbacks and provenance |
| tests/ | Publisher pacing and display-enrichment regression checks |
| scripts/validate_enrichment.py | Temporary-copy snapshot/API metadata validation |
| docs/enrichment_validation.json | Measured metadata coverage and preserved event/metric checks |
| assignment1_reference/database/ev_chargers.duckdb | Unchanged baseline; needed to create a fresh database |
| assignment1_reference/sql/schema.sql | Original Assignment 1 DDL; retained as schema reference |
| database/ev_stream.duckdb | Updated database containing the received full-network prefix |
| data/stations_input.csv | Original charger IDs, location IDs, coordinates, network metadata and simulation inputs |
| data/generated/stations.csv | Generator output station capacities and synthetic base prices |
| data/generated/prices_hourly.csv | 10,368 hourly station-price records |
| data/generated/sessions.csv | 5,288 synthetic charging sessions |
| data/generated/session_metering.csv | 29,460 telemetry readings |
| data/generated/aemo_cache/ | Real September 2026 NSW1 wholesale input; 8,640 observations |
| data/events.jsonl | Complete 46,084-event ordered stream |
| data/demo_events.jsonl | Optional generated three-device subset; not used by the startup procedure above |
| data/generation_summary.json | Event counts, dataset fingerprint and demonstration device IDs |
| data/station_mapping.json | Mapping rule, baseline checksum and capacity assumptions |
| data/aemo_provenance.json | AEMO URL, source checksum and generation parameters |
| COMP5339_2026s2_Assignment2_data _generator/ | Unmodified instructor generator and model/source documentation |

## Message preparation and database design

The data contains 432 DC devices at 430 coordinate locations, with 1,656 listed plugs. `station_id = DC-<charger_id>` preserves the original charger identity. The new stream_station table references charger; charger links to charger_location and operator. Plug types remain location-level attributes. The nine original Assignment 1 tables are preserved.

The converter produces price_update, session_start, session_end and meter messages. The first price establishes state; subsequent unchanged prices are suppressed (4,320 hourly records). Start messages contain no future energy or completion outcome. Each JSON message has schema_version, type, event_time, station_id, dataset_id, sequence, event_id and payload. Events are sorted by time, with deterministic tie order: price update, session end, session start, meter. IDs are SHA-256 hashes of canonical content.

The publisher waits for broker acknowledgment and enforces at least 0.1 seconds between send calls. The subscriber validates messages and commits storage before manual acknowledgment. Invalid raw messages and their reasons enter rejected_message. Duplicate event IDs do not increase totals. One database stores one generated dataset.

latest_price selects the newest event-time price. charging_session derives lifecycle state; active_session contains a received start without a received end. station_history summarises completed sessions, final energy, simulated revenue and average charging duration. Energy and monetary totals use fixed-point decimals. Meter energy is cumulative and is not summed across readings. Indexes cover station/time, session/time and event type/time. A process lock coordinates the shared DuckDB connection.

## Dashboard use

Markers appear after receiving their first event. The number inside each marker updates with its active-session count. Tooltips show price and occupied/total connectors; pop-ups show address, operator, plug types and price. Select a marker, table row or station to inspect session curves. The metric selector switches energy, power and state of charge. Active-session curves include older active sessions even outside the recent-history list. The dashboard polls every second; cards show current active sessions and historical completed-session count/energy. Operator filtering is included. The Observed chargers table can be sorted by price (lowest first, unavailable prices last) or available connector count (most first). Available connectors are modelled capacity minus active sessions, bounded at zero. Clicking a map marker, selecting an Observed chargers row or using the Charger detail selector highlights the same row and marker, pans the map to that charger, opens its popup and updates Charger detail. Selection and the chosen sort order persist during live refresh. The charger selector retains its options while being used, so automatic updates do not interrupt mouse or keyboard selection.

## Assumptions and limitations

- Listed plugs are modelled as independent connectors, and maximum listed power is treated as per-connector capacity. These are modelling assumptions, not verified simultaneous site capacity.
- Urban sites are Sydney SA4 regions, Newcastle and Lake Macquarie, Illawarra and Central Coast; other sites are regional. Missing source attributes remain unavailable.
- Timestamps use fixed UTC+10 AEMO market time. The generator shifts period-ending observations back five minutes, averages hourly and converts AUD/MWh to AUD/kWh. This is not a daylight-saving civil-time conversion.
- Sessions starting on the simulated day may finish after midnight; their remaining events are retained.
- The broker is loopback-only, unauthenticated and not configured for disk persistence. Stream replay can restore saved events idempotently; end-to-end exactly-once transport is not claimed.
- The single-process DuckDB setup is for the assignment workload. Larger-scale processing would require capacity validation, a persistent authenticated broker, durable queuing and benchmarked aggregates.
- Core frontend libraries are included locally. OpenStreetMap basemap tiles need internet and retain attribution.

## Submission and attribution

Submit this source/database ZIP, the project report PDF and the AI usage report as three separate Canvas items. The report and AI disclosure are supplied separately. This ZIP contains the executable implementation, necessary input/generated data, databases, DDL, runtime dependencies and this README.

The original regression suite contains eight automated tests, a real MQTT duplicate-replay check and browser checks. The final submitted database contains all 46,084 source event IDs. This confirms stored completeness; the recorded 412-event MQTT test measures short-run transport timing separately.

Extensive OpenAI Codex assistance was used for source code, SQL and documentation, as acknowledged in affected files and the separate AI usage report. The team must understand the work and verify its contribution declaration before submission.

Sources: the supplied COMP5339 Assignment 2 brief/generator and group Assignment 1 database/schema; AEMO https://www.aemo.com.au/aemo/data/nem/priceanddemand/PRICE_AND_DEMAND_202609_NSW1.csv ; Eclipse Paho https://eclipse.dev/paho/clients/python/docs/ ; DuckDB https://duckdb.org/docs/stable/ ; AMQTT https://amqtt.readthedocs.io/en/latest/ ; Leaflet https://leafletjs.com/ ; Chart.js https://www.chartjs.org/ . Vendored frontend license notices are retained.

## Final review fixes (28 October 2026)
Map pop-ups include current occupancy, historical completed count/energy and SVG energy curves refreshed from received meter events. Numeric values exceeding DECIMAL(12,3)/(12,2) are quarantined before storage; lifecycle timestamps are checked.

DC-3 has conflicting original address and OCM metadata. The original charger row is preserved. For this reviewed record, display uses the archived location-matched OCM address (82 Marsh Street, Armidale, 2350; OCM ID 170824; distance 29.23 m; original postcode mismatch), with an explicit conflict/source label. This is an evidence-based candidate from the existing snapshot, not a new independent verification of the physical site. Other records retain the existing precedence.

Before distributing updated databases, stop writers, execute CHECKPOINT and close DuckDB. Never discard an unrecovered WAL. This package excludes virtual environments and caches; create your own environment from requirements.txt. The original 8 tests are supplemented by test_storage_bounds.py. See docs/final_validation.json for the current run and count.
