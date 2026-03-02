import { useState, useEffect } from "react";

const CATEGORIES = {
  lobbying: { label: "Lobbying Network", color: "#ef4444", icon: "💰" },
  media: { label: "Media Capture", color: "#f59e0b", icon: "📺" },
  court: { label: "Supreme Court Pipeline", color: "#8b5cf6", icon: "⚖️" },
  foreign: { label: "Foreign Money Flow", color: "#ec4899", icon: "🌐" },
  offshoring: { label: "Offshoring Beneficiaries", color: "#64748b", icon: "📦" },
};

const counterThesisData = [
  // LOBBYING NETWORK
  { entity: "US Chamber of Commerce", category: "lobbying", amount: "$1.8B+ total lobbying", role: "Led PNTR push with 600+ companies; largest lobbying org in US history; filed amicus brief AGAINST tariffs in Learning Resources v. Trump", connections: ["Heritage Foundation", "Business Roundtable", "Cato Institute"], documented: true, source: "OpenSecrets / UNC Lobbying Database" },
  { entity: "Business Roundtable", category: "lobbying", amount: "$320M+ lobbying (2000-2024)", role: "CEO coalition that pushed PNTR; fought Section 301 tariffs on China; filed amicus brief against tariff authority", connections: ["US Chamber of Commerce", "Koch Network"], documented: true, source: "OpenSecrets" },
  { entity: "Koch Network (Americans for Prosperity)", category: "lobbying", amount: "$2B+ political/policy spending", role: "Funded Cato Institute free trade ideology; Club for Growth founding; systematic opposition to tariffs and industrial policy", connections: ["Cato Institute", "Heritage Foundation", "Club for Growth"], documented: true, source: "Jane Mayer / Dark Money" },
  { entity: "Cato Institute", category: "lobbying", amount: "~$40M annual budget", role: "Scott Lincicome: 25-year career arc from PNTR advocacy to authoring Learning Resources amicus brief against tariffs; ideological anchor for offshoring", connections: ["Koch Network", "Club for Growth"], documented: true, source: "Cato.org / UNC PNTR records" },
  { entity: "Club for Growth", category: "lobbying", amount: "$200M+ political spending", role: "Harlan Crow founding committee member; anti-tariff scorecards; primary challenges against protectionist Republicans", connections: ["Koch Network", "Harlan Crow"], documented: true, source: "OpenSecrets / FEC" },
  { entity: "National Foreign Trade Council", category: "lobbying", amount: "Trade association", role: "Filed amicus brief in Learning Resources; represents multinationals benefiting from offshoring", connections: ["US Chamber of Commerce"], documented: true, source: "Supreme Court filings" },

  // MEDIA CAPTURE
  { entity: "Bloomberg LP", category: "media", amount: "$150B directed into CCP-linked bonds", role: "Supported 364 Chinese firms (159 CCP-controlled); killed investigation into CCP elite wealth 2014; Bloomberg personally lobbied against Trump China trade policy", connections: ["CCP State-Owned Enterprises"], documented: true, source: "NPR / Epoch Times investigation" },
  { entity: "Vanguard/BlackRock (cross-ownership)", category: "media", amount: "Top shareholders of all major networks", role: "Institutional investors holding positions across media companies AND offshoring beneficiaries simultaneously; Harvard study mapped ownership overlap", connections: ["Disney/ABC", "Comcast/NBC", "All major networks"], documented: true, source: "Harvard cross-ownership study" },
  { entity: "Disney/ABC", category: "media", amount: "$3.6B Shanghai Disney", role: "Deep CCP financial ties through theme parks; ESPN China revenue dependency; incentivized to suppress anti-China trade coverage", connections: ["CCP State-Owned Enterprises", "Vanguard/BlackRock"], documented: true, source: "SEC filings / Epoch Times" },
  { entity: "Comcast/NBC Universal", category: "media", amount: "Licensed content to Baidu's iQIYI", role: "CMC Capital Partners (CCP-linked) acquired Oriental DreamWorks; NBC content licensed to Chinese platforms; financial incentive against negative China coverage", connections: ["CCP/CMC Capital Partners", "Vanguard/BlackRock"], documented: true, source: "Hollywood Reporter / SEC" },
  { entity: "Carlos Slim / NY Times", category: "media", amount: "Largest individual shareholder", role: "Giant Motors + JAC Motors JV to manufacture cars in Mexico specifically to circumvent Trump trade policy; Huawei 5G pitch with America Movil", connections: ["CCP/JAC Motors", "Huawei"], documented: true, source: "Bloomberg Law / Forbes" },

  // SUPREME COURT PIPELINE
  { entity: "Harlan Crow", category: "court", amount: "$2.5B net worth; $14.7M+ political donations", role: "20+ years undisclosed luxury gifts to Justice Thomas; $500K seed money for Ginni Thomas's Liberty Central; founding committee Club for Growth; AEI board; Supreme Court Historical Society board; St. Kitts citizenship for asset sheltering", connections: ["Clarence Thomas", "Ginni Thomas", "Heritage Foundation", "AEI", "Club for Growth"], documented: true, source: "ProPublica / OpenSecrets" },
  { entity: "Ginni Thomas / Liberty Consulting", category: "court", amount: "$680K Heritage Foundation (2003-2007) + undisclosed consulting", role: "One-woman lobbying firm hiding clients through disclosure loophole; paid by groups filing amicus briefs before her husband's court; Liberty Central funded by Crow; Council for National Policy; Groundswell/'Third Century Group' of 83 national conservative leaders", connections: ["Harlan Crow", "Heritage Foundation", "Federalist Society", "Frank Gaffney"], documented: true, source: "OpenSecrets / NPR / New Yorker (Jane Mayer)" },
  { entity: "Heritage Foundation", category: "court", amount: "$80M+ annual budget", role: "Paid Ginni Thomas $680K; files amicus briefs before Supreme Court; weighed in on SCOTUS confirmations; Project 2025 architect; filed brief in Learning Resources", connections: ["Ginni Thomas", "Koch Network", "Harlan Crow"], documented: true, source: "IRS 990s / OpenSecrets / SCOTUS filings" },
  { entity: "Leonard Leo / Federalist Society", category: "court", amount: "$1.6B dark money network", role: "Shaped Supreme Court composition; connected to groups filing amicus briefs; Arabella Advisors counterpart on right; judicial pipeline that determines which cases reach the court", connections: ["Heritage Foundation", "Harlan Crow", "Judicial Crisis Network"], documented: true, source: "ProPublica / New Yorker" },
  { entity: "Citizens United (ruling, not org)", category: "court", amount: "Unlimited corporate spending unleashed", role: "Thomas wanted to go FURTHER — eliminate ALL disclosure; Ginni Thomas's Liberty Central immediately began accepting donations legalized by ruling; Crow's $500K flowed through this", connections: ["Clarence Thomas", "Ginni Thomas", "Harlan Crow"], documented: true, source: "Supreme Court opinion / Jacobin / Lever" },

  // FOREIGN MONEY FLOW
  { entity: "CCP State-Owned Enterprises", category: "foreign", amount: "$150B+ through Bloomberg bond offerings alone", role: "159 CCP-controlled firms financed through US capital markets; COSCO shipping network in SE Europe; grain logistics (COFCO) in Romania; cinema industry control for propaganda", connections: ["Bloomberg LP", "Wall Street banks"], documented: true, source: "CSIS / Congressional testimony" },
  { entity: "Foreign Government Think Tank Funding", category: "foreign", amount: "$110M to top 50 US think tanks (5 years)", role: "UAE $16.7M, UK $15.5M, Qatar $9.1M, Norway $8.5M; foreign governments funding research that shapes US trade policy", connections: ["Brookings", "CSIS", "Atlantic Council"], documented: true, source: "NYT / Think Tank Watch" },
  { entity: "COSCO Shipping (CCP)", category: "foreign", amount: "Port acquisitions across SE Europe", role: "Container logistics network in Balkans; Croatia canceled Chinese port concession after US/EU lobbying; coercive economic statecraft through trade infrastructure", connections: ["CCP State-Owned Enterprises"], documented: true, source: "CSIS research report" },
  { entity: "Huawei Technologies", category: "foreign", amount: "5G infrastructure bids globally", role: "America Movil (Slim) pitching Huawei 5G in Colombia; actively undermining US security by overturning equipment bans; telecom infrastructure as geopolitical tool", connections: ["Carlos Slim", "CCP"], documented: true, source: "Bloomberg Law" },

  // OFFSHORING BENEFICIARIES (companies that lobbied for PNTR then moved production)
  { entity: "Boeing", category: "offshoring", amount: "Major PNTR lobbyist", role: "Among first companies pushing for China PNTR; subsequently offshored supply chain components to China; 737 MAX quality control failures linked to cost-cutting from offshored production model", connections: ["US Chamber of Commerce"], documented: true, source: "UNC PNTR lobbying records" },
  { entity: "Motorola", category: "offshoring", amount: "Major PNTR lobbyist", role: "Made PNTR 'highest priority' — '18 people in this office, 16 working on China'; subsequently offshored manufacturing; later split into Motorola Solutions and Motorola Mobility (acquired by Google then Lenovo/China)", connections: ["US Chamber of Commerce"], documented: true, source: "UNC PNTR lobbying records" },
  { entity: "Apple (pre-reshoring)", category: "offshoring", amount: "5 million Chinese workers in supply chain", role: "Foxconn network employing 5M Chinese; decision to build China-centric supply chains was 'stuff of the China Shock'; NOW reversing with $500B+ US commitment — proves thesis", connections: ["Foxconn", "US-China Business Council"], documented: true, source: "Fortune / Company filings" },
  { entity: "Walmart", category: "offshoring", amount: "Largest importer of Chinese goods", role: "Destroyed local retail while filling shelves with Chinese imports; beneficiary of PNTR's 60% tariff reduction; price pressure forced domestic suppliers to offshore or die", connections: ["US-China Business Council"], documented: true, source: "EPI / Academic research" },
];

