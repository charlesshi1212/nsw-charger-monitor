-- USYD CODE CITATION ACKNOWLEDGEMENT
-- Developed with extensive assistance from OpenAI Codex.
-- Display metadata only: source device identity, location and capacity stay in
-- their original tables. Only successful location-level matches may fill gaps.
CREATE OR REPLACE VIEW charger_display AS
WITH recorded_plugs AS (
    SELECT lp.location_id,
           string_agg(DISTINCT trim(pt.plug_type_name), ', '
                      ORDER BY trim(pt.plug_type_name)) AS plug_types
    FROM location_plug_type lp
    JOIN plug_type pt USING (plug_type_id)
    WHERE nullif(trim(pt.plug_type_name), '') IS NOT NULL
    GROUP BY lp.location_id
), candidates AS (
    SELECT c.charger_id,
           nullif(trim(c.station_name), '') AS original_name,
           nullif(trim(c.station_address), '') AS original_address,
           ocm.match_distance_m AS ocm_distance,
           ocm.ocm_town, ocm.ocm_postcode,
           nullif(trim(ocm.ocm_title), '') AS ocm_name,
           nullif(trim(ocm.ocm_address), '') AS ocm_address,
           nullif(trim(osm.osm_title), '') AS osm_name,
           p.plug_types AS recorded_plug_types,
           nullif(trim(osm.osm_plug_types), '') AS osm_plug_types
    FROM charger c
    LEFT JOIN recorded_plugs p USING (location_id)
    LEFT JOIN location_augmentation ocm
      ON ocm.location_id = c.location_id
     AND ocm.match_status = 'Matched'
     AND ocm.match_level = 'Location'
    LEFT JOIN location_augmentation_osm osm
      ON osm.location_id = c.location_id
     AND osm.match_status = 'Matched'
     AND osm.match_level = 'Location'
)
SELECT charger_id,
       coalesce(original_name, ocm_name, osm_name) AS name,
       CASE WHEN original_name IS NOT NULL THEN 'charger'
            WHEN ocm_name IS NOT NULL THEN 'ocm'
            WHEN osm_name IS NOT NULL THEN 'osm'
            ELSE 'unavailable' END AS name_source,
       CASE WHEN charger_id=3 AND ocm_name='Armidale Visitors Centre'
                  AND ocm_town='Armidale' AND ocm_postcode='2350'
                  AND ocm_distance <= 50 AND ocm_address IS NOT NULL
            THEN ocm_address || ', ' || ocm_town || ', ' || ocm_postcode
            ELSE coalesce(original_address, ocm_address) END AS address,
       CASE WHEN charger_id=3 AND ocm_name='Armidale Visitors Centre'
                  AND ocm_town='Armidale' AND ocm_postcode='2350'
                  AND ocm_distance <= 50 AND ocm_address IS NOT NULL
            THEN 'ocm_reviewed_conflict'
            WHEN original_address IS NOT NULL THEN 'charger'
            WHEN ocm_address IS NOT NULL THEN 'ocm'
            ELSE 'unavailable' END AS address_source,
       coalesce(recorded_plug_types, osm_plug_types) AS plug_types,
       CASE WHEN recorded_plug_types IS NOT NULL THEN 'location_plug_type'
            WHEN osm_plug_types IS NOT NULL THEN 'osm'
            ELSE 'unavailable' END AS plug_types_source
FROM candidates;
