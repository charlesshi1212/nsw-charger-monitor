-- COMP5339 Assignment 1 - DuckDB relational schema

INSTALL spatial;
LOAD spatial;

BEGIN TRANSACTION;

DROP TABLE IF EXISTS location_plug_type;
DROP TABLE IF EXISTS plug_type;
DROP TABLE IF EXISTS location_augmentation_city_sydney;
DROP TABLE IF EXISTS location_augmentation_osm;
DROP TABLE IF EXISTS location_augmentation;
DROP TABLE IF EXISTS charger;
DROP TABLE IF EXISTS charger_location;
DROP TABLE IF EXISTS operator;
DROP TABLE IF EXISTS sa4_region;

CREATE TABLE sa4_region (
    sa4_code VARCHAR PRIMARY KEY,
    sa4_name VARCHAR NOT NULL
);

CREATE TABLE operator (
    operator_id BIGINT PRIMARY KEY,
    source_operator_name VARCHAR NOT NULL UNIQUE,
    ocm_operator_name VARCHAR,
    website_url VARCHAR,
    phone VARCHAR,
    email VARCHAR
);

CREATE TABLE charger_location (
    location_id BIGINT PRIMARY KEY,
    latitude DOUBLE NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude DOUBLE NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    lga_name VARCHAR,
    postcode VARCHAR,
    sa4_code VARCHAR REFERENCES sa4_region(sa4_code),
    geom GEOMETRY NOT NULL,
    UNIQUE (latitude, longitude)
);

CREATE TABLE charger (
    charger_id BIGINT PRIMARY KEY,
    location_id BIGINT NOT NULL REFERENCES charger_location(location_id),
    operator_id BIGINT NOT NULL REFERENCES operator(operator_id),
    station_name VARCHAR,
    station_address VARCHAR,
    charger_type VARCHAR NOT NULL,
    number_of_plugs INTEGER CHECK (number_of_plugs >= 0),
    charger_rating VARCHAR,
    charger_rating_kw DOUBLE,
    max_charger_rating_kw DOUBLE,
    source VARCHAR
);

CREATE TABLE location_augmentation (
    location_id BIGINT PRIMARY KEY REFERENCES charger_location(location_id),
    ocm_id BIGINT,
    ocm_title VARCHAR,
    ocm_operator VARCHAR,
    ocm_address VARCHAR,
    ocm_town VARCHAR,
    ocm_postcode VARCHAR,
    ocm_number_of_points INTEGER,
    ocm_usage_type VARCHAR,
    ocm_status VARCHAR,
    ocm_max_power_kw DOUBLE,
    match_distance_m DOUBLE CHECK (
        match_distance_m IS NULL OR match_distance_m >= 0
    ),
    operator_match BOOLEAN NOT NULL,
    postcode_match BOOLEAN NOT NULL,
    match_level VARCHAR CHECK (
        match_level IS NULL OR match_level IN ('Location', 'Operator')
    ),
    match_status VARCHAR NOT NULL CHECK (
        match_status IN (
            'Matched',
            'Operator_Level_Match',
            'Outside_Threshold',
            'Rejected',
            'No_Candidate',
            'No_Valid_Candidate',
            'API_Error'
        )
    ),
    candidate_count INTEGER NOT NULL CHECK (candidate_count >= 0),
    error_message VARCHAR
);

CREATE TABLE location_augmentation_osm (
    location_id BIGINT PRIMARY KEY REFERENCES charger_location(location_id),
    osm_id VARCHAR,
    osm_title VARCHAR,
    osm_operator VARCHAR,
    osm_network VARCHAR,
    osm_max_power_kw DOUBLE,
    osm_number_of_points INTEGER,
    osm_plug_types VARCHAR,
    osm_pricing_info VARCHAR,
    osm_is_free BOOLEAN,
    osm_accessibility VARCHAR,
    osm_access_condition VARCHAR,
    osm_allows_card_payment BOOLEAN,
    osm_allows_reservation BOOLEAN,
    osm_opening_hours VARCHAR,
    osm_source_url VARCHAR,
    osm_last_updated VARCHAR,
    match_distance_m DOUBLE CHECK (
        match_distance_m IS NULL OR match_distance_m >= 0
    ),
    operator_match BOOLEAN NOT NULL,
    match_level VARCHAR CHECK (
        match_level IS NULL OR match_level IN ('Location', 'Operator')
    ),
    match_status VARCHAR NOT NULL CHECK (
        match_status IN (
            'Matched',
            'Operator_Level_Match',
            'Outside_Threshold',
            'Rejected',
            'No_Candidate',
            'No_Valid_Candidate',
            'API_Error'
        )
    ),
    candidate_count INTEGER NOT NULL CHECK (candidate_count >= 0),
    error_message VARCHAR
);

CREATE TABLE location_augmentation_city_sydney (
    location_id BIGINT PRIMARY KEY REFERENCES charger_location(location_id),
    city_sydney_id VARCHAR,
    city_operator VARCHAR,
    city_street VARCHAR,
    city_suburb VARCHAR,
    city_parking_area VARCHAR,
    city_source_url VARCHAR,
    match_distance_m DOUBLE CHECK (
        match_distance_m IS NULL OR match_distance_m >= 0
    ),
    street_match BOOLEAN NOT NULL,
    suburb_match BOOLEAN NOT NULL,
    operator_match BOOLEAN NOT NULL,
    match_status VARCHAR NOT NULL CHECK (
        match_status IN (
            'Matched',
            'Rejected',
            'Outside_Threshold',
            'No_Candidate',
            'API_Error'
        )
    ),
    candidate_count INTEGER NOT NULL CHECK (candidate_count >= 0),
    error_message VARCHAR
);

CREATE TABLE plug_type (
    plug_type_id BIGINT PRIMARY KEY,
    plug_type_name VARCHAR NOT NULL UNIQUE
);

CREATE TABLE location_plug_type (
    location_id BIGINT NOT NULL REFERENCES charger_location(location_id),
    plug_type_id BIGINT NOT NULL REFERENCES plug_type(plug_type_id),
    PRIMARY KEY (location_id, plug_type_id)
);

CREATE INDEX charger_location_sa4_idx
    ON charger_location(sa4_code);

CREATE INDEX charger_operator_idx
    ON charger(operator_id);

CREATE INDEX charger_location_idx
    ON charger(location_id);

CREATE INDEX location_augmentation_match_status_idx
    ON location_augmentation(match_status);

CREATE INDEX location_augmentation_osm_match_status_idx
    ON location_augmentation_osm(match_status);

CREATE INDEX location_augmentation_city_sydney_match_status_idx
    ON location_augmentation_city_sydney(match_status);

COMMIT;
