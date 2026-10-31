# Display metadata enrichment

The dashboard now joins a derived `charger_display` view to each Assignment 1 charger. This uses existing source tables; it does not require another external download or modify source records.

## Selection rules

| Field | Priority |
| --- | --- |
| Name | Nonempty `charger.station_name`, eligible OCM title, eligible OSM title |
| Address | Nonempty `charger.station_address`, eligible OCM address |
| Plug types | Nonempty normalized location plug data, eligible OSM plug types |

Empty/whitespace-only values are treated as missing. An augmentation row is eligible only if `match_status = 'Matched'` and `match_level = 'Location'`, joined by the original location ID. Operator-only or unsuccessful candidates cannot supply a device's display attributes. The new view produces one row per charger; co-located devices retain separate identifiers and can share location-level metadata.

The API adds `name_source`, `address_source` and `plug_types_source`. Values identify the original charger table, normalized plug table, OCM, OSM or unavailable data. The browser labels the sources in marker popups and the detail pane. Enriched plug types remain location-level information, not independently verified connector configurations. Source matching is inherited from Assignment 1, rather than newly verified against physical stations.

## Snapshot result

| Metadata coverage | Before | After | Added |
| --- | ---: | ---: | ---: |
| Devices with a name | 1 | 203 | 202 |
| Devices with plug types | 181 | 264 | 83 |

Name sources: original charger 1, OCM 181, OSM 21, unavailable 229. Plug-type sources: normalized Assignment 1 table 181, OSM 83, unavailable 168. No missing address was filled in the actual packaged snapshot; the OCM address fallback is covered by a regression fixture.

The snapshot still has 432 devices, 6,466 stored events, 144 active sessions, 560 completed sessions and 13,926.510 kWh. Checks compare all event IDs, original nonempty displayed values, device identities, coordinates and modelled capacities before/after. The Flask state endpoint returns 200 with source labels.

Eight regressions pass: five new enrichment checks plus three existing publisher-pacing checks. The fixtures cover source precedence, blank fields, rejected/operator-only candidates, missing candidates and co-located devices. The real MQTT validation is repeated separately against this implementation; its timings are in `enriched_mqtt_validation.json`.

## Run and reproduce

Start using the existing README instructions. The Store automatically creates/replaces the additive view from `sql/charger_display.sql`. No source-table migration, regeneration of generated CSV/JSONL files, or new runtime dependency is required.

```bash
python -m unittest discover -s tests -v
python scripts/validate_enrichment.py
python scripts/validate_mqtt_pacing.py --output docs/enriched_mqtt_validation.json
```

The source input CSV and generator output names retain their original reproducibility snapshot. The dashboard's enriched names are a presentation-time projection, not an event identity change. Dynamic prices still come from received price events, while occupancy, history and curves still come from received session/meter events.

## Suggested report update

Explain that the display joins source device records with successful location-level OCM/OSM matches using the original location ID, retaining each device's charger ID. Original nonempty fields take precedence. Quote the measured coverage counts above and identify plugs as location-level information. Include the new `charger_display` view and provenance fields in schema/design documentation, and update screenshots and AI-assistance file references to match the final submission.

The report PDFs are separate deliverables and were not rewritten in this code update.
