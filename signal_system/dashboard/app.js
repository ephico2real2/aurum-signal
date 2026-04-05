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
  text:'#7A8A9E',textB:'#A8B8CC',textBB:'#D0DCE8',textD:'#2A3550',
  mono:"'Courier New',monospace",
};
const CC={BRIDGE:T.teal,LISTENER:T.orange,LENS:T.cyan,SENTINEL:T.red,
  AEGIS:T.green,FORGE:T.amber,SCRIBE:T.purple,HERALD:T.blue,AURUM:T.gold,SYSTEM:T.text};
const MODES=[{id:'OFF',color:T.textD,desc:'Dormant'},{id:'WATCH',color:T.blue,desc:'Data only'},
  {id:'SIGNAL',color:T.amber,desc:'Signals'},{id:'SCALPER',color:T.cyan,desc:'Self-scalp'},
  {id:'HYBRID',color:T.gold,desc:'Both active'}];

const Dot=({ok,sz=6,b=false})=>(<div className={b&&ok?'blink':''}
  style={{width:sz,height:sz,borderRadius:'50%',flexShrink:0,
    background:ok?T.green:T.red,boxShadow:`0 0 ${sz+2}px ${ok?T.green:T.red}55`}}/>);
const Tag=({lbl,color,xs=false})=>(<span style={{fontSize:xs?6:7,fontFamily:T.mono,
  letterSpacing:1,border:`1px solid ${color}`,color,
  padding:xs?'0 3px':'1px 5px',borderRadius:2,whiteSpace:'nowrap'}}>{lbl}</span>);
