let PROPS=[], FACETS={}, REPORT={}, RESULTS=[], TERMS=[], UNITS=[], map, cluster;

const $ = s => document.querySelector(s);
const money = v => v==null ? '—' : '$'+Number(v).toLocaleString(undefined,{maximumFractionDigits:0});
const num = v => v==null ? '—' : Number(v).toLocaleString();
const esc = s => String(s??'').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const bedLabel = b => b==null ? '—' : (Number(b)===0 ? 'Studio' : Number(b)+' bd');

document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{
  document.querySelectorAll('nav button').forEach(x=>x.classList.remove('on'));
  document.querySelectorAll('.view').forEach(x=>x.classList.remove('on'));
  b.classList.add('on'); $('#v-'+b.dataset.v).classList.add('on');
  if(b.dataset.v==='map' && map) setTimeout(()=>map.invalidateSize(),50);
});

async function boot(){
  [PROPS, FACETS, REPORT, RESULTS, TERMS] = await Promise.all(
    ['/api/properties','/api/facets','/api/report','/api/site_results','/api/terms']
    .map(u=>fetch(u).then(r=>r.json())));
  fillFacets();
  const y = REPORT.yield||{};
  $('#hdr').textContent = `${num(y.listing_rows)} listing rows · ${PROPS.length} properties with data · ${num(y.sites_attempted)} sites attempted`;
  initMap(); drawMap(); loadUnits(); drawProps(); drawCoverage(); drawPlatforms(); drawTerms(); drawTrends();
}
async function reload(){ await fetch('/api/reload'); await boot(); }

function fillFacets(){
  const beds = (FACETS.bedrooms||[]).map(([b,n])=>`<option value="${b}">${bedLabel(b)} (${n})</option>`).join('');
  $('#m-beds').innerHTML = '<option value="any">any</option>'+beds;
  $('#u-beds').innerHTML = '<option value="any">any</option>'+beds;
  const cities = (FACETS.cities||[]).map(([c,n])=>`<option value="${esc(c)}">${esc(c)} (${n})</option>`).join('');
  $('#m-city').innerHTML = '<option value="">all</option>'+cities;
  $('#u-city').innerHTML = '<option value="">all</option>'+cities;
  $('#u-op').innerHTML = '<option value="">all</option>'+
    (FACETS.operators||[]).map(([o,n])=>`<option value="${esc(o)}">${esc(o)} (${n})</option>`).join('');
}

/* ---------------- map ---------------- */
function initMap(){
  if(map) return;
  map = L.map('map',{scrollWheelZoom:true}).setView([39.74,-104.99],11);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{
    maxZoom:19, attribution:'© OpenStreetMap contributors'
  }).addTo(map);
  cluster = L.markerClusterGroup({maxClusterRadius:45});
  map.addLayer(cluster);
}
function rentColor(r){
  if(r==null) return '#6f7887';
  if(r<1500) return '#4ade80'; if(r<2000) return '#a3e635';
  if(r<2600) return '#fbbf24'; if(r<3400) return '#fb923c'; return '#f87171';
}
async function drawMap(){
  const beds=$('#m-beds').value, maxr=$('#m-rent').value, city=$('#m-city').value;
  const q=new URLSearchParams(); if(beds!=='any')q.set('beds',beds);
  if(maxr)q.set('max_rent',maxr); if(city)q.set('city',city); q.set('limit','100000');
  const d = await fetch('/api/listings?'+q).then(r=>r.json());
  // group matching rows by property
  const g={};
  for(const l of d.rows){
    if(!l.lat) continue;
    const k=l.property_name||l.source_url;
    (g[k] = g[k] || {rows:[],l}).rows.push(l);
  }
  cluster.clearLayers();
  let n=0;
  for(const k in g){
    const rows=g[k].rows, l=g[k].l;
    const rents=rows.map(r=>r.rent).filter(v=>v!=null);
    const lo=rents.length?Math.min(...rents):null, hi=rents.length?Math.max(...rents):null;
    const avail=rows.filter(r=>r.granularity==='unit').length ||
                rows.reduce((a,r)=>a+(r.units_available||0),0);
    const m=L.circleMarker([l.lat,l.lon],{radius:7,weight:1.5,color:'#0f1115',
      fillColor:rentColor(lo),fillOpacity:.92});
    const plans=[...new Set(rows.map(r=>bedLabel(r.bedrooms)))].join(', ');
    m.bindPopup(`<b>${esc(l.property_name||'—')}</b><br>
      <span class="muted">${esc([l.street,l.city].filter(Boolean).join(', '))}</span><br>
      ${lo!=null?`Rent ${money(lo)}${hi!==lo?' – '+money(hi):''}<br>`:''}
      ${avail?`${avail} unit${avail===1?'':'s'} available<br>`:''}
      ${plans?`<span class="muted small">${esc(plans)}</span><br>`:''}
      ${l.operator?`<span class="muted small">${esc(l.operator)}</span><br>`:''}
      <a href="${esc(l.source_url)}" target="_blank" rel="noopener">source page ↗</a>`);
    cluster.addLayer(m); n++;
  }
  $('#m-count').textContent = `${n} properties mapped · ${d.n} matching rows`;
}