// Timeline data showing inverse correlation
const timelineData = [
  { year: 1993, event: "NAFTA signed", lobbySpend: 20, mfgJobs: 17.0, type: "policy" },
  { year: 2000, event: "PNTR passed — 600+ companies lobbied", lobbySpend: 35, mfgJobs: 17.3, type: "policy" },
  { year: 2001, event: "China enters WTO", lobbySpend: 40, mfgJobs: 16.4, type: "policy" },
  { year: 2005, event: "China Shock peak — 2.4M jobs lost", lobbySpend: 55, mfgJobs: 14.2, type: "consequence" },
  { year: 2008, event: "Financial crisis — offshoring accelerates", lobbySpend: 70, mfgJobs: 13.4, type: "consequence" },
  { year: 2010, event: "Citizens United — unlimited corporate spending", lobbySpend: 80, mfgJobs: 11.5, type: "policy" },
  { year: 2016, event: "Trump elected — 'China Shock' role documented", lobbySpend: 85, mfgJobs: 12.3, type: "inflection" },
  { year: 2018, event: "Section 301/232 tariffs imposed", lobbySpend: 75, mfgJobs: 12.8, type: "correction" },
  { year: 2022, event: "CHIPS Act + IRA — $1.85T industrial policy", lobbySpend: 65, mfgJobs: 12.9, type: "correction" },
  { year: 2025, event: "Learning Resources v. Trump — 37 vs 7 amicus", lobbySpend: 60, mfgJobs: 13.0, type: "correction" },
  { year: 2026, event: "FGIP founded — full causality documented", lobbySpend: 55, mfgJobs: 13.2, type: "correction" },
];

