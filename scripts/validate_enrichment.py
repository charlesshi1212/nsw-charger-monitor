# USYD CODE CITATION ACKNOWLEDGEMENT
# Developed with extensive assistance from OpenAI Codex.
"""Check enrichment against the packaged snapshot, using a temporary DB copy."""
from collections import Counter
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import duckdb
from evstream.app import create_app
from evstream.store import Store


def validate():
    result = {'passed': False}
    with tempfile.TemporaryDirectory(prefix='comp5339-enrichment-') as temporary:
        source = ROOT / 'database/ev_stream.duckdb'
        target = Path(temporary) / 'snapshot.duckdb'
        shutil.copy2(source, target)
        wal = source.with_suffix('.duckdb.wal')
        if wal.exists():
            shutil.copy2(wal, target.with_suffix('.duckdb.wal'))
        con = duckdb.connect(str(target))
        original_names = dict(con.execute("SELECT c.charger_id,nullif(trim(c.station_name),'') FROM stream_station s JOIN charger c USING(charger_id)").fetchall())
        original_plugs = dict(con.execute("""
            SELECT c.charger_id,string_agg(DISTINCT trim(pt.plug_type_name),', ' ORDER BY trim(pt.plug_type_name))
            FROM stream_station s JOIN charger c USING(charger_id)
            JOIN location_plug_type lp USING(location_id) JOIN plug_type pt USING(plug_type_id)
            WHERE nullif(trim(pt.plug_type_name),'') IS NOT NULL GROUP BY c.charger_id
        """).fetchall())
        original_geometry = {
            row[0]: tuple(row[1:]) for row in con.execute("""
                SELECT c.charger_id,c.location_id,l.latitude,l.longitude,s.connectors,s.max_kw
                FROM stream_station s JOIN charger c USING(charger_id)
                JOIN charger_location l USING(location_id)
            """).fetchall()
        }
        event_ids = set(row[0] for row in con.execute('SELECT event_id FROM stream_event').fetchall())
        before_metrics = con.execute("""SELECT
            (SELECT count(*) FROM active_session),
            (SELECT count(*) FROM charging_session WHERE end_time IS NOT NULL),
            (SELECT sum(energy_kwh) FROM charging_session WHERE end_time IS NOT NULL)
        """).fetchone()
        con.close()

        store = Store(target)
        try:
            state = store.snapshot()
            stations, metrics = state['stations'], state['metrics']
            assert len(stations) == len(original_names) == len({s['charger_id'] for s in stations})
            assert {row['event_id'] for row in store.query('SELECT event_id FROM stream_event')} == event_ids
            assert (metrics['active'], metrics['completed'], metrics['kwh']) == before_metrics
            for station in stations:
                charger = station['charger_id']
                if original_names[charger] is not None:
                    assert station['name'] == original_names[charger]
                    assert station['name_source'] == 'charger'
                if charger in original_plugs:
                    assert station['plug_types'] == original_plugs[charger]
                    assert station['plug_types_source'] == 'location_plug_type'
                assert (station['location_id'], station['lat'], station['lon'],
                        station['connectors'], station['max_kw']) == original_geometry[charger]
            response = create_app(store).test_client().get('/api/state')
            assert response.status_code == 200
            api_stations = response.get_json()['stations']
            assert len(api_stations) == len(stations)
            assert all({'name_source','address_source','plug_types_source'} <= s.keys() for s in api_stations)
            before_name_count = sum(name is not None for name in original_names.values())
            after_name_count = sum(s['name'] is not None for s in stations)
            result.update({
                'passed': True,
                'devices': len(stations),
                'names_before': before_name_count,
                'names_after': after_name_count,
                'names_added': after_name_count - before_name_count,
                'name_sources': dict(Counter(s['name_source'] for s in stations)),
                'plug_types_before': len(original_plugs),
                'plug_types_after': sum(s['plug_types'] is not None for s in stations),
                'plug_types_added': sum(s['plug_types_source'] == 'osm' for s in stations),
                'plug_type_sources': dict(Counter(s['plug_types_source'] for s in stations)),
                'event_ids_unchanged': True,
                'original_nonempty_fields_preserved': True,
                'device_identity_geometry_capacity_preserved': True,
                'metrics': metrics,
                'api_status': response.status_code,
                'examples': [{key: s[key] for key in ('station_id','name','name_source','plug_types','plug_types_source','active')}
                             for s in stations if s['name_source'] in ('ocm','osm') and s['plug_types_source'] == 'osm'][:8],
            })
        finally:
            store.close()
    return result


if __name__ == '__main__':
    result = validate()
    output = ROOT / 'docs/enrichment_validation.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, default=str) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2, default=str))
