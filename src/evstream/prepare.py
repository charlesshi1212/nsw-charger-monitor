# USYD CODE CITATION ACKNOWLEDGEMENT
# I declare that this file was developed with extensive assistance from OpenAI Codex.
"""Map actual Assignment 1 DC charger IDs to the instructor generator's input."""
import argparse
import csv
import json
import hashlib
import shutil
import duckdb
from .common import ROOT, DEFAULT_DB


def prepare(target=DEFAULT_DB):
    source = ROOT / 'assignment1_reference/database/ev_chargers.duckdb'
    target = target.resolve()
    if target.exists():
        raise FileExistsError(f'{target} exists. Use a new database path; no data was overwritten.')
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    con = duckdb.connect(str(target))
    rows = con.execute("""
      SELECT c.charger_id, c.location_id, c.station_name, c.station_address,
             c.number_of_plugs, c.max_charger_rating_kw, l.latitude, l.longitude,
             r.sa4_name, o.source_operator_name,
             (SELECT string_agg(p.plug_type_name, ', ' ORDER BY p.plug_type_name)
              FROM location_plug_type lp JOIN plug_type p USING(plug_type_id)
              WHERE lp.location_id=c.location_id) plug_types
      FROM charger c JOIN charger_location l USING(location_id)
      JOIN operator o USING(operator_id) LEFT JOIN sa4_region r USING(sa4_code)
      WHERE c.charger_type='DC' ORDER BY c.charger_id
    """).fetchall()
    con.close()
    fields = ['station_id','name','lat','lon','site_type','connectors','max_kw',
              'charger_id','location_id','address','operator','plug_types','sa4_name']
    records = []
    for cid, lid, name, address, plugs, power, lat, lon, region, operator, plug_types in rows:
        if not plugs or plugs < 1 or not power or power <= 0:
            raise ValueError(f'Invalid generator capacity for charger {cid}: {plugs}, {power}')
        records.append(dict(zip(fields, [f'DC-{cid}', name or f'{operator} DC charger {cid}',
            lat, lon, 'urban' if region and (region.startswith('Sydney -') or region in
                {'Newcastle and Lake Macquarie','Illawarra','Central Coast'}) else 'regional',
            plugs, power, cid, lid, address or 'Address unavailable', operator,
            plug_types or 'Not recorded', region or 'Unknown'])))
    folder = ROOT / 'data'
    folder.mkdir(exist_ok=True)
    with (folder / 'stations_input.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(records)
    metadata = {'source_database_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                'dc_chargers':len(records),'physical_locations':len({r['location_id'] for r in records}),
                'connectors':sum(r['connectors'] for r in records),
                'station_id_rule':'DC-<Assignment 1 charger_id>',
                'urban_rule':'Sydney SA4 regions, Newcastle and Lake Macquarie, Illawarra, Central Coast',
                'capacity_assumption':'number_of_plugs models independently occupied connectors; maximum listed kW per connector',
                'time_basis':'AEMO market time, fixed UTC+10; not daylight-saving civil time'}
    (folder/'station_mapping.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(json.dumps(metadata,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',type=__import__('pathlib').Path,default=DEFAULT_DB)
    prepare(p.parse_args().db)
