export const VERSION = '1.2.0';
export function normalizeRoute(points) {
  if (!Array.isArray(points) || points.length > 5000) throw Error('路线最多支持 5000 个点。');
  const result = [];
  for (const p of points) {
    const latitude = Number(p?.latitude), longitude = Number(p?.longitude);
    if (p?.latitude == null || p?.longitude == null || !Number.isFinite(latitude) || !Number.isFinite(longitude) || Math.abs(latitude)>85 || Math.abs(longitude)>180) throw Error('路线包含无效坐标。');
    const point = {latitude, longitude};
    if (!result.length || distance(result.at(-1), point) >= .1) result.push(point);
  }
  return result;
}
export function distance(a, b) {
  const rad = x=>x*Math.PI/180;
  const t = Math.sin(rad(b.latitude-a.latitude)/2)**2 + Math.cos(rad(a.latitude))*Math.cos(rad(b.latitude))*Math.sin(rad(b.longitude-a.longitude)/2)**2;
  return 6371000*2*Math.atan2(Math.sqrt(t), Math.sqrt(Math.max(0,1-t)));
}
export function routeDistance(points) {return points.slice(1).reduce((n,p,i)=>n+distance(points[i],p),0);}
export function validateRoute(points) {
  const clean = normalizeRoute(points), meters = routeDistance(clean);
  if (clean.length<2 || meters<5) throw Error('请绘制至少两个不同的点，路线长度至少 5 米。');
  if (meters>100000) throw Error('路线不能超过 100 公里。');
  return clean;
}
export function readRoute(data) {
  if (data?.coordinate_system !== 'WGS84') throw Error('仅支持明确标注 WGS84 的路线文件。');
  return {name:String(data.name || '导入路线').trim().slice(0,80), points:validateRoute(data.points)};
}
export function project(p, zoom) {
  const size=256*2**zoom, lat=p.latitude*Math.PI/180;
  return {x:(p.longitude+180)/360*size,y:(1-Math.log(Math.tan(lat)+1/Math.cos(lat))/Math.PI)/2*size};
}
export function unproject(p, zoom) {
  const size=256*2**zoom;
  return {longitude:p.x/size*360-180,latitude:Math.atan(Math.sinh(Math.PI*(1-2*p.y/size)))*180/Math.PI};
}
export function validateSettings(s) {
  const number=(key,min,max)=>{const x=Number(s[key]);if(!Number.isFinite(x)||x<min||x>max) throw Error(`参数 ${key} 不在有效范围内。`);return x;};
  number('pace',3,9); number('interval',1,60); number('days',1,31);
  if (!Number.isInteger(Number(s.days)) || !Number.isInteger(Number(s.interval))) throw Error('天数与采样间隔必须为整数。');
  number('paceMin',3,9);number('paceMax',3,9);
  if (Number(s.paceMin)>Number(s.paceMax)) throw Error('最小配速不能大于最大配速。');
  if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(s.time)) throw Error('请选择有效的出发时间。');
  const dates=[...new Set(String(s.dates||'').split(/[\s,，]+/).filter(Boolean))];
  if(s.dateMode==='dates') {
    if(!dates.length||dates.length>31) throw Error('请填写 1 至 31 个日期。');
    for(const date of dates) {
      if(!/^\d{4}-\d{2}-\d{2}$/.test(date)||Number.isNaN(Date.parse(date+'T00:00:00Z'))||new Date(date+'T00:00:00Z').toISOString().slice(0,10)!==date) throw Error(`日期无效：${date}`);
      const parts=new Intl.DateTimeFormat('en',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date()); const local=['year','month','day'].map(k=>parts.find(p=>p.type===k).value).join('-');
      if(date>local) throw Error('不能选择未来日期。');
    }
  }
  return {...s,pace:Number(s.pace),paceMin:Number(s.paceMin),paceMax:Number(s.paceMax),interval:Number(s.interval),days:Number(s.days),dates:dates.join(', ')};
}
export function toAppConfig(route, settings) {
  const points=validateRoute(route.points), s=validateSettings(settings), [h,m]=s.time.split(':').map(Number);
  return {'使用自定义路线':true,'自定义路线':points,'路线名称':route.name,'指定日期模式':s.dateMode==='dates','指定日期列表':s.dates.split(', ').filter(Boolean),'跑步天数':s.days,'参数随机':!!s.randomPace,'配速_分钟每公里':s.pace,'配速最小_分钟每公里':s.paceMin,'配速最大_分钟每公里':s.paceMax,'GPS采样间隔_秒':s.interval,'跑步时间随机':false,'固定跑步时间_时':h,'固定跑步时间_分':m,'起点纬度':points[0].latitude,'起点经度':points[0].longitude,'终点纬度':points.at(-1).latitude,'终点经度':points.at(-1).longitude};
}
export function xmlEscape(s) {return String(s).replace(/[<>&"']/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;',"'":'&apos;'}[c]));}
export function toGPX(route) {
  const points=validateRoute(route.points);
  return `<?xml version="1.0" encoding="UTF-8"?><gpx version="1.1" creator="SJTURunPlus Web" xmlns="http://www.topografix.com/GPX/1/1"><trk><name>${xmlEscape(route.name)}</name><trkseg>${points.map(p=>`<trkpt lat="${p.latitude}" lon="${p.longitude}"/>`).join('')}</trkseg></trk></gpx>`;
}
