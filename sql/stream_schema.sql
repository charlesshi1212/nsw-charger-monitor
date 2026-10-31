-- USYD CODE CITATION ACKNOWLEDGEMENT
-- I declare that this DDL was developed with extensive assistance from OpenAI Codex.
-- Additive extension: existing Assignment 1 tables are preserved.
CREATE TABLE IF NOT EXISTS stream_station (
 station_id VARCHAR PRIMARY KEY,
 charger_id BIGINT NOT NULL UNIQUE REFERENCES charger(charger_id),
 connectors INTEGER NOT NULL CHECK(connectors>0), site_type VARCHAR NOT NULL,
 max_kw DOUBLE NOT NULL CHECK(max_kw>0)
);
CREATE TABLE IF NOT EXISTS stream_event (
 event_id VARCHAR PRIMARY KEY, dataset_id VARCHAR NOT NULL, sequence BIGINT NOT NULL,
 event_type VARCHAR NOT NULL CHECK(event_type IN ('price_update','session_start','session_end','meter')),
 event_time TIMESTAMPTZ NOT NULL, station_id VARCHAR NOT NULL REFERENCES stream_station(station_id),
 session_id VARCHAR, connector_id INTEGER, payload JSON NOT NULL,
 received_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS rejected_message (
 receipt_id VARCHAR PRIMARY KEY, received_at TIMESTAMPTZ DEFAULT current_timestamp,
 topic VARCHAR, raw_payload VARCHAR, reason VARCHAR NOT NULL
);
CREATE INDEX IF NOT EXISTS event_station_time ON stream_event(station_id,event_time);
CREATE INDEX IF NOT EXISTS event_session_time ON stream_event(session_id,event_time);
CREATE INDEX IF NOT EXISTS event_kind_time ON stream_event(event_type,event_time);
CREATE OR REPLACE VIEW latest_price AS
 SELECT station_id,event_time,CAST(json_extract(payload,'$.price_per_kwh') AS DOUBLE) price_per_kwh
 FROM stream_event WHERE event_type='price_update'
 QUALIFY row_number() OVER(PARTITION BY station_id ORDER BY event_time DESC,sequence DESC)=1;
CREATE OR REPLACE VIEW charging_session AS
 SELECT station_id,session_id,
  min(event_time) FILTER(WHERE event_type='session_start') start_time,
  max(event_time) FILTER(WHERE event_type='session_end') end_time,
  max(connector_id) connector_id,
  max(CAST(json_extract(payload,'$.energy_kwh') AS DECIMAL(12,3))) FILTER(WHERE event_type='session_end') energy_kwh,
  max(CAST(json_extract(payload,'$.cost_aud') AS DECIMAL(12,2))) FILTER(WHERE event_type='session_end') cost_aud,
  max(CAST(json_extract(payload,'$.charge_minutes') AS DOUBLE)) FILTER(WHERE event_type='session_end') charge_minutes
 FROM stream_event WHERE session_id IS NOT NULL GROUP BY station_id,session_id;
CREATE OR REPLACE VIEW active_session AS
 SELECT * FROM charging_session WHERE start_time IS NOT NULL AND end_time IS NULL;
CREATE OR REPLACE VIEW station_history AS
 SELECT station_id,count(*) FILTER(WHERE end_time IS NOT NULL) completed_sessions,
  coalesce(sum(energy_kwh) FILTER(WHERE end_time IS NOT NULL),0) delivered_kwh,
  coalesce(sum(cost_aud) FILTER(WHERE end_time IS NOT NULL),0) revenue_aud,
  avg(charge_minutes) FILTER(WHERE end_time IS NOT NULL) mean_charge_minutes
 FROM charging_session GROUP BY station_id;