/* ---------------- units ---------------- */
const U_COLS=[
  ['property_name','Property',v=>esc(v)],
  ['city','City',v=>esc(v)],
  ['plan_name','Plan',v=>esc(v)],
  ['unit_number','Unit',v=>esc(v)],
  ['bedrooms','Bd',bedLabel,'num'],
  ['bathrooms','Ba',v=>v==null?'—':v,'num'],
  ['sqft','Sq ft',num,'num'],
  ['comparable_rent','Comparable',money,'num'],
  ['rent_per_bed_month','Per bed',money,'num'],
  ['rent_per_sqft_month','$/sqft',v=>v==null?'—':'$'+Number(v).toFixed(2),'num'],
  ['base_rent_month','Base',money,'num'],
  ['all_in_rent_month','All-in',money,'num'],
  ['mandatory_fees_monthly','Fees',money,'num'],
  ['comparable_rent_best_case','With concession',money,'num'],
  ['concession_months_free','Free mo',(v,r)=>v==null?'—':`${v}${r&&r.concession_is_upper_bound?' <span class="pill D" title="advertised as an upper bound, or limited to selected units">max</span>':''}`,'num'],
  ['rent_basis','Basis',v=>v==='per_bed'?'<span class="pill D">per bed</span>':'<span class="muted small">unit</span>'],
  ['lease_term_months','Term',v=>v==null?'—':v+' mo','num'],
  ['rent_term_matrix','Terms',v=>(v&&v.length)?`<span class="pill ok">${v.length}</span>`:'—','num'],
  ['rent','Quoted',money,'num'],
  ['units_available','Avail',num,'num'],
  ['available_display','Available',v=>esc(v)],
  ['market_rate','Mkt',v=>v===false?'<span class="pill D">restricted</span>':'<span class="muted small">yes</span>'],
  ['operator','Operator',v=>esc(v)],
  ['platform','Platform',v=>esc(v)],
  ['confidence','Conf',(v,r)=>`<span class="pill ${v==='high'?'ok':v==='low'?'no':'na'}" title="${esc((r&&r.confidence_reasons||[]).join(' | '))||'no caveats'}">${esc(v)}</span>`],
  ['cost_completeness','Cost data',(v,r)=>`<span class="pill ${v==='complete'?'ok':v==='minimal'?'no':'na'}" title="${esc((r&&r.cost_gaps||[]).join(' | '))||'nothing missing'}">${esc(v)}</span>`],
  ['quality_flags','Flags',v=>(v&&v.length)?v.map(f=>`<span class="pill ${f==='per_bed_pricing'?'D':f==='low_confidence_layer'?'C':'E'}">${esc(f.split('(')[0].replace(/_/g,' '))}</span>`).join(' '):''],
  ['source_url','Source',v=>`<a href="${esc(v)}" target="_blank" rel="noopener">↗</a>`],
];
let uSort={k:'comparable_rent',dir:1};
async function loadUnits(){
  const q=new URLSearchParams({limit:'100000'});
  if($('#u-q').value)q.set('search',$('#u-q').value);
  if($('#u-beds').value!=='any')q.set('beds',$('#u-beds').value);
  if($('#u-min').value)q.set('min_rent',$('#u-min').value);
  if($('#u-max').value)q.set('max_rent',$('#u-max').value);
  if($('#u-city').value)q.set('city',$('#u-city').value);
  if($('#u-op').value)q.set('operator',$('#u-op').value);
  if($('#u-hasrent').checked)q.set('has_rent','1');
  if($('#u-plaus').checked)q.set('plausible_only','1');
  if($('#u-hiconf').checked)q.set('high_conf','1');
  if($('#u-mkt').checked)q.set('market_rate','1');
  if($('#u-cmp').checked)q.set('has_comparable','1');
  const d=await fetch('/api/listings?'+q).then(r=>r.json());
  UNITS=d.rows;
  const cmp=UNITS.filter(r=>r.comparable_rent!=null).map(r=>r.comparable_rent).sort((a,b)=>a-b);
  const med = cmp.length ? cmp[Math.floor(cmp.length/2)] : null;
  const hi=UNITS.filter(r=>r.confidence==='high').length;
  $('#u-count').innerHTML=`${num(d.n)} rows · ${num(cmp.length)} with a comparable rent · median ${money(med)} · ${num(hi)} high-confidence`;
  renderUnits();
}
function renderUnits(){
  const rows=[...UNITS].sort((a,b)=>{
    const x=a[uSort.k], y=b[uSort.k];
    if(x==null&&y==null)return 0; if(x==null)return 1; if(y==null)return -1;
    return (typeof x==='number'?x-y:String(x).localeCompare(String(y)))*uSort.dir;
  });
  let h='<thead><tr>'+U_COLS.map(c=>
    `<th onclick="sortUnits('${c[0]}')">${c[1]}${uSort.k===c[0]?(uSort.dir>0?' ▲':' ▼'):''}</th>`).join('')+'</tr></thead><tbody>';
  for(const r of rows.slice(0,3000)){
    h+='<tr>'+U_COLS.map(c=>`<td class="${c[3]||''}">${c[2](r[c[0]],r)}</td>`).join('')+'</tr>';
  }
  $('#u-tbl').innerHTML=h+'</tbody>';
  if(rows.length>3000) $('#u-count').innerHTML+=' <span class="muted">(showing first 3,000 — export CSV for all)</span>';
}
function sortUnits(k){ uSort = {k, dir: uSort.k===k ? -uSort.dir : 1}; renderUnits(); }
function exportCsv(){
  const cols=Object.keys(UNITS[0]||{});
  const esc2=v=>{ if(v==null)return''; const s=Array.isArray(v)?v.join('|'):String(v);
    return /[",\n]/.test(s)?'"'+s.replace(/"/g,'""')+'"':s; };
  const csv=[cols.join(',')].concat(UNITS.map(r=>cols.map(c=>esc2(r[c])).join(','))).join('\n');
  const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob([csv],{type:'text/csv'}));
  a.download='housing_navigator_units.csv'; a.click();
}

/* ---------------- properties ---------------- */
function drawProps(){
  const q=($('#p-q').value||'').toLowerCase();
  const rows=PROPS.filter(p=>!q||[p.property_name,p.operator,p.city,p.street].join(' ').toLowerCase().includes(q));
  let h=`<thead><tr><th>Property</th><th>Address</th><th>Operator</th><th class="num">Rows</th>
    <th class="num">Units avail</th><th class="num">Rent range</th><th class="num">Sq ft</th>
    <th>Beds</th><th class="num">Walk</th><th>Platform</th><th>Terms</th><th>Source</th></tr></thead><tbody>`;
  for(const p of rows){
    const t=p.terms_verdict;
    h+=`<tr onclick="showProp('${esc(p.property_name).replace(/'/g,"\\'")}')" style="cursor:pointer">
      <td><b>${esc(p.property_name)}</b></td>
      <td class="muted">${esc([p.street,p.city,p.state,p.postal_code].filter(Boolean).join(', '))}</td>
      <td class="muted">${esc(p.operator||'—')}</td>
      <td class="num">${num(p.n_rows)}</td>
      <td class="num">${p.n_units?num(p.n_units):'—'}</td>
      <td class="num">${p.rent_min?money(p.rent_min)+(p.rent_max!==p.rent_min?'–'+money(p.rent_max):''):'—'}</td>
      <td class="num">${p.sqft_min?num(p.sqft_min)+(p.sqft_max!==p.sqft_min?'–'+num(p.sqft_max):''):'—'}</td>
      <td class="small">${(p.beds_offered||[]).map(bedLabel).join(', ')}</td>
      <td class="num">${p.walk_score??'—'}</td>
      <td class="small muted">${esc(p.platform)}${p.n_flagged?` <span class="pill E">${p.n_flagged} flagged</span>`:''}</td>
      <td><span class="pill ${t==='PROHIBITS'?'no':t==='SILENT'?'ok':'na'}">${esc(t||'—')}</span></td>
      <td><a href="${esc(p.source_url)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">↗</a></td></tr>`;
  }
  $('#p-tbl').innerHTML=h+'</tbody>';
}
function showProp(name){
  const p=PROPS.find(x=>x.property_name===name); if(!p)return;
  const am=(p.amenities||[]).map(a=>`<span class="amen">${esc(a.name||a)}</span>`).join('');
  const oh=(p.office_hours||[]).map(o=>`${[].concat(o.days||[]).join(', ')}: ${o.opens}–${o.closes}`).join('<br>');
  $('#p-detail').innerHTML=`<div class="card" style="margin-top:16px">
    <h2>${esc(p.property_name)}</h2>
    <div class="muted">${esc([p.street,p.city,p.state,p.postal_code].filter(Boolean).join(', '))}
      ${p.telephone?' · '+esc(p.telephone):''}${p.lat?` · ${p.lat.toFixed(5)}, ${p.lon.toFixed(5)}`:''}</div>
    ${p.description?`<p class="small">${esc(p.description)}</p>`:''}
    ${p.pet_policy?`<p class="small"><b>Pets:</b> ${esc(p.pet_policy)}</p>`:''}
    ${oh?`<p class="small"><b>Office hours:</b><br>${oh}</p>`:''}
    <p class="small"><b>Extraction:</b> ${esc(p.extraction_method)} · <b>Platform:</b> ${esc(p.platform)}
       · <b>Terms:</b> ${esc(p.terms_verdict||'—')}${p.terms_url?` (<a href="${esc(p.terms_url)}" target="_blank">doc</a>)`:''}</p>
    ${am?`<p class="small"><b>Amenities (${(p.amenities||[]).length}):</b><br>${am}</p>`:''}
  </div>`;
  $('#p-detail').scrollIntoView({behavior:'smooth',block:'nearest'});
}

/* ---------------- coverage ---------------- */
function drawCoverage(){
  const y=REPORT.yield||{}; const b=y.buckets||[];
  const code=c=>c.charAt(0);
  let h='<div class="cards">'+[
    ['Sites attempted',num(y.sites_attempted),''],
    ['Produced usable data',num(y.usable_any_data),(y.usable_pct??0)+'% of attempted'],
    ['Listing rows',num(y.listing_rows),num(y.unit_level_rows)+' unit-level'],
    ['Rows with rent',num(y.rows_with_rent),''],
    ['Rows with availability',num(y.rows_with_availability),''],
    ['Rows with lat/long',num(y.rows_with_geo),''],
  ].map(([k,v,n])=>`<div class="card"><div class="k">${k}</div><div class="v">${v}</div><div class="n">${n}</div></div>`).join('')+'</div>';

  const dq=REPORT.data_quality||{};
  h+='<h2>Data quality</h2><div class="cards">'+[
    ['Plausible rows',num(dq.plausible),`${num(dq.implausible)} flagged implausible`],
    ['High-confidence rows',num(dq.high_confidence_rows),'excludes the L4 HTML fallback'],
  ].map(([k,v,n])=>`<div class="card"><div class="k">${k}</div><div class="v">${v}</div><div class="n">${n}</div></div>`).join('')+'</div>';
  if(dq.rows_by_layer){
    h+='<div class="tblwrap" style="margin-bottom:8px"><table><thead><tr><th>Extraction layer</th><th class="num">Rows</th><th class="num">Priced rows</th></tr></thead><tbody>';
    for(const k of Object.keys(dq.rows_by_layer).sort())
      h+=`<tr><td>${esc(k)}</td><td class="num">${num(dq.rows_by_layer[k])}</td><td class="num">${num((dq.priced_rows_by_layer||{})[k]||0)}</td></tr>`;
    h+='</tbody></table></div>';
  }
  if(dq.flag_counts){
    h+='<div class="tblwrap"><table><thead><tr><th>Quality flag</th><th class="num">Rows</th></tr></thead><tbody>';
    for(const k of Object.keys(dq.flag_counts).sort((a,b)=>dq.flag_counts[b]-dq.flag_counts[a]))
      h+=`<tr><td>${esc(k.replace(/_/g,' '))}</td><td class="num">${num(dq.flag_counts[k])}</td></tr>`;
    h+='</tbody></table></div>';
  }
  h+='<h2>Outcome by site</h2><div class="tblwrap"><table><thead><tr><th>Code</th><th>Outcome</th><th class="num">Sites</th><th class="num">%</th><th></th></tr></thead><tbody>';
  const mx=Math.max(...b.map(x=>x.n),1);
  for(const x of b){ if(!x.n) continue;
    h+=`<tr><td><span class="pill ${code(x.code)}">${esc(x.code)}</span></td><td>${esc(x.label)}</td>
      <td class="num">${x.n}</td><td class="num">${x.pct}%</td>
      <td><div class="bar"><span style="width:${100*x.n/mx}%"></span></div></td></tr>`; }
  h+='</tbody></table></div>';

  const rs=REPORT.rent_stats_by_bedrooms||[];
  if(rs.length){
    h+='<h2>Collected rent distribution (sanity check)</h2><div class="tblwrap"><table><thead><tr><th>Bedrooms</th><th class="num">n</th><th class="num">min</th><th class="num">p25</th><th class="num">median</th><th class="num">p75</th><th class="num">max</th></tr></thead><tbody>';
    for(const r of rs) h+=`<tr><td>${bedLabel(r.bedrooms)}</td><td class="num">${num(r.n)}</td>
      <td class="num">${money(r.min)}</td><td class="num">${money(r.p25)}</td><td class="num">${money(r.median)}</td>
      <td class="num">${money(r.p75)}</td><td class="num">${money(r.max)}</td></tr>`;
    h+='</tbody></table></div>';
  }

  const br=REPORT.browser_recovery||{};
  if(br.bot_blocked_sites!==undefined){
    h+='<h2>Bot-blocked sites — browser recovery</h2>';
    h+='<div class="cards">'+[
      ['Bot-blocked (plain HTTP)',num(br.bot_blocked_sites),'5% of attempted, not 25%'],
      ['Pages captured via browser',num(br.attempted_via_browser),''],
      ['Yielded rent',num(br.recovered_with_rent),`${num(br.priced_rows)} priced rows`],
    ].map(([k,v,n])=>`<div class="card"><div class="k">${k}</div><div class="v">${v}</div><div class="n">${n}</div></div>`).join('')+'</div>';
    h+=`<div class="foot">${esc(br.note||'')}</div>`;
    if((br.captured_but_empty||[]).length)
      h+=`<div class="foot">Captured but yielded nothing (details load only on interaction): ${br.captured_but_empty.map(esc).join(', ')}</div>`;
  }
  h+='<h2>Every site attempted</h2><div class="row"><label class="f">Filter<input id="c-q" oninput="drawSiteRows()" placeholder="name, host, outcome…"></label></div><div class="tblwrap"><table id="c-tbl"></table></div>';
  $('#cov').innerHTML=h; drawSiteRows();
}
function drawSiteRows(){
  const q=($('#c-q')?.value||'').toLowerCase();
  const rows=RESULTS.filter(r=>!q||[r.name,r.marketing_url,r.outcome,r.platform,r.detail].join(' ').toLowerCase().includes(q))
    .sort((a,b)=>a.outcome.localeCompare(b.outcome)||String(a.name).localeCompare(String(b.name)));
  let h=`<thead><tr><th>Outcome</th><th>Name</th><th>Site</th><th>Platform</th><th class="num">Rows</th>
    <th class="num">Rent</th><th class="num">Avail</th><th>Layer</th><th>Terms</th><th>Detail</th></tr></thead><tbody>`;
  for(const r of rows){
    h+=`<tr><td><span class="pill ${r.outcome.charAt(0)}">${esc(r.outcome.split('_')[0])}</span></td>
      <td>${esc(r.name||'—')}</td>
      <td class="small"><a href="${esc(r.marketing_url)}" target="_blank" rel="noopener">${esc((r.marketing_url||'').replace(/^https?:\/\//,''))}</a></td>
      <td class="small muted">${esc(r.platform)}</td><td class="num">${num(r.n_rows)}</td>
      <td class="num">${num(r.n_rows_with_rent)}</td><td class="num">${r.n_units_available??'—'}</td>
      <td class="small muted">${esc(r.winning_layer||'—')}</td>
      <td class="small muted">${esc(r.terms_verdict||'—')}</td>
      <td class="small muted">${esc((r.detail||'').slice(0,90))}</td></tr>`;
  }
  $('#c-tbl').innerHTML=h+'</tbody>';
}

/* ---------------- platforms ---------------- */
function drawPlatforms(){
  const p=REPORT.platforms||[], wl=REPORT.winning_layers||{};
  let h='<h2>Platform fingerprint — which site builders yield structured data</h2>';
  h+='<div class="tblwrap"><table><thead><tr><th>Platform / builder</th><th class="num">Sites</th><th class="num">Yielded rent</th><th class="num">Yielded availability</th><th class="num">Blocked</th><th class="num">Nothing</th><th class="num">Rows</th><th class="num">Rent yield</th></tr></thead><tbody>';
  for(const x of p) h+=`<tr><td>${esc(x.platform)}</td><td class="num">${x.sites}</td>
    <td class="num">${x.with_rent}</td><td class="num">${x.with_avail}</td><td class="num">${x.blocked}</td>
    <td class="num">${x.nothing}</td><td class="num">${num(x.rows)}</td>
    <td class="num"><b>${x.usable_rate_pct}%</b></td></tr>`;
  h+='</tbody></table></div>';
  h+='<h2>Which extraction layer won</h2><div class="tblwrap"><table><thead><tr><th>Layer</th><th class="num">Sites</th></tr></thead><tbody>';
  for(const k of Object.keys(wl).sort((a,b)=>wl[b]-wl[a]))
    h+=`<tr><td>${esc(k)}</td><td class="num">${wl[k]}</td></tr>`;
  h+='</tbody></table></div><div class="foot">L1 = platform-specific JSON island (unit-level, highest confidence). L2 = generic framework/JSON island. L3 = schema.org JSON-LD walked recursively. L4 = rendered-HTML card parse (lowest confidence — not recommended as a production rent source). L5 = browser-rendered text, for hosts that refuse plain HTTP.</div>';
  $('#plat').innerHTML=h;
}

/* ---------------- terms ---------------- */
function drawTerms(){
  const t=REPORT.terms||{};
  let h='<div class="cards">';
  h+=`<div class="card"><div class="k">Sites checked</div><div class="v">${num(t.sites_checked)}</div></div>`;
  for(const [k,v] of Object.entries(t.verdicts||{}))
    h+=`<div class="card"><div class="k">${esc(k)}</div><div class="v">${v}</div></div>`;
  h+='</div>';
  if((t.prohibiting_sites||[]).length){
    h+='<h2>Sites dropped — terms prohibit automated access</h2>';
    for(const s of t.prohibiting_sites){
      h+=`<div class="card" style="margin-bottom:10px"><b>${esc(s.site)}</b>
        ${s.terms_url?` — <a href="${esc(s.terms_url)}" target="_blank" rel="noopener">terms document ↗</a>`:''}
        ${(s.snippets||[]).map(x=>`<div class="snip">${esc(x)}</div>`).join('')}</div>`;
    }
  }
  h+='<h2>Full per-site terms audit log</h2><div class="row"><label class="f">Filter<input id="t-q" oninput="drawTermRows()" placeholder="site or verdict…"></label></div><div class="tblwrap"><table id="t-tbl"></table></div>';
  h+='<div class="foot">This check runs on every collection pass, not once. Terms can be added at any time; a site that begins prohibiting automated access is dropped on the next run and the reason recorded here with a timestamp.</div>';
  $('#terms').innerHTML=h; drawTermRows();
}
function drawTermRows(){
  const q=($('#t-q')?.value||'').toLowerCase();
  const rows=TERMS.filter(t=>!q||[t.site,t.verdict,t.notes].join(' ').toLowerCase().includes(q))
    .sort((a,b)=>String(a.site).localeCompare(String(b.site)));
  let h='<thead><tr><th>Site</th><th>Verdict</th><th>Collect?</th><th>Terms doc</th><th>Found via</th><th class="num">Mentions</th><th>Checked at (UTC)</th><th>Notes</th></tr></thead><tbody>';
  for(const t of rows){
    h+=`<tr><td>${esc(t.site)}</td>
      <td><span class="pill ${t.verdict==='PROHIBITS'?'no':t.verdict==='SILENT'?'ok':'na'}">${esc(t.verdict)}</span></td>
      <td>${t.collect_allowed?'<span class="pill ok">yes</span>':'<span class="pill no">no</span>'}</td>
      <td class="small">${t.terms_url?`<a href="${esc(t.terms_url)}" target="_blank" rel="noopener">↗</a>`:'—'}</td>
      <td class="small muted">${esc(t.discovery)}</td><td class="num">${t.automation_mentions??'—'}</td>
      <td class="small muted">${esc((t.checked_at||'').slice(0,19))}</td>
      <td class="small muted">${esc((t.notes||'').slice(0,120))}</td></tr>`;
  }
  $('#t-tbl').innerHTML=h+'</tbody>';
}

boot();


/* ---------------- trends ---------------- */
async function drawTrends(){
  const ts = await fetch('/api/timeseries').then(r=>r.json()).catch(()=>({days:[],events:[]}));
  const el = $('#trends'); if(!el) return;
  if(!(ts.days||[]).length){ el.innerHTML='<p class="muted">No snapshots yet. Run <code>run_daily.py</code>.</p>'; return; }
  let h='<div class="cards">'+[
    ['Snapshots', num(ts.days.length), `${ts.days[0].date} → ${ts.days[ts.days.length-1].date}`],
    ['Latest listings', num(ts.days[ts.days.length-1].listings), ''],
    ['Latest median comparable', money(ts.days[ts.days.length-1].median_comparable_rent), 'high/med confidence'],
    ['Events recorded', num(ts.n_events||0), Object.entries(ts.event_counts||{}).map(([k,v])=>`${k}: ${v}`).join(' · ')],
  ].map(([k,v,n])=>`<div class="card"><div class="k">${k}</div><div class="v">${v}</div><div class="n">${esc(n)}</div></div>`).join('')+'</div>';

  h+='<h2>Daily market summary</h2><div class="tblwrap"><table><thead><tr><th>Date</th><th class="num">Listings observed</th><th class="num">Priced</th><th class="num">Median comparable rent</th></tr></thead><tbody>';
  for(const d of ts.days) h+=`<tr><td>${esc(d.date)}</td><td class="num">${num(d.listings)}</td><td class="num">${num(d.priced)}</td><td class="num">${money(d.median_comparable_rent)}</td></tr>`;
  h+='</tbody></table></div>';

  const ev=(ts.events||[]).slice().reverse().slice(0,400);
  if(ev.length){
    h+='<h2>Recent events</h2><div class="tblwrap"><table><thead><tr><th>Date</th><th>Event</th><th>Property</th><th>Unit / plan</th><th class="num">Detail</th></tr></thead><tbody>';
    for(const e of ev){
      const pill = e.event==='rent_change' ? (e.pct>0?'E':'A') : e.event==='listed' ? 'A' : 'C';
      const detail = e.event==='rent_change' ? `${money(e.from)} → ${money(e.to)} (${e.pct>0?'+':''}${e.pct}%)`
        : e.event==='listed' ? money(e.rent)
        : `last ${money(e.last_rent)} · listed ≥${e.days_observed_listed}d`;
      h+=`<tr><td>${esc(e.date)}</td><td><span class="pill ${pill}">${esc(e.event)}</span></td>
        <td>${esc(e.property||'—')}</td><td class="small muted">${esc((e.key||[]).slice(2).join(' '))}</td>
        <td class="num">${detail}</td></tr>`;
    }
    h+='</tbody></table></div>';
  }
  h+='<div class="foot">One observation per calendar day. "unlisted" means the listing disappeared from the source page — usually leased, but only the disappearance is observed. Rows from stale sources (e.g. browser-recovered pages not refreshed that day) are excluded rather than counted as stable.</div>';
  el.innerHTML=h;
}
