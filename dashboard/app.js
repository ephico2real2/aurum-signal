const {useState,useEffect,useRef,useMemo,useCallback} = React;
const API = window.location.hostname==='localhost'?'http://localhost:7842':'';
const T={
  bg:'#060709',panel:'#0B0D14',card:'#0F1119',row:'#13151F',
  border:'#1A1E2E',border2:'#232840',
  gold:'#D4AF37',goldL:'#E8C84A',goldBg:'rgba(212,175,55,0.07)',goldBdr:'rgba(212,175,55,0.18)',
  green:'#10B981',greenBg:'rgba(16,185,129,0.08)',
  red:'#EF4444',redBg:'rgba(239,68,68,0.07)',
  amber:'#F59E0B',amberBg:'rgba(245,158,11,0.08)',
  blue:'#3B82F6',cyan:'#06B6D4',cyanBg:'rgba(6,182,212,0.07)',
  purple:'#A855F7',orange:'#F97316',teal:'#14B8A6',
  // textD = secondary labels on dark panels (must stay light enough vs bg/panel)
  text:'#8E9EB2',textB:'#B4C2D4',textBB:'#D8E4F0',textD:'#96A6BA',
  mono:"'Courier New',monospace",
};
const CC={BRIDGE:T.teal,LISTENER:T.orange,LENS:T.cyan,SENTINEL:T.red,
  AEGIS:T.green,FORGE:T.amber,SCRIBE:T.purple,HERALD:T.blue,AURUM:T.gold,SYSTEM:T.text};
const MODES=[{id:'OFF',color:T.textD,desc:'Dormant'},{id:'WATCH',color:T.blue,desc:'Data only'},
  {id:'SIGNAL',color:T.amber,desc:'Signals'},{id:'SCALPER',color:T.cyan,desc:'Self-scalp'},
  {id:'HYBRID',color:T.gold,desc:'Both active'},{id:'AUTO_SCALPER',color:T.green,desc:'AURUM auto'}];
// Must match athena_api /api/live performance + /api/pnl_curve polling below
const PERF_ROLLING_DAYS=7;

function fmtAgeSec(sec){
  if(sec==null||sec===undefined||Number.isNaN(Number(sec)))return'—';
  const s=Number(sec);
  if(s<90)return`${Math.round(s)}s`;
  if(s<3600)return`${(s/60).toFixed(1)}m`;
  if(s<86400)return`${(s/3600).toFixed(1)}h`;
  return`${(s/86400).toFixed(1)}d`;
}

function fmtDateTime(ts){
  if(!ts)return'—';
  try{
    const d=new Date(ts);
    if(Number.isNaN(d.getTime()))throw new Error('bad date');
    const y=d.getFullYear();
    const m=String(d.getMonth()+1).padStart(2,'0');
    const day=String(d.getDate()).padStart(2,'0');
    const hh=String(d.getHours()).padStart(2,'0');
    const mm=String(d.getMinutes()).padStart(2,'0');
    const ss=String(d.getSeconds()).padStart(2,'0');
    return`${y}-${m}-${day} ${hh}:${mm}:${ss}`;
  }catch(e){
    return String(ts).replace('T',' ').slice(0,19);
  }
}

const Dot=({ok,sz=6,b=false})=>(<div className={b&&ok?'blink':''}
  style={{width:sz,height:sz,borderRadius:'50%',flexShrink:0,
    background:ok?T.green:T.red,boxShadow:`0 0 ${sz+2}px ${ok?T.green:T.red}55`}}/>);
const Tag=({lbl,color,xs=false})=>(<span style={{fontSize:9,fontFamily:T.mono,
  letterSpacing:1,border:`1px solid ${color}`,color,
  padding:xs?'0 3px':'1px 5px',borderRadius:2,whiteSpace:'nowrap'}}>{lbl}</span>);
const PT=({ch,color=T.gold,right})=>(<div style={{fontSize:9,fontFamily:T.mono,
  letterSpacing:2.5,color,textTransform:'uppercase',marginBottom:8,paddingBottom:5,
  borderBottom:`1px solid ${T.border}`,display:'flex',
  justifyContent:'space-between',alignItems:'center',fontWeight:600}}>
  <span>{ch}</span>{right}</div>);
const Sparkline=({data,w=160,h=32,color=T.green})=>{
  if(!data||data.length<2)return null;
  const mx=Math.max(...data),mn=Math.min(...data),r=mx-mn||1;
  const pts=data.map((v,i)=>`${(i/(data.length-1))*w},${h-((v-mn)/r)*(h-4)-2}`).join(' ');
  return(<svg width={w} height={h} style={{overflow:'visible'}}>
    <defs><linearGradient id="sg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stopColor={color} stopOpacity=".25"/>
      <stop offset="100%" stopColor={color} stopOpacity="0"/>
    </linearGradient></defs>
    <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round"/>
    <polygon points={`0,${h} ${pts} ${w},${h}`} fill="url(#sg)"/>
  </svg>);
};