function NetworkNode({ entity, isSelected, onClick, style }) {
  const cat = CATEGORIES[entity.category];
  return (
    <div
      onClick={onClick}
      style={{
        padding: "10px 14px",
        background: isSelected ? "#1e293b" : "#0f172a",
        border: `1px solid ${isSelected ? cat.color : "#1e293b"}`,
        borderRadius: 8,
        cursor: "pointer",
        transition: "all 0.2s",
        borderLeft: `3px solid ${cat.color}`,
        ...style,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div style={{ fontSize: 13, fontWeight: "bold", color: "#f1f5f9" }}>{entity.entity}</div>
        {entity.documented && <span style={{ fontSize: 8, color: "#4ade80", background: "#14532d", padding: "1px 6px", borderRadius: 4 }}>SOURCED</span>}
      </div>
      <div style={{ fontSize: 11, color: cat.color, marginTop: 2 }}>{cat.icon} {cat.label}</div>
      <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 4 }}>{entity.amount}</div>
    </div>
  );
}

function CorrelationChart({ data }) {
  const w = 700, h = 200, pad = 40;
  const xScale = (i) => pad + (i / (data.length - 1)) * (w - pad * 2);
  const yScale = (v, min, max) => h - pad - ((v - min) / (max - min)) * (h - pad * 2);

  const lobbyLine = data.map((d, i) => `${i === 0 ? "M" : "L"}${xScale(i)},${yScale(d.lobbySpend, 15, 90)}`).join(" ");
  const jobsLine = data.map((d, i) => `${i === 0 ? "M" : "L"}${xScale(i)},${yScale(d.mfgJobs, 10, 18)}`).join(" ");

  const typeColors = { policy: "#ef4444", consequence: "#f59e0b", inflection: "#8b5cf6", correction: "#4ade80" };

  return (
    <svg viewBox={`0 0 ${w} ${h + 30}`} style={{ width: "100%", background: "#0f172a", borderRadius: 8, border: "1px solid #1e293b" }}>
      {/* Grid */}
      {[0.25, 0.5, 0.75].map(t => (
        <line key={t} x1={pad} y1={pad + t * (h - pad * 2)} x2={w - pad} y2={pad + t * (h - pad * 2)} stroke="#1e293b" />
      ))}
      {/* Lobby spending line (red) */}
      <path d={lobbyLine} fill="none" stroke="#ef4444" strokeWidth={2.5} opacity={0.9} />
      {/* Mfg jobs line (green) */}
      <path d={jobsLine} fill="none" stroke="#4ade80" strokeWidth={2.5} opacity={0.9} />
      {/* Event dots */}
      {data.map((d, i) => (
        <g key={i}>
          <circle cx={xScale(i)} cy={yScale(d.lobbySpend, 15, 90)} r={4} fill={typeColors[d.type]} stroke="#0f172a" strokeWidth={1} />
          <circle cx={xScale(i)} cy={yScale(d.mfgJobs, 10, 18)} r={4} fill={typeColors[d.type]} stroke="#0f172a" strokeWidth={1} />
          <text x={xScale(i)} y={h + 8} textAnchor="middle" fill="#64748b" fontSize={8}>{d.year}</text>
          {i % 2 === 0 && (
            <text x={xScale(i)} y={h + 22} textAnchor="middle" fill="#475569" fontSize={6} style={{ maxWidth: 60 }}>
              {d.event.length > 25 ? d.event.slice(0, 25) + "…" : d.event}
            </text>
          )}
        </g>
      ))}
      {/* Labels */}
      <text x={pad - 4} y={pad + 5} textAnchor="end" fill="#ef4444" fontSize={8}>Lobby $</text>
      <text x={w - pad + 4} y={pad + 5} textAnchor="start" fill="#4ade80" fontSize={8}>Mfg Jobs (M)</text>
      {/* Legend */}
      <line x1={pad} y1={12} x2={pad + 30} y2={12} stroke="#ef4444" strokeWidth={2} />
      <text x={pad + 34} y={15} fill="#ef4444" fontSize={9}>Anti-reshoring lobby spending (indexed)</text>
      <line x1={w / 2 + 20} y1={12} x2={w / 2 + 50} y2={12} stroke="#4ade80" strokeWidth={2} />
      <text x={w / 2 + 54} y={15} fill="#4ade80" fontSize={9}>US manufacturing jobs (millions)</text>
    </svg>
  );
}