const PT=({ch,color=T.gold,right})=>(<div style={{fontSize:8,fontFamily:T.mono,
  letterSpacing:3,color,textTransform:'uppercase',marginBottom:8,paddingBottom:5,
  borderBottom:`1px solid ${T.border}`,display:'flex',
  justifyContent:'space-between',alignItems:'center'}}>
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

// ── ACTIVITY LOG ───────────────────────────────────────────────────
function ActivityLog({events=[], components=[]}){
  const [cf,setCf]=useState('ALL');
  const [lf,setLf]=useState('ALL');
  const [search,setSearch]=useState('');
  const [paused,setPaused]=useState(false);
  const [sel,setSel]=useState(null);
  const ref=useRef(null);
  const filtered=useMemo(()=>events.filter(e=>{
    if(cf!=='ALL'&&e.comp!==cf)return false;
    if(lf!=='ALL'&&e.level!==lf)return false;
    if(search&&!e.msg.toLowerCase().includes(search.toLowerCase())&&
      !e.comp.toLowerCase().includes(search.toLowerCase()))return false;
    return true;
  }),[events,cf,lf,search]);
  useEffect(()=>{if(!paused)ref.current?.scrollIntoView({behavior:'smooth'});},[filtered,paused]);
  const lc=(l)=>l==='WARN'?T.amber:l==='ERROR'?T.red:T.textD;
  const warns=events.filter(e=>e.level==='WARN').length;
  const errs=events.filter(e=>e.level==='ERROR').length;
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
      <div style={{display:'flex',gap:8,padding:'6px 10px',
        borderBottom:`1px solid ${T.border}`,alignItems:'center',
        flexShrink:0,background:T.panel}}>
        <input value={search} onChange={e=>setSearch(e.target.value)}
          placeholder="Search…"
          style={{background:T.row,border:`1px solid ${T.border2}`,color:T.textB,
            padding:'3px 8px',borderRadius:4,fontSize:9,fontFamily:T.mono,width:150}}/>
        <div style={{display:'flex',gap:3}}>
          {['ALL','INFO','WARN','ERROR'].map(l=>(
            <button key={l} onClick={()=>setLf(l)} style={{fontSize:7,fontFamily:T.mono,
              letterSpacing:1,
              background:lf===l?(l==='WARN'?T.amberBg:l==='ERROR'?T.redBg:T.goldBg):'transparent',
              border:`1px solid ${lf===l?(l==='WARN'?T.amber:l==='ERROR'?T.red:T.gold):T.border}`,
              color:lf===l?(l==='WARN'?T.amber:l==='ERROR'?T.red:T.gold):T.text,
              padding:'2px 6px',borderRadius:3,cursor:'pointer'}}>{l}</button>
          ))}
        </div>
        <div style={{marginLeft:'auto',display:'flex',gap:10,alignItems:'center'}}>
          <span style={{fontSize:8,color:T.textD,fontFamily:T.mono}}>
            {filtered.length} events
            {warns>0&&<span style={{color:T.amber}}> · {warns}⚠</span>}
            {errs>0&&<span style={{color:T.red}}> · {errs}✕</span>}
          </span>
          <button onClick={()=>setPaused(p=>!p)} style={{fontSize:7,fontFamily:T.mono,
            background:paused?T.amberBg:'transparent',
            border:`1px solid ${paused?T.amber:T.border}`,
            color:paused?T.amber:T.text,
            padding:'2px 6px',borderRadius:3,cursor:'pointer'}}>
            {paused?'▶ RESUME':'⏸ PAUSE'}
          </button>
        </div>
      </div>
      {/* Events */}
      <div style={{flex:1,overflowY:'auto',minHeight:0}}>
        {filtered.map((e,i)=>{
          const cc=CC[e.comp]||T.text;
          const isSel=sel===e.id;
          return(
            <div key={e.id} onClick={()=>setSel(isSel?null:e.id)}
              className={i<3?'slide':''}
              style={{display:'flex',alignItems:'center',gap:0,
                borderBottom:`1px solid ${T.border}`,cursor:'pointer',
                background:isSel?`${cc}08`:e.level==='WARN'?'rgba(245,158,11,0.04)':
                  e.level==='ERROR'?'rgba(239,68,68,0.04)':'transparent',
                borderLeft:`2px solid ${e.level==='WARN'?T.amber:e.level==='ERROR'?T.red:cc}`,
                transition:'background 0.1s'}}>
              <span style={{fontFamily:T.mono,fontSize:8,color:T.textD,
                padding:'5px 7px',flexShrink:0,width:58}}>{e.t}</span>
              <span style={{fontFamily:T.mono,fontSize:8,color:cc,
                fontWeight:700,letterSpacing:1,width:65,flexShrink:0}}>{e.comp}</span>
              <span style={{fontFamily:T.mono,fontSize:7,color:lc(e.level),
                width:38,flexShrink:0}}>{e.level}</span>
              <span style={{fontSize:10,flex:1,padding:'5px 8px',lineHeight:1.4,
                color:e.level==='WARN'?T.amber:e.level==='ERROR'?T.red:T.textB}}>
                {e.msg}
              </span>
            </div>
          );
        })}
        {filtered.length===0&&(
          <div style={{textAlign:'center',padding:40,fontSize:10,
            color:T.textD,fontFamily:T.mono}}>No events match filter</div>
        )}
        <div ref={ref}/>
      </div>
      {/* Selected detail */}
      {sel&&(()=>{const e=events.find(x=>x.id===sel);if(!e)return null;
        const cc=CC[e.comp]||T.text;
        return(<div style={{flexShrink:0,borderTop:`1px solid ${T.border}`,
          padding:'8px 12px',background:T.panel,
          display:'flex',gap:12,alignItems:'flex-start'}}>
          <div style={{display:'flex',flexDirection:'column',gap:3,flexShrink:0}}>
            <Tag lbl={e.comp} color={cc}/><Tag lbl={e.level} color={lc(e.level)||T.textD} xs/>
            <span style={{fontSize:7,color:T.textD,fontFamily:T.mono}}>{e.t}</span>
          </div>
          <span style={{flex:1,fontSize:10,color:T.textBB,lineHeight:1.6,fontFamily:T.mono}}>{e.msg}</span>
          <button onClick={()=>setSel(null)} style={{background:'transparent',border:'none',
            color:T.textD,cursor:'pointer',fontSize:14}}>✕</button>
        </div>);
      })()}
      {/* Footer */}
      <div style={{flexShrink:0,borderTop:`1px solid ${T.border}`,padding:'4px 12px',
        background:T.panel,display:'flex',justifyContent:'space-between'}}>
        <div style={{display:'flex',alignItems:'center',gap:5}}>
          <Dot ok={true} sz={4} b={!paused}/>
          <span style={{fontSize:7,color:T.textD,fontFamily:T.mono}}>
            {paused?'PAUSED':'LIVE — SCRIBE system_events + component callbacks'}
          </span>
        </div>
        <span style={{fontSize:7,color:T.textD,fontFamily:T.mono}}>Click row for detail</span>
      </div>
    </div>
  );
}