/** SENTINEL RSS buckets from /api/live → sentinel.news_feeds (see docs/SENTINEL.md) */
function SentinelHeadlines({newsFeeds}){
  const nf=newsFeeds&&typeof newsFeeds==='object'?newsFeeds:{};
  const order=['fxstreet','google_news','investing_forex','dailyfx','extra'];
  const labels={fxstreet:'FXStreet',google_news:'Google',investing_forex:'Investing',dailyfx:'DailyFX',extra:'Extra'};
  const rows=[];
  for(const k of order){
    const arr=Array.isArray(nf[k])?nf[k]:[];
    for(const it of arr){
      if(it&&String(it.title||'').trim())
        rows.push({title:it.title,link:it.link||'',source:labels[k]||k});
    }
  }
  const err=nf.errors;
  const hasErr=Array.isArray(err)&&err.length>0;
  if(!rows.length){
    return(
      <div style={{marginTop:8}}>
        <div style={{fontSize:9,color:T.textD,fontFamily:T.mono,letterSpacing:1,marginBottom:3}}>
          HEADLINES
        </div>
        <div style={{fontSize:9,color:T.textD,fontFamily:T.mono,lineHeight:1.4,padding:'6px 0'}}>
          {hasErr?`RSS error: ${String(err[0]).slice(0,120)}`:'No headlines yet — wait for BRIDGE SENTINEL tick (~60s) or check docs/SENTINEL.md'}
        </div>
      </div>
    );
  }
  const cap=24,show=rows.slice(0,cap);
  return(
    <div style={{marginTop:8}}>
      <div style={{fontSize:9,color:T.textD,fontFamily:T.mono,letterSpacing:1,marginBottom:4,
        display:'flex',justifyContent:'space-between',alignItems:'baseline',gap:6}}>
        <span>HEADLINES</span>
        <span style={{color:T.textD}}>{rows.length}{rows.length>cap?` · top ${cap}`:''}</span>
      </div>
      <div style={{maxHeight:168,overflowY:'auto',overscrollBehavior:'contain',
        border:`1px solid ${T.border2}`,borderRadius:4,background:T.row,padding:'5px 7px'}}>
        {show.map((it,i)=>(
          <div key={i} style={{marginBottom:7,paddingBottom:6,
            borderBottom:i<show.length-1?`1px solid ${T.border}`:'none'}}>
            <div style={{fontSize:9,color:T.cyan,fontFamily:T.mono,marginBottom:2}}>{it.source}</div>
            {it.link?(
              <a href={it.link} target="_blank" rel="noopener noreferrer"
                style={{fontSize:9,color:T.textB,textDecoration:'none',lineHeight:1.35,wordBreak:'break-word',
                  display:'block'}}>
                {it.title.length>160?`${it.title.slice(0,157)}…`:it.title}
              </a>
            ):(
              <span style={{fontSize:9,color:T.text,lineHeight:1.35}}>{it.title}</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

const ACTIVITY_CATS=['ALL','MODE','TRADE','RISK','AURUM','SYSTEM'];
const ACTIVITY_CAT_COLOR={MODE:T.blue,TRADE:T.green,RISK:T.red,AURUM:T.gold,SYSTEM:T.text};

function activityComponent(raw){
  if(raw&&raw.triggered_by) return String(raw.triggered_by).toUpperCase();
  const et=String((raw&&raw.event_type)||'SYSTEM');
  return et.split('_')[0];
}
function activityCategory(eventType){
  const t=String(eventType||'');
  if(/^(MODE_|SESSION_|STARTUP|SHUTDOWN)/i.test(t)) return 'MODE';
  if(/CIRCUIT|NEWS_GUARD/i.test(t)) return 'RISK';
  if(/^AURUM_/.test(t)) return 'AURUM';
  if(/TRADE_|SIGNAL_|CLOSE_ALL|POSITION_/.test(t)) return 'TRADE';
  return 'SYSTEM';
}
function activityLevelForEvent(eventType){
  const t=String(eventType||'').toUpperCase();
  if(t.includes('ERROR')) return 'ERROR';
  if(t==='CIRCUIT_BREAKER_ON') return 'ERROR';
  if(t==='SHUTDOWN') return 'WARN';
  if(/REJECT|INVALID|SKIPPED|WARN/.test(t)) return 'WARN';
  return 'INFO';
}
function formatActivityMessage(raw){
  const parts=[];
  if(raw.event_type) parts.push(raw.event_type);
  if(raw.prev_mode||raw.new_mode){
    const m=[raw.prev_mode,raw.new_mode].filter(Boolean);
    if(m.length) parts.push(m.join('→'));
  }
  if(raw.reason) parts.push(raw.reason);
  if(raw.session&&String(raw.event_type||'').indexOf('SESSION')<0)
    parts.push(`sess ${raw.session}`);
  if(raw.notes){
    let n=String(raw.notes);
    if(n.length>160) n=n.slice(0,157)+'…';
    parts.push(n);
  }
  return parts.join(' · ')||'—';
}
function normalizeActivityEvent(e,idx){
  const id=e.id!=null?e.id:`row-${idx}-${e.timestamp||idx}`;
  const t=fmtDateTime(e.timestamp);
  const comp=activityComponent(e);
  const cat=activityCategory(e.event_type);
  const level=activityLevelForEvent(e.event_type);
  const msg=formatActivityMessage(e);
  return {id,t,comp,cat,level,msg,raw:e};
}

function activityLevelColor(l){
  return l==='WARN'?T.amber:l==='ERROR'?T.red:T.textD;
}

function isUploadEvent(raw){
  const et=String((raw&&raw.event_type)||'').toUpperCase();
  return et.includes('_UPLOAD_')||et.startsWith('SIGNAL_CHART_');
}

function ActivityCategoryChips({catf,setCatf}){
  return(
    <div style={{display:'flex',gap:3,flexWrap:'wrap',alignItems:'center'}}>
      {ACTIVITY_CATS.map(c=>{
        const on=catf===c;
        const col=c==='ALL'?T.gold:ACTIVITY_CAT_COLOR[c]||T.text;
        return(
          <button key={c} type="button" onClick={()=>setCatf(c)}
            style={{fontSize:9,fontFamily:T.mono,letterSpacing:1,
              background:on?`${col}22`:'transparent',
              border:`1px solid ${on?col:T.border}`,
              color:on?col:T.text,
              padding:'2px 6px',borderRadius:3,cursor:'pointer'}}>{c}</button>
        );
      })}
    </div>
  );
}

function ActivityEventRow({e,sel,setSel,isRecent}){
  const cc=CC[e.comp]||T.text;
  const catc=ACTIVITY_CAT_COLOR[e.cat]||T.text;
  const isSel=sel===e.id;
  const lc=activityLevelColor(e.level);
  return(
    <div onClick={()=>setSel(isSel?null:e.id)}
      className={isRecent?'slide':''}
      style={{display:'flex',alignItems:'center',gap:0,
        borderBottom:`1px solid ${T.border}`,cursor:'pointer',
        background:isSel?`${cc}08`:e.level==='WARN'?'rgba(245,158,11,0.04)':
          e.level==='ERROR'?'rgba(239,68,68,0.04)':'transparent',
        borderLeft:`2px solid ${e.level==='WARN'?T.amber:e.level==='ERROR'?T.red:cc}`,
        transition:'background 0.1s'}}>
      <span style={{fontFamily:T.mono,fontSize:9,color:T.textD,
        padding:'5px 7px',flexShrink:0,width:132}}>{e.t}</span>
      <span style={{fontFamily:T.mono,fontSize:9,color:cc,
        fontWeight:700,letterSpacing:1,width:56,flexShrink:0}}>{e.comp}</span>
      <span style={{fontFamily:T.mono,fontSize:9,color:catc,
        width:44,flexShrink:0,textAlign:'center',letterSpacing:0.5}}>{e.cat}</span>
      <span style={{fontFamily:T.mono,fontSize:9,color:lc,
        width:36,flexShrink:0}}>{e.level}</span>
      <span style={{fontSize:10,flex:1,padding:'5px 8px',lineHeight:1.4,
        color:e.level==='WARN'?T.amber:e.level==='ERROR'?T.red:T.textB}}>
        {e.msg}
      </span>
    </div>
  );
}

// ── ACTIVITY LOG ───────────────────────────────────────────────────
function ActivityLog({events=[], components=[]}){
  const [cf,setCf]=useState('ALL');
  const [catf,setCatf]=useState('ALL');
  const [lf,setLf]=useState('ALL');
  const [search,setSearch]=useState('');
  const [paused,setPaused]=useState(false);
  const [sel,setSel]=useState(null);
  const scrollRef=useRef(null);
  const atBottomRef=useRef(true);
  const q=search.trim().toLowerCase();
  const filtered=useMemo(()=>events.filter(e=>{
    if(cf!=='ALL'&&e.comp!==cf)return false;
    if(catf!=='ALL'&&e.cat!==catf)return false;
    if(lf!=='ALL'&&e.level!==lf)return false;
    if(q){
      const et=String(e.raw&&e.raw.event_type||'').toLowerCase();
      const blob=(e.msg+' '+e.comp+' '+e.cat+' '+et).toLowerCase();
      if(!blob.includes(q)) return false;
    }
    return true;
  }),[events,cf,catf,lf,q]);
  /** Oldest first, newest last — matches terminal / chat; live tail stays at bottom. */
  const displayList=useMemo(()=>{
    const a=[...filtered];
    a.reverse();
    return a;
  },[filtered]);
  const onActivityScroll=()=>{
    const el=scrollRef.current;
    if(!el)return;
    const gap=el.scrollHeight-el.scrollTop-el.clientHeight;
    atBottomRef.current=gap<100;
  };
  useEffect(()=>{
    if(paused)return;
    const el=scrollRef.current;
    if(!el||!atBottomRef.current)return;
    requestAnimationFrame(()=>{
      const box=scrollRef.current;
      if(box)box.scrollTop=box.scrollHeight;
    });
  },[displayList,paused]);
  const lc=(l)=>activityLevelColor(l);
  const warns=events.filter(e=>e.level==='WARN').length;
  const errs=events.filter(e=>e.level==='ERROR').length;
  const exportHref=`${API}/api/events/export?limit=10000`;
  return(
    <div style={{display:'flex',flexDirection:'column',height:'100%'}}>
      {/* Component strip */}
      <div style={{display:'flex',borderBottom:`1px solid ${T.border}`,
        flexShrink:0,overflowX:'auto',background:T.panel}}>
        {['ALL',...(components.map(c=>c.name))].map(name=>{
          const comp=components.find(c=>c.name===name);
          const color=CC[name]||T.text;
          return(
          <div key={name} onClick={()=>setCf(cf===name?'ALL':name)}
            style={{padding:'5px 8px',cursor:'pointer',flexShrink:0,
              background:cf===name?`${color}11`:'transparent',
              borderBottom:cf===name?`2px solid ${color}`:'2px solid transparent',
              display:'flex',flexDirection:'column',alignItems:'center',gap:2,minWidth:58}}>
            <div style={{display:'flex',alignItems:'center',gap:3}}>
              <Dot ok={comp?.ok??true} sz={4}/>
              <span style={{fontFamily:T.mono,fontSize:9,
                color:cf===name?color:T.text,letterSpacing:1}}>{name}</span>
            </div>
            <span style={{fontSize:9,color:T.textD,fontFamily:T.mono}}>
              {fmtDateTime(comp?.timestamp)}
            </span>
          </div>
          );
        })}
      </div>
      {/* Filter bar */}
      <div style={{display:'flex',flexDirection:'column',gap:6,padding:'6px 10px',
        borderBottom:`1px solid ${T.border}`,flexShrink:0,background:T.panel}}>
        <div style={{display:'flex',gap:8,alignItems:'center',flexWrap:'wrap'}}>
          <input value={search} onChange={e=>setSearch(e.target.value)}
            placeholder="Search…"
            style={{background:T.row,border:`1px solid ${T.border2}`,color:T.textB,
              padding:'3px 8px',borderRadius:4,fontSize:9,fontFamily:T.mono,width:150}}/>
          <div style={{display:'flex',gap:3}}>
            {['ALL','INFO','WARN','ERROR'].map(l=>(
              <button key={l} type="button" onClick={()=>setLf(l)} style={{fontSize:9,fontFamily:T.mono,
                letterSpacing:1,
                background:lf===l?(l==='WARN'?T.amberBg:l==='ERROR'?T.redBg:T.goldBg):'transparent',
                border:`1px solid ${lf===l?(l==='WARN'?T.amber:l==='ERROR'?T.red:T.gold):T.border}`,
                color:lf===l?(l==='WARN'?T.amber:l==='ERROR'?T.red:T.gold):T.text,
                padding:'2px 6px',borderRadius:3,cursor:'pointer'}}>{l}</button>
            ))}
          </div>
          <div style={{marginLeft:'auto',display:'flex',gap:8,alignItems:'center',flexWrap:'wrap'}}>
            <a href={exportHref} download="system_events.ndjson"
              style={{fontSize:9,fontFamily:T.mono,letterSpacing:1,color:T.cyan,
                border:`1px solid ${T.cyan}`,padding:'2px 6px',borderRadius:3,
                textDecoration:'none'}}>EXPORT NDJSON</a>
            <span style={{fontSize:9,color:T.textD,fontFamily:T.mono}}>
              {filtered.length} events
              {warns>0&&<span style={{color:T.amber}}> · {warns}⚠</span>}
              {errs>0&&<span style={{color:T.red}}> · {errs}✕</span>}
            </span>
            <button type="button" onClick={()=>setPaused(p=>!p)} style={{fontSize:9,fontFamily:T.mono,
              background:paused?T.amberBg:'transparent',
              border:`1px solid ${paused?T.amber:T.border}`,
              color:paused?T.amber:T.text,
              padding:'2px 6px',borderRadius:3,cursor:'pointer'}}>
              {paused?'▶ RESUME':'⏸ PAUSE'}
            </button>
          </div>
        </div>
        <ActivityCategoryChips catf={catf} setCatf={setCatf}/>
      </div>
      {/* Events: chronological (oldest → top, newest → bottom). Auto-scroll only while pinned to bottom. */}
      <div ref={scrollRef} onScroll={onActivityScroll}
        style={{flex:1,overflowY:'auto',minHeight:0,overscrollBehavior:'contain'}}>
        {displayList.map((e,idx)=>(
          <ActivityEventRow key={e.id} e={e} sel={sel} setSel={setSel}
            isRecent={idx>=displayList.length-3}/>
        ))}
        {displayList.length===0&&(
          <div style={{textAlign:'center',padding:40,fontSize:10,
            color:T.textD,fontFamily:T.mono}}>No events match filter</div>
        )}
      </div>
      {/* Selected detail */}
      {sel&&(()=>{const e=events.find(x=>x.id===sel);if(!e)return null;
        const cc=CC[e.comp]||T.text;
        const catc=ACTIVITY_CAT_COLOR[e.cat]||T.text;
        return(<div style={{flexShrink:0,borderTop:`1px solid ${T.border}`,
          padding:'8px 12px',background:T.panel,
          display:'flex',gap:12,alignItems:'flex-start'}}>
          <div style={{display:'flex',flexDirection:'column',gap:3,flexShrink:0}}>
            <Tag lbl={e.comp} color={cc}/>
            <Tag lbl={e.cat} color={catc} xs/>
            <Tag lbl={e.level} color={lc(e.level)||T.textD} xs/>
            <span style={{fontSize:9,color:T.textD,fontFamily:T.mono}}>{e.t}</span>
          </div>
          <div style={{flex:1,minWidth:0}}>
            <div style={{fontSize:10,color:T.textBB,lineHeight:1.6,fontFamily:T.mono,
              marginBottom:6}}>{e.msg}</div>
            <pre style={{fontSize:9,fontFamily:T.mono,color:T.textD,margin:0,
              padding:8,background:T.row,border:`1px solid ${T.border2}`,borderRadius:4,
              overflow:'auto',maxHeight:140,whiteSpace:'pre-wrap',wordBreak:'break-word'}}>
              {JSON.stringify(e.raw,null,2)}
            </pre>
          </div>
          <button type="button" onClick={()=>setSel(null)} style={{background:'transparent',border:'none',
            color:T.textD,cursor:'pointer',fontSize:14}}>✕</button>
        </div>);
      })()}
      {/* Footer */}
      <div style={{flexShrink:0,borderTop:`1px solid ${T.border}`,padding:'4px 12px',
        background:T.panel,display:'flex',justifyContent:'space-between',flexWrap:'wrap',gap:6}}>
        <div style={{display:'flex',alignItems:'center',gap:5}}>
          <Dot ok={true} sz={4} b={!paused}/>
          <span style={{fontSize:9,color:T.textD,fontFamily:T.mono}}>
            {paused?'PAUSED':'LIVE — SCRIBE system_events; disk audit logs/audit/system_events.jsonl'}
          </span>
        </div>
        <span style={{fontSize:9,color:T.textD,fontFamily:T.mono}}>Click row for JSON detail</span>
      </div>
    </div>
  );
}

// ── AURUM CHAT ─────────────────────────────────────────────────────
const SOUL="You are AURUM — the AI intelligence layer of a XAUUSD scalping system. Be concise (2-4 sentences), use numbers, lead with the answer. Never use filler phrases.";
function aurumWelcome(d){
  if(!d||d.mode==='DISCONNECTED')
    return 'AURUM online — waiting for live data from ATHENA (/api/live).';
  const a=d.account||{};
  const bal=a.balance!=null
    ? `$${Number(a.balance).toLocaleString('en',{minimumFractionDigits:2,maximumFractionDigits:2})}`
    : '—';
  const pos=a.open_positions_count!=null?String(a.open_positions_count):'—';
  const ex=d.execution||{};
  let q='';
  if(ex.usable&&ex.bid!=null&&ex.ask!=null)
    q=`MT5 ${Number(ex.bid).toFixed(2)} / ${Number(ex.ask).toFixed(2)}`;
  else if(ex.stale_reason)
    q='MT5 quote stale — check FORGE';
  else
    q='MT5 —';
  return `AURUM online · ${d.mode||'—'} · Balance ${bal} · ${pos} open · ${q}. What do you need?`;
}
function AurumChat({liveData}){
  const [msgs,setMsgs]=useState([]);
  const [inp,setInp]=useState('');const [loading,setLoading]=useState(false);
  const ref=useRef(null);const taRef=useRef(null);
  // Set welcome message once real data arrives (skip DISCONNECTED fallback)
  const welcomeSet=useRef(false);
  useEffect(()=>{
    if(!liveData)return;
    if(liveData.mode==='DISCONNECTED')return;  // wait for real data
    if(welcomeSet.current)return;
    setMsgs([{role:'assistant',text:aurumWelcome(liveData)}]);
    welcomeSet.current=true;
  },[liveData]);
  // Only scroll when USER sends a message or AURUM replies (not on data poll)
  const lastMsgCount=useRef(0);
  useEffect(()=>{
    if(msgs.length>lastMsgCount.current&&msgs.length>1){
      ref.current?.scrollIntoView({behavior:'smooth'});}
    lastMsgCount.current=msgs.length;
  },[msgs]);
  const ctx=()=>{if(!liveData)return'No live data.';
    const a=liveData.account||{},s=liveData.sentinel||{},p=liveData.performance||{};
    const ex=liveData.execution||{},tv=liveData.tradingview||{};
    const sess=liveData.session_utc||liveData.session||'—';
    const tvRef=tv.last!=null?Number(tv.last).toFixed(2):'—';
    const tvAge=tv.age_seconds!=null?fmtAgeSec(tv.age_seconds):'—';
    const mid=ex.usable&&ex.mid!=null?Number(ex.mid).toFixed(2):'—';
    const q=ex.usable?`MT5 ${ex.symbol||'XAUUSD'} bid/ask ${ex.bid}/${ex.ask} mid ${mid}`
      :`MT5 quote stale (${fmtAgeSec(ex.age_sec)}) — TV chart last $${tvRef} not verified as broker gold`;
    const wr=p.win_rate==null||p.total===0?'—':`${p.win_rate}%`;
    return`Mode:${liveData.mode} Session(UTC kill zones):${sess} Balance:$${a.balance?.toFixed(2)} SessionPnL:$${a.session_pnl?.toFixed(2)} Positions:${a.open_positions_count}\n${q}\nLENS (TV): RSI ${tv.rsi?.toFixed?.(1)??'—'} BB ${tv.bb_rating??'—'} ADX ${tv.adx?.toFixed?.(1)??'—'} snapshot age ${tvAge}\nSentinel:${s.active?'ACTIVE':'Clear'} Next:${s.next_event} in ${s.next_in_min}min\nSCRIBE ${PERF_ROLLING_DAYS}d (closed): PnL $${(p.total_pnl??0).toFixed(2)} WR:${wr} Trades:${p.total??0}`;};
  const send=async()=>{
    const text=inp.trim();if(!text||loading)return;
    setInp('');if(taRef.current)taRef.current.style.height='auto';
    const nm=[...msgs,{role:'user',text}];setMsgs(nm);setLoading(true);
    // ALWAYS route through ATHENA backend — never call Anthropic from the browser.
    // The backend is what writes aurum_cmd.json and triggers ANALYSIS_RUN / OPEN_GROUP / etc.
    // Bypassing it produces a chat reply that never reaches BRIDGE.
    try{
      const r=await fetch(`${API}/api/aurum/ask`,{method:'POST',
        headers:{'Content-Type':'application/json'},body:JSON.stringify({query:text})});
      if(!r.ok){
        const errBody=await r.text().catch(()=> '');
        throw new Error(`backend HTTP ${r.status}${errBody?` — ${errBody.slice(0,200)}`:''}`);
      }
      const d=await r.json();
      const reply=d.response||'(empty AURUM response)';
      setMsgs(p=>[...p,{role:'assistant',text:reply}]);
    }catch(e){
      setMsgs(p=>[...p,{role:'assistant',text:`AURUM backend unreachable — ${e.message}. Verify ATHENA at ${API}/api/health.`}]);
    }
    finally{setLoading(false);}
  };
  return(<div style={{display:'flex',flexDirection:'column',height:'100%',gap:6}}>
    <PT ch="⚡ AURUM · Telegram + Dashboard" color={T.gold}/>
    <div style={{display:'flex',flexWrap:'wrap',gap:4,marginBottom:2}}>
      {["P&L today?","Open groups?","LENS reading?","All clear?"].map(q=>(
        <button key={q} onClick={()=>setInp(q)} style={{fontSize:9,fontFamily:T.mono,
          background:T.goldBg,border:`1px solid ${T.goldBdr}`,color:T.gold,
          padding:'2px 6px',borderRadius:3,cursor:'pointer'}}>{q}</button>
      ))}
    </div>
    <div style={{flex:1,overflowY:'auto',display:'flex',flexDirection:'column',gap:5,minHeight:0}}>
      {msgs.map((m,i)=>(
        <div key={i} className="fade" style={{alignSelf:m.role==='user'?'flex-end':'flex-start',maxWidth:'92%'}}>
          <div style={{fontSize:10,lineHeight:1.6,
            background:m.role==='user'?T.goldBg:T.row,
            border:`1px solid ${m.role==='user'?T.goldBdr:T.border}`,
            color:m.role==='user'?T.goldL:T.textBB,
            padding:'5px 9px',borderRadius:5,
            fontFamily:m.role==='user'?T.mono:'Georgia,serif'}}>
            {m.role==='assistant'&&<span style={{color:T.gold,fontFamily:T.mono,
              fontSize:9,marginRight:5,letterSpacing:1}}>AURUM ◆</span>}
            {m.text}
          </div>
        </div>
      ))}
      {loading&&<div className="blink" style={{alignSelf:'flex-start',fontSize:10,
        color:T.gold,fontFamily:T.mono,background:T.row,border:`1px solid ${T.border}`,
        padding:'5px 9px',borderRadius:5}}>AURUM ◆ thinking…</div>}
      <div ref={ref}/>
    </div>
    <div style={{display:'flex',gap:5,alignItems:'flex-end'}}>
      <textarea ref={taRef} value={inp} onChange={e=>{setInp(e.target.value);e.target.style.height='auto';e.target.style.height=Math.min(e.target.scrollHeight,120)+'px';}}
        onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send();}}}
        placeholder="Ask AURUM anything…"
        rows={1}
        style={{flex:1,background:T.row,border:`1px solid ${T.border2}`,
          borderRadius:4,padding:'5px 8px',color:T.textBB,fontSize:10,fontFamily:T.mono,
          resize:'none',overflow:'hidden',lineHeight:1.5,minHeight:24,maxHeight:120}}/>
      <button onClick={send} disabled={loading} style={{background:T.goldBg,
        border:`1px solid ${T.goldBdr}`,color:T.gold,padding:'5px 10px',
        borderRadius:4,cursor:loading?'not-allowed':'pointer',
        fontFamily:T.mono,fontSize:9,alignSelf:'flex-end'}}>{loading?'…':'SEND'}</button>
    </div>
    <div style={{fontSize:9,color:T.textD,fontFamily:T.mono,textAlign:'center'}}>
      Also on Telegram — same AURUM, same live context
    </div>
  </div>);
}

// ── MAIN ───────────────────────────────────────────────────────────
function ATHENA(){
  const [data,setData]=useState(null);
  const [tab,setTab]=useState('groups');
  const [mode,setMode]=useState('HYBRID');
  const [connected,setConnected]=useState(false);
  const [tick,setTick]=useState(0);
  const [events,setEvents]=useState([]);
  const [components,setComponents]=useState([]);
  const [signals,setSignals]=useState([]);
  const [signalStats,setSignalStats]=useState(null);
  const [pnlCurve,setPnlCurve]=useState([]);
  const [mgmtNote,setMgmtNote]=useState('');
  const [aurumH,setAurumH]=useState(72); // collapsed by default — drag up to expand
  const aurumDragRef=useRef(null);
  // Column + panel resize state
  const [leftW,setLeftW]=useState(186);    // left sidebar width (px)
  // Backtest tab state
  const [btRuns,setBtRuns]=useState([]);
  const [btAllRuns,setBtAllRuns]=useState([]);       // full list (pre-display-limit slice)
  const [btSelRun,setBtSelRun]=useState(null);       // aurum_run_id currently viewed
  const [btPinnedRuns,setBtPinnedRuns]=useState([]); // pinned run IDs — only cleared by explicit user action
  const btPinnedRunsRef=useRef([]);                  // ref so interval callbacks always see latest pins
  const [btDetail,setBtDetail]=useState(null);       // /api/backtest/run/:id response
  const [btCompares,setBtCompares]=useState([]);     // array of /api/backtest/compare results (one per pin or prev)
  const [gateLegend,setGateLegend]=useState({});         // gate_reason → {label, explanation}
  const [indLegend,setIndLegend]=useState({});           // acronym → indicator detail
  const [mgmtBusy,setMgmtBusy]=useState(false);
  const [autoscalperConditions,setAutoscalperConditions]=useState(null);
  const [autoscalperConditionsError,setAutoscalperConditionsError]=useState(null);

  // Keep btPinnedRunsRef in sync — interval callbacks read ref, never stale state
  useEffect(()=>{ btPinnedRunsRef.current=btPinnedRuns; },[btPinnedRuns]);

  useEffect(()=>{
    const poll=async()=>{
      try{const r=await fetch(`${API}/api/live`);
        if(r.ok){const d=await r.json();setData(d);setMode(d.mode||'SIGNAL');setConnected(true);}
        try{const rc=await fetch(`${API}/api/components`);
          if(rc.ok){const cd=await rc.json();setComponents(cd.components||[]);}}catch(e){}
        const re=await fetch(`${API}/api/events?limit=500`);
        if(re.ok){const ev=await re.json();
          setEvents(Array.isArray(ev)?ev.map(normalizeActivityEvent):[]);}
        try{const rs=await fetch(`${API}/api/signals?limit=50&session=current&stats=1`);
          if(rs.ok){const sj=await rs.json();
            if(sj&&Array.isArray(sj.signals)){setSignals(sj.signals);setSignalStats(sj.stats||null);}
            else if(Array.isArray(sj)){setSignals(sj);setSignalStats(null);}}}
        catch(e){}
        try{const rp=await fetch(`${API}/api/pnl_curve?days=${PERF_ROLLING_DAYS}`);
          if(rp.ok){const curve=await rp.json();
            if(Array.isArray(curve))setPnlCurve(curve.map(x=>Number(x.cumulative)).filter(v=>!Number.isNaN(v)));}}
        catch(e){}
        try{
          const ra=await fetch(`${API}/api/autoscalper/conditions?responses=5`);
          const ct=(ra.headers.get('content-type')||'').toLowerCase();
          if(ra.ok&&ct.includes('application/json')){
            const aj=await ra.json();
            if(aj&&typeof aj==='object'&&!Array.isArray(aj)&&!aj.error){
              setAutoscalperConditions(aj);setAutoscalperConditionsError(null);
            }else{
              setAutoscalperConditions(null);
              setAutoscalperConditionsError((aj&&aj.error)?String(aj.error):'invalid_payload');
            }
          }else if(ra.ok){
            setAutoscalperConditions(null);
            setAutoscalperConditionsError('non_json_response');
          }else{
            setAutoscalperConditions(null);
            setAutoscalperConditionsError(`HTTP ${ra.status}`);
          }
        }catch(e){
          setAutoscalperConditions(null);
          setAutoscalperConditionsError('unreachable');
        }
      }catch(e){setConnected(false);}
    };
    poll();const t=setInterval(poll,3000);return()=>clearInterval(t);
  },[]);
  useEffect(()=>{const t=setInterval(()=>setTick(x=>x+1),1000);return()=>clearInterval(t);},[]);

  // Gate legend — fetch once when backtest tab first opens
  useEffect(()=>{
    if(tab!=='backtest'||Object.keys(gateLegend).length>0)return;
    fetch(`${API}/api/gate_legend`).then(r=>r.ok?r.json():null).then(j=>{if(j)setGateLegend(j);}).catch(()=>{});
  },[tab]);

  // Indicator legend — fetch once when indicators tab first opens
  useEffect(()=>{
    if(tab!=='indicators'||Object.keys(indLegend).length>0)return;
    fetch(`${API}/api/indicator_legend`).then(r=>r.ok?r.json():null).then(j=>{if(j)setIndLegend(j);}).catch(()=>{});
  },[tab]);

  // Backtest runs — fetch on tab open and refresh every 30s
  useEffect(()=>{
    if(tab!=='backtest')return;
    const load=async()=>{
      try{const r=await fetch(`${API}/api/backtest/runs`);
        if(r.ok){const j=await r.json();
          const all=j.runs||[];
          const displayLimit=j.display_limit||10;
          setBtAllRuns(all);
          // Use ref — closure captures stale state; ref always has latest pins array
          const pins=btPinnedRunsRef.current||[];
          const slice=all.slice(0,displayLimit);
          // Inject any pinned runs not already in the slice (they survive display limit)
          const sliceIds=new Set(slice.map(r=>r.aurum_run_id));
          const extra=pins.map(id=>all.find(r=>r.aurum_run_id===id)).filter(r=>r&&!sliceIds.has(r.aurum_run_id));
          setBtRuns([...slice,...extra]);
          if(!btSelRun&&slice.length>0)setBtSelRun(slice[0].aurum_run_id);}}
      catch(e){}};
    load();const t=setInterval(load,300000);return()=>clearInterval(t); // 5 min — runs list changes slowly
  },[tab]);

  // Backtest run detail — fetch on selection only, no auto-poll (stable data; manual refresh below)
  const loadBtDetail=useCallback(async()=>{
    if(!btSelRun)return;
    try{const r=await fetch(`${API}/api/backtest/run/${btSelRun}`);
      if(r.ok){const j=await r.json();setBtDetail(j);}}
    catch(e){};
  },[btSelRun]);
  useEffect(()=>{loadBtDetail();},[btSelRun]);

  // Backtest compare — one fetch per pinned run; or vs previous run when nothing pinned
  useEffect(()=>{
    if(tab!=='backtest'||!btSelRun)return;
    const pins=btPinnedRuns.filter(id=>id!==btSelRun);
    // baselines: pinned runs if any, else the run immediately before selected in list
    const baselines=pins.length>0
      ? pins
      : [btAllRuns.find(r=>r.aurum_run_id<btSelRun)?.aurum_run_id].filter(Boolean);
    if(!baselines.length){setBtCompares([]);return;}
    Promise.all(
      baselines.map(runB=>
        fetch(`${API}/api/backtest/compare?run_a=${btSelRun}&run_b=${runB}`)
          .then(r=>r.ok?r.json():null)
          .catch(()=>null)
      )
    ).then(results=>setBtCompares(results.filter(j=>j&&!j.error)));
  },[btSelRun,btPinnedRuns,tab]);

  const switchMode=async(m)=>{
    try{await fetch(`${API}/api/mode`,{method:'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:m})});}
    catch(e){}setMode(m);
  };

  const postMgmt=async(intent,pct,groupId)=>{
    if(!API){setMgmtNote('API base URL missing');return;}
    setMgmtBusy(true);setMgmtNote('');
    try{
      const body={intent};
      if(intent==='CLOSE_PCT'||intent==='CLOSE_GROUP_PCT')body.pct=pct!=null?pct:70;
      if(groupId)body.group_id=groupId;
      const r=await fetch(`${API}/api/management`,{method:'POST',
        headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const j=await r.json().catch(()=>({}));
      if(!r.ok)setMgmtNote(j.error||`HTTP ${r.status}`);
      else{setMgmtNote(j.hint||'Queued — BRIDGE → FORGE');setTimeout(()=>setMgmtNote(''),7000);}
    }catch(e){setMgmtNote(String(e));}
    finally{setMgmtBusy(false);}
  };

  const D=data||{
    mode:'DISCONNECTED',effective_mode:'DISCONNECTED',
    session:'UNKNOWN',cycle:0,
    account_type:'UNKNOWN',broker:'',server:'',
    mt5_connected:false,circuit_breaker:false,
    sentinel_active:false,mt5_fresh:false,mt5_quote_stale:true,chart_symbol:null,
    execution:{
      symbol:null,bid:null,ask:null,mid:null,spread_usd:null,spread_points:null,
      timestamp_utc:null,timestamp_unix:null,age_sec:null,stale:true,usable:false,stale_reason:null,
    },
    tradingview:{
      last:null,timeframe:null,age_seconds:null,rsi:null,macd_hist:null,bb_rating:null,
      adx:null,di_plus:null,di_minus:null,dmi_present:false,dmi_study:null,
      order_block_present:false,order_block_study:null,order_block_values:{},
      ema_20:null,ema_50:null,tv_recommend:null,tv_recommend_source:null,
      tv_brief:null,tv_brief_source:null,tv_brief_timestamp:null,divergence_from_mt5_usd:null,
    },
    account:{balance:null,equity:null,total_floating_pnl:null,
      margin:null,free_margin:null,margin_level:null,
      open_positions_count:0,session_pnl:null},
    price:{bid:null,ask:null,spread_points:null},
    lens:{price:null,bid:null,ask:null,rsi:null,macd_hist:null,bb_rating:null,
      bb_width:null,adx:null,di_plus:null,di_minus:null,dmi_present:false,dmi_study:null,
      order_block_present:false,order_block_study:null,order_block_values:{},
      ema_20:null,ema_50:null,
      tv_recommend:null,tv_recommend_source:null,tv_brief:null,tv_brief_source:null,tv_brief_timestamp:null,
      timeframe:'--',age_seconds:null,spread_usd:null,
      tradingview_close:null,tv_price_mismatch:false,mt5_symbol:null},
    sentinel:{active:false,next_event:'Unknown',next_in_min:null,next_time:null,news_feeds:{}},
    open_groups:[],open_groups_queued:[],open_groups_policy:'',
    pending_orders:[],pending_orders_forge_count:null,
    performance:{total_pnl:0,total:0,wins:0,losses:0,win_rate:null,avg_pips:0},
    performance_window:null,
    aegis:{scale_factor:1,scale_reason:'UNKNOWN',session_pnl:0,streak:0,streak_type:'NONE'},
    regime:{
      config:{enabled:false,entry_mode:'off',min_confidence:0.6,stale_sec:180,retrain_interval_sec:3600,min_train_samples:120},
      current:{label:'UNKNOWN',confidence:0,model_name:null,entry_mode:'off',age_sec:null,stale:true},
      transitions_24h:[],
      performance_30d:{days:30,by_regime:[],fallback_count:0,snapshot_count:0,fallback_rate:0},
    },
    reconciler:null,
    components:{},
    scalper_gates:{require_macd_sell:null,require_macd_buy:null,
      macd_fast:3,macd_slow:10,macd_signal:16,
      osma_m5:null,osma_bias:null,sell_osma_pass:null,buy_osma_pass:null,
      session_ny_sell_cutoff:null,adx_sell_block:null},
  };

  const acc=D.account||{},sent=D.sentinel||{};
  const ex=D.execution||{},tv=D.tradingview||{};
  const sg=D.scalper_gates||{};
  const sym=ex.symbol||D.chart_symbol||'—';
  const tvSnapSec=tv.age_seconds!=null?Math.floor(Number(tv.age_seconds)):null;
  const tvSnapAge=tvSnapSec!=null?`${Math.floor(tvSnapSec/60)}m ${tvSnapSec%60}s ago`:'—';
  const modeColor=MODES.find(m=>m.id===mode)?.color||T.gold;
  const timeStr=new Date().toUTCString().split(' ')[4]+' UTC';
  const warnCount=events.filter(e=>e.level==='WARN'||e.level==='ERROR').length;
  const uploadEvents=events.filter(e=>isUploadEvent(e.raw));
  const uploadCount=uploadEvents.length;
  const st=signalStats||{received:0,executed:0,skipped:0,expired:0};
  const pnlSpark=(()=>{
    if(!pnlCurve||pnlCurve.length<1)return null;
    if(pnlCurve.length===1)return[0,pnlCurve[0]];
    return pnlCurve;
  })();
  const sparkColor=(pnlSpark&&pnlSpark[pnlSpark.length-1]>=0)?T.green:T.red;
  const perf=D.performance||{};
  const winRateLbl=(perf.win_rate==null||!perf.total)?'—':`${perf.win_rate}%`;
  const avgPipsVal=perf.avg_pips!=null?Number(perf.avg_pips):0;
  const avgPipsLbl=`${avgPipsVal>=0?'+':''}${avgPipsVal.toFixed(1)}`;
  const regime=D.regime||{};
  const regimeCfg=regime.config||{};
  const regimeCurrent=regime.current||{};
  const regimeTransitions=Array.isArray(regime.transitions_24h)?regime.transitions_24h:[];
  const regimePerf=regime.performance_30d||{};
  const regimeRows=Array.isArray(regimePerf.by_regime)?regimePerf.by_regime:[];
  const regimeFeatures=regimeCurrent.features||{};
  const regimePosterior=regimeCurrent.posterior||{};
  const regimeMode=((regimeCfg.entry_mode||regimeCurrent.entry_mode||'off')+'').toUpperCase();
  const regimeModeColor=regimeMode==='ACTIVE'?T.green:regimeMode==='SHADOW'?T.amber:T.textD;
  const regimeConfPct=(regimeCurrent.confidence==null||Number.isNaN(Number(regimeCurrent.confidence)))
    ?'—':`${Math.round(Number(regimeCurrent.confidence)*100)}%`;
  const asr=autoscalperConditions||{};
  const asrPref=asr.bridge_prefilters||{};
  const asrSetup=asr.setup_snapshot||{};
  const asrOverall=asr.overall||{};
  const asrLens=asr.lens_indicators||{};
  const asrLatest=(Array.isArray(asr.latest_autoscalper_responses)&&asr.latest_autoscalper_responses.length>0)
    ?asr.latest_autoscalper_responses[0]:null;
  const asrFailed=Array.isArray(asrOverall.failed_checks)?asrOverall.failed_checks:[];
  // pattern_ready = true when either SELL (H1 BEAR+upperBB) or BUY (H1 BULL+lowerBB) is confirmed
  const asrReady=asrOverall.pattern_ready===true||asrOverall.g47_g48_sell_pattern_match===true;
  const asrReadyColor=asrReady?T.green:T.red;
  const asrDirection=asrOverall.direction_ready||null;
  const asrPrefilterPass=asrPref.prefilter_pass===true;
  const asrTesterMode=asr.strategy_tester===true||asrPref.mt5_tester_mode===true;

  return(<div style={{background:T.bg,height:'100vh',color:T.textB,
    fontFamily:'Georgia,serif',display:'flex',flexDirection:'column',overflow:'hidden'}}>

    {/* HEADER */}
    <div style={{background:T.panel,borderBottom:`1px solid ${T.border}`,
      padding:'7px 16px',display:'flex',alignItems:'center',
      justifyContent:'space-between',flexShrink:0}}>
      <div style={{display:'flex',alignItems:'center',gap:14}}>
        <div>
          <div style={{fontFamily:T.mono,fontSize:15,fontWeight:700,color:T.gold,letterSpacing:4}}>⚒ ATHENA</div>
          <div style={{fontSize:9,color:T.text,letterSpacing:2,textTransform:'uppercase'}}>Signal System · XAUUSD</div>
        </div>
        <div style={{background:`${modeColor}11`,border:`1px solid ${modeColor}`,
          padding:'3px 10px',borderRadius:4,display:'flex',alignItems:'center',gap:6}}>
          <Dot ok={true} sz={5} b={true}/><span style={{fontFamily:T.mono,fontSize:10,
            color:modeColor,letterSpacing:2}}>{mode}</span></div>
        {D.account_type&&D.account_type!=='UNKNOWN'&&(
          <div style={{background:D.account_type==='DEMO'?'rgba(59,130,246,0.1)':'rgba(16,185,129,0.1)',
            border:`1px solid ${D.account_type==='DEMO'?T.blue:T.green}`,
            padding:'3px 10px',borderRadius:4,display:'flex',alignItems:'center',gap:5}}>
            <span style={{fontFamily:T.mono,fontSize:10,letterSpacing:2,
              color:D.account_type==='DEMO'?T.blue:T.green}}>{D.account_type}</span>
          </div>
        )}
        <span style={{fontSize:9,color:T.text,fontFamily:T.mono}}>{timeStr}</span>
        <span style={{fontSize:9,color:T.text,fontFamily:T.mono}} title="session_utc = UTC kill-zone clock; session = last BRIDGE write">
          {D.session_utc||D.session}</span>
      </div>
      <div style={{display:'flex',alignItems:'center',gap:10}}>
        <div style={{display:'flex',alignItems:'center',gap:5,fontSize:9,
          fontFamily:T.mono,color:connected?T.green:T.amber}}>
          <Dot ok={connected} sz={5} b={connected}/>{connected?'LIVE':'DEMO'}
        </div>
        <span style={{fontSize:9,color:T.textD,fontFamily:T.mono}}>Cycle {D.cycle}</span>
      </div>
    </div>

    {/* BODY */}
    <div style={{flex:1,display:'grid',gridTemplateColumns:`${leftW}px 1fr 258px`,
      overflow:'hidden',minHeight:0}}>

      {/* LEFT — drag handle on right edge to resize width */}
      <div style={{borderRight:`1px solid ${T.border}`,padding:'12px 10px',
        overflowY:'auto',display:'flex',flexDirection:'column',gap:14,position:'relative'}}>
        {/* left column right-edge drag handle */}
        <div title="Drag to resize sidebar"
          onMouseDown={e=>{
            e.preventDefault();
            const startX=e.clientX,startW=leftW;
            const onMove=ev=>setLeftW(Math.max(140,Math.min(320,startW+(ev.clientX-startX))));
            const onUp=()=>{document.removeEventListener('mousemove',onMove);document.removeEventListener('mouseup',onUp);};
            document.addEventListener('mousemove',onMove);document.addEventListener('mouseup',onUp);
          }}
          style={{position:'absolute',top:0,right:-4,width:8,height:'100%',cursor:'col-resize',zIndex:10,
            display:'flex',alignItems:'center',justifyContent:'center'}}>
          <div style={{width:3,height:36,borderRadius:2,background:T.border2,opacity:.5}}/>
        </div>

        <div>
          <PT ch="⬡ Account · MT5 Live"/>
          {D.mt5_quote_stale&&(
            <div style={{fontSize:9,color:T.amber,fontFamily:T.mono,marginBottom:6,padding:'5px 6px',
              background:T.amberBg,border:`1px solid ${T.amber}`,borderRadius:4,lineHeight:1.4}}>
              FORGE quote file stale ({fmtAgeSec(ex.age_sec)}) — bid/ask hidden until fresh.
            </div>
          )}
          <div style={{fontFamily:T.mono,fontSize:20,color:T.gold,fontWeight:700,marginBottom:1}}>
            {acc.balance!=null?'$'+acc.balance.toLocaleString('en',{minimumFractionDigits:2}):'—'}</div>
          <div style={{fontSize:9,color:T.text,marginBottom:8}}>BALANCE (from market_data.json)</div>
          {[['EQUITY',acc.equity!=null?'$'+acc.equity.toLocaleString('en',{minimumFractionDigits:2}):'—',T.textBB],
            ['MRG LVL',acc.margin_level!=null?acc.margin_level.toFixed(0)+'%':'—',T.green],
            ['POSITIONS (filled)',acc.open_positions_count??0,T.amber],
            ['PENDING ORDERS',(D.pending_orders||[]).length,T.cyan],
            ['FORGE pendings',D.pending_orders_forge_count!=null?D.pending_orders_forge_count:'—',T.text]].map(([l,v,c])=>(
            <div key={l} style={{display:'flex',justifyContent:'space-between',
              padding:'3px 0',borderBottom:`1px solid ${T.border}`,marginBottom:2}}>
              <span style={{fontSize:9,color:T.textD,fontFamily:T.mono}}>{l}</span>
              <span style={{fontSize:10,fontFamily:T.mono,color:c}}>{v}</span>
            </div>
          ))}
          {(D.pending_orders||[]).length>0&&(
            <div style={{marginTop:8,maxHeight:120,overflowY:'auto',
              border:`1px solid ${T.border2}`,borderRadius:4,background:T.row,padding:6}}>
              <div style={{fontSize:9,color:T.textD,fontFamily:T.mono,marginBottom:4,letterSpacing:1}}>
                MT5 PENDING (market_data.json)</div>
              {(D.pending_orders||[]).map((p,i)=>(
                <div key={p.ticket||i} style={{fontSize:9,fontFamily:T.mono,color:T.textBB,
                  borderBottom:i<(D.pending_orders||[]).length-1?`1px solid ${T.border}`:'none',
                  padding:'4px 0',lineHeight:1.35}}>
                  <span style={{color:T.cyan}}>#{p.ticket}</span>
                  {' '}{p.order_type||'?'} @ {p.price}
                  {' · '}{p.volume} lot
                  {p.magic!=null&&<span style={{color:T.textD}}> · mgc {p.magic}</span>}
                  {p.forge_managed&&<Tag lbl="FORGE" color={T.amber} xs/>}
                </div>
              ))}
            </div>
          )}
          <div style={{marginTop:6,padding:'5px 8px',
            background:(acc.session_pnl??0)>=0?T.greenBg:T.redBg,
            border:`1px solid ${(acc.session_pnl??0)>=0?T.green:T.red}`,
            borderRadius:4,display:'flex',justifyContent:'space-between',alignItems:'center'}}>
            <span style={{fontSize:9,fontFamily:T.mono,color:T.text}}>SESSION</span>
            <span style={{fontFamily:T.mono,fontWeight:700,
              color:(acc.session_pnl??0)>=0?T.green:T.red}}>
              {acc.session_pnl!=null?((acc.session_pnl>=0?'+':'')+acc.session_pnl.toFixed(2)):'—'}
            </span>
          </div>
          <div style={{marginTop:6,padding:'4px',background:T.card,borderRadius:4}}>
            {pnlSpark&&pnlSpark.length>=2?(
              <Sparkline data={pnlSpark} w={158} h={28} color={sparkColor}/>
            ):(
              <div style={{fontSize:9,color:T.textD,fontFamily:T.mono,textAlign:'center',padding:'6px 2px'}}>
                No closed trades ({PERF_ROLLING_DAYS}d UTC)</div>
            )}
            <div style={{fontSize:9,color:T.textD,fontFamily:T.mono,textAlign:'center',marginTop:1}}>
              Cumulative P&L ({PERF_ROLLING_DAYS}d)</div>
          </div>
          <div style={{marginTop:4,fontSize:8,color:T.textD,fontFamily:T.mono}}>
            Source: SCRIBE trade_positions · balance/equity from MT5/market_data.json
          </div>
        </div>

        <div>
          <PT ch="⬡ Mode Control"/>
          {MODES.map(m=>(
            <button key={m.id} onClick={()=>switchMode(m.id)} style={{
              display:'flex',justifyContent:'space-between',alignItems:'center',
              padding:'5px 7px',marginBottom:3,width:'100%',
              background:mode===m.id?`${m.color}11`:'transparent',
              border:`1px solid ${mode===m.id?m.color:T.border}`,
              borderRadius:4,cursor:'pointer'}}>
              <span style={{fontFamily:T.mono,fontSize:9,
                color:mode===m.id?m.color:T.text,letterSpacing:1}}>{m.id}</span>
              <span style={{fontSize:9,color:T.textD}}>{m.desc}</span>
              {mode===m.id&&<Dot ok={true} sz={4}/>}
            </button>
          ))}
          <div style={{fontSize:9,color:T.textD,fontFamily:T.mono,textAlign:'center',marginTop:3}}>
            BRIDGE → FORGE via config.json
          </div>
          <div style={{marginTop:4,fontSize:8,color:T.textD,fontFamily:T.mono}}>
            Source: MT5/config.json + config/aurum_cmd.json · written by BRIDGE
          </div>
        </div>

        {D.circuit_breaker&&(
          <div style={{padding:'8px 10px',background:'rgba(232,68,90,0.1)',
            border:'1px solid #E8445A',borderRadius:5}}>
            <div style={{fontSize:9,color:'#E8445A',fontFamily:T.mono,fontWeight:700,marginBottom:2}}>
              ⚡ CIRCUIT BREAKER
            </div>
            <div style={{fontSize:9,color:T.text}}>MT5 data stale — trading suspended</div>
          </div>
        )}

        <div>
          <PT ch={sent.active?'⚠ SENTINEL ACTIVE':'✓ SENTINEL'} color={sent.active?T.red:T.green}/>
          <div style={{padding:'5px 8px',background:sent.active?T.redBg:T.greenBg,
            border:`1px solid ${sent.active?T.red:T.green}`,borderRadius:4,
            marginBottom:6,textAlign:'center'}}>
            <span style={{fontSize:9,fontFamily:T.mono,color:sent.active?T.red:T.green}}>
              {sent.active?'TRADING PAUSED':'CLEAR TO TRADE'}</span>
          </div>
          <div style={{fontSize:9,color:T.text}}>Next: <span style={{color:T.amber}}>{sent.next_event}</span></div>
          <div style={{fontFamily:T.mono,fontSize:11,color:T.textBB,marginTop:2}}>{sent.next_time}</div>
          <div style={{fontSize:9,color:T.textD,marginTop:1}}>
            in {Math.floor((sent.next_in_min||0)/60)}h {(sent.next_in_min||0)%60}m</div>
          {Array.isArray(sent.calendar_currencies)&&sent.calendar_currencies.length>0&&(
            <div style={{fontSize:9,color:T.textD,fontFamily:T.mono,marginTop:4,lineHeight:1.3}}>
              Cal: {sent.calendar_currencies.join(', ')}
            </div>
          )}
          <SentinelHeadlines newsFeeds={sent.news_feeds}/>
          <div style={{marginTop:4,fontSize:8,color:T.textD,fontFamily:T.mono}}>
            Source: config/sentinel_status.json · SENTINEL writes every cycle
          </div>
        </div>

        <div>
          <PT ch="⬡ System Health"/>
          {(components.length>0?components:[]).map(c=>(
            <div key={c.name} style={{display:'flex',alignItems:'center',gap:5,marginBottom:5}}>
              <Dot ok={c.ok} sz={5}/>
              <span style={{fontFamily:T.mono,fontSize:9,color:c.ok?(CC[c.name]||T.text):T.red,
                width:64,flexShrink:0}}>{c.name}</span>
              <span style={{fontSize:9,color:T.textD,overflow:'hidden',
                textOverflow:'ellipsis',whiteSpace:'nowrap',flex:1}}>{c.note}</span>
            </div>
          ))}
          {components.length===0&&(
            <div style={{fontSize:9,color:T.textD,fontFamily:T.mono,textAlign:'center',padding:'8px 0'}}>
              No heartbeats yet
            </div>
          )}
          <div style={{marginTop:4,fontSize:8,color:T.textD,fontFamily:T.mono}}>
            Source: SCRIBE component_heartbeats · /api/components
          </div>
        </div>
      </div>

      {/* CENTER */}
      <div style={{display:'flex',flexDirection:'column',overflow:'hidden',minHeight:0}}>
        <div style={{display:'flex',borderBottom:`1px solid ${T.border}`,flexShrink:0}}>
          {[{id:'groups',label:'Groups'},{id:'closures',label:'Closures'},{id:'activity',label:'Activity',badge:warnCount||null},
            {id:'signals',label:'Signals'},{id:'uploads',label:'Uploads',badge:uploadCount||null},{id:'perf',label:'Performance'},
            {id:'backtest',label:'🔬 Backtest',badge:btRuns.length||null},
            {id:'indicators',label:'📊 Indicators'}].map(t=>(
            <button key={t.id} type="button" data-testid={`tab-${t.id}`}
              onClick={()=>setTab(t.id)} style={{
              padding:'6px 10px',background:'transparent',border:'none',
              borderBottom:tab===t.id?`2px solid ${T.gold}`:'2px solid transparent',
              color:tab===t.id?T.gold:T.text,fontFamily:T.mono,fontSize:9,
              letterSpacing:0.5,cursor:'pointer',textTransform:'uppercase',
              display:'flex',alignItems:'center',gap:5}}>
              {t.label}
              {t.badge&&<span style={{background:T.amberBg,color:T.amber,
                border:`1px solid ${T.amber}`,fontSize:9,fontFamily:T.mono,
                padding:'0 5px',borderRadius:8}}>{t.badge}</span>}
            </button>
          ))}
        </div>

        <div style={{flex:1,overflow:'hidden',minHeight:0}}>
          {tab==='activity'&&<ActivityLog events={events} components={components}/>}

          {tab==='groups'&&(
            <div style={{overflowY:'auto',height:'100%',padding:'12px 14px'}}>
              {mgmtNote&&(
                <div style={{fontSize:9,color:T.cyan,fontFamily:T.mono,marginBottom:10,padding:'6px 8px',
                  background:T.cyanBg,border:`1px solid ${T.cyan}`,borderRadius:4}}>{mgmtNote}</div>
              )}
              {(D.open_groups_queued||[]).length>0&&(
                <div style={{fontSize:9,color:T.amber,fontFamily:T.mono,marginBottom:10,padding:'6px 8px',
                  background:T.amberBg,border:`1px solid ${T.amber}`,borderRadius:4,lineHeight:1.35}}>
                  {(D.open_groups_queued||[]).length} group(s) in SCRIBE only — waiting for FORGE magic on MT5
                  (positions/pendings). Tiles below are MT5-confirmed.
                </div>
              )}
              {(D.open_groups||[]).map(g=>{
                const cl=g.trades_closed||0,tot=g.num_trades||8;
                // Match live MT5 positions to this group by magic number
                const gMagic=g.magic_number||0;
                const livePos=(D.open_positions||[]).filter(p=>p.magic===gMagic);
                const liveFloating=livePos.reduce((s,p)=>s+(p.profit||0),0);
                const hasLive=livePos.length>0;
                // Use live floating P&L for open groups, SCRIBE total_pnl for closed
                const displayPnl=hasLive?liveFloating:(g.total_pnl||0);
                return(<div key={g.id} className="fade" style={{background:T.card,
                  border:`1px solid ${T.border2}`,
                  borderLeft:`3px solid ${g.direction==='BUY'?T.green:T.red}`,
                  borderRadius:7,padding:12,marginBottom:10}}>
                  <div style={{display:'flex',justifyContent:'space-between',
                    alignItems:'flex-start',marginBottom:8}}>
                    <div>
                      <div style={{display:'flex',gap:6,alignItems:'center',marginBottom:4}}>
                        <span style={{fontFamily:T.mono,fontSize:13,fontWeight:700,
                          color:T.textBB}}>G{g.id}</span>
                        <Tag lbl={g.direction} color={g.direction==='BUY'?T.green:T.red}/>
                        <Tag lbl={`×${tot}`} color={T.text}/>
                        <Tag lbl={`${g.lot_per_trade}lot`} color={T.amber}/>
                        {g.source==='FORGE_NATIVE_SCALP'&&<Tag lbl="FORGE" color={T.cyan}/>}
                        {g.source==='AUTO_SCALPER'&&<Tag lbl="AURUM" color={T.gold}/>}
                        {g.source==='SIGNAL'&&<Tag lbl="SIGNAL" color={T.orange}/>}
                      </div>
                      <div style={{fontSize:9,color:T.text,fontFamily:T.mono}}>
                        {g.entry_low}–{g.entry_high} · SL:{g.sl} · TP1:{g.tp1}
                        {g.tp2&&` · TP2:${g.tp2}`} · TP3:{g.tp3||'OPEN'}
                      </div>
                    </div>
                    <div style={{textAlign:'right'}}>
                      <span style={{fontFamily:T.mono,color:displayPnl>=0?T.green:T.red,fontWeight:700,
                        fontSize:hasLive?15:13}}>
                        {displayPnl>=0?'+':''}{displayPnl.toFixed(2)}</span>
                      {hasLive&&<div style={{fontSize:9,color:T.gold,fontFamily:T.mono}}>LIVE</div>}
                      {!hasLive&&<div style={{fontSize:9,color:T.text,fontFamily:T.mono}}>
                        +{(g.pips_captured||0).toFixed(1)}p</div>}
                    </div>
                  </div>
                  {/* Position grid: show entry price + live P&L from MT5 */}
                  <div style={{display:'grid',gridTemplateColumns:`repeat(${tot},1fr)`,
                    gap:2,marginBottom:8}}>
                    {Array.from({length:tot}).map((_,i)=>{
                      const isCl=i<cl;
                      const pos=livePos[i-cl];  // map remaining slots to live positions
                      const activePos=!isCl&&i-cl>=0&&i-cl<livePos.length?livePos[i-cl]:null;
                      return(
                      <div key={i} title={activePos?`#${activePos.ticket} @ ${activePos.open_price} pnl $${activePos.profit}`:''}
                        style={{height:activePos?28:14,borderRadius:2,
                        background:isCl?(g.direction==='BUY'?T.greenBg:T.redBg)
                          :(g.direction==='BUY'?'rgba(16,185,129,0.2)':'rgba(239,68,68,0.2)'),
                        border:`1px solid ${isCl?T.border:(g.direction==='BUY'?T.green:T.red)}`,
                        display:'flex',alignItems:'center',justifyContent:'center',
                        flexDirection:'column',gap:1,
                        fontSize:9,color:isCl?T.textD:(g.direction==='BUY'?T.green:T.red),
                        fontFamily:T.mono}}>
                        {isCl?'✓':activePos?(<>
                          <span style={{fontSize:9,color:T.textD}}>{activePos.open_price}</span>
                          <span style={{fontSize:9,fontWeight:700,
                            color:(activePos.profit||0)>=0?T.green:T.red}}>
                            {(activePos.profit||0)>=0?'+':''}{(activePos.profit||0).toFixed(2)}</span>
                        </>):'●'}
                      </div>);})}
                  </div>
                  <div style={{height:3,background:T.border,borderRadius:2,overflow:'hidden',marginBottom:4}}>
                    <div style={{width:`${Math.min(100,(cl/tot)*140)}%`,height:'100%',
                      background:cl>0?T.green:T.gold,borderRadius:2}}/></div>
                  <div style={{display:'flex',justifyContent:'space-between',marginBottom:7}}>
                    <span style={{fontSize:9,fontFamily:T.mono,color:T.text}}>{cl}/{tot} closed</span>
                    <div style={{display:'flex',gap:4}}>
                      {cl>0&&<Tag lbl="TP1✓" color={T.green} xs/>}
                      {g.be_moved&&<Tag lbl="BE✓" color={T.cyan} xs/>}
                    </div>
                  </div>
                  <div style={{display:'flex',gap:5,flexWrap:'wrap'}}>
                    {[
                      ['Close Group','CLOSE_GROUP',null],
                      ['Move BE','MOVE_BE',null],
                      ['Close 70%','CLOSE_GROUP_PCT',70],
                    ].map(([label,intent,pct])=>(
                      <button key={label} type="button" disabled={mgmtBusy||!API}
                        onClick={()=>postMgmt(intent,pct,g.id)}
                        style={{fontSize:9,fontFamily:T.mono,
                        background:mgmtBusy?T.border:'transparent',
                        border:`1px solid ${T.border2}`,color:T.text,
                        padding:'2px 7px',borderRadius:3,
                        cursor:mgmtBusy||!API?'not-allowed':'pointer',
                        opacity:mgmtBusy?0.5:1}}>{label}</button>
                    ))}
                  </div>
                </div>);
              })}
              {(D.open_groups||[]).length===0&&(
                <div style={{fontSize:10,color:T.textD,fontFamily:T.mono,
                  textAlign:'center',padding:40}}>No open groups</div>
              )}
              <div style={{marginTop:4,fontSize:8,color:T.textD,fontFamily:T.mono}}>
                Source: SCRIBE trade_groups + MT5 open_positions · /api/live
              </div>
            </div>
          )}

          {tab==='closures'&&(
            <div style={{overflowY:'auto',height:'100%',padding:'12px 14px'}}>
              {/* Closure stats summary */}
              {D.closure_stats&&D.closure_stats.total>0&&(
                <div style={{display:'flex',gap:12,marginBottom:12,flexWrap:'wrap'}}>
                  {[['SL Hits',D.closure_stats.sl_hits,T.red,`${D.closure_stats.sl_rate}%`],
                    ['TP1 Hits',D.closure_stats.tp1_hits,T.green,`${D.closure_stats.tp_rate}% TP`],
                    ['TP2 Hits',D.closure_stats.tp2_hits,T.cyan,null],
                    ['Manual',D.closure_stats.manual,T.amber,null],
                    ['Total P&L',null,D.closure_stats.total_pnl>=0?T.green:T.red,`$${D.closure_stats.total_pnl.toFixed(2)}`],
                  ].map(([label,count,color,extra])=>(
                    <div key={label} style={{background:T.card,border:`1px solid ${T.border2}`,
                      borderTop:`2px solid ${color}`,borderRadius:5,padding:'8px 12px',
                      textAlign:'center',minWidth:70}}>
                      {count!=null&&<div style={{fontFamily:T.mono,fontSize:16,color,fontWeight:700}}>{count}</div>}
                      {extra&&<div style={{fontFamily:T.mono,fontSize:count!=null?8:14,color,fontWeight:count!=null?400:700}}>{extra}</div>}
                      <div style={{fontSize:9,color:T.textD,marginTop:2}}>{label}</div>
                    </div>
                  ))}
                </div>
              )}
              {/* Recent closures list */}
              {(D.recent_closures||[]).length>0?(
                (D.recent_closures||[]).map((c,i)=>{
                  const reasonRaw=c.close_reason||'?';
                  const reasonLabel=(['SL_HIT','TP1_HIT','TP2_HIT','TP3_HIT','MANUAL_CLOSE'].includes(reasonRaw))
                    ?reasonRaw:'MANUAL_CLOSE';
                  const isSL=reasonLabel==='SL_HIT';
                  const isTP=reasonLabel&&reasonLabel.startsWith('TP');
                  const reasonColor=isSL?T.red:isTP?T.green:T.amber;
                  return(
                    <div key={c.id||i} className="fade" style={{display:'flex',alignItems:'center',
                      gap:10,padding:'6px 10px',marginBottom:4,
                      background:T.card,border:`1px solid ${T.border2}`,borderRadius:5,
                      borderLeft:`3px solid ${reasonColor}`}}>
                      <Tag lbl={reasonLabel} color={reasonColor}/>
                      <Tag lbl={c.direction||'?'} color={c.direction==='BUY'?T.green:T.red} xs/>
                      <span style={{fontFamily:T.mono,fontSize:9,color:T.textD}}>#{c.ticket}</span>
                      <span style={{fontFamily:T.mono,fontSize:9,color:T.textD}}>G{c.trade_group_id}</span>
                      <span style={{fontFamily:T.mono,fontSize:10,fontWeight:700,
                        color:(c.pnl||0)>=0?T.green:T.red,marginLeft:'auto'}}>
                        {(c.pnl||0)>=0?'+':''}{(c.pnl||0).toFixed(2)}</span>
                      <span style={{fontFamily:T.mono,fontSize:9,color:T.textD}}>
                        {(c.pips||0)>=0?'+':''}{(c.pips||0).toFixed(1)}p</span>
                      {c.pip_value_usd!=null&&(<span style={{fontFamily:T.mono,fontSize:9,color:(c.pip_value_usd||0)>=0?T.green:T.red}}>
                        {(c.pip_value_usd||0)>=0?'+':''}{(c.pip_value_usd||0).toFixed(2)}$pv</span>)}
                      <span style={{fontSize:9,color:T.textD,fontFamily:T.mono}}>
                        {fmtDateTime(c.timestamp)}</span>
                    </div>
                  );
                })
              ):(
                <div style={{fontSize:10,color:T.textD,fontFamily:T.mono,
                  textAlign:'center',padding:40}}>No closures recorded yet</div>
              )}
              <div style={{fontSize:9,color:T.textD,fontFamily:T.mono,textAlign:'center',marginTop:8}}>
                Showing last 24h · Full history: GET /api/closures?days=7
              </div>
              <div style={{marginTop:4,fontSize:8,color:T.textD,fontFamily:T.mono}}>
                Source: SCRIBE trade_positions (status=CLOSED) · /api/closures
              </div>
            </div>
          )}

          {tab==='signals'&&(()=>{
            // Channel filter state
            const channels=[...new Set(signals.map(s=>s.channel_name).filter(Boolean))];
            const [chFilter,setChFilter]=window.__sigChFilter||[null,v=>{window.__sigChFilter=[v,window.__sigChFilter[1]];}];
            if(!window.__sigChFilter)window.__sigChFilter=[null,v=>{window.__sigChFilter=[v,window.__sigChFilter[1]];}];
            const filtered=chFilter?signals.filter(s=>s.channel_name===chFilter):signals;
            return(
            <div style={{overflowY:'auto',height:'100%',padding:'12px 14px'}}>
              {/* Stats tiles */}
              <div style={{display:'flex',gap:20,marginBottom:8,alignItems:'flex-end',flexWrap:'wrap'}}>
                {[['Received',st.received,T.textBB],['Executed',st.executed,T.green],
                  ['Skipped',st.skipped,T.amber],['Expired',st.expired,T.textD]].map(([l,v,c])=>(
                  <div key={l} style={{textAlign:'center'}}>
                    <div style={{fontFamily:T.mono,fontSize:16,color:c,fontWeight:700}}>{v}</div>
                    <div style={{fontSize:9,color:T.textD,letterSpacing:1}}>{l}</div>
                  </div>
                ))}
              </div>
              {/* Channel filter strip */}
              {channels.length>0&&(
                <div style={{display:'flex',gap:3,flexWrap:'wrap',marginBottom:8}}>
                  <button type="button" onClick={()=>setChFilter(null)}
                    style={{fontSize:9,fontFamily:T.mono,letterSpacing:1,
                      background:!chFilter?T.goldBg:'transparent',
                      border:`1px solid ${!chFilter?T.gold:T.border}`,
                      color:!chFilter?T.gold:T.text,
                      padding:'2px 6px',borderRadius:3,cursor:'pointer'}}>ALL</button>
                  {channels.map(ch=>(
                    <button key={ch} type="button" onClick={()=>setChFilter(chFilter===ch?null:ch)}
                      style={{fontSize:9,fontFamily:T.mono,letterSpacing:0.5,
                        background:chFilter===ch?T.cyanBg:'transparent',
                        border:`1px solid ${chFilter===ch?T.cyan:T.border}`,
                        color:chFilter===ch?T.cyan:T.text,
                        padding:'2px 6px',borderRadius:3,cursor:'pointer'}}>{ch}</button>
                  ))}
                </div>
              )}
              <div style={{fontSize:9,color:T.textD,fontFamily:T.mono,marginBottom:8,letterSpacing:1}}>
                {filtered.length} signals · current session</div>
              {/* Signal rows — separate ENTRY from MANAGEMENT/other */}
              {filtered.map((row)=>{
                const t=fmtDateTime(row.timestamp);
                const sigType=(row.signal_type||'ENTRY').toUpperCase();
                const dir=(row.direction||'').toUpperCase();
                const low=row.entry_low,high=row.entry_high;
                const entry=(low!=null&&high!=null)
                  ?`${Number(low).toFixed(0)}–${Number(high).toFixed(0)}`:'';
                const act=(row.action_taken||'PENDING').toUpperCase();
                const ch=row.channel_name||'unknown';
                const isMgmt=sigType==='MANAGEMENT'||(!dir&&!entry);
                let info='';
                if(row.trade_group_id!=null)info=`G${row.trade_group_id}`;
                if(row.skip_reason)info=info?`${info} · ${row.skip_reason}`:String(row.skip_reason);
                if(!info)info=(row.raw_text||'').slice(0,80)||'—';
                // Management messages: subtle style
                if(isMgmt){
                  const intent=row.mgmt_intent||'';
                  return(<div key={row.id||`${t}-mgmt`} style={{
                    background:T.panel,border:`1px solid ${T.border}`,
                    borderLeft:`3px solid ${T.purple}`,
                    borderRadius:4,padding:'6px 10px',marginBottom:4,opacity:0.8}}>
                    <div style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}>
                      <div style={{display:'flex',alignItems:'center',gap:6}}>
                        <span style={{fontSize:9,color:T.textD,fontFamily:T.mono}}>{t}</span>
                        <Tag lbl={intent||'MSG'} color={T.purple} xs/>
                        <span style={{fontSize:9,color:T.textD,fontFamily:T.mono,
                          overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',maxWidth:400}}>
                          {(row.raw_text||'').slice(0,80)}</span>
                      </div>
                      <span style={{fontSize:9,fontFamily:T.mono,color:T.textD,
                        border:`1px solid ${T.border}`,padding:'1px 5px',borderRadius:2}}>{ch}</span>
                    </div>
                  </div>);
                }
                // Entry signals: full card
                const leftC=act==='EXECUTED'?(dir==='BUY'?T.green:T.red):act==='SKIPPED'?T.amber:
                  act==='EXPIRED'?T.textD:dir==='BUY'?T.green:dir==='SELL'?T.red:T.textD;
                return(<div key={row.id||`${t}-${act}-${dir}`} style={{
                  background:T.row,border:`1px solid ${T.border}`,
                  borderLeft:`3px solid ${leftC}`,
                  borderRadius:4,padding:'8px 10px',marginBottom:5}}>
                  <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:4}}>
                    <div style={{display:'flex',alignItems:'center',gap:6}}>
                      <span style={{fontSize:9,color:T.text,fontFamily:T.mono}}>{t}</span>
                      {dir&&<Tag lbl={dir} color={dir==='BUY'?T.green:T.red}/>}
                      {entry&&<span style={{fontSize:9,color:T.textB,fontFamily:T.mono,fontWeight:600}}>{entry}</span>}
                      <Tag lbl={act} color={act==='EXECUTED'?T.green:act==='SKIPPED'?T.amber:act==='EXPIRED'?T.textD:T.blue}/>
                    </div>
                    <span style={{fontSize:9,fontFamily:T.mono,color:T.cyan,
                      border:`1px solid ${T.cyan}33`,padding:'1px 5px',borderRadius:2,
                      letterSpacing:0.5}}>{ch}</span>
                  </div>
                  {(row.sl||row.tp1)&&(
                    <div style={{fontSize:9,fontFamily:T.mono,color:T.text,marginBottom:2}}>
                      {row.sl!=null&&<span style={{color:T.red}}>SL:{Number(row.sl).toFixed(0)} </span>}
                      {row.tp1!=null&&<span style={{color:T.green}}>TP1:{Number(row.tp1).toFixed(0)} </span>}
                      {row.tp2!=null&&<span style={{color:T.green}}>TP2:{Number(row.tp2).toFixed(0)} </span>}
                      {row.tp3!=null&&<span style={{color:T.green}}>TP3:{Number(row.tp3).toFixed(0)}</span>}
                    </div>
                  )}
                  <div style={{fontSize:9,color:T.textD,fontFamily:T.mono,lineHeight:1.35,
                    overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{info}</div>
                </div>);
              })}
              {filtered.length===0&&(
                <div style={{fontSize:10,color:T.textD,fontFamily:T.mono,
                  textAlign:'center',padding:32}}>
                  {signals.length===0?'No signals this session — LISTENER monitors Telegram channels'
                    :`No signals from ${chFilter||'this channel'}`}
                </div>
              )}
              <div style={{marginTop:4,fontSize:8,color:T.textD,fontFamily:T.mono}}>
                Source: SCRIBE signals_received · /api/signals
              </div>
            </div>
            );})()}

          {tab==='uploads'&&(
            <div style={{overflowY:'auto',height:'100%',padding:'12px 14px'}}>
              <div style={{fontSize:9,color:T.textD,fontFamily:T.mono,marginBottom:8,letterSpacing:1}}>
                Direct bot uploads + signal-room chart media events
              </div>
              {uploadEvents.map((e,i)=>{
                const raw=e.raw||{};
                const et=String(raw.event_type||'');
                const isFail=et.includes('FAILED');
                const c=isFail?T.red:(et.startsWith('AURUM_')?T.gold:T.cyan);
                return(
                  <div key={raw.id||`upload-${i}`} style={{
                    background:T.card,border:`1px solid ${T.border2}`,
                    borderLeft:`3px solid ${c}`,borderRadius:5,padding:'8px 10px',marginBottom:6
                  }}>
                    <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:4}}>
                      <div style={{display:'flex',gap:6,alignItems:'center'}}>
                        <Tag lbl={et} color={c} xs/>
                        <Tag lbl={(raw.triggered_by||'SYSTEM').toUpperCase()} color={CC[(raw.triggered_by||'SYSTEM').toUpperCase()]||T.textD} xs/>
                      </div>
                      <span style={{fontSize:9,color:T.textD,fontFamily:T.mono}}>
                        {fmtDateTime(raw.timestamp)}
                      </span>
                    </div>
                    <div style={{fontSize:9,color:T.textB,fontFamily:T.mono,lineHeight:1.4}}>
                      {raw.reason||'—'}
                    </div>
                    {raw.notes&&(
                      <div style={{fontSize:9,color:T.textD,fontFamily:T.mono,lineHeight:1.35,marginTop:4,whiteSpace:'pre-wrap'}}>
                        {String(raw.notes)}
                      </div>
                    )}
                  </div>
                );
              })}
              {uploadEvents.length===0&&(
                <div style={{fontSize:10,color:T.textD,fontFamily:T.mono,textAlign:'center',padding:36}}>
                  No upload/chart media events recorded yet.
                </div>
              )}
              <div style={{marginTop:4,fontSize:8,color:T.textD,fontFamily:T.mono}}>
                Source: SCRIBE signal_media · filtered from system_events (upload/chart event types)
              </div>
            </div>
          )}

          {tab==='perf'&&(
            <div style={{overflowY:'auto',height:'100%',padding:'12px 14px'}}>
              <div style={{fontSize:9,color:T.textD,fontFamily:T.mono,marginBottom:8,lineHeight:1.4}}>
                {D.performance_window?.label||`Closed trades in SCRIBE · rolling ${PERF_ROLLING_DAYS}d UTC`}
              </div>
              <div style={{fontSize:9,color:T.textD,fontFamily:T.mono,marginBottom:10}}>
                Last update: {fmtDateTime(D.timestamp)}
              </div>
              <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr',gap:8,marginBottom:14}}>
                {(()=>{const avgPv=D.performance?.avg_pip_value_usd!=null?Number(D.performance.avg_pip_value_usd):null;
                  const avgPvLbl=avgPv!=null?`${avgPv>=0?'+':''}$${avgPv.toFixed(2)}`:'—';
                  const avgPvColor=avgPv==null?T.textD:avgPv>=0?T.green:T.red;
                  return[['Win Rate',winRateLbl,T.green],
                  ['Avg Pips',avgPipsLbl,T.gold],
                  ['Avg Pip $',avgPvLbl,avgPvColor],
                  ['Total P&L',`$${(D.performance?.total_pnl||0).toFixed(2)}`,(D.performance?.total_pnl||0)>=0?T.green:T.red],
                  ['Trades',D.performance?.total||0,T.textBB],
                  ['Wins',D.performance?.wins||0,T.green],
                  ['Losses',D.performance?.losses||0,T.red],
                ]})().map(([l,v,c])=>(
                  <div key={l} style={{background:T.card,border:`1px solid ${T.border}`,
                    borderRadius:5,padding:'10px 12px',textAlign:'center'}}>
                    <div style={{fontSize:18,fontFamily:T.mono,color:c,fontWeight:700}}>{v}</div>
                    <div style={{fontSize:9,color:T.text,marginTop:3,letterSpacing:1}}>{l}</div>
                  </div>
                ))}
              </div>
              <div style={{background:T.card,border:`1px solid ${T.border}`,
                borderRadius:6,padding:14}}>
                <div style={{fontSize:9,color:T.textD,fontFamily:T.mono,marginBottom:8,letterSpacing:2}}>
                  CUMULATIVE P&L · {PERF_ROLLING_DAYS}D (UTC)</div>
                {pnlSpark&&pnlSpark.length>=2?(
                  <Sparkline data={pnlSpark} w={420} h={70} color={sparkColor}/>
                ):(
                  <div style={{fontSize:9,color:T.textD,fontFamily:T.mono,padding:'20px 8px'}}>
                    No closed trades in SCRIBE in the last {PERF_ROLLING_DAYS} days (UTC), or curve needs 1+ closes.</div>
                )}
              </div>
              <div style={{marginTop:4,fontSize:8,color:T.textD,fontFamily:T.mono}}>
                Source: SCRIBE trade_positions (rolling {PERF_ROLLING_DAYS}d) · /api/live + /api/pnl_curve
              </div>
            </div>
          )}

          {tab==='backtest'&&(
            <div style={{overflowY:'auto',height:'100%',padding:'12px 14px'}}>
              {/* Header */}
              <div style={{display:'flex',alignItems:'center',gap:8,marginBottom:10}}>
                <span style={{fontSize:9,color:T.cyan,fontFamily:T.mono,letterSpacing:2}}>🔬 BACKTEST — aurum_tester.db</span>
                <span style={{fontSize:9,color:T.textD,fontFamily:T.mono}}>{btRuns.length} run(s) stored</span>
              </div>
              {/* Run selector */}
              {btRuns.length===0?(
                <div style={{fontSize:9,color:T.textD,fontFamily:T.mono,padding:'20px 0'}}>
                  No backtest runs in aurum_tester.db yet. Run a tester backtest to populate.</div>
              ):(
                <>
                  <div style={{display:'flex',flexWrap:'wrap',gap:6,marginBottom:12}}>
                    {btRuns.map(r=>{
                      const isSel=btSelRun===r.aurum_run_id;
                      const isPinned=btPinnedRuns.includes(r.aurum_run_id);
                      return(
                        <div key={r.aurum_run_id} style={{display:'flex',alignItems:'center',gap:2}}>
                          <button type="button" onClick={()=>setBtSelRun(r.aurum_run_id)}
                            style={{padding:'4px 10px',fontFamily:T.mono,fontSize:9,cursor:'pointer',
                              borderRadius:4,
                              border:`1px solid ${isSel?T.gold:isPinned?T.cyan:T.border}`,
                              background:isSel?T.card:'transparent',
                              color:isSel?T.gold:isPinned?T.cyan:T.textD}}>
                            {isPinned&&<span style={{marginRight:3}}>📌</span>}
                            Run #{r.aurum_run_id}
                            {r.forge_version&&<span style={{marginLeft:4,color:T.textD}}>v{r.forge_version}</span>}
                            {r.total_pnl!=null&&<span style={{marginLeft:4,color:r.total_pnl>=0?T.green:T.red}}>
                              {r.total_pnl>=0?'+':''}{r.total_pnl?.toFixed(2)}</span>}
                          </button>
                          {/* pin toggle */}
                          <button type="button" title={isPinned?'Unpin run':'Pin as comparison baseline'}
                            onClick={e=>{
                              e.stopPropagation();
                              const next=isPinned
                                ? btPinnedRuns.filter(id=>id!==r.aurum_run_id)
                                : [...btPinnedRuns,r.aurum_run_id];
                              btPinnedRunsRef.current=next;
                              setBtPinnedRuns(next);
                            }}
                            style={{padding:'3px 5px',fontSize:9,cursor:'pointer',border:'none',
                              background:'transparent',color:isPinned?T.cyan:T.border,lineHeight:1}}>
                            📌
                          </button>
                        </div>
                      );
                    })}
                  </div>
                  {/* Run detail */}
                  {btDetail&&btDetail.meta&&btSelRun===btDetail.meta.aurum_run_id&&(()=>{
                    const p=btDetail.performance||{};
                    const m=btDetail.meta||{};
                    const wins=p.wins||0; const losses=p.losses||0;
                    const sparkData=(btDetail.pnl_curve||[]).map(x=>x.pnl);
                    const sparkColor=p.total_pnl>=0?T.green:T.red;
                    return(
                      <>
                        {/* Meta row + manual refresh */}
                        <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start',marginBottom:8}}>
                        <div style={{fontSize:9,color:T.textD,fontFamily:T.mono,lineHeight:1.6}}>
                          {m.symbol} · v{m.forge_version} · {m.scalper_mode}
                          {m.sim_start&&<> · sim start {m.sim_start}</>}
                          {m.balance&&<> · balance ${Number(m.balance).toFixed(0)}</>}
                          {' · '}first seen {(m.first_seen_utc||'').slice(0,16)} UTC
                        </div>
                          <button type="button" onClick={loadBtDetail} title="Refresh run detail"
                            style={{fontSize:9,fontFamily:T.mono,cursor:'pointer',padding:'2px 7px',
                              border:`1px solid ${T.border}`,borderRadius:3,background:'transparent',
                              color:T.textD,flexShrink:0,marginLeft:8}}>↻ Refresh</button>
                        </div>
                        {/* ── RUN ANALYSIS — first panel after meta, dynamic multi-compare ── */}
                        {btCompares.length>0&&(()=>{
                          const scroll=btCompares.length>2;
                          return(
                          <div style={{marginBottom:12}}>
                            <div style={{maxHeight:scroll?380:undefined,overflowY:scroll?'auto':undefined,
                              display:'flex',flexDirection:'column',gap:8}}>
                              {btCompares.map((cmp,ci)=>{
                                if(!cmp||!cmp.run_a||!cmp.run_b)return null;
                                const isPinnedB=btPinnedRuns.includes(cmp.run_b.aurum_run_id);
                                return(
                                <div key={ci} style={{background:T.card,border:`1px solid ${T.border}`,borderRadius:6,padding:'8px 10px'}}>
                                  <div style={{fontSize:9,color:T.cyan,fontFamily:T.mono,fontWeight:600,
                                    letterSpacing:1.5,marginBottom:6,display:'flex',alignItems:'center',flexWrap:'wrap',gap:5}}>
                                    <span>⚖ Run #{cmp.run_a.aurum_run_id} vs Run #{cmp.run_b.aurum_run_id}</span>
                                    {isPinnedB&&<span style={{color:T.cyan,fontSize:8}}>📌 pinned</span>}
                                    {cmp.winner&&cmp.winner!=='tie'
                                      ?<span style={{color:T.gold}}>· Winner #{cmp.winner}</span>
                                      :<span style={{color:T.textD}}>· Tie</span>}
                                  </div>
                                  <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:6,marginBottom:6}}>
                                    {[cmp.run_a,cmp.run_b].map(run=>(
                                      <div key={run.aurum_run_id} style={{padding:'5px 7px',background:T.bg,borderRadius:4,
                                        border:`1px solid ${cmp.winner===run.aurum_run_id?T.gold:isPinnedB&&run.aurum_run_id===cmp.run_b.aurum_run_id?T.cyan:T.border}`}}>
                                        <div style={{fontSize:9,color:T.gold,fontFamily:T.mono,fontWeight:600,marginBottom:3}}>
                                          Run #{run.aurum_run_id}
                                          {run.score!=null&&<span style={{marginLeft:5,color:T.cyan}}>{run.score}/100</span>}
                                        </div>
                                        {[
                                          ['P&L',`$${(run.total_pnl||0).toFixed(2)}`],
                                          ['Return',run.pnl_return_pct!=null?`${run.pnl_return_pct.toFixed(2)}%`:'n/a'],
                                          ['WR',run.win_rate_pct!=null?`${run.win_rate_pct}%`:'n/a'],
                                          ['Taken',run.taken??'—'],
                                          ['Losses',run.losses??'—'],
                                        ].map(([k,v])=>(
                                          <div key={k} style={{display:'flex',justifyContent:'space-between',
                                            fontSize:9,fontFamily:T.mono,color:T.textD,marginBottom:1}}>
                                            <span>{k}</span><span style={{color:T.text}}>{v}</span>
                                          </div>
                                        ))}
                                      </div>
                                    ))}
                                  </div>
                                  <div style={{display:'flex',flexWrap:'wrap',gap:3}}>
                                    {Object.entries(cmp.deltas||{}).filter(([k,v])=>v!=null&&v!==0&&
                                      ['total_pnl','pnl_return_pct','win_rate_pct','taken','losses','score'].includes(k)
                                    ).map(([k,v])=>{
                                      const pos=v>0,color=pos?T.green:T.red;
                                      const label=k==='pnl_return_pct'?'return%':k==='win_rate_pct'?'WR%':k==='total_pnl'?'P&L':k;
                                      return(
                                        <span key={k} style={{fontSize:8,fontFamily:T.mono,padding:'2px 5px',
                                          borderRadius:3,background:T.bg,color}}>
                                          {label} {pos?'+':''}{typeof v==='number'?v.toFixed(2):v}
                                        </span>
                                      );
                                    })}
                                  </div>
                                </div>
                                );
                              })}
                            </div>
                            <div style={{marginTop:5,fontSize:8,color:T.textD,fontFamily:T.mono}}>
                              {btCompares[0]?.note} · Source: /api/backtest/compare → backtest_compare.py
                            </div>
                          </div>
                          );
                        })()}
                        {/* Stat grid */}
                        <div style={{fontSize:9,color:T.textBB,fontFamily:T.mono,fontWeight:600,
                          letterSpacing:2,marginBottom:8}}>RUN STATISTICS</div>
                        <div style={{display:'grid',gridTemplateColumns:'repeat(5,1fr)',gap:5,marginBottom:10}}>
                          {[
                            ['P&L',`${p.total_pnl>=0?'+':''}$${(p.total_pnl||0).toFixed(2)}`,p.total_pnl>=0?T.green:T.red],
                            ['Win Rate',p.win_rate!=null?`${p.win_rate}%`:'—',T.green],
                            ['Trades',p.total||0,T.textBB],
                            ['Wins',wins,T.green],
                            ['Losses',losses,T.red],
                            ['Best Win',`$${(p.best_win||0).toFixed(2)}`,T.green],
                            ['Worst Loss',`$${(p.worst_loss||0).toFixed(2)}`,T.red],
                            ['TAKEN',btDetail.signals?.taken||0,T.gold],
                            ['Open',btDetail.signals?.open_at_end??'—',btDetail.signals?.open_at_end>0?T.amber:T.textD],
                            ['Skipped',btDetail.signals?.skipped||0,T.textD],
                          ].map(([l,v,c])=>(
                            <div key={l} style={{background:T.card,border:`1px solid ${T.border}`,
                              borderRadius:4,padding:'5px 6px',textAlign:'center'}}>
                              <div style={{fontSize:11,fontFamily:T.mono,color:c,fontWeight:700}}>{v}</div>
                              <div style={{fontSize:8,color:T.textD,marginTop:1,letterSpacing:.5}}>{l}</div>
                            </div>
                          ))}
                        </div>
                        <div style={{marginBottom:10,fontSize:8,color:T.textD,fontFamily:T.mono}}>
                          Source: aurum_tester.db forge_signals + forge_journal_trades · /api/backtest/run/:id
                        </div>
                        {/* P&L curve with labeled axes */}
                        {sparkData.length>=2&&(()=>{
                          const total=btDetail.pnl_curve?.length||sparkData.length;
                          const maxPnl=Math.max(...sparkData);
                          const minPnl=Math.min(...sparkData,0);
                          const rng=maxPnl-minPnl||1;
                          const PL=52,PB=22,PT=10,PR=10;
                          const CW=380,CH=96;
                          const cw=CW-PL-PR,ch=CH-PT-PB;
                          const pts=sparkData.map((v,i)=>
                            `${PL+(i/(sparkData.length-1))*cw},${PT+ch-((v-minPnl)/rng)*ch}`
                          ).join(' ');
                          const zeroY=PT+ch-((0-minPnl)/rng)*ch;
                          const showZero=minPnl<0&&maxPnl>0;
                          return(
                          <div style={{background:T.card,border:`1px solid ${T.border}`,borderRadius:6,padding:12,marginBottom:12}}>
                            <div style={{fontSize:9,color:T.textBB,fontFamily:T.mono,fontWeight:600,marginBottom:6,letterSpacing:1}}>CUMULATIVE P&amp;L</div>
                            <svg width={CW} height={CH} style={{overflow:'visible',display:'block'}}>
                              <defs><linearGradient id="btsg" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="0%" stopColor={sparkColor} stopOpacity=".25"/>
                                <stop offset="100%" stopColor={sparkColor} stopOpacity="0"/>
                              </linearGradient></defs>
                              {/* axes */}
                              <line x1={PL} y1={PT} x2={PL} y2={PT+ch} stroke={T.border2} strokeWidth={1}/>
                              <line x1={PL} y1={PT+ch} x2={PL+cw} y2={PT+ch} stroke={T.border2} strokeWidth={1}/>
                              {/* zero line */}
                              {showZero&&<line x1={PL} y1={zeroY} x2={PL+cw} y2={zeroY} stroke={T.border2} strokeWidth={1} strokeDasharray="4,3"/>}
                              {/* Y tick labels */}
                              <text x={PL-5} y={PT+5} textAnchor="end" fill={T.textB} fontSize={8} fontFamily="'Courier New',monospace">${maxPnl.toFixed(0)}</text>
                              {showZero&&<text x={PL-5} y={zeroY+3} textAnchor="end" fill={T.textB} fontSize={8} fontFamily="'Courier New',monospace">$0</text>}
                              <text x={PL-5} y={PT+ch} textAnchor="end" fill={T.textB} fontSize={8} fontFamily="'Courier New',monospace">${minPnl.toFixed(0)}</text>
                              {/* Y axis label — P&L Yield */}
                              <text x={10} y={PT+ch/2} textAnchor="middle" fill={T.text} fontSize={8} fontFamily="'Courier New',monospace"
                                transform={`rotate(-90,10,${PT+ch/2})`}>P&amp;L Yield ($)</text>
                              {/* X tick labels */}
                              <text x={PL} y={PT+ch+14} textAnchor="middle" fill={T.textB} fontSize={8} fontFamily="'Courier New',monospace">1</text>
                              <text x={PL+cw} y={PT+ch+14} textAnchor="middle" fill={T.textB} fontSize={8} fontFamily="'Courier New',monospace">{total}</text>
                              {/* X axis label */}
                              <text x={PL+cw/2} y={CH} textAnchor="middle" fill={T.text} fontSize={8} fontFamily="'Courier New',monospace">Trade #</text>
                              {/* chart fill + line */}
                              <polygon points={`${PL},${PT+ch} ${pts} ${PL+cw},${PT+ch}`} fill="url(#btsg)"/>
                              <polyline points={pts} fill="none" stroke={sparkColor} strokeWidth="1.5" strokeLinejoin="round"/>
                            </svg>
                            <div style={{marginTop:6,fontSize:8,color:T.textD,fontFamily:T.mono,lineHeight:1.4}}>
                              P&amp;L Yield — running sum of closed-trade profit/loss in USD across all TAKEN entries for this run.
                              Each point = cumulative P&amp;L after trade N. Source: <span style={{color:T.gold}}>forge_journal_trades</span> (aurum_tester.db).
                            </div>
                          </div>
                        );})()}
                        {/* TAKEN entries — shown before gate breakdown */}
                        {(btDetail.taken||[]).length>0&&(
                          <div style={{background:T.card,border:`1px solid ${T.border}`,borderRadius:6,padding:12,marginBottom:12}}>
                            <div style={{fontSize:9,color:T.textBB,fontFamily:T.mono,fontWeight:600,marginBottom:8,letterSpacing:1}}>TAKEN ENTRIES</div>
                            {/* header row — Section 508: min 9px, color ≥4.5:1 contrast */}
                            <div style={{display:'grid',gridTemplateColumns:'96px 52px 68px 76px 88px 52px 52px 64px',
                              gap:4,borderBottom:`1px solid ${T.border2}`,paddingBottom:5,marginBottom:2,
                              fontSize:9,color:T.textBB,fontFamily:T.mono,fontWeight:600,letterSpacing:.5}}>
                              <span>TIME (UTC)</span><span>DIR</span><span>SESSION</span>
                              <span>SETUP</span><span>OUTCOME</span>
                              <span>RSI</span><span>ADX</span><span style={{textAlign:'right'}}>P&amp;L</span>
                            </div>
                            {(btDetail.taken||[]).map((e,i)=>{
                              const outcome=e.trade_outcome||'—';
                              const isTP=outcome.startsWith('TP');
                              const isSL=outcome==='SL';
                              const isOpen=outcome==='OPEN';
                              const outcomeColor=isSL?T.red:isOpen?T.amber:isTP?T.gold:T.green;
                              const pnl=e.pnl||0;
                              const pnlColor=pnl>0?T.green:pnl<0?T.red:T.textB;
                              const sess=(e.session||'').toUpperCase();
                              const sessColor=sess.includes('LONDON')&&sess.includes('NEW_YORK')?T.teal
                                :sess.includes('LONDON')?T.blue
                                :sess.includes('NEW_YORK')||sess.includes('NY')?T.green
                                :sess.includes('SYDNEY')?T.purple
                                :sess.includes('ASIAN')||sess.includes('ASIA')?T.cyan:T.textB;
                              const sessShort=sess.replace('NEW_YORK','NY').replace('LONDON','LON')
                                .replace('SYDNEY','SYD').replace('ASIAN','ASIA').slice(0,12);
                              return(
                              <div key={i} style={{display:'grid',gridTemplateColumns:'96px 52px 68px 76px 88px 52px 52px 64px',
                                gap:4,borderBottom:`1px solid ${T.border}`,padding:'6px 0',fontSize:10,fontFamily:T.mono,alignItems:'center'}}>
                                <span style={{color:T.textBB}}>{(e.timestamp_utc||'').slice(0,16).replace('T',' ')}</span>
                                <span style={{color:e.direction==='BUY'?T.green:T.red,fontWeight:'bold'}}>{e.direction}</span>
                                <span style={{color:sessColor,fontWeight:600}}>{sessShort||'—'}</span>
                                <span style={{color:T.textB}}>{(e.setup_type||'').replace('BB_','')}</span>
                                <span style={{display:'inline-flex',alignItems:'center',gap:4}}>
                                  <span style={{background:outcomeColor+'28',color:outcomeColor,
                                    border:`1px solid ${outcomeColor}66`,borderRadius:3,
                                    padding:'2px 6px',fontSize:9,fontWeight:'bold',letterSpacing:.5}}>
                                    {outcome}
                                  </span>
                                  {e.close_comment&&!isSL&&(
                                    <span style={{color:T.textB,fontSize:9}} title={e.close_comment}>
                                      {e.close_comment.replace('tp ','@')}
                                    </span>
                                  )}
                                </span>
                                <span style={{color:T.textBB}}>RSI {e.rsi}</span>
                                <span style={{color:T.textBB}}>ADX {e.adx}</span>
                                <span style={{color:pnlColor,textAlign:'right',fontWeight:'bold'}}>
                                  {pnl>0?'+':''}{pnl!==0?`$${pnl.toFixed(2)}`:'—'}
                                </span>
                              </div>
                            );})}
                          </div>
                        )}
                        {/* Gate breakdown with legend explanations */}
                        {(btDetail.gates||[]).length>0&&(
                          <div style={{background:T.card,border:`1px solid ${T.border}`,borderRadius:6,padding:12,marginBottom:12}}>
                            <div style={{fontSize:9,color:T.textBB,fontFamily:T.mono,fontWeight:600,marginBottom:8,letterSpacing:1}}>GATE BREAKDOWN (SKIP)</div>
                            {(btDetail.gates||[]).map(g=>{
                              const leg=gateLegend[g.gate_reason]||{};
                              return(
                              <div key={g.gate_reason} style={{borderBottom:`1px solid ${T.border}`,padding:'6px 0'}}>
                                {/* row 1: technical name + count */}
                                <div style={{display:'flex',justifyContent:'space-between',alignItems:'baseline'}}>
                                  <span style={{color:T.textBB,fontSize:10,fontFamily:T.mono}}>{g.gate_reason}</span>
                                  <span style={{color:T.amber,fontSize:10,fontFamily:T.mono,fontWeight:'bold',marginLeft:8,flexShrink:0}}>{g.cnt.toLocaleString()}</span>
                                </div>
                                {/* row 2: human label */}
                                {leg.label&&(
                                  <div style={{color:T.green,fontSize:9,fontFamily:T.mono,marginTop:1}}>↳ {leg.label}</div>
                                )}
                                {/* row 3: plain-English explanation */}
                                {leg.explanation&&(
                                  <div style={{color:T.textB,fontSize:9,fontFamily:'sans-serif',marginTop:2,lineHeight:1.4,paddingLeft:10}}>
                                    {leg.explanation}
                                  </div>
                                )}
                              </div>
                            );})}
                          </div>
                        )}
                      </>
                    );
                  })()}
                </>
              )}
            </div>
          )}
          {tab==='indicators'&&(
            <div style={{overflowY:'auto',height:'100%',padding:'12px 14px'}}>
              <div style={{fontSize:10,color:T.textBB,fontFamily:T.mono,fontWeight:600,marginBottom:12,letterSpacing:1}}>
                📊 FORGE INDICATOR REFERENCE
              </div>
              <div style={{fontSize:9,color:T.textB,fontFamily:'sans-serif',marginBottom:16,lineHeight:1.5}}>
                Every indicator FORGE uses — parameters, what it measures, and how it gates entries. Source: <span style={{color:T.gold,fontFamily:T.mono}}>config/indicator_legend.json</span>
              </div>
              {Object.keys(indLegend).length===0?(
                <div style={{color:T.textD,fontSize:9}}>Loading indicator definitions…</div>
              ):(
                Object.entries(indLegend).map(([key,ind])=>(
                  <div key={key} style={{background:T.card,border:`1px solid ${ind.color||T.border}44`,
                    borderLeft:`3px solid ${ind.color||T.border}`,borderRadius:6,padding:12,marginBottom:10}}>
                    {/* Header */}
                    <div style={{display:'flex',alignItems:'baseline',gap:10,marginBottom:4}}>
                      <span style={{fontSize:14,fontFamily:T.mono,fontWeight:700,color:ind.color||T.gold}}>{ind.acronym||key}</span>
                      <span style={{fontSize:9,color:T.textBB,fontFamily:T.mono}}>{ind.full_name}</span>
                      <span style={{marginLeft:'auto',fontSize:9,color:ind.color||T.textD,fontFamily:T.mono,
                        background:(ind.color||T.gold)+'18',borderRadius:3,padding:'1px 6px'}}>
                        {ind.category}
                      </span>
                    </div>
                    {/* Params + timeframes */}
                    <div style={{display:'flex',gap:12,marginBottom:6,flexWrap:'wrap'}}>
                      {ind.forge_params&&(
                        <span style={{fontSize:9,color:T.textD,fontFamily:T.mono}}>
                          <span style={{color:T.textB}}>params:</span> {ind.forge_params}
                        </span>
                      )}
                      {ind.timeframes&&(
                        <span style={{fontSize:9,color:T.textD,fontFamily:T.mono}}>
                          <span style={{color:T.textB}}>TF:</span> {ind.timeframes.join(' · ')}
                        </span>
                      )}
                      {ind.range&&(
                        <span style={{fontSize:9,color:T.textD,fontFamily:T.mono}}>
                          <span style={{color:T.textB}}>range:</span> {ind.range}
                        </span>
                      )}
                    </div>
                    {/* What it measures */}
                    <div style={{fontSize:9,color:T.textBB,fontFamily:'sans-serif',lineHeight:1.5,marginBottom:6}}>
                      {ind.what_it_measures}
                    </div>
                    {/* Reading guide */}
                    {ind.reading_guide&&(
                      <div style={{marginBottom:6}}>
                        {Object.entries(ind.reading_guide).map(([k,v])=>(
                          <div key={k} style={{display:'flex',gap:6,padding:'2px 0',borderTop:`1px solid ${T.border}`}}>
                            <span style={{fontSize:9,color:ind.color||T.gold,fontFamily:T.mono,minWidth:120,flexShrink:0}}>{k.replace(/_/g,' ')}</span>
                            <span style={{fontSize:9,color:T.textB,fontFamily:'sans-serif'}}>{v}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    {/* FORGE usage */}
                    <div style={{background:T.row,borderRadius:4,padding:'6px 8px'}}>
                      <div style={{fontSize:9,color:T.gold,fontFamily:T.mono,marginBottom:2}}>HOW FORGE USES IT</div>
                      <div style={{fontSize:9,color:T.textB,fontFamily:'sans-serif',lineHeight:1.5}}>{ind.forge_usage}</div>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
        {/* AURUM panel — drag the top border to resize */}
        <div style={{borderTop:`2px solid ${T.border}`,flexShrink:0,height:aurumH,display:'flex',flexDirection:'column',position:'relative'}}>
          {/* drag handle */}
          <div
            title="Drag to resize AURUM panel"
            onMouseDown={e=>{
              e.preventDefault();
              const startY=e.clientY;
              const startH=aurumH;
              const onMove=ev=>{
                const delta=startY-ev.clientY;
                setAurumH(Math.max(140,Math.min(600,startH+delta)));
              };
              const onUp=()=>{
                document.removeEventListener('mousemove',onMove);
                document.removeEventListener('mouseup',onUp);
              };
              document.addEventListener('mousemove',onMove);
              document.addEventListener('mouseup',onUp);
            }}
            style={{position:'absolute',top:-4,left:0,right:0,height:8,cursor:'row-resize',
              zIndex:10,display:'flex',alignItems:'center',justifyContent:'center'}}>
            <div style={{width:36,height:3,borderRadius:2,background:T.border2,opacity:.6}}/>
          </div>
          <div style={{flex:1,overflow:'hidden',padding:'8px 10px',minHeight:0}}>
            <AurumChat liveData={D}/>
          </div>
        </div>
      </div>

      {/* RIGHT — FORGE + LENS/TradingView data panel */}
      <div style={{borderLeft:`1px solid ${T.border}`,display:'flex',flexDirection:'column',
        overflow:'hidden',minHeight:0}}>
      <div style={{padding:'12px 10px',overflowY:'auto',overscrollBehavior:'contain',
        display:'flex',flexDirection:'column',gap:14}}>
        <div>
          <PT ch="◆ FORGE · execution quote" color={T.amber}/>
          {ex.usable?(
            <>
              <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:8,marginBottom:6}}>
                <div style={{background:T.card,border:`1px solid ${T.border}`,borderRadius:5,padding:'8px 10px'}}>
                  <div style={{fontSize:9,color:T.textB,fontFamily:T.mono,marginBottom:3,
                    fontWeight:600,letterSpacing:0.3}}>SELL (bid)</div>
                  <div style={{fontFamily:T.mono,fontSize:17,color:T.textBB,fontWeight:700,
                    letterSpacing:0.5}}>
                    ${Number(ex.bid).toFixed(2)}</div>
                </div>
                <div style={{background:T.card,border:`1px solid ${T.border}`,borderRadius:5,padding:'8px 10px'}}>
                  <div style={{fontSize:9,color:T.textB,fontFamily:T.mono,marginBottom:3,
                    fontWeight:600,letterSpacing:0.3}}>BUY (ask)</div>
                  <div style={{fontFamily:T.mono,fontSize:17,color:T.textBB,fontWeight:700,
                    letterSpacing:0.5}}>
                    ${Number(ex.ask).toFixed(2)}</div>
                </div>
              </div>
              <div style={{fontSize:9,color:T.textB,fontFamily:T.mono,marginBottom:10,lineHeight:1.55}}>
                <span style={{color:T.textBB,fontWeight:600}}>{sym}</span>
                {' · file age '}{fmtAgeSec(ex.age_sec)}
                {' · spread '}
                <span style={{color:T.amber,fontWeight:600}}>${Number(ex.spread_usd).toFixed(2)}</span>
                {ex.spread_points!=null?` (~${ex.spread_points} pt)`:''}
                <br/><span style={{color:T.textBB}}>FORGE</span>{' '}{ex.timestamp_utc||'—'}
              </div>
            </>
          ):(
            <div style={{marginBottom:10,padding:'8px 10px',background:'rgba(245,158,11,0.08)',
              border:`1px solid ${T.amber}`,borderRadius:5}}>
              <div style={{fontSize:9,color:T.amber,fontFamily:T.mono,fontWeight:700,marginBottom:4}}>
                NO LIVE BROKER QUOTE</div>
              <div style={{fontSize:9,color:T.text,fontFamily:T.mono,lineHeight:1.4}}>
                {ex.stale_reason||'market_data.json missing or unusable.'}
              </div>
              <div style={{fontSize:9,color:T.textB,fontFamily:T.mono,marginTop:6,lineHeight:1.45}}>
                File age: {fmtAgeSec(ex.age_sec)} · {ex.timestamp_utc||'no timestamp'}
              </div>
            </div>
          )}

          <div style={{marginTop:2,fontSize:8,color:T.textD,fontFamily:T.mono}}>
            Source: MT5/market_data.json price block · FORGE EA writes every tick
          </div>

          {/* ── OsMA GATE panel (FORGE 2.7.7+) ───────────────────────── */}
          <div>
            <PT ch={"◈ OsMA GATE · "+(D.forge_version||"FORGE")} color={T.amber}/>
            <div style={{padding:'7px 9px',background:T.card,border:`1px solid ${T.border2}`,borderRadius:4}}>
              {/* OsMA value + bias */}
              <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:6}}>
                <span style={{fontSize:9,color:T.textB,fontFamily:T.mono,fontWeight:600}}>
                  {`OsMA(${sg.macd_fast||3},${sg.macd_slow||10},${sg.macd_signal||16}) M5`}
                </span>
                <span style={{fontFamily:T.mono,fontSize:12,fontWeight:700,
                  color:sg.osma_m5==null?T.textD:sg.osma_m5>0?T.green:sg.osma_m5<0?T.red:T.textBB}}>
                  {sg.osma_m5!=null?((sg.osma_m5>0?'+':'')+sg.osma_m5.toFixed(5)):'—'}
                  {sg.osma_bias!=null&&(
                    <span style={{marginLeft:5,fontSize:9,
                      color:sg.osma_bias==='bull'?T.green:sg.osma_bias==='bear'?T.red:T.textD}}>
                      {sg.osma_bias==='bull'?'BULL':sg.osma_bias==='bear'?'BEAR':'FLAT'}
                    </span>
                  )}
                </span>
              </div>
              {/* Gate rows */}
              {[
                ['SELL gate','Q2 req (neg↓)',sg.require_macd_sell,sg.sell_osma_pass],
                ['BUY  gate','Q0 req (pos↑)',sg.require_macd_buy, sg.buy_osma_pass],
              ].map(([lbl,req,on,pass])=>(
                <div key={lbl} style={{display:'flex',justifyContent:'space-between',
                  alignItems:'center',padding:'3px 0',borderTop:`1px solid ${T.border}`}}>
                  <span style={{fontSize:9,color:T.textB,fontFamily:T.mono,fontWeight:600,width:58}}>{lbl}</span>
                  <span style={{fontSize:9,fontFamily:T.mono,color:on?T.amber:T.textD,width:28,textAlign:'center'}}>
                    {on?'ON':'OFF'}
                  </span>
                  <span style={{fontSize:9,fontFamily:T.mono,color:T.textD,flex:1,textAlign:'center'}}>{req}</span>
                  <span style={{fontSize:13,fontFamily:T.mono,fontWeight:700,width:16,textAlign:'right',
                    color:pass==null?T.textD:pass?T.green:T.red}}>
                    {pass==null?(on?'?':'—'):pass?'✓':'✗'}
                  </span>
                </div>
              ))}
              {/* Session / ADX block footnote */}
              {(sg.session_ny_sell_cutoff||sg.adx_sell_block)&&(
                <div style={{marginTop:5,fontSize:9,color:T.textD,fontFamily:T.mono,lineHeight:1.4}}>
                  {sg.session_ny_sell_cutoff?`SELL cutoff ≥${sg.session_ny_sell_cutoff}:00 UTC  `:null}
                  {sg.adx_sell_block?`ADX≥${sg.adx_sell_block} blocks SELL`:null}
                </div>
              )}
            </div>
          </div>
          <div style={{marginTop:2,fontSize:8,color:T.textD,fontFamily:T.mono}}>
            Source: MT5/market_data.json indicators_m5 (iOsMA) · FORGE EA writes every tick
          </div>

          <PT ch="🔭 TradingView · indicators" color={T.cyan}/>
          <div style={{display:'flex',justifyContent:'space-between',alignItems:'baseline',marginBottom:6}}>
            <span style={{fontFamily:T.mono,fontSize:16,color:T.textBB,fontWeight:700,letterSpacing:0.5}}>
              {tv.last!=null?'$'+Number(tv.last).toFixed(2):'—'}</span>
            <span style={{fontFamily:T.mono,fontSize:10,color:T.cyan,fontWeight:600}}>last (FX)</span>
          </div>
          <div style={{fontSize:9,color:T.textB,fontFamily:T.mono,marginBottom:8,lineHeight:1.55}}>
            <span style={{color:T.textBB,fontWeight:600}}>{tv.timeframe||'—'}</span>
            {' · snapshot '}{tvSnapAge}
            {tv.divergence_from_mt5_usd!=null&&ex.usable?(
              <span><br/><span style={{color:T.amber,fontWeight:600}}>
                Δ vs MT5 mid: {tv.divergence_from_mt5_usd>=0?'+':''}{Number(tv.divergence_from_mt5_usd).toFixed(2)} USD (different venue / symbol)
              </span></span>
            ):null}
            {!ex.usable&&tv.last!=null?(
              <span><br/><span style={{color:T.textB}}>
                Use this TV last as spot reference while FORGE is stale; it is not your broker fill.
              </span></span>
            ):null}
          </div>
          {[['RSI 14',tv.rsi!=null?tv.rsi.toFixed(1):'—',tv.rsi!=null?(tv.rsi>70?T.red:tv.rsi<30?T.green:T.textBB):T.textBB],
            ['MACD',tv.macd_hist!=null?(tv.macd_hist>0?'+'+tv.macd_hist.toFixed(5):tv.macd_hist.toFixed(5)):'—',tv.macd_hist!=null?(tv.macd_hist>0?T.green:T.red):T.textBB],
            ['BB Rtg',tv.bb_rating!=null?(tv.bb_rating>0?'+'+tv.bb_rating:tv.bb_rating):'—',tv.bb_rating!=null?(tv.bb_rating>0?T.green:T.textBB):T.textBB],
            ['ADX',tv.adx!=null?tv.adx.toFixed(1):'—',T.amber],
            ['DI+',tv.di_plus!=null?tv.di_plus.toFixed(2):'—',T.green],
            ['DI-',tv.di_minus!=null?tv.di_minus.toFixed(2):'—',T.red],
            ['EMA20',tv.ema_20!=null?'$'+tv.ema_20.toFixed(1):'—',T.textBB],
            ['EMA50',tv.ema_50!=null?'$'+tv.ema_50.toFixed(1):'—',T.textBB],
          ].map(([l,v,c])=>(
            <div key={l} style={{display:'flex',justifyContent:'space-between',
              alignItems:'center',padding:'4px 0',borderBottom:`1px solid ${T.border}`}}>
              <span style={{fontSize:9,color:T.textB,fontFamily:T.mono,width:52,fontWeight:600}}>{l}</span>
              <span style={{fontSize:11,fontFamily:T.mono,color:c,fontWeight:600}}>{v}</span>
            </div>
          ))}
          <div style={{marginTop:8,padding:'6px 8px',background:T.card,border:`1px solid ${T.border2}`,borderRadius:4}}>
            <div style={{fontSize:9,color:T.textD,fontFamily:T.mono,marginBottom:4,letterSpacing:1}}>DMI STUDY</div>
            <div style={{fontSize:9,color:T.cyan,fontFamily:T.mono,lineHeight:1.4}}>
              {tv.dmi_present?(tv.dmi_study||'present'):'missing on chart'}
            </div>
            <div style={{fontSize:9,color:T.text,fontFamily:T.mono,lineHeight:1.35,marginTop:4}}>
              ADX {tv.adx!=null?tv.adx.toFixed(1):'—'} · DI+ {tv.di_plus!=null?tv.di_plus.toFixed(2):'—'} · DI- {tv.di_minus!=null?tv.di_minus.toFixed(2):'—'}
            </div>
          </div>
          <div style={{marginTop:6,padding:'6px 8px',background:tv.order_block_present?T.greenBg:T.amberBg,border:`1px solid ${tv.order_block_present?T.green:T.amber}`,borderRadius:4}}>
            <div style={{fontSize:9,color:T.textD,fontFamily:T.mono,marginBottom:3,letterSpacing:1}}>ORDER BLOCK DETECTOR</div>
            <div style={{fontSize:9,color:tv.order_block_present?T.green:T.amber,fontFamily:T.mono,lineHeight:1.35}}>
              {tv.order_block_present?(tv.order_block_study||'present on chart'):'missing on chart'}
            </div>
            {tv.order_block_values&&Object.keys(tv.order_block_values).length>0&&(
              <div style={{fontSize:9,color:T.text,fontFamily:T.mono,marginTop:4,lineHeight:1.35}}>
                {tv.order_block_values.zone_count!=null?(
                  <span>zone_count:{tv.order_block_values.zone_count}</span>
                ):null}
                {Array.isArray(tv.order_block_values.zones)&&tv.order_block_values.zones.length>0?(
                  <div style={{marginTop:4}}>
                    {tv.order_block_values.zones.slice(0,6).map((z,idx)=>(
                      <div key={idx}>Z{idx+1}: H {z.high} · L {z.low}</div>
                    ))}
                  </div>
                ):(
                  Object.entries(tv.order_block_values)
                    .filter(([k])=>k!=='zones')
                    .map(([k,v])=>`${k}:${v}`)
                    .join(' · ')
                )}
              </div>
            )}
          </div>
          <div style={{marginTop:7,padding:'5px 8px',background:T.cyanBg,
            border:`1px solid ${T.cyan}`,borderRadius:4,textAlign:'center'}}>
            <span style={{fontFamily:T.mono,fontSize:10,color:T.cyan,letterSpacing:1.5,fontWeight:600}}>
              TV suggest: {tv.tv_recommend==null?'N/A':tv.tv_recommend}
              {tv.tv_recommend_source?` (${tv.tv_recommend_source})`:''}
            </span>
          </div>
          {tv.tv_brief&&(
            <div style={{marginTop:6,padding:'6px 8px',background:T.card,border:`1px solid ${T.border2}`,borderRadius:4}}>
              <div style={{fontSize:9,color:T.textD,fontFamily:T.mono,marginBottom:3,letterSpacing:1}}>
                TV BRIEF {tv.tv_brief_source?`(${tv.tv_brief_source})`:''}
              </div>
              <div style={{fontSize:9,color:T.text,fontFamily:T.mono,lineHeight:1.35,whiteSpace:'pre-wrap'}}>
                {String(tv.tv_brief).slice(0,280)}
              </div>
            </div>
          )}
          <div style={{marginTop:4,fontSize:8,color:T.textD,fontFamily:T.mono}}>
            Source: config/lens_snapshot.json · LENS/TV MCP poller writes on each snapshot
          </div>
          <PT ch="🧪 AUTO_SCALPER readiness" color={asrReady?T.green:T.amber}/>
          <div style={{padding:'6px 8px',background:T.card,border:`1px solid ${T.border2}`,borderRadius:4,marginBottom:6}}>
            {autoscalperConditions?(
              <>
                <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:4}}>
                  <Tag lbl={asrReady?(asrDirection?`READY·${asrDirection}`:'READY'):'BLOCKED'} color={asrReadyColor}/>
                  <span style={{fontSize:9,color:T.textD,fontFamily:T.mono}}>
                    {fmtDateTime(asr.timestamp)}
                  </span>
                </div>
                {asrTesterMode&&(
                  <div style={{fontSize:9,color:T.cyan,fontFamily:T.mono,marginBottom:4,padding:'2px 5px',
                    background:'rgba(6,182,212,0.08)',border:`1px solid ${T.cyan}`,borderRadius:3}}>
                    STRATEGY TESTER — mt5 timestamps are simulated
                  </div>
                )}
                <div style={{fontSize:9,color:T.textB,fontFamily:T.mono,lineHeight:1.4}}>
                  prefilters <span style={{color:asrPrefilterPass?T.green:T.red}}>{asrPrefilterPass?'PASS':'FAIL'}</span>
                  {' · '}h1 {asrPref.h1_bias||'UNKNOWN'}
                  {' · '}{asrPref.h1_bias==='BULL'?'lowerBB':'upperBB'}{' '}
                  {asrPref.h1_bias==='BULL'
                    ?(asrSetup.near_lower_bb===true?'YES':asrSetup.near_lower_bb===false?'NO':'—')
                    :(asrSetup.near_upper_bb===true?'YES':asrSetup.near_upper_bb===false?'NO':'—')}
                </div>
                <div style={{fontSize:9,color:T.text,fontFamily:T.mono,lineHeight:1.35,marginTop:3}}>
                  quality {asrSetup.indicator_data_quality||'—'}
                  {' · '}open {asrPref.open_groups!=null?asrPref.open_groups:'—'}/{asrPref.max_groups!=null?asrPref.max_groups:'—'}
                  {' · '}mt5 {asrTesterMode?'tester':asrPref.mt5_fresh===true?'fresh':asrPref.mt5_fresh===false?'stale':'—'}
                </div>
                {/* TradingView LENS — what AURUM reads to make the AUTO_SCALPER decision */}
                {(asrLens.rsi!=null||asrLens.macd_hist!=null)&&(
                  <div style={{marginTop:5,padding:'4px 6px',background:T.row,
                    border:`1px solid ${T.border}`,borderRadius:3}}>
                    <div style={{fontSize:9,color:T.textD,fontFamily:T.mono,marginBottom:3,letterSpacing:0.8}}>
                      TV LENS · AURUM context
                    </div>
                    <div style={{fontSize:9,fontFamily:T.mono,lineHeight:1.5}}>
                      {asrLens.rsi!=null&&(
                        <span style={{marginRight:8}}>
                          RSI <span style={{color:asrLens.rsi>60?T.red:asrLens.rsi<40?T.green:T.textBB,fontWeight:600}}>
                            {asrLens.rsi.toFixed(1)}
                          </span>
                        </span>
                      )}
                      {asrLens.macd_hist!=null&&(
                        <span style={{marginRight:8}}>
                          MACD <span style={{color:asrLens.macd_hist<0?T.green:T.red,fontWeight:600}}>
                            {asrLens.macd_hist>0?'+':''}{asrLens.macd_hist.toFixed(3)}
                          </span>
                        </span>
                      )}
                      {asrLens.adx!=null&&(
                        <span style={{marginRight:8}}>
                          ADX <span style={{color:T.amber,fontWeight:600}}>{asrLens.adx.toFixed(1)}</span>
                        </span>
                      )}
                      {asrLens.bb_rating!=null&&(
                        <span>
                          BB <span style={{color:asrLens.bb_rating>0?T.green:asrLens.bb_rating<0?T.red:T.textD,fontWeight:600}}>
                            {asrLens.bb_rating>0?'+':''}{asrLens.bb_rating}
                          </span>
                        </span>
                      )}
                    </div>
                    {(asrLens.di_plus!=null&&asrLens.di_minus!=null)&&(
                      <div style={{fontSize:9,color:T.textB,fontFamily:T.mono,marginTop:2}}>
                        DI+ {asrLens.di_plus.toFixed(1)} · DI- {asrLens.di_minus.toFixed(1)}
                        {' · '}<span style={{color:asrLens.di_bear?T.red:T.green}}>
                          {asrLens.di_bear?'BEAR dir':'BULL dir'}
                        </span>
                      </div>
                    )}
                    {asrLens.age_sec!=null&&(
                      <div style={{fontSize:9,color:T.textD,fontFamily:T.mono,marginTop:2}}>
                        lens age {asrLens.age_sec.toFixed(0)}s
                      </div>
                    )}
                  </div>
                )}
                {asrFailed.length>0&&(
                  <div style={{fontSize:9,color:T.amber,fontFamily:T.mono,lineHeight:1.35,marginTop:4}}>
                    failed: {asrFailed.slice(0,4).join(', ')}
                  </div>
                )}
                {asrLatest&&(
                  <div style={{fontSize:9,color:T.cyan,fontFamily:T.mono,lineHeight:1.35,marginTop:4}}>
                    latest: {asrLatest.decision||'—'} · {fmtDateTime(asrLatest.timestamp)}
                  </div>
                )}
              </>
            ):(
              <div style={{fontSize:9,color:T.textD,fontFamily:T.mono,lineHeight:1.35}}>
                Endpoint unavailable{autoscalperConditionsError?`: ${autoscalperConditionsError}`:''}
              </div>
            )}
          </div>
          <div style={{marginTop:2,fontSize:8,color:T.textD,fontFamily:T.mono}}>
            Source: /api/autoscalper/conditions → bridge.py AUTO_SCALPER logic
          </div>

          <PT ch="🧭 Regime Engine" color={T.purple}/>
          <div style={{padding:'6px 8px',background:T.card,border:`1px solid ${T.border2}`,borderRadius:4,marginBottom:6}}>
            <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:4}}>
              <Tag lbl={regimeMode} color={regimeModeColor}/>
              <span style={{fontSize:9,color:T.textD,fontFamily:T.mono}}>
                {regimeCfg.enabled?'enabled':'disabled'}
              </span>
            </div>
            <div style={{fontSize:9,color:T.textB,fontFamily:T.mono,lineHeight:1.45}}>
              <span style={{color:T.textD}}>Regime:</span> {regimeCurrent.label||'UNKNOWN'} ·
              <span style={{color:T.gold}}> {regimeConfPct}</span>
              <br/>
              <span style={{color:T.textD}}>Model:</span> {regimeCurrent.model_name||'—'}
              <span style={{color:T.textD}}> · age </span>{fmtAgeSec(regimeCurrent.age_sec)}
              {!!regimeCurrent.stale&&<span style={{color:T.amber}}> · stale</span>}
            </div>
            {/* Posterior probability distribution */}
            {Object.keys(regimePosterior).length>0&&(
              <div style={{display:'flex',gap:6,marginTop:5,flexWrap:'wrap'}}>
                {Object.entries(regimePosterior).sort((a,b)=>b[1]-a[1]).map(([lbl,prob])=>(
                  <span key={lbl} style={{fontSize:9,fontFamily:T.mono,
                    color:lbl===regimeCurrent.label?T.gold:T.textD}}>
                    {lbl} {Math.round(prob*100)}%
                  </span>
                ))}
              </div>
            )}
            {/* LENS vs MT5 source indicator */}
            {regimeFeatures.source&&(
              <div style={{fontSize:9,color:T.textD,fontFamily:T.mono,marginTop:4,lineHeight:1.4}}>
                src <span style={{color:regimeFeatures.lens_used?T.cyan:T.amber}}>
                  {regimeFeatures.source}
                </span>
                {regimeFeatures.rsi!=null&&` · RSI ${Number(regimeFeatures.rsi).toFixed(1)}`}
                {regimeFeatures.macd_hist!=null&&` · MACD ${Number(regimeFeatures.macd_hist).toFixed(3)}`}
                {regimeFeatures.adx!=null&&` · ADX ${Number(regimeFeatures.adx).toFixed(1)}`}
              </div>
            )}
            {(regimeCurrent.entry_gate_reason||regimeCurrent.fallback_reason)&&(
              <div style={{fontSize:9,color:T.amber,fontFamily:T.mono,marginTop:4,lineHeight:1.35}}>
                gate: {regimeCurrent.entry_gate_reason||'—'}
                {regimeCurrent.fallback_reason?` · fallback: ${regimeCurrent.fallback_reason}`:''}
              </div>
            )}
          </div>

          <div style={{padding:'6px 8px',background:T.card,border:`1px solid ${T.border2}`,borderRadius:4,marginBottom:6}}>
            <div style={{fontSize:9,color:T.textD,fontFamily:T.mono,marginBottom:4,letterSpacing:1}}>
              TRANSITIONS (24H)
            </div>
            {regimeTransitions.slice(0,4).map((tr,i)=>(
              <div key={`${tr.timestamp||i}-${i}`} style={{fontSize:9,color:T.textB,fontFamily:T.mono,lineHeight:1.35,marginBottom:3}}>
                {tr.from||'?'} → <span style={{color:T.cyan}}>{tr.to||'?'}</span>
                <span style={{color:T.textD}}> · {fmtDateTime(tr.timestamp)}</span>
                {tr.stale&&<span style={{color:T.amber}}> stale</span>}
              </div>
            ))}
            {regimeTransitions.length===0&&(
              <div style={{fontSize:9,color:T.textD,fontFamily:T.mono}}>No transitions in window</div>
            )}
          </div>

          <div style={{padding:'6px 8px',background:T.card,border:`1px solid ${T.border2}`,borderRadius:4}}>
            <div style={{fontSize:9,color:T.textD,fontFamily:T.mono,marginBottom:4,letterSpacing:1}}>
              REGIME METRICS ({regimePerf.days||30}D)
            </div>
            <div style={{fontSize:9,color:T.text,fontFamily:T.mono,lineHeight:1.4,marginBottom:4}}>
              snapshots {regimePerf.snapshot_count||0} · fallback {regimePerf.fallback_rate||0}%
            </div>
            {regimeRows.map((row,i)=>(
              <div key={`${row.regime_label||i}-${i}`} style={{display:'flex',justifyContent:'space-between',fontSize:9,fontFamily:T.mono,lineHeight:1.45}}>
                <span style={{color:row.regime_label===regimeCurrent.label?T.gold:T.textB}}>
                  {row.regime_label||'UNKNOWN'} ({row.total||0})
                </span>
                <span style={{color:(row.total_pnl||0)>=0?T.green:T.red}}>
                  {(row.total_pnl||0)>=0?'+':''}{Number(row.total_pnl||0).toFixed(2)}
                </span>
              </div>
            ))}
            {regimeRows.length===0&&(
              <div style={{fontSize:9,color:T.textD,fontFamily:T.mono}}>No closed trades with regime labels yet</div>
            )}
          </div>
          <div style={{marginTop:4,fontSize:8,color:T.textD,fontFamily:T.mono}}>
            Source: config/status.json → python/regime.py (HMM inference) · /api/live
          </div>
        </div>
      </div>
    </div>
    </div>

    {/* FOOTER */}
    <div style={{borderTop:`1px solid ${T.border}`,padding:'4px 16px',
      display:'flex',justifyContent:'space-between',alignItems:'center',
      fontSize:9,color:T.textD,fontFamily:T.mono,flexShrink:0,background:T.panel}}>
      <span>ATHENA · /api/live: execution + tradingview · FORGE + TV MCP · SCRIBE</span>
      {!connected&&<span style={{color:T.amber}}>⚠ DEMO — run bridge.py + athena_api.py for live</span>}
      <span>Tick {tick} · 3s poll</span>
    </div>
  </div>);
}

ReactDOM.createRoot(document.getElementById('root')).render(<ATHENA/>);
