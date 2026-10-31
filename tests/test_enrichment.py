# USYD CODE CITATION ACKNOWLEDGEMENT
# Developed with extensive assistance from OpenAI Codex.
"""Metadata precedence, match safety and device-grain regression checks."""
from pathlib import Path
import unittest
import duckdb

DDL = (Path(__file__).resolve().parents[1] / 'sql/charger_display.sql').read_text(encoding='utf-8')


class EnrichmentTests(unittest.TestCase):
    def setUp(self):
        self.con = duckdb.connect(':memory:')
        self.con.execute('''
            CREATE TABLE charger(charger_id BIGINT,location_id BIGINT,
                                 station_name VARCHAR,station_address VARCHAR);
            CREATE TABLE plug_type(plug_type_id BIGINT,plug_type_name VARCHAR);
            CREATE TABLE location_plug_type(location_id BIGINT,plug_type_id BIGINT);
            CREATE TABLE location_augmentation(location_id BIGINT,ocm_title VARCHAR,
                ocm_address VARCHAR,match_status VARCHAR,match_level VARCHAR,match_distance_m DOUBLE,ocm_town VARCHAR,ocm_postcode VARCHAR);
            CREATE TABLE location_augmentation_osm(location_id BIGINT,osm_title VARCHAR,
                osm_plug_types VARCHAR,match_status VARCHAR,match_level VARCHAR);
        ''')
        self.con.execute(DDL)

    def tearDown(self):
        self.con.close()

    def rows(self):
        result = self.con.execute('SELECT * FROM charger_display ORDER BY charger_id')
        columns = [column[0] for column in result.description]
        return [dict(zip(columns, row)) for row in result.fetchall()]

    def test_original_metadata_wins_over_augmentation(self):
        self.con.execute("INSERT INTO charger VALUES(1,10,' Source station ',' Source address ')")
        self.con.execute("INSERT INTO plug_type VALUES(1,'CCS (Type 2)')")
        self.con.execute('INSERT INTO location_plug_type VALUES(10,1)')
        self.con.execute("INSERT INTO location_augmentation(location_id,ocm_title,ocm_address,match_status,match_level) VALUES(10,'Other OCM','Other address','Matched','Location')")
        self.con.execute("INSERT INTO location_augmentation_osm VALUES(10,'Other OSM','CHAdeMO','Matched','Location')")
        row = self.rows()[0]
        self.assertEqual((row['name'], row['name_source']), ('Source station', 'charger'))
        self.assertEqual((row['address'], row['address_source']), ('Source address', 'charger'))
        self.assertEqual((row['plug_types'], row['plug_types_source']), ('CCS (Type 2)', 'location_plug_type'))

    def test_ocm_name_then_osm_name_and_osm_plugs_fill_gaps(self):
        self.con.execute("INSERT INTO charger VALUES(1,10,NULL,NULL),(2,20,'   ',NULL)")
        self.con.execute("INSERT INTO location_augmentation(location_id,ocm_title,ocm_address,match_status,match_level) VALUES(10,'OCM title','OCM address','Matched','Location'),(20,'   ',NULL,'Matched','Location')")
        self.con.execute("INSERT INTO location_augmentation_osm VALUES(10,'OSM title','CCS | CHAdeMO','Matched','Location'),(20,'Second OSM','CCS','Matched','Location')")
        first, second = self.rows()
        self.assertEqual((first['name'], first['name_source']), ('OCM title', 'ocm'))
        self.assertEqual((first['address'], first['address_source']), ('OCM address', 'ocm'))
        self.assertEqual((first['plug_types'], first['plug_types_source']), ('CCS | CHAdeMO', 'osm'))
        self.assertEqual((second['name'], second['name_source']), ('Second OSM', 'osm'))

    def test_operator_only_and_unsuccessful_matches_are_excluded(self):
        for index, (status, level) in enumerate([
            ('Operator_Level_Match', 'Operator'), ('Rejected', 'Location'),
            ('Outside_Threshold', 'Location'), ('Matched', 'Operator'),
            ('Matched', None), ('No_Candidate', None),
        ], 1):
            self.con.execute('INSERT INTO charger VALUES(?,?,NULL,NULL)', [index, index])
            self.con.execute('INSERT INTO location_augmentation(location_id,ocm_title,ocm_address,match_status,match_level) VALUES(?,?,?,?,?)',
                             [index, 'Unsafe name', 'Unsafe address', status, level])
            self.con.execute('INSERT INTO location_augmentation_osm VALUES(?,?,?,?,?)',
                             [index, 'Unsafe name', 'Unsafe plugs', status, level])
        for row in self.rows():
            for field in ('name', 'address', 'plug_types'):
                self.assertIsNone(row[field])
                self.assertEqual(row[field + '_source'], 'unavailable')

    def test_colocated_devices_and_devices_without_matches_are_preserved(self):
        self.con.execute('INSERT INTO charger VALUES(1,10,NULL,NULL),(2,10,NULL,NULL),(3,30,NULL,NULL)')
        self.con.execute("INSERT INTO location_augmentation(location_id,ocm_title,ocm_address,match_status,match_level) VALUES(10,'Shared location',NULL,'Matched','Location')")
        rows = self.rows()
        self.assertEqual([row['charger_id'] for row in rows], [1, 2, 3])
        self.assertEqual([row['name'] for row in rows], ['Shared location', 'Shared location', None])

    def test_blank_recorded_plug_value_allows_verified_osm_fallback(self):
        self.con.execute('INSERT INTO charger VALUES(1,10,NULL,NULL)')
        self.con.execute("INSERT INTO plug_type VALUES(1,'   ')")
        self.con.execute('INSERT INTO location_plug_type VALUES(10,1)')
        self.con.execute("INSERT INTO location_augmentation_osm VALUES(10,NULL,' CCS ','Matched','Location')")
        row = self.rows()[0]
        self.assertEqual((row['plug_types'], row['plug_types_source']), ('CCS', 'osm'))


if __name__ == '__main__':
    unittest.main()
