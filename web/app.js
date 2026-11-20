"use strict";
const $ = id => document.getElementById(id);
const scheduleRoot = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba";
const modelURL = "https://raw.githubusercontent.com/ej770/nba-game-predictor/web-data/season-picks.json";
const dateInEast = d => new Intl.DateTimeFormat("en-CA",{timeZone:"America/New_York",year:"numeric",month:"2-digit",day:"2-digit"}).format(d);
const day = $("day");
day.value = dateInEast(new Date());
let generation = 0, filter = "all", games = [], modelRows = {}, modelLoaded = false;
const schedules = new Map();
function node(tag, value, cls) {
  const el = document.createElement(tag);
  if (value != null) el.textContent = value;
  if (cls) el.className = cls;
  return el;
}
async function json(url) {
  const r = await fetch(url, {signal:AbortSignal.timeout(14000)});
  if (!r.ok) throw new Error("Feed unavailable");
  return r.json();
}
function estimate(awayFor, awayAgainst, homeFor, homeAgainst) {
  const away = (awayFor + homeAgainst) / 2 - 1.5;
  const home = (homeFor + awayAgainst) / 2 + 1.5;
  const z = (home-away)/12;
  const t = 1 / (1 + .2316419*Math.abs(z));
  const tail = Math.exp(-z*z/2)/Math.sqrt(2*Math.PI)*t*(.31938153+t*(-.356563782+t*(1.781477937+t*(-1.821255978+t*1.330274429))));
  return {away, home, p:z >= 0 ? 1-tail : tail};
}
function recent(team, year, tip) {
  const key = team.id + "/" + year;
  if (!schedules.has(key)) {
    const request = json(scheduleRoot+"/teams/"+encodeURIComponent(team.id)+"/schedule?season="+year+"&seasontype=2")
      .catch(error => { schedules.delete(key); throw error; });
    schedules.set(key, request);
  }
  return schedules.get(key).then(data => {
    const cutoff = Date.parse(tip);
    const events = (data.events || []).filter(e => {
      const c = e.competitions?.[0];
      return c?.status?.type?.completed && Date.parse(e.date) < cutoff && (!e.season?.type || e.season.type === 2);
    }).sort((a,b)=> Date.parse(b.date)-Date.parse(a.date));
    const pairs = [];
    for (const e of events) {
      const sides = e.competitions[0].competitors;
      const own = sides.find(s=>String(s.team.id)===String(team.id));
      const opp = sides.find(s=>String(s.team.id)!==String(team.id));
      const score = s => Number(s?.score?.value ?? s?.score?.displayValue ?? s?.score);
      const a = score(own), b = score(opp);
      if (a>0 && b>0) pairs.push([a,b]);
      if (pairs.length===10) break;
    }
    if (!pairs.length) return null;
    return [0,1].map(i=>pairs.reduce((total,p)=>total+p[i],0)/pairs.length);
  });
}
function render() {
  const board = $("games"); board.replaceChildren();
  const visible = games.filter(g => filter==="all" || (filter==="live" ? g.state==="in" : Number.isFinite(g.p) && Math.max(g.p,1-g.p)>=.70));
  if (!visible.length) {board.append(node("div", games.length ? "No games match this filter." : "No NBA games scheduled for this date.","empty"));return;}
  for (const g of visible) {
    const card=node("article",null,"card"), top=node("div",null,"cardtop");
    top.append(node("span",g.state==="in" ? "LIVE" : g.state==="post" ? "FINAL" : "MATCHUP"),node("span",g.detail));card.append(top);
    for(const [key,side] of [["away",g.away],["home",g.home]]) {
      const row=node("div",null,"team");
      if(side.team.logo?.startsWith("https://")) {const img=node("img");img.src=side.team.logo;img.alt="";img.loading="lazy";row.append(img);}
      row.append(node("span",side.team.shortDisplayName || side.team.displayName),node("strong",g.state==="pre" ? (g.est ? Math.round(g.est[key]) : "—") : side.score ?? "—"));card.append(row);
    }
    card.append(node("p",g.state==="pre" ? "Projected final score" : "Actual score","sub"));
    const box=node("div",null,"pick");
    if(Number.isFinite(g.p)) {
      const conf=Math.max(g.p,1-g.p);
      box.append(node("b",g.p===.5 ? "Even matchup" : (g.p>.5 ? g.home : g.away).team.abbreviation+" · "+(100*conf).toFixed(1)+"%"),node("div",g.source+" · pre-game","sub"));
      const bar=node("div",null,"track"), fill=node("i");fill.style.width=(100*conf)+"%";bar.append(fill);box.append(bar);
    } else box.append(node("span",g.loading ? "Loading prediction…" : "Pre-game prediction unavailable","sub"));
    if(g.est && g.state!=="pre") box.append(node("div","Projected score · "+Math.round(g.est.away)+" – "+Math.round(g.est.home),"sub"));
    card.append(box);board.append(card);
  }
}
async function loadBoard() {
  const run=++generation;
  const selected=day.value;
  if(!selected) return;
  $("status").textContent="Loading scoreboard…"; $("games").replaceChildren(); games=[];
  const model = modelLoaded ? Promise.resolve() : json(modelURL).then(data=>{modelRows=data;modelLoaded=true;}).catch(()=>{});
  try {
    const data=await json(scheduleRoot+"/scoreboard?dates="+selected.replaceAll("-",""));
    if(run!==generation) return;
    if(!Array.isArray(data.events)) throw new Error("Invalid scoreboard");
    const list=data.events.map(e=>{
      const c=e.competitions[0], status=c.status, state=status.type.state;
      return {id:e.id,year:e.season.year, regular:e.season.type===2,tip:e.date,state,
        detail:state==="pre" && status.type.name==="STATUS_SCHEDULED" ? new Date(e.date).toLocaleTimeString("en-US",{hour:"numeric",minute:"2-digit",timeZoneName:"short"}) : status.type.shortDetail,
        home:c.competitors.find(s=>s.homeAway==="home"),away:c.competitors.find(s=>s.homeAway==="away"),loading:true};
    }).filter(g=>g.home && g.away);
    games=list;render();
    $("status").textContent=list.length+" games · ESPN scoreboard · Updated "+new Date().toLocaleTimeString([],{hour:"numeric",minute:"2-digit"});
    await Promise.all(list.map(async g=>{
      if(g.regular) {
        const [stats] = await Promise.all([Promise.all([recent(g.away.team,g.year,g.tip),recent(g.home.team,g.year,g.tip)]).catch(()=>[]), model]);
        if(stats.length===2 && stats.every(Boolean)) g.est=estimate(...stats[0],...stats[1]);
        const original=modelRows[g.id];
        if(Number.isFinite(original)&&original>=0&&original<=1){g.p=original;g.source="Repository model";}
        else if(g.est){g.p=g.est.p;g.source="Score estimate";}
      }
      g.loading=false;if(run===generation)render();
    }));
  } catch(error) {
    if(run!==generation)return;
    $("status").textContent="ESPN scoreboard unavailable.";
    const msg=node("div","Refresh to retry the scoreboard, or explore a projection in the ","empty");
    const link=node("a","matchup lab");link.href="#lab";msg.append(link);$("games").replaceChildren(msg);
  }
}
function route() {
  const page=["board","lab","model"].includes(location.hash.slice(1)) ? location.hash.slice(1) : "board";
  for(const id of ["board","lab","model"]) $(id).hidden=id!==page;
  document.querySelectorAll("nav a").forEach(a=>{if(a.hash==="#"+page)a.setAttribute("aria-current","page");else a.removeAttribute("aria-current");});
}
function simulate(){
  const values=["af","aa","hf","ha"].map(id=>$(id).valueAsNumber);
  if(!$("sim").checkValidity()){$("out").textContent="Enter an average between 50 and 200 for each field.";return;}
  const result=estimate(...values);
  $("out").textContent="Away "+Math.round(result.away)+" · Home "+Math.round(result.home)+" | Home win "+(result.p*100).toFixed(1)+"%";
}
document.querySelectorAll("[data-filter]").forEach(b=>b.onclick=()=>{
  filter=b.dataset.filter;document.querySelectorAll("[data-filter]").forEach(x=>x.setAttribute("aria-pressed",String(x===b)));
  if(games.length)render();
});
$("refresh").onclick=()=>{schedules.clear();modelLoaded=false;loadBoard();};
day.onchange=loadBoard;$("sim").oninput=simulate;
window.addEventListener("hashchange",route);route();simulate();loadBoard();
setInterval(()=>{if(!document.hidden && !$("board").hidden && day.value===dateInEast(new Date()))loadBoard();},60000);
