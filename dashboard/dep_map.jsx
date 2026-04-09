import { useState } from "react";

const G = {
  bg:"#060709",panel:"#0C0E16",card:"#10121C",border:"#1A1E2E",border2:"#242840",
  gold:"#D4AF37",goldBg:"rgba(212,175,55,0.08)",goldBdr:"rgba(212,175,55,0.2)",
  green:"#10B981",greenBg:"rgba(16,185,129,0.08)",
  red:"#EF4444",redBg:"rgba(239,68,68,0.07)",
  amber:"#F59E0B",amberBg:"rgba(245,158,11,0.08)",
  blue:"#3B82F6",blueBg:"rgba(59,130,246,0.07)",
  cyan:"#06B6D4",cyanBg:"rgba(6,182,212,0.07)",
  purple:"#A855F7",purpleBg:"rgba(168,85,247,0.07)",
  orange:"#F97316",orangeBg:"rgba(249,115,22,0.07)",
  teal:"#14B8A6",tealBg:"rgba(20,184,166,0.07)",
  text:"#7A8A9E",textB:"#A8B8CC",textBB:"#D0DCE8",textD:"#2A3550",
  mono:"'Courier New', monospace",
};

const NODES = [
  {
    id:"scribe", name:"SCRIBE", icon:"📜", order:1,
    color:G.purple, bg:G.purpleBg, file:"python/scribe.py",
    category:"DATA", x:380, y:40,
    desc:"SQLite logger. No Python dependencies — pure stdlib. Must be built first as everything else writes to it.",
    deps:[],
    rdeps:["herald","sentinel","lens","aegis","listener","aurum","bridge","athena"],
    files_out:["data/aurum_intelligence.db"],
    files_in:[],
    install:[],
  },
  {
    id:"forge", name:"FORGE", icon:"⚒️", order:2,
    color:G.amber, bg:G.amberBg, file:"ea/FORGE.mq5",
    category:"MT5", x:660, y:40,
    desc:"MQL5 Expert Advisor. Compiled inside MetaEditor. No Python deps. Build second — independent of all Python.",
    deps:[],
    rdeps:["bridge","athena"],
    files_out:["MT5/market_data.json","MT5/mode_status.json","MT5/tick_data.json"],
    files_in:["MT5/command.json","MT5/config.json"],
    install:["Compile FORGE.mq5 in MetaEditor (F7)","Attach to XAUUSD chart"],
  },
  {
    id:"herald", name:"HERALD", icon:"📣", order:3,
    color:G.blue, bg:G.blueBg, file:"python/herald.py",
    category:"NOTIFY", x:100, y:180,
    desc:"Telegram Bot API sender. Only needs bot token in .env. No other component dependencies.",
    deps:[],
    rdeps:["listener","aurum","bridge"],
    files_out:[],
    files_in:[],
    install:["pip install python-telegram-bot","Create bot via @BotFather","Add TELEGRAM_BOT_TOKEN to .env"],
  },
  {
    id:"sentinel", name:"SENTINEL", icon:"🛡️", order:4,
    color:G.red, bg:G.redBg, file:"python/sentinel.py",
    category:"PROTECTION", x:660, y:180,
    desc:"News guard polling ForexFactory. Depends on SCRIBE for event logging only.",
    deps:["scribe"],
    rdeps:["bridge"],
    files_out:["config/sentinel_status.json"],
    files_in:[],
    install:["pip install requests","No API key needed (scrapes ForexFactory)"],
  },
  {
    id:"lens", name:"LENS", icon:"🔭", order:5,
    color:G.cyan, bg:G.cyanBg, file:"python/lens.py",
    category:"MARKET", x:900, y:180,
    desc:"TradingView MCP wrapper. Needs Node.js MCP server running. Depends on SCRIBE for snapshots.",
    deps:["scribe"],
    rdeps:["bridge","aurum"],
    files_out:["config/lens_snapshot.json"],
    files_in:[],
    install:["npm install -g tradingview-mcp-jackson","pip install mcp","node tradingview-mcp-jackson"],
  },
  {
    id:"aegis", name:"AEGIS", icon:"⚖️", order:6,
    color:G.green, bg:G.greenBg, file:"python/aegis.py",
    category:"RISK", x:380, y:180,
    desc:"Risk manager and lot sizer. Reads SCRIBE for daily P&L tracking. Pure calculation logic.",
    deps:["scribe"],
    rdeps:["bridge"],
    files_out:[],
    files_in:["data/aurum_intelligence.db (SCRIBE)"],
    install:[],
  },
  {
    id:"listener", name:"LISTENER", icon:"📡", order:7,
    color:G.orange, bg:G.orangeBg, file:"python/listener.py",
    category:"SIGNAL", x:100, y:340,
    desc:"Telegram signal reader. Needs Telethon (user account) + Claude API + HERALD for errors + SCRIBE for logging.",
    deps:["scribe","herald"],
    rdeps:["bridge"],
    files_out:["config/parsed_signal.json","config/management_cmd.json"],
    files_in:[],
    install:["pip install telethon anthropic","TELEGRAM_API_ID, API_HASH, PHONE in .env","ANTHROPIC_API_KEY in .env","Run once for auth: python listener.py --auth"],
  },
  {
    id:"aurum", name:"AURUM", icon:"⚡", order:8,
    color:G.gold, bg:G.goldBg, file:"python/aurum.py + SOUL.md + SKILL.md",
    category:"AI AGENT", x:660, y:340,
    desc:"Claude-powered AI agent. Reads all status files. Needs SCRIBE, HERALD, LENS, Claude API. SOUL.md + SKILL.md define identity and capabilities.",
    deps:["scribe","herald","lens"],
    rdeps:["bridge"],
    files_out:["config/aurum_cmd.json"],
    files_in:["config/lens_snapshot.json","MT5/market_data.json","config/status.json","SOUL.md","SKILL.md"],
    install:["pip install anthropic telethon","ANTHROPIC_API_KEY in .env","Create Telegram bot for AURUM responses"],
  },
  {
    id:"bridge", name:"BRIDGE", icon:"🔗", order:9,
    color:G.teal, bg:G.tealBg, file:"python/bridge.py",
    category:"ORCHESTRATION", x:380, y:480,
    desc:"Central orchestrator. Depends on ALL other Python components. Last Python module to build. Entry point: python bridge.py",
    deps:["scribe","herald","sentinel","lens","aegis","listener","aurum"],
    rdeps:["athena"],
    files_out:["MT5/command.json","MT5/config.json","config/status.json"],
    files_in:["config/parsed_signal.json","config/lens_snapshot.json","config/sentinel_status.json","MT5/market_data.json","config/aurum_cmd.json"],
    install:["pip install schedule","All dependencies of sub-components must be installed first"],
  },
  {
    id:"athena", name:"ATHENA", icon:"🖥️", order:10,
    color:G.gold, bg:G.goldBg, file:"python/athena_api.py + dashboard/athena.jsx",
    category:"INTERFACE", x:660, y:620,
    desc:"Flask API + React dashboard. Reads SCRIBE + all JSON files. Served on localhost:7842. Last to build.",
    deps:["scribe","forge"],
    rdeps:[],
    files_out:[],
    files_in:["MT5/market_data.json","config/status.json","config/lens_snapshot.json","data/aurum_intelligence.db"],
    install:["pip install flask flask-cors","npm install (in dashboard/)","Serve on localhost:7842"],
  },
];

