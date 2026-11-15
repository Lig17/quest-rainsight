const $ = (selector) => document.querySelector(selector);
const state = {runId:null, locations:[], cityId:'chennai', compareA:'bengaluru', compareB:'chennai', threshold:10, selectedStep:null, timeline:null, city:null, map:null, layer:null};
const number = (value, digits=1) => Number(value).toLocaleString('en-IN',{maximumFractionDigits:digits,minimumFractionDigits:0});
const dateTime = (iso, options={}) => new Intl.DateTimeFormat('en-IN',{timeZone:'Asia/Kolkata',hour:'2-digit',minute:'2-digit',hour12:false,...options}).format(new Date(iso));
const fullDate = (iso) => new Intl.DateTimeFormat('en-IN',{timeZone:'UTC',weekday:'short',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(iso))+' UTC';
const localDay = (iso) => new Intl.DateTimeFormat('en-IN',{timeZone:'Asia/Kolkata',day:'numeric',month:'short'}).format(new Date(iso));
const localDateTime = (iso) => `${localDay(iso)}, ${dateTime(iso)}`;
async function api(path){
  if(state.runId&&!path.startsWith('/api/health')&&!path.startsWith('/api/runs'))path+=`${path.includes('?')?'&':'?'}run_id=${encodeURIComponent(state.runId)}`;
  for(let attempt=0;attempt<2;attempt++){
    let response;
    try{response=await fetch(path,{headers:{Accept:'application/json'}})}catch(error){if(attempt===0){await new Promise(resolve=>setTimeout(resolve,1000));continue}throw error}
    if(!response.ok){const body=await response.json().catch(()=>({detail:'Forecast service unavailable'}));if(response.status>=500&&attempt===0){await new Promise(resolve=>setTimeout(resolve,1000));continue}throw new Error(body.detail||`Request failed (${response.status})`)}
    return response.json();
  }
  throw new Error('Forecast service unavailable');
}
function setFreshness(freshness){const dot=$('.status-dot'),chip=$('#run-chip-text');if(freshness.expired){dot.className='status-dot error';chip.textContent='Forecast horizon ended';$('#freshness-label').textContent=`No future intervals · horizon ended ${fullDate(freshness.forecast_horizon_end)}`}else if(freshness.stale){dot.className='status-dot stale';chip.textContent='Stored run · stale';$('#freshness-label').textContent=`Last processed ${number(freshness.cache_age_hours,0)} h ago · run may be stale`}else{dot.className='status-dot';chip.textContent='Forecast data available';$('#freshness-label').textContent=`Processed ${number(freshness.cache_age_hours,0)} h ago · run age ${number(freshness.run_age_hours,0)} h`}}
function showError(message){const toast=$('#toast');toast.textContent=message;toast.classList.add('show');clearTimeout(showError.timer);showError.timer=setTimeout(()=>toast.classList.remove('show'),3800)}
function rainfallColor(value){if(value<.1)return '#cddfd9';if(value<1)return '#85cbb3';if(value<3)return '#45ad91';if(value<7)return '#e4bc62';if(value<15)return '#e8894c';return '#bd5144'}
function initMap(){if(!window.L){$('#map-loading').textContent='Map library did not load. Location and timeline data are still available.';return}state.map=L.map('map',{zoomControl:true,scrollWheelZoom:false,preferCanvas:true}).setView([22.8,79.1],4.5);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:10,attribution:'© OpenStreetMap contributors'}).addTo(state.map);state.layer=L.layerGroup().addTo(state.map);$('#map-loading').classList.add('hidden');$('#reset-map').addEventListener('click',()=>state.map.setView([22.8,79.1],4.5))}
function addSelectOptions(select, selected){select.innerHTML=state.locations.map(location=>`<option value="${location.id}">${location.name}</option>`).join('');select.value=selected}
function currentCity(){return state.locations.find(x=>x.id===state.cityId)}
function currentCityInterval(){return state.city?.intervals.find(x=>x.end_step===state.selectedStep)}
function renderTimeline(){
  if(!state.timeline)return;
  const citySeries=state.city?.intervals||[];
  $('#timeline').innerHTML=state.timeline.intervals.map(interval=>{
    const start=dateTime(interval.start_time), end=dateTime(interval.end_time);
    const startDay=localDay(interval.start_time), endDay=localDay(interval.end_time);
    const cityInterval=citySeries.find(x=>x.end_step===interval.end_step);
    const crossed=cityInterval?cityInterval.threshold_crossed:interval.threshold_crossed_somewhere;
    const phase=interval.phase||'upcoming';
    const phaseLabel=phase==='elapsed'?'Elapsed':phase==='in_progress'?'In progress':'Upcoming';
    const ariaPhase=phase==='in_progress'?'currently in progress, full-interval total':phaseLabel.toLowerCase();
    return `<button type="button" role="listitem" class="time-slot ${phase} ${interval.end_step===state.selectedStep?'selected':''} ${crossed?'crossed':''}" data-step="${interval.end_step}" ${phase==='elapsed'?'disabled':''} aria-disabled="${phase==='elapsed'}" aria-pressed="${interval.end_step===state.selectedStep}" aria-label="${ariaPhase}, ${localDateTime(interval.start_time)} to ${localDateTime(interval.end_time)} IST, ${cityInterval?.rainfall_mm??'map'} millimetres${crossed?', threshold reached':''}"><span class="time-time">${start}–${end}</span><span class="time-day">${phaseLabel} · ${startDay}${startDay===endDay?'':` → ${endDay}`} · IST</span><span class="time-amount">${cityInterval?number(cityInterval.rainfall_mm):number(interval.max_grid_mm)} <small>${cityInterval?'mm':'max mm'}</small></span></button>`;
  }).join('');
  $('#timeline').querySelectorAll('.time-slot:not(:disabled)').forEach(button=>button.addEventListener('click',()=>selectStep(Number(button.dataset.step))));
}
function renderCity(){
  const city=currentCity(), interval=currentCityInterval();
  if(!city||!interval)return;
  $('#city-amount').textContent=number(interval.rainfall_mm,2);
  $('#selected-interval-label').textContent=`${localDateTime(interval.start_time)}–${localDateTime(interval.end_time)} IST · ${city.name.toUpperCase()}`;
  $('#city-cumulative').textContent=`${number(interval.cumulative_mm,2)} mm across ${state.timeline.intervals.length*3} forecast hours`;
  $('#overview-city-value').textContent=`${number(interval.rainfall_mm,2)} mm`;
  $('#overview-city-foot').textContent=`${city.name} · ${localDateTime(interval.start_time)}–${localDateTime(interval.end_time)} IST`;
  $('#threshold-value').textContent=state.threshold;
  $('#threshold-slider').value=state.threshold;
  $('#threshold-copy').textContent=interval.threshold_crossed?`This interval meets your ${state.threshold} mm threshold at ${city.name}. A model estimate, not an official warning.`:`This interval is below your ${state.threshold} mm threshold at ${city.name}.`;
}
function renderRunDetail(provenance){$('#run-detail').innerHTML=`${provenance.model}<br>${provenance.resolution_degrees}° grid · ${provenance.grib_metadata.length} tp fields<br>Run ${provenance.run_id}<br>${provenance.grib_sha256.slice(0,16)}…`}
function renderMap(features){
  if(!state.map||!state.layer)return;
  state.layer.clearLayers();
  for(const feature of features){
    const [lon,lat]=feature.geometry.coordinates, mm=feature.properties.rainfall_mm;
    const marker=L.circleMarker([lat,lon],{radius:5,weight:.7,color:'#fff',fillColor:rainfallColor(mm),fillOpacity:.84,className:'rain-dot'});
    const title=$('#map-interval-title');
    marker.bindPopup(`<b>${number(mm,2)} mm</b><br>Interval rainfall<br><span>${localDateTime(title.dataset.start)}–${localDateTime(title.dataset.end)} IST</span>`);
    state.layer.addLayer(marker);
  }
}
async function loadCity(){
  const cityId=state.cityId,threshold=state.threshold,runId=state.runId;
  const data=await api(`/api/location/${cityId}?threshold_mm=${threshold}`);
  if(cityId!==state.cityId||threshold!==state.threshold||data.run_id!==runId)return;
  state.city=data;setFreshness(data.freshness);renderCity();renderTimeline();
}
async function loadTimeline(){
  const threshold=state.threshold,runId=state.runId;
  const data=await api(`/api/timeline?threshold_mm=${threshold}`);
  if(threshold!==state.threshold||data.run_id!==runId)return;
  state.timeline=data;
  const selectable=data.intervals.filter(x=>x.phase!=='elapsed');
  if(!selectable.length)throw new Error('Forecast horizon has ended; waiting for a current ECMWF run.');
  if(state.selectedStep==null||!selectable.some(x=>x.end_step===state.selectedStep))state.selectedStep=(selectable.find(x=>x.phase==='upcoming')||selectable[0]).end_step;
  $('#stat-horizon').textContent=`${data.intervals.length*3} h`;$('#run-init').textContent=fullDate(data.initialization);setFreshness(data.freshness);renderTimeline();
}
async function loadSpatial(){
  const endStep=state.selectedStep,runId=state.runId;
  const data=await api(`/api/spatial?end_step=${endStep}`);
  if(endStep!==state.selectedStep||data.end_step!==endStep||data.run_id!==runId)return;
  const interval=$('#map-interval-title');
  interval.dataset.start=data.start_time; interval.dataset.end=data.end_time;
  interval.textContent=`${localDateTime(data.start_time)}–${localDateTime(data.end_time)} IST`;
  renderMap(data.features);
}
async function selectStep(step){state.selectedStep=step;renderTimeline();try{await Promise.all([loadCity(),loadSpatial()])}catch(error){showError(error.message)}}
async function setCity(cityId){
  state.cityId=cityId;state.city=null;renderTimeline();
  $('#city-amount').textContent='—';$('#selected-interval-label').textContent=`Loading ${currentCity()?.name||'location'} forecast…`;
  $('#city-cumulative').textContent='Loading forecast data…';$('#threshold-copy').textContent='Updating the selected location forecast…';
  try{await loadCity()}catch(error){showError(error.message)}
}
async function loadProvenance(){const data=await api('/api/provenance');renderRunDetail(data);$('#provenance-json').textContent=JSON.stringify(data,null,2)}
function drawComparison(){const canvas=$('#compare-chart'),ctx=canvas.getContext('2d'),rect=canvas.getBoundingClientRect(),dpr=window.devicePixelRatio||1;if(!rect.width)return;canvas.width=rect.width*dpr;canvas.height=rect.height*dpr;ctx.scale(dpr,dpr);const w=rect.width,h=rect.height,p={l:39,r:14,t:12,b:32};const a=state.compareData?.a,b=state.compareData?.b;if(!a||!b)return;const values=[...a.intervals.map(x=>x.rainfall_mm),...b.intervals.map(x=>x.rainfall_mm)],max=Math.max(1,...values),xCount=a.intervals.length;ctx.font='9px DM Mono, monospace';ctx.textBaseline='middle';ctx.strokeStyle='#edf0f3';ctx.fillStyle='#8792a0';ctx.lineWidth=1;for(let i=0;i<=4;i++){const y=p.t+(h-p.t-p.b)*i/4;ctx.beginPath();ctx.moveTo(p.l,y);ctx.lineTo(w-p.r,y);ctx.stroke();ctx.textAlign='right';ctx.fillText(number(max*(1-i/4),1),p.l-7,y)}ctx.strokeStyle='#d9dfe5';ctx.beginPath();ctx.moveTo(p.l,p.t);ctx.lineTo(p.l,h-p.b);ctx.lineTo(w-p.r,h-p.b);ctx.stroke();for(let i=0;i<xCount;i++){const x=p.l+(w-p.l-p.r)*(i/(Math.max(1,xCount-1)));if(i%Math.max(1,Math.ceil(xCount/8))===0||i===xCount-1){ctx.fillStyle='#8994a2';ctx.textAlign='center';ctx.fillText(dateTime(a.intervals[i].end_time),x,h-p.b+17)}}[[a,'#16877e'],[b,'#d58c42']].forEach(([series,color])=>{ctx.strokeStyle=color;ctx.lineWidth=2;ctx.beginPath();series.intervals.forEach((point,i)=>{const x=p.l+(w-p.l-p.r)*(i/(Math.max(1,xCount-1))),y=p.t+(h-p.t-p.b)*(1-point.rainfall_mm/max);if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y)});ctx.stroke();series.intervals.forEach((point,i)=>{const x=p.l+(w-p.l-p.r)*(i/(Math.max(1,xCount-1))),y=p.t+(h-p.t-p.b)*(1-point.rainfall_mm/max);ctx.beginPath();ctx.arc(x,y,2.4,0,Math.PI*2);ctx.fillStyle=color;ctx.fill()})})}
async function loadComparison(){
  const compareA=state.compareA,compareB=state.compareB,runId=state.runId;
  try{
    const [a,b]=await Promise.all([api(`/api/location/${compareA}`),api(`/api/location/${compareB}`)]);
    if(compareA!==state.compareA||compareB!==state.compareB||a.run_id!==runId||b.run_id!==runId)return;
    state.compareData={a,b};$('#compare-a-name').textContent=a.location.name;$('#compare-b-name').textContent=b.location.name;
    $('#compare-a-total').textContent=`${number(a.interval_total_mm,2)} mm`;$('#compare-b-total').textContent=`${number(b.interval_total_mm,2)} mm`;drawComparison();
  }catch(error){showError(error.message)}
}
async function waitForForecast(){
  let lastError=new Error('Checking the current ECMWF forecast');
  for(let attempt=0;attempt<80;attempt++){
    try{
      const health=await api('/api/health');
      if(health.forecast_available)return health;
      lastError=new Error(health.detail||'Waiting for a current ECMWF run');
      $('#run-chip-text').textContent='Waiting for future intervals';
    }catch(error){
      lastError=error;
      $('#run-chip-text').textContent='Reconnecting to forecast service';
    }
    $('#freshness-label').textContent=lastError.message;
    $('#map-loading').textContent=`${lastError.message}. Checking again in 15 seconds.`;
    if(attempt<79)await new Promise(resolve=>setTimeout(resolve,15000));
  }
  throw lastError;
}
async function monitorForecast(){try{const health=await api('/api/health');if(health.forecast_available&&health.run_id!==state.runId){window.location.reload();return}if(!health.forecast_available){$('.status-dot').className='status-dot stale';$('#run-chip-text').textContent='Waiting for future intervals';$('#freshness-label').textContent=health.detail||'Waiting for the next ECMWF forecast run'}}catch(error){showError(error.message)}}
async function init(){try{initMap();const health=await waitForForecast();state.runId=health.run_id;const [locations,provenance]=await Promise.all([api('/api/locations'),api('/api/provenance')]);if(locations.run_id!==state.runId)throw new Error('Forecast run changed during startup; reload the page.');state.locations=locations.locations;addSelectOptions($('#city-select'),state.cityId);addSelectOptions($('#compare-a'),state.compareA);addSelectOptions($('#compare-b'),state.compareB);$('#compare-b').value=state.compareB;await loadTimeline();renderRunDetail(provenance);$('#provenance-json').textContent=JSON.stringify(provenance,null,2);await Promise.all([loadCity(),loadSpatial(),loadComparison()]);$('#city-select').addEventListener('change',event=>setCity(event.target.value));$('#compare-a').addEventListener('change',event=>{state.compareA=event.target.value;loadComparison()});$('#compare-b').addEventListener('change',event=>{state.compareB=event.target.value;loadComparison()});$('#threshold-slider').addEventListener('input',event=>{state.threshold=Number(event.target.value);$('#threshold-value').textContent=state.threshold});$('#threshold-slider').addEventListener('change',async()=>{await Promise.all([loadCity(),loadTimeline()]);renderTimeline()});window.addEventListener('resize',()=>drawComparison());const links=[...document.querySelectorAll('.nav-link')];const sections=links.map(link=>document.querySelector(link.getAttribute('href')));const observer=new IntersectionObserver(entries=>entries.forEach(entry=>{if(entry.isIntersecting){links.forEach(link=>link.classList.toggle('active',link.getAttribute('href')===`#${entry.target.id}`))}}),{rootMargin:'-20% 0px -70% 0px'});sections.filter(Boolean).forEach(section=>observer.observe(section));setInterval(monitorForecast,5*60*1000)}catch(error){$('.status-dot').className='status-dot error';$('#run-chip-text').textContent='Forecast unavailable';$('#map-loading').textContent=error.message;showError(error.message)}}
init();
