// USYD CODE CITATION ACKNOWLEDGEMENT
// I declare that this file was developed with extensive assistance from OpenAI Codex.
'use strict';
const el=id=>document.getElementById(id);
const escapeHTML=x=>String(x??'Unavailable').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=x=>x==null?'—':`$${Number(x).toFixed(2)}`;
const metadataSourceLabel=source=>({charger:'Assignment 1',location_plug_type:'Assignment 1 plug data',ocm_reviewed_conflict:'OCM candidate (29.23 m); original address conflicts',ocm:'Open Charge Map (location match)',osm:'OpenStreetMap (location match)',unavailable:'Not recorded'}[source]||'Not recorded');
let state=null,selected=null,fitted=false,detailData=null;
let stationOptionsKey=null,stationSelectorEditing=false;
const map=L.map('map').setView([-32.8,148.7],6);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,attribution:'© OpenStreetMap contributors'}).addTo(map);
const markers=new Map();
const chart=new Chart(el('curve'),{
 type:'line',data:{labels:[],datasets:[]},
 options:{
  responsive:true,maintainAspectRatio:false,animation:false,
  plugins:{legend:{display:true,labels:{boxWidth:10,font:{size:10}}}},
  scales:{
   x:{ticks:{maxTicksLimit:5,font:{size:9}},grid:{display:false}},
   y:{beginAtZero:true,ticks:{font:{size:10}},title:{display:true,text:'Energy (kWh)',font:{size:10}}}
  }
 }
});
function visible(){return state.stations.filter(s=>s.last_event&&(!el('operator').value||s.operator===el('operator').value));}
const available=s=>Math.max(0,Number(s.connectors)-Number(s.active));
function sortedStations(stations){
 const mode=el('sortChargers').value;
 return [...stations].sort((a,b)=>{
  let diff=0;
  if(mode==='price')diff=(a.price==null?Infinity:Number(a.price))-(b.price==null?Infinity:Number(b.price));
  if(mode==='available')diff=available(b)-available(a);
  return diff|| (mode==='default'?0:a.station_id.localeCompare(b.station_id,undefined,{numeric:true}));
 });
}
function syncStationSelector(force=false){
 if(!state)return;
 const selector=el('stationSelect');
 // Keep the native menu and any uncommitted keyboard choice intact during polling.
 if(!force&&(stationSelectorEditing||document.activeElement===selector))return;
 const options=visible().map(s=>[s.station_id,`${s.station_id} · ${s.name||s.operator}`]);
 const key=JSON.stringify(options);
 if(key!==stationOptionsKey){
  selector.replaceChildren(new Option('Select a charger',''),...options.map(([id,label])=>new Option(label,id)));
  stationOptionsKey=key;
 }
 const value=selected||'';
 if(selector.value!==value)selector.value=value;
}
function syncSelection(forceSelector=false){
 for(const [id,marker]of markers){
  marker.getElement()?.classList.toggle('is-selected',id===selected);
  marker.setZIndexOffset(id===selected?1000:0);
 }
 el('rows').querySelectorAll('tr').forEach(row=>{
  const active=row.dataset.id===selected;
  row.classList.toggle('selected',active);row.setAttribute('aria-selected',String(active));
 });
 syncStationSelector(forceSelector);
}
function fit(){const all=visible();if(all.length)map.fitBounds(all.map(s=>[s.lat,s.lon]),{padding:[40,40],maxZoom:10});}
function popupContent(s){
 const data=s.station_id===selected?detailData:null;
 const curves=data?.curves||[], points=curves.flatMap(c=>c.points);
 let graph='<p>Waiting for session readings...</p>';
 if(points.length){
  const times=points.map(p=>Date.parse(p.event_time)),lo=Math.min(...times),hi=Math.max(...times);
  const top=Math.max(1,...points.map(p=>p.energy_kwh)),colors=['#098661','#d39428','#4e7eaa','#9365b8'];
  const x=p=>30+(Date.parse(p.event_time)-lo)/Math.max(1,hi-lo)*240;
  const y=p=>120-p.energy_kwh/top*100;
  graph=`<svg viewBox="0 0 290 150" role="img" aria-label="Charging progress: cumulative energy in kWh" style="width:100%;height:150px"><path d="M30 20V120H275" fill="none" stroke="#aaa"/><text x="30" y="12" font-size="10">Cumulative kWh (max ${top.toFixed(2)})</text>`;
  curves.forEach((c,i)=>{const color=colors[i%colors.length];graph+=`<polyline fill="none" stroke="${color}" stroke-width="2" points="${c.points.map(p=>`${x(p)},${y(p)}`).join(' ')}"/>`+c.points.map(p=>`<circle cx="${x(p)}" cy="${y(p)}" r="2.5" fill="${color}"/>`).join('');});
  graph+=`<text x="30" y="140" font-size="9">${new Date(lo+36000000).toISOString().slice(11,19)}</text><text x="220" y="140" font-size="9">${new Date(hi+36000000).toISOString().slice(11,19)}</text></svg>`;
  graph+=`<small>${s.active?'Live active sessions':'Latest completed session'} · ${points.length} meter readings · UTC+10<br>${curves.map((c,i)=>`<span style="color:${colors[i%colors.length]}">${escapeHTML(c.session_id)}</span>`).join('<br>')}</small>`;
 }
 return `<b>${escapeHTML(s.name||s.station_id)}</b><br>${escapeHTML(s.address)}<br>Operator: ${escapeHTML(s.operator)}<br>Plugs: ${escapeHTML(s.plug_types||'Not recorded')}<br>Latest price: ${money(s.price)}/kWh · Active: ${s.active}/${s.connectors}<br>History: ${s.completed} completed · ${Number(s.delivered_kwh).toFixed(3)} kWh<br>ID: ${escapeHTML(s.station_id)}<br><small>Address source: ${escapeHTML(metadataSourceLabel(s.address_source))}</small>${graph}`;
}
function render(){
 const m=state.metrics;
 ['active','completed','events'].forEach(k=>el(k).textContent=Number(m[k]).toLocaleString());
 el('kwh').textContent=Number(m.kwh).toLocaleString(undefined,{maximumFractionDigits:1});
 el('observed').textContent=`${m.observed_stations} / ${state.stations.length}`;
 el('connection').textContent=state.mqtt.subscribed?'● MQTT connected · QoS 1':'● MQTT disconnected';el('connection').className='badge'+(state.mqtt.subscribed?' good':'');
 el('statusline').textContent=`SIMULATION WATERMARK  ${m.watermark?m.watermark.replace('T',' '):'No events received'}  ·  ${m.rejected} quarantined messages`;
 const stations=visible(),ids=new Set(stations.map(s=>s.station_id));
 for(const [id,marker]of markers)if(!ids.has(id)){map.removeLayer(marker);markers.delete(id);}
 stations.forEach(s=>{
  // Co-located charger devices retain their actual coordinates; no artificial jitter.
  let marker=markers.get(s.station_id);
  if(!marker){marker=L.marker([s.lat,s.lon],{icon:L.divIcon({className:'occupancy-marker',html:'',iconSize:[22,22]})}).addTo(map);markers.set(s.station_id,marker);}
  if(marker.activeCount!==s.active){
   marker.setIcon(L.divIcon({className:'occupancy-marker',iconSize:[22,22],iconAnchor:[11,11],
    html:`<span style="display:flex;align-items:center;justify-content:center;width:22px;height:22px;border:2px solid white;border-radius:50%;background:${s.active?'#c88213':'#087b5b'};color:white;font-size:10px;font-weight:700;box-shadow:0 1px 3px #0004">${s.active}</span>`}));
   marker.activeCount=s.active;
  }
  const label=`${money(s.price)} · ${s.active}/${s.connectors}`;
  if(marker.getTooltip())marker.setTooltipContent(label);else marker.bindTooltip(label,{permanent:stations.length<15,direction:'top',className:'marker-label'});
  const content=popupContent(s);
  if(marker.getPopup())marker.setPopupContent(content);else{
   marker.bindPopup(content,{maxWidth:420,minWidth:280});
   // Bind after Leaflet's popup handler so it cannot close the popup opened by select().
   marker.on('click',()=>select(s.station_id));
  }
 });
 el('rows').innerHTML=sortedStations(stations).map(s=>`<tr tabindex="0" data-id="${escapeHTML(s.station_id)}"><td><b>${escapeHTML(s.name||s.station_id)}</b><br><small>${escapeHTML(s.station_id)}</small></td><td>${escapeHTML(s.operator)}</td><td>${money(s.price)}</td><td><span class="pill">${s.active} / ${s.connectors}</span></td><td>${available(s)}</td><td>${s.completed}</td><td>${Number(s.delivered_kwh).toFixed(1)}</td></tr>`).join('');
 el('rows').querySelectorAll('tr').forEach(r=>{r.onclick=()=>select(r.dataset.id);r.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select(r.dataset.id);}};});
 if(!stations.some(s=>s.station_id===selected)){selected=null;detailData=null;chart.data.labels=[];chart.data.datasets=[];chart.update();}
 if(!selected&&stations.length)selected=(stations.find(s=>s.active)||stations[0]).station_id;
 if(!selected){
  el('name').textContent='No observed chargers';el('address').textContent='Wait for charger events or change the operator filter.';
  ['price','occupancy','operatorName','plugs','power','source'].forEach(id=>el(id).textContent='—');
  el('history').textContent='';el('curveNote').textContent='Waiting for meter events';
  el('metadataSources').textContent='';
 }
 if(!fitted&&stations.length){fit();fitted=true;}
 syncSelection();
}
async function select(id){if(!id)return;if(selected!==id)detailData=null;selected=id;syncSelection(true);const marker=markers.get(id);if(marker){map.panTo(marker.getLatLng());marker.openPopup();}await refreshDetail();}
async function refreshDetail(){
 if(!selected||!state)return;
 const s=state.stations.find(x=>x.station_id===selected);if(!s)return;
 el('name').textContent=s.name||s.station_id;el('address').textContent=s.address||'Address unavailable';
 el('metadataSources').textContent=`Name: ${metadataSourceLabel(s.name_source)} · Address: ${metadataSourceLabel(s.address_source)} · Plugs: ${metadataSourceLabel(s.plug_types_source)}`;
 el('price').textContent=money(s.price);el('occupancy').textContent=`${s.active} / ${s.connectors} active`;
 el('operatorName').textContent=s.operator;el('plugs').textContent=s.plug_types||'Not recorded';
 el('power').textContent=s.max_kw+' kW';el('source').textContent=`Charger ${s.charger_id} · Location ${s.location_id}`;
 el('history').textContent=`Historical total: ${s.completed} completed sessions · ${Number(s.delivered_kwh).toFixed(2)} kWh · ${money(s.revenue_aud)} simulated revenue`;
 const id=selected;const r=await fetch('/api/station/'+encodeURIComponent(id));if(!r.ok)throw Error('Detail fetch failed');const data=await r.json();if(selected!==id)return;detailData=data;draw();const marker=markers.get(id);if(marker?.getPopup())marker.setPopupContent(popupContent(s));
}
function draw(){
 if(!detailData)return;
 const key=el('measure').value,colors=['#098661','#d39428','#4e7eaa','#9365b8'];
 const times=[...new Set(detailData.curves.flatMap(c=>c.points.map(p=>p.event_time)))].sort();
 chart.data.labels=times.map(x=>x.slice(11,16));
 chart.data.datasets=detailData.curves.map((c,i)=>({label:c.session_id.split('-').slice(-2).join(' · '),data:times.map(t=>c.points.find(p=>p.event_time===t)?.[key]??null),borderColor:colors[i%colors.length],backgroundColor:colors[i%colors.length],borderWidth:2,pointRadius:2,tension:.15,spanGaps:true}));
 chart.options.scales.y.title.text={energy_kwh:'Cumulative energy (kWh)',power_kw:'Power (kW)',soc_pct:'State of charge (%)'}[key];chart.update();
 const n=detailData.curves.reduce((v,c)=>v+c.points.length,0);
 const active=detailData.sessions.filter(s=>!s.end_time).length;
 el('curveNote').textContent=`${active?'Live active sessions':'Most recent completed session'} · ${n} received meter readings · 5-minute generator interval`;
}
async function tick(){try{const r=await fetch('/api/state');if(!r.ok)throw Error('State fetch failed');state=await r.json();if(el('operator').options.length===1){const ops=[...new Set(state.stations.map(s=>s.operator))].sort();ops.forEach(o=>el('operator').add(new Option(o,o)));}render();await refreshDetail();}catch(e){el('connection').textContent='Dashboard connection interrupted';el('connection').className='badge';console.error(e);}finally{setTimeout(tick,1000);}}
const stationSelector=el('stationSelect');
stationSelector.onfocus=()=>{stationSelectorEditing=true;};
stationSelector.onpointerdown=()=>{stationSelectorEditing=true;};
stationSelector.onkeydown=()=>{stationSelectorEditing=true;};
stationSelector.onblur=()=>{stationSelectorEditing=false;syncStationSelector(true);};
stationSelector.onchange=e=>{stationSelectorEditing=false;return select(e.target.value);};
el('sortChargers').onchange=()=>render();el('operator').onchange=()=>{render();fit();refreshDetail();};el('fit').onclick=fit;el('measure').onchange=draw;tick();