const EDGES = [];
NODES.forEach(n => {
  n.deps.forEach(dep => {
    EDGES.push({ from: dep, to: n.id });
  });
});

function getNodePos(id) {
  return NODES.find(n => n.id === id);
}

const ORDER_COLORS = [G.purple,G.amber,G.blue,G.red,G.cyan,G.green,G.orange,G.gold,G.teal,G.gold];

export default function DepMap() {
  const [sel, setSel] = useState(null);
  const [hover, setHover] = useState(null);
  const [view, setView] = useState("map"); // map | order | files

  const selected = NODES.find(n => n.id === (sel || hover));

  const isHighlighted = (id) => {
    if (!sel && !hover) return true;
    const focus = sel || hover;
    if (id === focus) return true;
    const focusNode = NODES.find(n => n.id === focus);
    if (!focusNode) return true;
    return focusNode.deps.includes(id) || focusNode.rdeps.includes(id);
  };

  const SVG_W = 1050, SVG_H = 720;
  const NODE_W = 110, NODE_H = 54;

  return (
    <div style={{ background:G.bg, minHeight:"100vh", color:G.textB,
      fontFamily:"Georgia, serif", display:"flex", flexDirection:"column" }}>

      {/* Header */}
      <div style={{ borderBottom:`1px solid ${G.border}`, padding:"10px 20px",
        display:"flex", justifyContent:"space-between", alignItems:"center" }}>
        <div>
          <div style={{ fontFamily:G.mono, fontSize:16, color:G.gold, letterSpacing:4 }}>
            ⚒ SIGNAL SYSTEM — DEPENDENCY MAP
          </div>
          <div style={{ fontSize:9, color:G.text, letterSpacing:2,
            textTransform:"uppercase", marginTop:2 }}>
            10 components · Build order 1→10 · Click any node to inspect
          </div>
        </div>
        <div style={{ display:"flex", gap:6 }}>
          {["map","order","files"].map(v => (
            <button key={v} onClick={()=>setView(v)} style={{
              background: view===v ? G.goldBg : "transparent",
              border:`1px solid ${view===v ? G.gold : G.border}`,
              color: view===v ? G.gold : G.text,
              padding:"5px 12px", borderRadius:4, cursor:"pointer",
              fontFamily:G.mono, fontSize:9, letterSpacing:2, textTransform:"uppercase",
            }}>{v}</button>
          ))}
        </div>
      </div>

      <div style={{ display:"flex", flex:1, overflow:"hidden" }}>
        {/* MAP VIEW */}
        {view==="map" && (
          <div style={{ flex:1, position:"relative", overflow:"auto" }}>
            <svg width={SVG_W} height={SVG_H} style={{ display:"block" }}>
              <defs>
                {NODES.map(n => (
                  <marker key={n.id} id={`arr-${n.id}`} markerWidth="8" markerHeight="8"
                    refX="6" refY="3" orient="auto">
                    <path d="M0,0 L0,6 L8,3 z" fill={n.color} opacity="0.6"/>
                  </marker>
                ))}
              </defs>

              {/* Edges */}
              {EDGES.map((e,i) => {
                const from = getNodePos(e.from);
                const to   = getNodePos(e.to);
                if (!from || !to) return null;
                const fx = from.x + NODE_W/2, fy = from.y + NODE_H;
                const tx = to.x + NODE_W/2,   ty = to.y;
                const mx = (fx+tx)/2, my = (fy+ty)/2;
                const focusId = sel || hover;
                const active = !focusId ||
                  (to.id === focusId && NODES.find(n=>n.id===focusId)?.deps.includes(from.id)) ||
                  (from.id === focusId && NODES.find(n=>n.id===focusId)?.rdeps.includes(to.id));
                const toNode = getNodePos(e.to);
                return (
                  <g key={i} opacity={active ? 1 : 0.08}>
                    <path d={`M${fx},${fy} C${fx},${my} ${tx},${my} ${tx},${ty}`}
                      fill="none" stroke={toNode.color} strokeWidth={active?1.5:1}
                      opacity="0.5"
                      markerEnd={`url(#arr-${e.to})`}/>
                  </g>
                );
              })}

              {/* Nodes */}
              {NODES.map(n => {
                const lit = isHighlighted(n.id);
                const isSel = n.id === sel;
                return (
                  <g key={n.id} transform={`translate(${n.x},${n.y})`}
                    style={{ cursor:"pointer" }}
                    onClick={()=>setSel(sel===n.id?null:n.id)}
                    onMouseEnter={()=>setHover(n.id)}
                    onMouseLeave={()=>setHover(null)}>
                    <rect width={NODE_W} height={NODE_H} rx="6"
                      fill={isSel ? n.bg : G.panel}
                      stroke={isSel || n.id===hover ? n.color : G.border2}
                      strokeWidth={isSel?2:1}
                      opacity={lit?1:0.2}/>
                    {/* Build order badge */}
                    <rect x={NODE_W-18} y={0} width={18} height={16} rx="0 6 0 0"
                      fill={n.color} opacity="0.8"/>
                    <text x={NODE_W-9} y={11} textAnchor="middle"
                      fill={G.bg} fontSize={9} fontFamily={G.mono} fontWeight="700">
                      {n.order}
                    </text>
                    <text x={12} y={20} fill={n.color} fontSize={16}>{n.icon}</text>
                    <text x={32} y={20} fill={lit?n.color:G.textD}
                      fontSize={10} fontFamily={G.mono} fontWeight="700"
                      letterSpacing="1">{n.name}</text>
                    <text x={10} y={34} fill={lit?G.text:G.textD}
                      fontSize={7} fontFamily={G.mono}>{n.category}</text>
                    <text x={10} y={47} fill={lit?G.textD:"#1a2030"}
                      fontSize={7} fontFamily={G.mono}>{n.file.split("/").pop()}</text>
                  </g>
                );
              })}

              {/* Layer labels */}
              {[
                {y:20, label:"LAYER 1 — FOUNDATION (no deps)"},
                {y:160, label:"LAYER 2 — SERVICES"},
                {y:320, label:"LAYER 3 — INTELLIGENCE"},
                {y:460, label:"LAYER 4 — ORCHESTRATION"},
                {y:600, label:"LAYER 5 — INTERFACE"},
              ].map((l,i) => (
                <text key={i} x={10} y={l.y} fill={G.textD}
                  fontSize={8} fontFamily={G.mono} letterSpacing="2">
                  {l.label}
                </text>
              ))}
            </svg>
          </div>
        )}

        {/* ORDER VIEW */}
        {view==="order" && (
          <div style={{ flex:1, overflowY:"auto", padding:20 }}>
            <div style={{ fontSize:10, color:G.text, fontFamily:G.mono,
              marginBottom:16 }}>
              BUILD IN THIS ORDER — each step depends on all previous steps being complete
            </div>
            {NODES.sort((a,b)=>a.order-b.order).map((n,i) => (
              <div key={n.id} onClick={()=>setSel(sel===n.id?null:n.id)}
                style={{
                  display:"flex", gap:16, padding:"14px 16px", marginBottom:8,
                  background: sel===n.id ? n.bg : G.panel,
                  border:`1px solid ${sel===n.id ? n.color : G.border}`,
                  borderLeft:`3px solid ${n.color}`, borderRadius:7, cursor:"pointer",
                }}>
                <div style={{ fontFamily:G.mono, fontSize:22, color:n.color,
                  fontWeight:700, width:32, flexShrink:0 }}>
                  {n.order}
                </div>
                <div style={{ flex:1 }}>
                  <div style={{ display:"flex", gap:10, alignItems:"center",
                    marginBottom:4 }}>
                    <span style={{ fontSize:18 }}>{n.icon}</span>
                    <span style={{ fontFamily:G.mono, fontSize:13,
                      color:n.color, letterSpacing:2 }}>{n.name}</span>
                    <span style={{ fontSize:8, color:G.text, fontFamily:G.mono }}>
                      {n.file}
                    </span>
                  </div>
                  <div style={{ fontSize:10, color:G.textB, lineHeight:1.5 }}>
                    {n.desc}
                  </div>
                  {n.deps.length > 0 && (
                    <div style={{ marginTop:6, display:"flex", gap:6,
                      flexWrap:"wrap" }}>
                      <span style={{ fontSize:8, color:G.textD,
                        fontFamily:G.mono }}>REQUIRES:</span>
                      {n.deps.map(d => {
                        const dn = NODES.find(x=>x.id===d);
                        return (
                          <span key={d} style={{ fontSize:8, fontFamily:G.mono,
                            color:dn?.color, border:`1px solid ${dn?.color}`,
                            padding:"1px 6px", borderRadius:3 }}>
                            {d.toUpperCase()}
                          </span>
                        );
                      })}
                    </div>
                  )}
                  {n.install.length > 0 && (
                    <div style={{ marginTop:8 }}>
                      {n.install.map((cmd,j) => (
                        <div key={j} style={{ fontSize:9, fontFamily:G.mono,
                          color:G.text, background:G.card, padding:"2px 8px",
                          borderRadius:3, marginBottom:3,
                          borderLeft:`2px solid ${n.color}` }}>
                          {cmd}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* FILES VIEW */}
        {view==="files" && (
          <div style={{ flex:1, overflowY:"auto", padding:20 }}>
            <div style={{ fontSize:10, color:G.text, fontFamily:G.mono,
              marginBottom:16 }}>
              FILE I/O MAP — every file, who writes it, who reads it
            </div>
            {[
              {file:"MT5/market_data.json",     writer:"FORGE",    readers:["BRIDGE","ATHENA","AURUM"], color:G.amber},
              {file:"MT5/command.json",          writer:"BRIDGE",   readers:["FORGE"],                   color:G.teal},
              {file:"MT5/config.json",           writer:"BRIDGE",   readers:["FORGE"],                   color:G.teal},
              {file:"MT5/tick_data.json",        writer:"FORGE",    readers:["SCRIBE"],                  color:G.amber},
              {file:"config/parsed_signal.json", writer:"LISTENER", readers:["BRIDGE"],                  color:G.orange},
              {file:"config/management_cmd.json",writer:"LISTENER", readers:["BRIDGE"],                  color:G.orange},
              {file:"config/lens_snapshot.json", writer:"LENS",     readers:["BRIDGE","AURUM","ATHENA"], color:G.cyan},
              {file:"config/sentinel_status.json",writer:"SENTINEL",readers:["BRIDGE"],                  color:G.red},
              {file:"config/status.json",        writer:"BRIDGE",   readers:["ATHENA","AURUM"],          color:G.teal},
              {file:"config/aurum_cmd.json",     writer:"AURUM",    readers:["BRIDGE"],                  color:G.gold},
              {file:"data/aurum_intelligence.db",writer:"SCRIBE",   readers:["AEGIS","ATHENA","AURUM"],  color:G.purple},
              {file:"SOUL.md",                   writer:"(you)",    readers:["AURUM"],                   color:G.gold},
              {file:"SKILL.md",                  writer:"(you)",    readers:["AURUM"],                   color:G.gold},
            ].map((f,i) => (
              <div key={i} style={{ display:"grid",
                gridTemplateColumns:"240px 100px 1fr",
                gap:12, padding:"8px 12px", marginBottom:4,
                background:G.panel, border:`1px solid ${G.border}`,
                borderLeft:`2px solid ${f.color}`, borderRadius:5,
                alignItems:"center" }}>
                <span style={{ fontFamily:G.mono, fontSize:10,
                  color:G.textBB }}>{f.file}</span>
                <div>
                  <div style={{ fontSize:7, color:G.textD,
                    fontFamily:G.mono, marginBottom:2 }}>WRITER</div>
                  <span style={{ fontSize:9, fontFamily:G.mono,
                    color:f.color }}>{f.writer}</span>
                </div>
                <div>
                  <div style={{ fontSize:7, color:G.textD,
                    fontFamily:G.mono, marginBottom:2 }}>READERS</div>
                  <div style={{ display:"flex", gap:5, flexWrap:"wrap" }}>
                    {f.readers.map(r => {
                      const rn = NODES.find(n=>n.name===r);
                      return (
                        <span key={r} style={{ fontSize:8, fontFamily:G.mono,
                          color:rn?.color||G.text, border:`1px solid ${rn?.color||G.border}`,
                          padding:"1px 5px", borderRadius:3 }}>{r}</span>
                      );
                    })}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Detail panel */}
        {selected && (
          <div style={{ width:300, borderLeft:`1px solid ${G.border}`,
            padding:16, overflowY:"auto", background:G.panel,
            flexShrink:0 }}>
            <div style={{ display:"flex", justifyContent:"space-between",
              marginBottom:12 }}>
              <div style={{ fontFamily:G.mono, fontSize:14, color:selected.color,
                letterSpacing:2 }}>
                {selected.icon} {selected.name}
              </div>
              <div style={{ fontFamily:G.mono, fontSize:18, color:selected.color,
                fontWeight:700 }}>#{selected.order}</div>
            </div>
            <div style={{ fontSize:10, color:G.textB, lineHeight:1.6,
              marginBottom:14, padding:"8px 10px",
              background:selected.bg, borderRadius:5,
              borderLeft:`2px solid ${selected.color}` }}>
              {selected.desc}
            </div>
            <div style={{ fontSize:8, color:G.textD, fontFamily:G.mono,
              marginBottom:6 }}>FILE</div>
            <div style={{ fontSize:9, fontFamily:G.mono, color:G.textB,
              marginBottom:14 }}>{selected.file}</div>

            {selected.deps.length>0 && <>
              <div style={{ fontSize:8, color:G.textD, fontFamily:G.mono,
                marginBottom:6 }}>DEPENDS ON</div>
              {selected.deps.map(d => {
                const dn=NODES.find(n=>n.id===d);
                return <div key={d} style={{ fontSize:9, fontFamily:G.mono,
                  color:dn.color, marginBottom:3 }}>#{dn.order} {dn.name}</div>;
              })}
              <div style={{ marginBottom:14 }}/>
            </>}

            {selected.rdeps.length>0 && <>
              <div style={{ fontSize:8, color:G.textD, fontFamily:G.mono,
                marginBottom:6 }}>USED BY</div>
              {selected.rdeps.map(d => {
                const dn=NODES.find(n=>n.id===d);
                return <div key={d} style={{ fontSize:9, fontFamily:G.mono,
                  color:dn.color, marginBottom:3 }}>#{dn.order} {dn.name}</div>;
              })}
              <div style={{ marginBottom:14 }}/>
            </>}

            {selected.files_out.length>0 && <>
              <div style={{ fontSize:8, color:G.green, fontFamily:G.mono,
                marginBottom:6 }}>WRITES</div>
              {selected.files_out.map((f,i)=>(
                <div key={i} style={{ fontSize:9, fontFamily:G.mono,
                  color:G.text, marginBottom:3 }}>→ {f}</div>
              ))}
              <div style={{ marginBottom:14 }}/>
            </>}

            {selected.files_in.length>0 && <>
              <div style={{ fontSize:8, color:G.cyan, fontFamily:G.mono,
                marginBottom:6 }}>READS</div>
              {selected.files_in.map((f,i)=>(
                <div key={i} style={{ fontSize:9, fontFamily:G.mono,
                  color:G.text, marginBottom:3 }}>← {f}</div>
              ))}
              <div style={{ marginBottom:14 }}/>
            </>}

            {selected.install.length>0 && <>
              <div style={{ fontSize:8, color:G.amber, fontFamily:G.mono,
                marginBottom:6 }}>SETUP STEPS</div>
              {selected.install.map((s,i)=>(
                <div key={i} style={{ fontSize:9, fontFamily:G.mono,
                  color:G.text, background:G.card, padding:"4px 8px",
                  borderRadius:3, marginBottom:4,
                  borderLeft:`2px solid ${selected.color}` }}>
                  {i+1}. {s}
                </div>
              ))}
            </>}
          </div>
        )}
      </div>

      <div style={{ borderTop:`1px solid ${G.border}`, padding:"5px 20px",
        fontSize:7, color:G.textD, fontFamily:G.mono,
        display:"flex", justifyContent:"space-between" }}>
        <span>MAP · ORDER · FILES — three views of the same system</span>
        <span>Build order 1→10 · Arrows show dependencies · Numbers show build sequence</span>
      </div>
    </div>
  );
}