// ── AURUM CHAT ─────────────────────────────────────────────────────
const SOUL="You are AURUM — the AI intelligence layer of a XAUUSD scalping system. Be concise (2-4 sentences), use numbers, lead with the answer. Never use filler phrases.";
function AurumChat({liveData}){
  const [msgs,setMsgs]=useState([{role:'assistant',text:"AURUM online. Balance $36,420 · G047 TP1 hit, SL at BE. What do you need?"}]);
  const [inp,setInp]=useState('');const [loading,setLoading]=useState(false);
  const ref=useRef(null);
  useEffect(()=>{ref.current?.scrollIntoView({behavior:'smooth'});},[msgs]);
  const ctx=()=>{if(!liveData)return'No live data.';
    const a=liveData.account||{},l=liveData.lens||{},s=liveData.sentinel||{},p=liveData.performance||{};
    return`Mode:${liveData.mode} Balance:$${a.balance?.toFixed(2)} SessionPnL:$${a.session_pnl?.toFixed(2)} Positions:${a.open_positions_count}\nLENS: $${l.price?.toFixed(2)} RSI:${l.rsi?.toFixed(1)} BB:${l.bb_rating} ADX:${l.adx?.toFixed(1)}\nSentinel:${s.active?'ACTIVE':'Clear'} Next:${s.next_event} in ${s.next_in_min}min\nToday: PnL $${p.total_pnl?.toFixed(2)} WR:${p.win_rate}%`;};
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

  useEffect(()=>{
    const poll=async()=>{
      try{const r=await fetch(`${API}/api/live`);
        if(r.ok){const d=await r.json();setData(d);setMode(d.mode||'SIGNAL');setConnected(true);}
        try{const rc=await fetch(`${API}/api/components`);
          if(rc.ok){const cd=await rc.json();setComponents(cd.components||[]);}}catch(e){}
        const re=await fetch(`${API}/api/events?limit=200`);
        if(re.ok){const ev=await re.json();
          if(ev.length>0)setEvents(ev.map((e,i)=>({id:e.id||i,t:(e.timestamp||'').slice(11,19)||'',
            comp:e.triggered_by||(e.event_type||'SYSTEM').split('_')[0],
            level:(e.event_type||'').includes('ERROR')?'ERROR':(e.event_type||'').includes('WARN')?'WARN':'INFO',
            msg:`${e.event_type||''} ${e.reason||''} ${e.notes||''}`.trim()})));}
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

  const D=data||{
    mode:'DISCONNECTED',effective_mode:'DISCONNECTED',
    session:'UNKNOWN',cycle:0,
    account_type:'UNKNOWN',broker:'',server:'',
    mt5_connected:false,circuit_breaker:false,
    sentinel_active:false,mt5_fresh:false,
    account:{balance:null,equity:null,total_floating_pnl:null,
      margin:null,free_margin:null,margin_level:null,
      open_positions_count:0,session_pnl:null},
    price:{bid:null,ask:null,spread_points:null},
    lens:{price:null,rsi:null,macd_hist:null,bb_rating:null,
      bb_width:null,adx:null,ema_20:null,ema_50:null,
      tv_recommend:null,timeframe:'--',age_seconds:null},
    sentinel:{active:false,next_event:'Unknown',next_in_min:null,next_time:null},
    open_groups:[],
    performance:{total_pnl:0,total:0,wins:0,win_rate:0,avg_pips:0},
    aegis:{scale_factor:1,scale_reason:'UNKNOWN',session_pnl:0,streak:0,streak_type:'NONE'},
    reconciler:null,
    components:{},
  };

  const acc=D.account||{},lens=D.lens||{},sent=D.sentinel||{};
  const modeColor=MODES.find(m=>m.id===mode)?.color||T.gold;
  const timeStr=new Date().toUTCString().split(' ')[4]+' UTC';
  const warnCount=events.filter(e=>e.level==='WARN'||e.level==='ERROR').length;

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
        <span style={{fontSize:9,color:T.text,fontFamily:T.mono}}>{D.session}</span>
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
          <div style={{fontFamily:T.mono,fontSize:20,color:T.gold,fontWeight:700,marginBottom:1}}>
            {acc.balance!=null?'$'+acc.balance.toLocaleString('en',{minimumFractionDigits:2}):'—'}</div>
          <div style={{fontSize:8,color:T.text,marginBottom:8}}>BALANCE (live from broker)</div>
          {[['EQUITY',acc.equity!=null?'$'+acc.equity.toLocaleString('en',{minimumFractionDigits:2}):'—',T.textBB],
            ['MRG LVL',acc.margin_level!=null?acc.margin_level.toFixed(0)+'%':'—',T.green],
            ['POSITIONS',acc.open_positions_count??0,T.amber]].map(([l,v,c])=>(
            <div key={l} style={{display:'flex',justifyContent:'space-between',
              padding:'3px 0',borderBottom:`1px solid ${T.border}`,marginBottom:2}}>
              <span style={{fontSize:8,color:T.textD,fontFamily:T.mono}}>{l}</span>
              <span style={{fontSize:10,fontFamily:T.mono,color:c}}>{v}</span>
            </div>
          ))}
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
            <Sparkline data={[0,0,12,34,28,56,89,120,99,134,312,445,589,634,712,847]} w={158} h={28}/>
            <div style={{fontSize:7,color:T.textD,fontFamily:T.mono,textAlign:'center',marginTop:1}}>P&L today</div>
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
            <button key={t.id} onClick={()=>setTab(t.id)} style={{
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
                  <div style={{display:'flex',gap:5}}>
                    {['Close All','Move BE','Close 70%'].map(a=>(
                      <button key={a} style={{fontSize:7,fontFamily:T.mono,background:'transparent',
                        border:`1px solid ${T.border2}`,color:T.text,
                        padding:'2px 7px',borderRadius:3,cursor:'pointer'}}>{a}</button>
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

          {tab==='signals'&&(
            <div style={{overflowY:'auto',height:'100%',padding:'12px 14px'}}>
              <div style={{display:'flex',gap:20,marginBottom:12}}>
                {[['Received',5,T.textBB],['Executed',3,T.green],
                  ['Skipped',1,T.amber],['Expired',1,T.textD]].map(([l,v,c])=>(
                  <div key={l} style={{textAlign:'center'}}>
                    <div style={{fontFamily:T.mono,fontSize:16,color:c,fontWeight:700}}>{v}</div>
                    <div style={{fontSize:7,color:T.textD,letterSpacing:1}}>{l}</div>
                  </div>
                ))}
              </div>
              {[{t:'14:22',dir:'BUY',entry:'3181–3185',act:'EXECUTED',info:'G047 · 8 trades'},
                {t:'12:51',dir:'SELL',entry:'3198–3202',act:'EXECUTED',info:'G046 · 8 trades'},
                {t:'11:34',dir:'BUY',entry:'3165–3169',act:'SKIPPED',info:'SLIPPAGE +22pips'},
                {t:'10:17',dir:'SELL',entry:'3225–3229',act:'EXECUTED',info:'G044 · 8 trades'},
                {t:'09:02',dir:'BUY',entry:'3148–3152',act:'EXPIRED',info:'NEWS_GUARD'},
              ].map((s,i)=>(
                <div key={i} style={{display:'grid',
                  gridTemplateColumns:'40px 44px 100px 80px 1fr',
                  gap:8,alignItems:'center',padding:'6px 10px',marginBottom:4,
                  background:T.row,border:`1px solid ${T.border}`,
                  borderLeft:`2px solid ${s.act==='EXECUTED'?(s.dir==='BUY'?T.green:T.red):s.act==='SKIPPED'?T.amber:T.textD}`,
                  borderRadius:4}}>
                  <span style={{fontSize:8,color:T.text,fontFamily:T.mono}}>{s.t}</span>
                  <Tag lbl={s.dir} color={s.dir==='BUY'?T.green:T.red}/>
                  <span style={{fontSize:9,color:T.textB,fontFamily:T.mono}}>{s.entry}</span>
                  <Tag lbl={s.act} color={s.act==='EXECUTED'?T.green:s.act==='SKIPPED'?T.amber:T.textD}/>
                  <span style={{fontSize:8,color:T.textD,fontFamily:T.mono}}>{s.info}</span>
                </div>
              ))}
            </div>
          )}

          {tab==='perf'&&(
            <div style={{overflowY:'auto',height:'100%',padding:'12px 14px'}}>
              <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr',gap:8,marginBottom:14}}>
                {[['Win Rate',`${D.performance?.win_rate||0}%`,T.green],
                  ['Avg Pips',`+${D.performance?.avg_pips||0}`,T.gold],
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
                  TODAY'S P&L CURVE</div>
                <Sparkline data={[0,0,12,34,28,56,89,120,99,134,312,445,589,634,712,847]} w={420} h={70}/>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* RIGHT */}
      <div style={{borderLeft:`1px solid ${T.border}`,padding:'12px 10px',
        overflowY:'auto',display:'flex',flexDirection:'column',gap:14}}>
        <div>
          <PT ch="🔭 LENS · TradingView MCP" color={T.cyan}/>
          <div style={{display:'flex',justifyContent:'space-between',
            alignItems:'baseline',marginBottom:4}}>
            <span style={{fontFamily:T.mono,fontSize:18,color:T.textBB,fontWeight:700}}>
              {lens.price!=null?'$'+lens.price.toFixed(2):'—'}</span>
            <span style={{fontFamily:T.mono,fontSize:10,color:T.green}}>+0.28%</span>
          </div>
          <div style={{fontSize:7,color:T.textD,fontFamily:T.mono,marginBottom:8}}>
            XAUUSD · {lens.timeframe} · {lens.age_seconds!=null?Math.floor(lens.age_seconds/60)+'m '+(lens.age_seconds%60)+'s ago':'—'}</div>
          {[['RSI 14',lens.rsi!=null?lens.rsi.toFixed(1):'—',lens.rsi!=null?(lens.rsi>70?T.red:lens.rsi<30?T.green:T.text):T.text],
            ['MACD',lens.macd_hist!=null?(lens.macd_hist>0?'+'+lens.macd_hist.toFixed(5):lens.macd_hist.toFixed(5)):'—',lens.macd_hist!=null?(lens.macd_hist>0?T.green:T.red):T.text],
            ['BB Rtg',lens.bb_rating!=null?(lens.bb_rating>0?'+'+lens.bb_rating:lens.bb_rating):'—',lens.bb_rating!=null?(lens.bb_rating>0?T.green:T.text):T.text],
            ['ADX',lens.adx!=null?lens.adx.toFixed(1):'—',T.amber],
            ['EMA20',lens.ema_20!=null?'$'+lens.ema_20.toFixed(1):'—',T.textB],
            ['EMA50',lens.ema_50!=null?'$'+lens.ema_50.toFixed(1):'—',T.textB],
          ].map(([l,v,c])=>(
            <div key={l} style={{display:'flex',justifyContent:'space-between',
              alignItems:'center',padding:'3px 0',borderBottom:`1px solid ${T.border}`}}>
              <span style={{fontSize:8,color:T.textD,fontFamily:T.mono,width:44}}>{l}</span>
              <span style={{fontSize:10,fontFamily:T.mono,color:c}}>{v}</span>
            </div>
          ))}
          <div style={{marginTop:7,padding:'5px 8px',background:T.cyanBg,
            border:`1px solid ${T.cyan}`,borderRadius:4,textAlign:'center'}}>
            <span style={{fontFamily:T.mono,fontSize:9,color:T.cyan,letterSpacing:2}}>
              TV: {lens.tv_recommend||'BUY'}</span>
            <span style={{color:T.green,marginLeft:8,fontSize:8}}>✓ NO CONFLICT</span>
          </div>
        </div>
        <div style={{flex:1,display:'flex',flexDirection:'column',minHeight:260}}>
          <AurumChat liveData={data}/>
        </div>
      </div>
    </div>

    {/* FOOTER */}
    <div style={{borderTop:`1px solid ${T.border}`,padding:'4px 16px',
      display:'flex',justifyContent:'space-between',alignItems:'center',
      fontSize:7,color:T.textD,fontFamily:T.mono,flexShrink:0,background:T.panel}}>
      <span>ATHENA v1.0 · MT5:FORGE · TradingView:LewisWJackson MCP · DB:SCRIBE SQLite</span>
      {!connected&&<span style={{color:T.amber}}>⚠ DEMO — run bridge.py + athena_api.py for live</span>}
      <span>Tick {tick} · 3s poll</span>
    </div>
  </div>);
}

ReactDOM.createRoot(document.getElementById('root')).render(<ATHENA/>);
