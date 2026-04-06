const {useState,useEffect,useRef,useMemo} = React;
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

const Dot=({ok,sz=6,b=false})=>(<div className={b&&ok?'blink':''}
  style={{width:sz,height:sz,borderRadius:'50%',flexShrink:0,
    background:ok?T.green:T.red,boxShadow:`0 0 ${sz+2}px ${ok?T.green:T.red}55`}}/>);
const Tag=({lbl,color,xs=false})=>(<span style={{fontSize:xs?6:7,fontFamily:T.mono,
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
        <div style={{fontSize:7,color:T.textD,fontFamily:T.mono,letterSpacing:1,marginBottom:3}}>
          HEADLINES
        </div>
        <div style={{fontSize:7,color:T.textD,fontFamily:T.mono,lineHeight:1.4,padding:'6px 0'}}>
          {hasErr?`RSS error: ${String(err[0]).slice(0,120)}`:'No headlines yet — wait for BRIDGE SENTINEL tick (~60s) or check docs/SENTINEL.md'}
        </div>
      </div>
    );
  }
  const cap=24,show=rows.slice(0,cap);
  return(
    <div style={{marginTop:8}}>
      <div style={{fontSize:7,color:T.textD,fontFamily:T.mono,letterSpacing:1,marginBottom:4,
        display:'flex',justifyContent:'space-between',alignItems:'baseline',gap:6}}>
        <span>HEADLINES</span>
        <span style={{color:T.textD}}>{rows.length}{rows.length>cap?` · top ${cap}`:''}</span>
      </div>
      <div style={{maxHeight:168,overflowY:'auto',overscrollBehavior:'contain',
        border:`1px solid ${T.border2}`,borderRadius:4,background:T.row,padding:'5px 7px'}}>
        {show.map((it,i)=>(
          <div key={i} style={{marginBottom:7,paddingBottom:6,
            borderBottom:i<show.length-1?`1px solid ${T.border}`:'none'}}>
            <div style={{fontSize:6,color:T.cyan,fontFamily:T.mono,marginBottom:2}}>{it.source}</div>
            {it.link?(
              <a href={it.link} target="_blank" rel="noopener noreferrer"
                style={{fontSize:8,color:T.textB,textDecoration:'none',lineHeight:1.35,wordBreak:'break-word',
                  display:'block'}}>
                {it.title.length>160?`${it.title.slice(0,157)}…`:it.title}
              </a>
            ):(
              <span style={{fontSize:8,color:T.text,lineHeight:1.35}}>{it.title}</span>
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
  if(/TRADE_|SIGNAL_|CLOSE_ALL/.test(t)) return 'TRADE';
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
  const t=(e.timestamp||'').slice(11,19)||'';
  const comp=activityComponent(e);
  const cat=activityCategory(e.event_type);
  const level=activityLevelForEvent(e.event_type);
  const msg=formatActivityMessage(e);
  return {id,t,comp,cat,level,msg,raw:e};
}

function activityLevelColor(l){
  return l==='WARN'?T.amber:l==='ERROR'?T.red:T.textD;
}

function ActivityCategoryChips({catf,setCatf}){
  return(
    <div style={{display:'flex',gap:3,flexWrap:'wrap',alignItems:'center'}}>
      {ACTIVITY_CATS.map(c=>{
        const on=catf===c;
        const col=c==='ALL'?T.gold:ACTIVITY_CAT_COLOR[c]||T.text;
        return(
          <button key={c} type="button" onClick={()=>setCatf(c)}
            style={{fontSize:7,fontFamily:T.mono,letterSpacing:1,
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
      <span style={{fontFamily:T.mono,fontSize:8,color:T.textD,
        padding:'5px 7px',flexShrink:0,width:58}}>{e.t}</span>
      <span style={{fontFamily:T.mono,fontSize:8,color:cc,
        fontWeight:700,letterSpacing:1,width:56,flexShrink:0}}>{e.comp}</span>
      <span style={{fontFamily:T.mono,fontSize:6,color:catc,
        width:44,flexShrink:0,textAlign:'center',letterSpacing:0.5}}>{e.cat}</span>
      <span style={{fontFamily:T.mono,fontSize:7,color:lc,
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
              <span style={{fontFamily:T.mono,fontSize:7,
                color:cf===name?color:T.text,letterSpacing:1}}>{name}</span>
            </div>
            <span style={{fontSize:6,color:T.textD,fontFamily:T.mono}}>
              {comp?.timestamp?.slice(11,19)||'--:--:--'}
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
              <button key={l} type="button" onClick={()=>setLf(l)} style={{fontSize:7,fontFamily:T.mono,
                letterSpacing:1,
                background:lf===l?(l==='WARN'?T.amberBg:l==='ERROR'?T.redBg:T.goldBg):'transparent',
                border:`1px solid ${lf===l?(l==='WARN'?T.amber:l==='ERROR'?T.red:T.gold):T.border}`,
                color:lf===l?(l==='WARN'?T.amber:l==='ERROR'?T.red:T.gold):T.text,
                padding:'2px 6px',borderRadius:3,cursor:'pointer'}}>{l}</button>
            ))}
          </div>
          <div style={{marginLeft:'auto',display:'flex',gap:8,alignItems:'center',flexWrap:'wrap'}}>
            <a href={exportHref} download="system_events.ndjson"
              style={{fontSize:7,fontFamily:T.mono,letterSpacing:1,color:T.cyan,
                border:`1px solid ${T.cyan}`,padding:'2px 6px',borderRadius:3,
                textDecoration:'none'}}>EXPORT NDJSON</a>
            <span style={{fontSize:8,color:T.textD,fontFamily:T.mono}}>
              {filtered.length} events
              {warns>0&&<span style={{color:T.amber}}> · {warns}⚠</span>}
              {errs>0&&<span style={{color:T.red}}> · {errs}✕</span>}
            </span>
            <button type="button" onClick={()=>setPaused(p=>!p)} style={{fontSize:7,fontFamily:T.mono,
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
            <span style={{fontSize:7,color:T.textD,fontFamily:T.mono}}>{e.t}</span>
          </div>
          <div style={{flex:1,minWidth:0}}>
            <div style={{fontSize:10,color:T.textBB,lineHeight:1.6,fontFamily:T.mono,
              marginBottom:6}}>{e.msg}</div>
            <pre style={{fontSize:8,fontFamily:T.mono,color:T.textD,margin:0,
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
          <span style={{fontSize:7,color:T.textD,fontFamily:T.mono}}>
            {paused?'PAUSED':'LIVE — SCRIBE system_events; disk audit logs/audit/system_events.jsonl'}
          </span>
        </div>
        <span style={{fontSize:7,color:T.textD,fontFamily:T.mono}}>Click row for JSON detail</span>
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
  const ref=useRef(null);
  useEffect(()=>{
    if(!liveData)return;
    setMsgs(m=>(m.length>1?m:[{role:'assistant',text:aurumWelcome(liveData)}]));
  },[liveData]);
  useEffect(()=>{ref.current?.scrollIntoView({behavior:'smooth'});},[msgs]);
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
    setInp('');const nm=[...msgs,{role:'user',text}];setMsgs(nm);setLoading(true);
    try{
      let reply;
      try{const r=await fetch(`${API}/api/aurum/ask`,{method:'POST',
        headers:{'Content-Type':'application/json'},body:JSON.stringify({query:text})});
        if(r.ok){const d=await r.json();reply=d.response;}}catch(e){}
      if(!reply){const r=await fetch('https://api.anthropic.com/v1/messages',{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({model:'claude-sonnet-4-20250514',max_tokens:600,
          system:`${SOUL}\n\nLIVE:\n${ctx()}`,
          messages:nm.map(m=>({role:m.role==='user'?'user':'assistant',content:m.text}))})});
        const d=await r.json();reply=d.content?.find(b=>b.type==='text')?.text||'No response.';}
      setMsgs(p=>[...p,{role:'assistant',text:reply}]);
    }catch(e){setMsgs(p=>[...p,{role:'assistant',text:`Error: ${e.message}`}]);}
    finally{setLoading(false);}
  };
  return(<div style={{display:'flex',flexDirection:'column',height:'100%',gap:6}}>
    <PT ch="⚡ AURUM · Telegram + Dashboard" color={T.gold}/>
    <div style={{display:'flex',flexWrap:'wrap',gap:4,marginBottom:2}}>
      {["P&L today?","Open groups?","LENS reading?","All clear?"].map(q=>(
        <button key={q} onClick={()=>setInp(q)} style={{fontSize:7,fontFamily:T.mono,
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
              fontSize:7,marginRight:5,letterSpacing:1}}>AURUM ◆</span>}
            {m.text}
          </div>
        </div>
      ))}
      {loading&&<div className="blink" style={{alignSelf:'flex-start',fontSize:10,
        color:T.gold,fontFamily:T.mono,background:T.row,border:`1px solid ${T.border}`,
        padding:'5px 9px',borderRadius:5}}>AURUM ◆ thinking…</div>}
      <div ref={ref}/>
    </div>
    <div style={{display:'flex',gap:5}}>
      <input value={inp} onChange={e=>setInp(e.target.value)}
        onKeyDown={e=>e.key==='Enter'&&send()}
        placeholder="Ask AURUM anything…"
        style={{flex:1,background:T.row,border:`1px solid ${T.border2}`,
          borderRadius:4,padding:'5px 8px',color:T.textBB,fontSize:10,fontFamily:T.mono}}/>
      <button onClick={send} disabled={loading} style={{background:T.goldBg,
        border:`1px solid ${T.goldBdr}`,color:T.gold,padding:'5px 10px',
        borderRadius:4,cursor:loading?'not-allowed':'pointer',
        fontFamily:T.mono,fontSize:8}}>{loading?'…':'SEND'}</button>
    </div>
    <div style={{fontSize:7,color:T.textD,fontFamily:T.mono,textAlign:'center'}}>
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
  const [mgmtBusy,setMgmtBusy]=useState(false);

  useEffect(()=>{
    const poll=async()=>{
      try{const r=await fetch(`${API}/api/live`);
        if(r.ok){const d=await r.json();setData(d);setMode(d.mode||'SIGNAL');setConnected(true);}
        try{const rc=await fetch(`${API}/api/components`);
          if(rc.ok){const cd=await rc.json();setComponents(cd.components||[]);}}catch(e){}
        const re=await fetch(`${API}/api/events?limit=500`);
        if(re.ok){const ev=await re.json();
          setEvents(Array.isArray(ev)?ev.map(normalizeActivityEvent):[]);}
        try{const rs=await fetch(`${API}/api/signals?limit=50&days=7&stats=1`);
          if(rs.ok){const sj=await rs.json();
            if(sj&&Array.isArray(sj.signals)){setSignals(sj.signals);setSignalStats(sj.stats||null);}
            else if(Array.isArray(sj)){setSignals(sj);setSignalStats(null);}}}
        catch(e){}
        try{const rp=await fetch(`${API}/api/pnl_curve?days=${PERF_ROLLING_DAYS}`);
          if(rp.ok){const curve=await rp.json();
            if(Array.isArray(curve))setPnlCurve(curve.map(x=>Number(x.cumulative)).filter(v=>!Number.isNaN(v)));}}
        catch(e){}
      }catch(e){setConnected(false);}
    };
    poll();const t=setInterval(poll,3000);return()=>clearInterval(t);
  },[]);
  useEffect(()=>{const t=setInterval(()=>setTick(x=>x+1),1000);return()=>clearInterval(t);},[]);

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
      adx:null,ema_20:null,ema_50:null,tv_recommend:null,divergence_from_mt5_usd:null,
    },
    account:{balance:null,equity:null,total_floating_pnl:null,
      margin:null,free_margin:null,margin_level:null,
      open_positions_count:0,session_pnl:null},
    price:{bid:null,ask:null,spread_points:null},
    lens:{price:null,bid:null,ask:null,rsi:null,macd_hist:null,bb_rating:null,
      bb_width:null,adx:null,ema_20:null,ema_50:null,
      tv_recommend:null,timeframe:'--',age_seconds:null,spread_usd:null,
      tradingview_close:null,tv_price_mismatch:false,mt5_symbol:null},
    sentinel:{active:false,next_event:'Unknown',next_in_min:null,next_time:null,news_feeds:{}},
    open_groups:[],open_groups_queued:[],open_groups_policy:'',
    pending_orders:[],pending_orders_forge_count:null,
    performance:{total_pnl:0,total:0,wins:0,win_rate:null,avg_pips:0},
    performance_window:null,
    aegis:{scale_factor:1,scale_reason:'UNKNOWN',session_pnl:0,streak:0,streak_type:'NONE'},
    reconciler:null,
    components:{},
  };

  const acc=D.account||{},sent=D.sentinel||{};
  const ex=D.execution||{},tv=D.tradingview||{};
  const sym=ex.symbol||D.chart_symbol||'—';
  const tvSnapSec=tv.age_seconds!=null?Math.floor(Number(tv.age_seconds)):null;
  const tvSnapAge=tvSnapSec!=null?`${Math.floor(tvSnapSec/60)}m ${tvSnapSec%60}s ago`:'—';
  const modeColor=MODES.find(m=>m.id===mode)?.color||T.gold;
  const timeStr=new Date().toUTCString().split(' ')[4]+' UTC';
  const warnCount=events.filter(e=>e.level==='WARN'||e.level==='ERROR').length;
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

  return(<div style={{background:T.bg,height:'100vh',color:T.textB,
    fontFamily:'Georgia,serif',display:'flex',flexDirection:'column',overflow:'hidden'}}>

    {/* HEADER */}
    <div style={{background:T.panel,borderBottom:`1px solid ${T.border}`,
      padding:'7px 16px',display:'flex',alignItems:'center',
      justifyContent:'space-between',flexShrink:0}}>
      <div style={{display:'flex',alignItems:'center',gap:14}}>
        <div>
          <div style={{fontFamily:T.mono,fontSize:15,fontWeight:700,color:T.gold,letterSpacing:4}}>⚒ ATHENA</div>
          <div style={{fontSize:8,color:T.text,letterSpacing:2,textTransform:'uppercase'}}>Signal System · XAUUSD</div>
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
          <Dot ok={connected} sz={5}/>{connected?'LIVE':'DEMO'}
        </div>
        <span style={{fontSize:8,color:T.textD,fontFamily:T.mono}}>Cycle {D.cycle}</span>
      </div>
    </div>

    {/* BODY */}
    <div style={{flex:1,display:'grid',gridTemplateColumns:'186px 1fr 258px',
      overflow:'hidden',minHeight:0}}>

      {/* LEFT */}
      <div style={{borderRight:`1px solid ${T.border}`,padding:'12px 10px',
        overflowY:'auto',display:'flex',flexDirection:'column',gap:14}}>

        <div>
          <PT ch="⬡ Account · MT5 Live"/>
          {D.mt5_quote_stale&&(
            <div style={{fontSize:7,color:T.amber,fontFamily:T.mono,marginBottom:6,padding:'5px 6px',
              background:T.amberBg,border:`1px solid ${T.amber}`,borderRadius:4,lineHeight:1.35}}>
              FORGE quote file stale ({fmtAgeSec(ex.age_sec)}) — bid/ask on the right are hidden until fresh.
            </div>
          )}
          <div style={{fontFamily:T.mono,fontSize:20,color:T.gold,fontWeight:700,marginBottom:1}}>
            {acc.balance!=null?'$'+acc.balance.toLocaleString('en',{minimumFractionDigits:2}):'—'}</div>
          <div style={{fontSize:8,color:T.text,marginBottom:8}}>BALANCE (from market_data.json)</div>
          {[['EQUITY',acc.equity!=null?'$'+acc.equity.toLocaleString('en',{minimumFractionDigits:2}):'—',T.textBB],
            ['MRG LVL',acc.margin_level!=null?acc.margin_level.toFixed(0)+'%':'—',T.green],
            ['POSITIONS (filled)',acc.open_positions_count??0,T.amber],
            ['PENDING ORDERS',(D.pending_orders||[]).length,T.cyan],
            ['FORGE pendings',D.pending_orders_forge_count!=null?D.pending_orders_forge_count:'—',T.text]].map(([l,v,c])=>(
            <div key={l} style={{display:'flex',justifyContent:'space-between',
              padding:'3px 0',borderBottom:`1px solid ${T.border}`,marginBottom:2}}>
              <span style={{fontSize:8,color:T.textD,fontFamily:T.mono}}>{l}</span>
              <span style={{fontSize:10,fontFamily:T.mono,color:c}}>{v}</span>
            </div>
          ))}
          {(D.pending_orders||[]).length>0&&(
            <div style={{marginTop:8,maxHeight:120,overflowY:'auto',
              border:`1px solid ${T.border2}`,borderRadius:4,background:T.row,padding:6}}>
              <div style={{fontSize:7,color:T.textD,fontFamily:T.mono,marginBottom:4,letterSpacing:1}}>
                MT5 PENDING (from market_data.json)</div>
              {(D.pending_orders||[]).map((p,i)=>(
                <div key={p.ticket||i} style={{fontSize:7,fontFamily:T.mono,color:T.textBB,
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
            <span style={{fontSize:8,fontFamily:T.mono,color:T.text}}>SESSION</span>
            <span style={{fontFamily:T.mono,fontWeight:700,
              color:(acc.session_pnl??0)>=0?T.green:T.red}}>
              {acc.session_pnl!=null?((acc.session_pnl>=0?'+':'')+acc.session_pnl.toFixed(2)):'—'}
            </span>
          </div>
          <div style={{marginTop:6,padding:'4px',background:T.card,borderRadius:4}}>
            {pnlSpark&&pnlSpark.length>=2?(
              <Sparkline data={pnlSpark} w={158} h={28} color={sparkColor}/>
            ):(
              <div style={{fontSize:7,color:T.textD,fontFamily:T.mono,textAlign:'center',padding:'6px 2px'}}>
                No closed trades ({PERF_ROLLING_DAYS}d UTC)</div>
            )}
            <div style={{fontSize:7,color:T.textD,fontFamily:T.mono,textAlign:'center',marginTop:1}}>
              Cumulative P&L ({PERF_ROLLING_DAYS}d)</div>
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
              <span style={{fontSize:7,color:T.textD}}>{m.desc}</span>
              {mode===m.id&&<Dot ok={true} sz={4}/>}
            </button>
          ))}
          <div style={{fontSize:7,color:T.textD,fontFamily:T.mono,textAlign:'center',marginTop:3}}>
            BRIDGE → FORGE via config.json
          </div>
        </div>

        {D.circuit_breaker&&(
          <div style={{padding:'8px 10px',background:'rgba(232,68,90,0.1)',
            border:'1px solid #E8445A',borderRadius:5}}>
            <div style={{fontSize:9,color:'#E8445A',fontFamily:T.mono,fontWeight:700,marginBottom:2}}>
              ⚡ CIRCUIT BREAKER
            </div>
            <div style={{fontSize:8,color:T.text}}>MT5 data stale — trading suspended</div>
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
          <div style={{fontSize:8,color:T.textD,marginTop:1}}>
            in {Math.floor((sent.next_in_min||0)/60)}h {(sent.next_in_min||0)%60}m</div>
          {Array.isArray(sent.calendar_currencies)&&sent.calendar_currencies.length>0&&(
            <div style={{fontSize:6,color:T.textD,fontFamily:T.mono,marginTop:4,lineHeight:1.3}}>
              Cal: {sent.calendar_currencies.join(', ')}
            </div>
          )}
          <SentinelHeadlines newsFeeds={sent.news_feeds}/>
        </div>

        <div>
          <PT ch="⬡ System Health"/>
          {(components.length>0?components:[]).map(c=>(
            <div key={c.name} style={{display:'flex',alignItems:'center',gap:5,marginBottom:5}}>
              <Dot ok={c.ok} sz={5}/>
              <span style={{fontFamily:T.mono,fontSize:8,color:c.ok?(CC[c.name]||T.text):T.red,
                width:56,flexShrink:0}}>{c.name}</span>
              <span style={{fontSize:7,color:T.textD,overflow:'hidden',
                textOverflow:'ellipsis',whiteSpace:'nowrap',flex:1}}>{c.note}</span>
            </div>
          ))}
          {components.length===0&&(
            <div style={{fontSize:8,color:T.textD,fontFamily:T.mono,textAlign:'center',padding:'8px 0'}}>
              No heartbeats yet
            </div>
          )}
        </div>
      </div>

      {/* CENTER */}
      <div style={{display:'flex',flexDirection:'column',overflow:'hidden',minHeight:0}}>
        <div style={{display:'flex',borderBottom:`1px solid ${T.border}`,flexShrink:0}}>
          {[{id:'groups',label:'Groups'},{id:'activity',label:'Activity',badge:warnCount||null},
            {id:'signals',label:'Signals'},{id:'perf',label:'Performance'}].map(t=>(
            <button key={t.id} type="button" data-testid={`tab-${t.id}`}
              onClick={()=>setTab(t.id)} style={{
              padding:'6px 14px',background:'transparent',border:'none',
              borderBottom:tab===t.id?`2px solid ${T.gold}`:'2px solid transparent',
              color:tab===t.id?T.gold:T.text,fontFamily:T.mono,fontSize:8,
              letterSpacing:1,cursor:'pointer',textTransform:'uppercase',
              display:'flex',alignItems:'center',gap:5}}>
              {t.label}
              {t.badge&&<span style={{background:T.amberBg,color:T.amber,
                border:`1px solid ${T.amber}`,fontSize:7,fontFamily:T.mono,
                padding:'0 4px',borderRadius:8}}>{t.badge}</span>}
            </button>
          ))}
        </div>

        <div style={{flex:1,overflow:'hidden',minHeight:0}}>
          {tab==='activity'&&<ActivityLog events={events} components={components}/>}

          {tab==='groups'&&(
            <div style={{overflowY:'auto',height:'100%',padding:'12px 14px'}}>
              {mgmtNote&&(
                <div style={{fontSize:8,color:T.cyan,fontFamily:T.mono,marginBottom:10,padding:'6px 8px',
                  background:T.cyanBg,border:`1px solid ${T.cyan}`,borderRadius:4}}>{mgmtNote}</div>
              )}
              {(D.open_groups_queued||[]).length>0&&(
                <div style={{fontSize:8,color:T.amber,fontFamily:T.mono,marginBottom:10,padding:'6px 8px',
                  background:T.amberBg,border:`1px solid ${T.amber}`,borderRadius:4,lineHeight:1.35}}>
                  {(D.open_groups_queued||[]).length} group(s) in SCRIBE only — waiting for FORGE magic on MT5
                  (positions/pendings). Tiles below are MT5-confirmed.
                </div>
              )}
              {(D.open_groups||[]).map(g=>{
                const cl=g.trades_closed||0,tot=g.num_trades||8;
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
                      </div>
                      <div style={{fontSize:9,color:T.text,fontFamily:T.mono}}>
                        {g.entry_low}–{g.entry_high} · SL:{g.sl} · TP1:{g.tp1}
                        {g.tp2&&` · TP2:${g.tp2}`} · TP3:{g.tp3||'OPEN'}
                      </div>
                    </div>
                    <div style={{textAlign:'right'}}>
                      <span style={{fontFamily:T.mono,color:(g.total_pnl||0)>=0?T.green:T.red,fontWeight:700}}>
                        {(g.total_pnl||0)>=0?'+':''}{(g.total_pnl||0).toFixed(2)}</span>
                      <div style={{fontSize:8,color:T.text,fontFamily:T.mono}}>
                        +{(g.pips_captured||0).toFixed(1)}p</div>
                    </div>
                  </div>
                  <div style={{display:'grid',gridTemplateColumns:`repeat(${tot},1fr)`,
                    gap:3,marginBottom:8}}>
                    {Array.from({length:tot}).map((_,i)=>{const isCl=i<cl;return(
                      <div key={i} style={{height:18,borderRadius:2,
                        background:isCl?(g.direction==='BUY'?T.greenBg:T.redBg)
                          :(g.direction==='BUY'?'rgba(16,185,129,0.2)':'rgba(239,68,68,0.2)'),
                        border:`1px solid ${isCl?T.border:(g.direction==='BUY'?T.green:T.red)}`,
                        display:'flex',alignItems:'center',justifyContent:'center',
                        fontSize:7,color:isCl?T.textD:(g.direction==='BUY'?T.green:T.red),
                        fontFamily:T.mono}}>{isCl?'✓':'●'}</div>);})}
                  </div>
                  <div style={{height:3,background:T.border,borderRadius:2,overflow:'hidden',marginBottom:4}}>
                    <div style={{width:`${Math.min(100,(cl/tot)*140)}%`,height:'100%',
                      background:cl>0?T.green:T.gold,borderRadius:2}}/></div>
                  <div style={{display:'flex',justifyContent:'space-between',marginBottom:7}}>
                    <span style={{fontSize:7,fontFamily:T.mono,color:T.text}}>{cl}/{tot} closed</span>
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
                        style={{fontSize:7,fontFamily:T.mono,
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
                    <div style={{fontSize:7,color:T.textD,letterSpacing:1}}>{l}</div>
                  </div>
                ))}
              </div>
              {/* Channel filter strip */}
              {channels.length>0&&(
                <div style={{display:'flex',gap:3,flexWrap:'wrap',marginBottom:8}}>
                  <button type="button" onClick={()=>setChFilter(null)}
                    style={{fontSize:7,fontFamily:T.mono,letterSpacing:1,
                      background:!chFilter?T.goldBg:'transparent',
                      border:`1px solid ${!chFilter?T.gold:T.border}`,
                      color:!chFilter?T.gold:T.text,
                      padding:'2px 6px',borderRadius:3,cursor:'pointer'}}>ALL</button>
                  {channels.map(ch=>(
                    <button key={ch} type="button" onClick={()=>setChFilter(chFilter===ch?null:ch)}
                      style={{fontSize:7,fontFamily:T.mono,letterSpacing:0.5,
                        background:chFilter===ch?T.cyanBg:'transparent',
                        border:`1px solid ${chFilter===ch?T.cyan:T.border}`,
                        color:chFilter===ch?T.cyan:T.text,
                        padding:'2px 6px',borderRadius:3,cursor:'pointer'}}>{ch}</button>
                  ))}
                </div>
              )}
              <div style={{fontSize:7,color:T.textD,fontFamily:T.mono,marginBottom:8,letterSpacing:1}}>
                {filtered.length} signals · last 7 days (UTC)</div>
              {/* Signal rows — separate ENTRY from MANAGEMENT/other */}
              {filtered.map((row)=>{
                const ts=(row.timestamp||'').replace('T',' ');
                const t=ts.length>=19?ts.slice(11,19):(row.timestamp||'').slice(11,19)||'—';
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
                        <span style={{fontSize:8,color:T.textD,fontFamily:T.mono}}>{t}</span>
                        <Tag lbl={intent||'MSG'} color={T.purple} xs/>
                        <span style={{fontSize:7,color:T.textD,fontFamily:T.mono,
                          overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',maxWidth:400}}>
                          {(row.raw_text||'').slice(0,80)}</span>
                      </div>
                      <span style={{fontSize:6,fontFamily:T.mono,color:T.textD,
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
                      <span style={{fontSize:8,color:T.text,fontFamily:T.mono}}>{t}</span>
                      {dir&&<Tag lbl={dir} color={dir==='BUY'?T.green:T.red}/>}
                      {entry&&<span style={{fontSize:9,color:T.textB,fontFamily:T.mono,fontWeight:600}}>{entry}</span>}
                      <Tag lbl={act} color={act==='EXECUTED'?T.green:act==='SKIPPED'?T.amber:act==='EXPIRED'?T.textD:T.blue}/>
                    </div>
                    <span style={{fontSize:6,fontFamily:T.mono,color:T.cyan,
                      border:`1px solid ${T.cyan}33`,padding:'1px 5px',borderRadius:2,
                      letterSpacing:0.5}}>{ch}</span>
                  </div>
                  {(row.sl||row.tp1)&&(
                    <div style={{fontSize:7,fontFamily:T.mono,color:T.text,marginBottom:2}}>
                      {row.sl!=null&&<span style={{color:T.red}}>SL:{Number(row.sl).toFixed(0)} </span>}
                      {row.tp1!=null&&<span style={{color:T.green}}>TP1:{Number(row.tp1).toFixed(0)} </span>}
                      {row.tp2!=null&&<span style={{color:T.green}}>TP2:{Number(row.tp2).toFixed(0)} </span>}
                      {row.tp3!=null&&<span style={{color:T.green}}>TP3:{Number(row.tp3).toFixed(0)}</span>}
                    </div>
                  )}
                  <div style={{fontSize:8,color:T.textD,fontFamily:T.mono,lineHeight:1.35,
                    overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{info}</div>
                </div>);
              })}
              {filtered.length===0&&(
                <div style={{fontSize:10,color:T.textD,fontFamily:T.mono,
                  textAlign:'center',padding:32}}>
                  {signals.length===0?'No signals in the last 7 days — LISTENER monitors 3 Telegram channels'
                    :`No signals from ${chFilter||'this channel'}`}
                </div>
              )}
            </div>
            );})()}

          {tab==='perf'&&(
            <div style={{overflowY:'auto',height:'100%',padding:'12px 14px'}}>
              <div style={{fontSize:7,color:T.textD,fontFamily:T.mono,marginBottom:8,lineHeight:1.4}}>
                {D.performance_window?.label||`Closed trades in SCRIBE · rolling ${PERF_ROLLING_DAYS}d UTC`}
              </div>
              <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr',gap:8,marginBottom:14}}>
                {[['Win Rate',winRateLbl,T.green],
                  ['Avg Pips',avgPipsLbl,T.gold],
                  ['Total P&L',`$${(D.performance?.total_pnl||0).toFixed(2)}`,(D.performance?.total_pnl||0)>=0?T.green:T.red],
                  ['Trades',D.performance?.total||0,T.textBB],
                  ['Wins',D.performance?.wins||0,T.green],
                  ['Losses',(D.performance?.total||0)-(D.performance?.wins||0),T.red],
                ].map(([l,v,c])=>(
                  <div key={l} style={{background:T.card,border:`1px solid ${T.border}`,
                    borderRadius:5,padding:'10px 12px',textAlign:'center'}}>
                    <div style={{fontSize:18,fontFamily:T.mono,color:c,fontWeight:700}}>{v}</div>
                    <div style={{fontSize:8,color:T.text,marginTop:3,letterSpacing:1}}>{l}</div>
                  </div>
                ))}
              </div>
              <div style={{background:T.card,border:`1px solid ${T.border}`,
                borderRadius:6,padding:14}}>
                <div style={{fontSize:8,color:T.textD,fontFamily:T.mono,marginBottom:8,letterSpacing:2}}>
                  CUMULATIVE P&L · {PERF_ROLLING_DAYS}D (UTC)</div>
                {pnlSpark&&pnlSpark.length>=2?(
                  <Sparkline data={pnlSpark} w={420} h={70} color={sparkColor}/>
                ):(
                  <div style={{fontSize:9,color:T.textD,fontFamily:T.mono,padding:'20px 8px'}}>
                    No closed trades in SCRIBE in the last {PERF_ROLLING_DAYS} days (UTC), or curve needs 1+ closes.</div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* RIGHT */}
      <div style={{borderLeft:`1px solid ${T.border}`,padding:'12px 10px',
        overflowY:'auto',display:'flex',flexDirection:'column',gap:14}}>
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
              <div style={{fontSize:8,color:T.textB,fontFamily:T.mono,marginBottom:10,lineHeight:1.55}}>
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
              <div style={{fontSize:8,color:T.amber,fontFamily:T.mono,fontWeight:700,marginBottom:4}}>
                NO LIVE BROKER QUOTE</div>
              <div style={{fontSize:7,color:T.text,fontFamily:T.mono,lineHeight:1.4}}>
                {ex.stale_reason||'market_data.json missing or unusable.'}
              </div>
              <div style={{fontSize:8,color:T.textB,fontFamily:T.mono,marginTop:6,lineHeight:1.45}}>
                File age: {fmtAgeSec(ex.age_sec)} · {ex.timestamp_utc||'no timestamp'}
              </div>
            </div>
          )}

          <PT ch="🔭 TradingView · indicators" color={T.cyan}/>
          <div style={{display:'flex',justifyContent:'space-between',alignItems:'baseline',marginBottom:6}}>
            <span style={{fontFamily:T.mono,fontSize:16,color:T.textBB,fontWeight:700,letterSpacing:0.5}}>
              {tv.last!=null?'$'+Number(tv.last).toFixed(2):'—'}</span>
            <span style={{fontFamily:T.mono,fontSize:10,color:T.cyan,fontWeight:600}}>last (FX)</span>
          </div>
          <div style={{fontSize:8,color:T.textB,fontFamily:T.mono,marginBottom:8,lineHeight:1.55}}>
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
            ['EMA20',tv.ema_20!=null?'$'+tv.ema_20.toFixed(1):'—',T.textBB],
            ['EMA50',tv.ema_50!=null?'$'+tv.ema_50.toFixed(1):'—',T.textBB],
          ].map(([l,v,c])=>(
            <div key={l} style={{display:'flex',justifyContent:'space-between',
              alignItems:'center',padding:'4px 0',borderBottom:`1px solid ${T.border}`}}>
              <span style={{fontSize:9,color:T.textB,fontFamily:T.mono,width:52,fontWeight:600}}>{l}</span>
              <span style={{fontSize:11,fontFamily:T.mono,color:c,fontWeight:600}}>{v}</span>
            </div>
          ))}
          <div style={{marginTop:7,padding:'5px 8px',background:T.cyanBg,
            border:`1px solid ${T.cyan}`,borderRadius:4,textAlign:'center'}}>
            <span style={{fontFamily:T.mono,fontSize:10,color:T.cyan,letterSpacing:1.5,fontWeight:600}}>
              TV suggest: {tv.tv_recommend??'—'}</span>
          </div>
        </div>
        <div style={{flex:1,display:'flex',flexDirection:'column',minHeight:260}}>
          <AurumChat liveData={D}/>
        </div>
      </div>
    </div>

    {/* FOOTER */}
    <div style={{borderTop:`1px solid ${T.border}`,padding:'4px 16px',
      display:'flex',justifyContent:'space-between',alignItems:'center',
      fontSize:7,color:T.textD,fontFamily:T.mono,flexShrink:0,background:T.panel}}>
      <span>ATHENA · /api/live: execution + tradingview · FORGE + TV MCP · SCRIBE</span>
      {!connected&&<span style={{color:T.amber}}>⚠ DEMO — run bridge.py + athena_api.py for live</span>}
      <span>Tick {tick} · 3s poll</span>
    </div>
  </div>);
}

ReactDOM.createRoot(document.getElementById('root')).render(<ATHENA/>);