export default function CounterThesisTracker() {
  const [selectedEntity, setSelectedEntity] = useState(null);
  const [activeCategory, setActiveCategory] = useState("all");
  const [showAddForm, setShowAddForm] = useState(false);
  const [entities, setEntities] = useState(counterThesisData);
  const [form, setForm] = useState({ entity: "", category: "lobbying", amount: "", role: "", source: "" });

  const filtered = activeCategory === "all" ? entities : entities.filter(e => e.category === activeCategory);

  const addEntity = () => {
    if (!form.entity) return;
    setEntities([...entities, { ...form, connections: [], documented: !!form.source }]);
    setForm({ entity: "", category: form.category, amount: "", role: "", source: "" });
    setShowAddForm(false);
  };

  const catCounts = {};
  Object.keys(CATEGORIES).forEach(k => { catCounts[k] = entities.filter(e => e.category === k).length; });

  return (
    <div style={{ background: "#0f172a", minHeight: "100vh", color: "#e2e8f0", fontFamily: "system-ui, sans-serif" }}>
      {/* Header */}
      <div style={{ padding: "20px 24px", borderBottom: "1px solid #1e293b" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12 }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 20, color: "#ef4444", letterSpacing: "-0.5px" }}>
              ⚠️ FGIP COUNTER-THESIS TRACKER
            </h1>
            <p style={{ margin: "4px 0 0", color: "#64748b", fontSize: 11 }}>
              Accountability Index — Who Broke It & How the Money Flowed
            </p>
          </div>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
            {Object.entries(CATEGORIES).map(([k, v]) => (
              <div key={k} style={{ textAlign: "center" }}>
                <div style={{ fontSize: 16, fontWeight: "bold", color: v.color }}>{catCounts[k]}</div>
                <div style={{ fontSize: 8, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.5px" }}>{v.label.split(" ")[0]}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Correlation chart */}
      <div style={{ padding: "16px 24px" }}>
        <h2 style={{ fontSize: 14, color: "#94a3b8", margin: "0 0 8px", fontWeight: "normal" }}>
          THE INVERSE CORRELATION — As lobby spending rose, manufacturing jobs fell
        </h2>
        <CorrelationChart data={timelineData} />
        <div style={{ display: "flex", gap: 12, marginTop: 8, flexWrap: "wrap" }}>
          {[
            { color: "#ef4444", label: "Policy capture event" },
            { color: "#f59e0b", label: "Documented consequence" },
            { color: "#8b5cf6", label: "Political inflection" },
            { color: "#4ade80", label: "Correction / reversal" },
          ].map(l => (
            <div key={l.label} style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <div style={{ width: 8, height: 8, borderRadius: "50%", background: l.color }} />
              <span style={{ fontSize: 10, color: "#64748b" }}>{l.label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Category filters */}
      <div style={{ padding: "0 24px", display: "flex", gap: 6, flexWrap: "wrap" }}>
        <button onClick={() => setActiveCategory("all")}
          style={{ padding: "5px 12px", borderRadius: 6, border: `1px solid ${activeCategory === "all" ? "#ef4444" : "#334155"}`, background: activeCategory === "all" ? "#3f1a1a" : "transparent", color: activeCategory === "all" ? "#ef4444" : "#94a3b8", fontSize: 11, cursor: "pointer" }}>
          All ({entities.length})
        </button>
        {Object.entries(CATEGORIES).map(([k, v]) => (
          <button key={k} onClick={() => setActiveCategory(k)}
            style={{ padding: "5px 12px", borderRadius: 6, border: `1px solid ${activeCategory === k ? v.color : "#334155"}`, background: activeCategory === k ? v.color + "22" : "transparent", color: activeCategory === k ? v.color : "#94a3b8", fontSize: 11, cursor: "pointer" }}>
            {v.icon} {v.label} ({catCounts[k]})
          </button>
        ))}
        <div style={{ flex: 1 }} />
        <button onClick={() => setShowAddForm(!showAddForm)}
          style={{ padding: "5px 14px", borderRadius: 6, border: "1px solid #ef4444", background: showAddForm ? "#3f1a1a" : "transparent", color: "#ef4444", fontSize: 11, cursor: "pointer", fontWeight: "bold" }}>
          + Add Entity
        </button>
      </div>

      {/* Add form */}
      {showAddForm && (
        <div style={{ padding: "12px 24px", margin: "8px 24px", background: "#1e293b", borderRadius: 8 }}>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-end" }}>
            <div>
              <label style={{ fontSize: 9, color: "#64748b", display: "block" }}>Entity Name</label>
              <input value={form.entity} onChange={e => setForm({ ...form, entity: e.target.value })} placeholder="Name" style={{ padding: "5px 8px", background: "#0f172a", border: "1px solid #334155", borderRadius: 4, color: "#e2e8f0", fontSize: 12, width: 140 }} />
            </div>
            <div>
              <label style={{ fontSize: 9, color: "#64748b", display: "block" }}>Category</label>
              <select value={form.category} onChange={e => setForm({ ...form, category: e.target.value })} style={{ padding: "5px 8px", background: "#0f172a", border: "1px solid #334155", borderRadius: 4, color: "#e2e8f0", fontSize: 11 }}>
                {Object.entries(CATEGORIES).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              </select>
            </div>
            <div>
              <label style={{ fontSize: 9, color: "#64748b", display: "block" }}>Amount/Scale</label>
              <input value={form.amount} onChange={e => setForm({ ...form, amount: e.target.value })} placeholder="$X lobbying" style={{ padding: "5px 8px", background: "#0f172a", border: "1px solid #334155", borderRadius: 4, color: "#e2e8f0", fontSize: 12, width: 120 }} />
            </div>
            <div style={{ flex: 1, minWidth: 180 }}>
              <label style={{ fontSize: 9, color: "#64748b", display: "block" }}>Role / What They Did</label>
              <input value={form.role} onChange={e => setForm({ ...form, role: e.target.value })} placeholder="How they contributed to the problem" style={{ padding: "5px 8px", background: "#0f172a", border: "1px solid #334155", borderRadius: 4, color: "#e2e8f0", fontSize: 12, width: "100%" }} />
            </div>
            <div>
              <label style={{ fontSize: 9, color: "#64748b", display: "block" }}>Source</label>
              <input value={form.source} onChange={e => setForm({ ...form, source: e.target.value })} placeholder="Where documented" style={{ padding: "5px 8px", background: "#0f172a", border: "1px solid #334155", borderRadius: 4, color: "#e2e8f0", fontSize: 12, width: 140 }} />
            </div>
            <button onClick={addEntity} style={{ padding: "5px 16px", background: "#ef4444", border: "none", borderRadius: 4, color: "#fff", fontWeight: "bold", fontSize: 12, cursor: "pointer" }}>Add</button>
          </div>
        </div>
      )}

      {/* Entity grid + detail panel */}
      <div style={{ padding: "16px 24px", display: "flex", gap: 16, flexWrap: "wrap" }}>
        {/* Entity list */}
        <div style={{ flex: "1 1 340px", display: "flex", flexDirection: "column", gap: 6, maxHeight: 500, overflowY: "auto" }}>
          {filtered.map((e, i) => (
            <NetworkNode key={`${e.entity}-${i}`} entity={e} isSelected={selectedEntity?.entity === e.entity} onClick={() => setSelectedEntity(e)} />
          ))}
        </div>

        {/* Detail panel */}
        <div style={{ flex: "1 1 400px" }}>
          {selectedEntity ? (
            <div style={{ background: "#1e293b", borderRadius: 10, padding: 20, border: `1px solid ${CATEGORIES[selectedEntity.category]?.color}` }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <div style={{ fontSize: 20, fontWeight: "bold" }}>{selectedEntity.entity}</div>
                  <div style={{ fontSize: 12, color: CATEGORIES[selectedEntity.category]?.color, marginTop: 2 }}>
                    {CATEGORIES[selectedEntity.category]?.icon} {CATEGORIES[selectedEntity.category]?.label}
                  </div>
                </div>
                {selectedEntity.documented && (
                  <div style={{ background: "#14532d", border: "1px solid #22c55e", borderRadius: 6, padding: "4px 10px" }}>
                    <div style={{ fontSize: 9, color: "#4ade80", textTransform: "uppercase", letterSpacing: "1px" }}>Documented</div>
                  </div>
                )}
              </div>

              <div style={{ marginTop: 16 }}>
                <div style={{ fontSize: 10, color: "#64748b", textTransform: "uppercase", letterSpacing: "1px", marginBottom: 4 }}>Financial Scale</div>
                <div style={{ fontSize: 16, color: "#ef4444", fontWeight: "bold" }}>{selectedEntity.amount}</div>
              </div>

              <div style={{ marginTop: 16 }}>
                <div style={{ fontSize: 10, color: "#64748b", textTransform: "uppercase", letterSpacing: "1px", marginBottom: 4 }}>Role in Causality Chain</div>
                <div style={{ fontSize: 13, color: "#cbd5e1", lineHeight: 1.6 }}>{selectedEntity.role}</div>
              </div>

              {selectedEntity.connections && selectedEntity.connections.length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <div style={{ fontSize: 10, color: "#64748b", textTransform: "uppercase", letterSpacing: "1px", marginBottom: 6 }}>Connected To</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                    {selectedEntity.connections.map(c => (
                      <span key={c} onClick={() => {
                        const found = entities.find(e => e.entity === c);
                        if (found) { setSelectedEntity(found); setActiveCategory("all"); }
                      }} style={{
                        padding: "3px 10px", background: "#334155", borderRadius: 4, fontSize: 11, color: "#94a3b8",
                        cursor: entities.find(e => e.entity === c) ? "pointer" : "default",
                        borderBottom: entities.find(e => e.entity === c) ? "1px dashed #64748b" : "none"
                      }}>
                        {c}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {selectedEntity.source && (
                <div style={{ marginTop: 16 }}>
                  <div style={{ fontSize: 10, color: "#64748b", textTransform: "uppercase", letterSpacing: "1px", marginBottom: 4 }}>Source Documentation</div>
                  <div style={{ fontSize: 12, color: "#60a5fa", fontStyle: "italic" }}>{selectedEntity.source}</div>
                </div>
              )}

              {/* FGIP thesis connection */}
              <div style={{ marginTop: 20, padding: 12, background: "#0f172a", borderRadius: 8, borderLeft: "3px solid #4ade80" }}>
                <div style={{ fontSize: 10, color: "#4ade80", textTransform: "uppercase", letterSpacing: "1px", marginBottom: 4 }}>FGIP Core Index Counterpoint</div>
                <div style={{ fontSize: 12, color: "#94a3b8" }}>
                  {selectedEntity.category === "lobbying" && "Every dollar this entity spent fighting reshoring is a dollar the FGIP core index companies are now recapturing through domestic investment. Their spend is inversely correlated with our index performance."}
                  {selectedEntity.category === "media" && "This entity's financial ties to China incentivize suppressing coverage of the industrial damage documented in FGIP's causality chain. Independent journalism fills the gap they created."}
                  {selectedEntity.category === "court" && "The judicial pipeline this entity funds shapes which cases reach SCOTUS and how trade law is interpreted. Learning Resources v. Trump (37 vs 7 amicus ratio) is the founding exhibit."}
                  {selectedEntity.category === "foreign" && "Foreign capital flowing through these channels undermines the domestic manufacturing base that FGIP core index companies are rebuilding. Their influence wanes as reshoring accelerates."}
                  {selectedEntity.category === "offshoring" && "This entity lobbied for the policies that created the problems. Some are now reversing course (proving the thesis). Others remain counter-positioned to FGIP's core holdings."}
                </div>
              </div>
            </div>
          ) : (
            <div style={{ background: "#1e293b", borderRadius: 10, padding: 40, textAlign: "center" }}>
              <div style={{ fontSize: 40, marginBottom: 12 }}>🔍</div>
              <div style={{ fontSize: 14, color: "#94a3b8" }}>Select an entity to see the full money trail</div>
              <div style={{ fontSize: 11, color: "#64748b", marginTop: 8 }}>Every entry is sourced from government records, court filings, financial disclosures, or investigative journalism</div>
            </div>
          )}
        </div>
      </div>

      {/* Key thesis statement */}
      <div style={{ padding: "16px 24px 24px" }}>
        <div style={{ background: "#1e293b", borderRadius: 10, padding: 20, border: "1px solid #334155" }}>
          <div style={{ fontSize: 14, fontWeight: "bold", color: "#ef4444", marginBottom: 8 }}>THE COUNTER-THESIS IN ONE SENTENCE</div>
          <div style={{ fontSize: 13, color: "#cbd5e1", lineHeight: 1.7 }}>
            The same network that spent $1.8B+ lobbying for PNTR, directed $150B into CCP-controlled bonds, paid a Supreme Court Justice's wife $680K through a disclosure loophole while filing amicus briefs before his court, and funded 37 of 44 briefs opposing tariff authority in Learning Resources v. Trump — that network's financial interests are <span style={{ color: "#ef4444", fontWeight: "bold" }}>inversely correlated</span> with the domestic manufacturing health measured by the FGIP core index. When their influence peaks, America's industrial base collapses. When it wanes, the correction begins. <span style={{ color: "#4ade80", fontWeight: "bold" }}>Track both sides and the thesis proves itself.</span>
          </div>
        </div>
      </div>
    </div>
  );
}
