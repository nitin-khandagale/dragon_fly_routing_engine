from __future__ import annotations
import json
from pathlib import Path

def generate_html(route_data, building_geojson_path: Path, output_path: Path, title="DragonFly Route"):
    buildings = json.loads(building_geojson_path.read_text(encoding="utf-8"))
    route_json = json.dumps(route_data)
    buildings_json = json.dumps(buildings)

    html = r'''<!doctype html>
<html><head><meta charset="utf-8"><title>__TITLE__</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
html,body{margin:0;height:100%;font-family:Arial,sans-serif;background:#f7f7f7}
#map{height:62vh;background:#fff;border-bottom:1px solid #ccc}
#panel{height:38vh;overflow:auto;padding:14px 18px;box-sizing:border-box}
.grid{display:grid;grid-template-columns:repeat(5,minmax(120px,1fr));gap:10px}
.card{border:1px solid #ddd;border-radius:6px;padding:10px;background:white}
.label{font-size:12px;color:#666}.value{font-size:18px;font-weight:600;margin-top:4px}
#profile{width:100%;height:180px;background:white}
@media(max-width:900px){.grid{grid-template-columns:repeat(2,1fr)}#map{height:55vh}#panel{height:45vh}}
</style></head><body>
<div id="map"><svg id="scene" width="100%" height="100%" viewBox="0 0 1000 600"
preserveAspectRatio="xMidYMid meet"></svg></div>
<div id="panel"><h2>DragonFly Route</h2>
<div class="grid" id="metrics"></div><h3>Altitude Profile</h3>
<canvas id="profile"></canvas></div>
<script>
const routeData=__ROUTE__, buildings=__BUILDINGS__, waypoints=routeData.waypoints||[];
const svg=document.getElementById('scene'),NS='http://www.w3.org/2000/svg';
function geomPoints(g){if(!g)return[];if(g.type==='Polygon')return g.coordinates.flat();if(g.type==='MultiPolygon')return g.coordinates.flat(2);return[]}
let all=[];
for(const f of (buildings.features||[]))all.push(...geomPoints(f.geometry));
for(const w of waypoints)all.push([w.longitude,w.latitude]);
let minX=Math.min(...all.map(p=>p[0])),maxX=Math.max(...all.map(p=>p[0])),
minY=Math.min(...all.map(p=>p[1])),maxY=Math.max(...all.map(p=>p[1]));
function project(p){const pad=35;return [
pad+(p[0]-minX)/(maxX-minX||1)*(1000-2*pad),
600-pad-(p[1]-minY)/(maxY-minY||1)*(600-2*pad)]}
function draw(){
while(svg.firstChild)svg.removeChild(svg.firstChild);
const bg=document.createElementNS(NS,'rect');bg.setAttribute('width',1000);bg.setAttribute('height',600);
bg.setAttribute('fill','#fafafa');svg.appendChild(bg);
for(const f of (buildings.features||[])){const pts=geomPoints(f.geometry);if(!pts.length)continue;
const poly=document.createElementNS(NS,'polygon');poly.setAttribute('points',pts.map(p=>project(p).join(',')).join(' '));
poly.setAttribute('fill','#b9b0c9');poly.setAttribute('fill-opacity','.65');poly.setAttribute('stroke','#7b6f88');
poly.addEventListener('click',()=>alert('Building\nHeight: '+((f.properties||{}).height??'unknown')+' m'));
svg.appendChild(poly)}
if(waypoints.length){const line=document.createElementNS(NS,'polyline');
line.setAttribute('points',waypoints.map(w=>project([w.longitude,w.latitude]).join(',')).join(' '));
line.setAttribute('fill','none');line.setAttribute('stroke','#e11');line.setAttribute('stroke-width','4');svg.appendChild(line);
for(const [w,c] of [[waypoints[0],'#1683ff'],[waypoints.at(-1),'#16a34a']]){
const [x,y]=project([w.longitude,w.latitude]);const dot=document.createElementNS(NS,'circle');
dot.setAttribute('cx',x);dot.setAttribute('cy',y);dot.setAttribute('r',7);dot.setAttribute('fill',c);svg.appendChild(dot)}}}
draw();

function hav(a,b){const R=6371000,p1=a.latitude*Math.PI/180,p2=b.latitude*Math.PI/180,
dp=(b.latitude-a.latitude)*Math.PI/180,dl=(b.longitude-a.longitude)*Math.PI/180,
x=Math.sin(dp/2)**2+Math.cos(p1)*Math.cos(p2)*Math.sin(dl/2)**2;
return 2*R*Math.atan2(Math.sqrt(x),Math.sqrt(1-x))}
let horizontal=0,climb=0,descent=0,d3=0;
for(let i=1;i<waypoints.length;i++){const a=waypoints[i-1],b=waypoints[i],h=hav(a,b),
dz=(b.altitude_meters||0)-(a.altitude_meters||0);horizontal+=h;d3+=Math.hypot(h,dz);
if(dz>0)climb+=dz;if(dz<0)descent-=dz}
const maxAlt=waypoints.length?Math.max(...waypoints.map(w=>Number(w.altitude_meters||0))):0;
document.getElementById('metrics').innerHTML=[
['Status',routeData.status||'unknown'],['Waypoints',waypoints.length],['Max altitude',maxAlt.toFixed(1)+' m'],
['Climb',climb.toFixed(1)+' m'],['Descent',descent.toFixed(1)+' m'],
['Horizontal distance',horizontal.toFixed(1)+' m'],['3D distance',d3.toFixed(1)+' m'],
['Energy','— (vehicle model pending)']].map(x=>'<div class="card"><div class="label">'+x[0]+
'</div><div class="value">'+x[1]+'</div></div>').join('');
const canvas=document.getElementById('profile'),ctx=canvas.getContext('2d');
function profile(){const d=devicePixelRatio||1,w=canvas.clientWidth,h=canvas.clientHeight,p=35;
canvas.width=w*d;canvas.height=h*d;ctx.setTransform(d,0,0,d,0,0);ctx.clearRect(0,0,w,h);
if(!waypoints.length)return;const maxY=Math.max(15,maxAlt),xs=(w-2*p)/Math.max(1,waypoints.length-1);
ctx.beginPath();waypoints.forEach((q,i)=>{const x=p+i*xs,y=h-p-(Number(q.altitude_meters||0)/maxY)*(h-2*p);i?ctx.lineTo(x,y):ctx.moveTo(x,y)});
ctx.stroke();ctx.fillText(maxY.toFixed(0)+' m',3,p);ctx.fillText('0 m',10,h-p)}
profile();addEventListener('resize',profile);
</script></body></html>'''
    html = html.replace("__TITLE__", title.replace("<","&lt;"))
    html = html.replace("__ROUTE__", route_json).replace("__BUILDINGS__", buildings_json)
    output_path.write_text(html, encoding="utf-8")
