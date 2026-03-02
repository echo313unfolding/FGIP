import { useState, useRef, useEffect } from "react";

const SECTORS = {
  "Pharma Supply Chain": { color: "#2563eb", icon: "💊" },
  "Semiconductors": { color: "#7c3aed", icon: "🔬" },
  "Steel & Metals": { color: "#dc2626", icon: "🏗️" },
  "Critical Minerals": { color: "#d97706", icon: "⛏️" },
  "Shipbuilding & Defense": { color: "#059669", icon: "🚢" },
  "Industrial Automation": { color: "#0891b2", icon: "⚙️" },
  "Consumer Reshoring": { color: "#e11d48", icon: "🏭" },
  "Energy & Grid": { color: "#ca8a04", icon: "⚡" },
  "Tech Sovereignty": { color: "#6366f1", icon: "🖥️" },
  "Supply Chain Verified": { color: "#64748b", icon: "✅" },
};

const TIERS = {
  core: { label: "Core Index", color: "#1e3a5f", ring: 0 },
  adjusting: { label: "Adjusting", color: "#2d5a27", ring: 1 },
  supply_chain: { label: "Supply Chain", color: "#5a4327", ring: 2 },
};

const initialData = [
  // CORE - Pharma
  { name: "Eli Lilly", ticker: "LLY", price: 1009.52, sector: "Pharma Supply Chain", tier: "core", note: "$27B domestic API expansion" },
  { name: "AbbVie", ticker: "ABBV", price: 224.81, sector: "Pharma Supply Chain", tier: "core", note: "$10B+ US, $195M API facility" },
  { name: "AstraZeneca", ticker: "AZN", price: 204.20, sector: "Pharma Supply Chain", tier: "core", note: "Virginia API facility" },
  { name: "Merck", ticker: "MRK", price: 122.26, sector: "Pharma Supply Chain", tier: "core", note: "US vaccine/biologics expansion" },
  { name: "J&J", ticker: "JNJ", price: 242.49, sector: "Pharma Supply Chain", tier: "core", note: "Domestic pharma mfg leader" },
  { name: "Sanofi", ticker: "SNY", price: 46.76, sector: "Pharma Supply Chain", tier: "core", note: "US insulin/biologics mfg" },
  // CORE - Semiconductors
  { name: "TSMC", ticker: "TSM", price: 370.54, sector: "Semiconductors", tier: "core", note: "$100B Arizona — 3 fabs" },
  { name: "Micron", ticker: "MU", price: 428.17, sector: "Semiconductors", tier: "core", note: "$200B ID/NY/VA memory fabs" },
  { name: "NVIDIA", ticker: "NVDA", price: 189.82, sector: "Semiconductors", tier: "core", note: "$500B US — Blackwell AZ" },
  { name: "Intel", ticker: "INTC", price: 44.11, sector: "Semiconductors", tier: "core", note: "Ohio mega-fab, foundry svcs" },
  { name: "Amkor", ticker: "AMKR", price: 47.94, sector: "Semiconductors", tier: "core", note: "US advanced packaging AZ" },
  // CORE - Steel
  { name: "Nucor", ticker: "NUE", price: 180.01, sector: "Steel & Metals", tier: "core", note: "EAF steel — datacenter/fab boom" },
  { name: "Cleveland-Cliffs", ticker: "CLF", price: 10.65, sector: "Steel & Metals", tier: "core", note: "$500M grant — hydrogen DRI" },
  { name: "Steel Dynamics", ticker: "STLD", price: 193.39, sector: "Steel & Metals", tier: "core", note: "Aluminum + BIOEDGE low-carbon" },
  { name: "ATI Inc", ticker: "ATI", price: 158.87, sector: "Steel & Metals", tier: "core", note: "Specialty alloys — Ti, Ni" },
  // CORE - Critical Minerals
  { name: "MP Materials", ticker: "MP", price: 55.34, sector: "Critical Minerals", tier: "core", note: "Mountain Pass + TX magnets" },
  // CORE - Shipbuilding
  { name: "Huntington Ingalls", ticker: "HII", price: 437.57, sector: "Shipbuilding & Defense", tier: "core", note: "Only US nuclear carrier/sub" },
  { name: "General Dynamics", ticker: "GD", price: 351.42, sector: "Shipbuilding & Defense", tier: "core", note: "Bath Iron Works + NASSCO" },
  { name: "Palantir", ticker: "PLTR", price: 135.24, sector: "Shipbuilding & Defense", tier: "core", note: "ShipOS — Navy sub AI layer" },
  { name: "Powell Industries", ticker: "POWL", price: 546.82, sector: "Shipbuilding & Defense", tier: "core", note: "Switchgear for shipyard infra" },
  // CORE - Industrial
  { name: "Rockwell", ticker: "ROK", price: 398.79, sector: "Industrial Automation", tier: "core", note: "Factory automation platforms" },
  { name: "Caterpillar", ticker: "CAT", price: 759.74, sector: "Industrial Automation", tier: "core", note: "Heavy equip — factory build" },
  { name: "Cognex", ticker: "CGNX", price: 56.03, sector: "Industrial Automation", tier: "core", note: "Machine vision for production" },
  { name: "Ingersoll Rand", ticker: "IR", price: 95.60, sector: "Industrial Automation", tier: "core", note: "Compressed air/fluid mgmt" },
  { name: "Parker-Hannifin", ticker: "PH", price: 1022.23, sector: "Industrial Automation", tier: "core", note: "Motion & control systems" },
  { name: "Applied Ind Tech", ticker: "AIT", price: 281.97, sector: "Industrial Automation", tier: "core", note: "Industrial distribution" },
  { name: "Terex", ticker: "TEX", price: 68.17, sector: "Industrial Automation", tier: "core", note: "Aerial platforms, materials" },
  // CORE - Consumer
  { name: "Whirlpool", ticker: "WHR", price: 84.49, sector: "Consumer Reshoring", tier: "core", note: "$300M OH — KitchenAid back" },
  { name: "Stellantis", ticker: "STLA", price: 7.73, sector: "Consumer Reshoring", tier: "core", note: "$13B / 50% domestic increase" },
  { name: "John Deere", ticker: "DE", price: 662.49, sector: "Consumer Reshoring", tier: "core", note: "$20B decade, NC excavator fac" },
  // CORE - Energy
  { name: "Eaton", ticker: "ETN", price: 373.38, sector: "Energy & Grid", tier: "core", note: "Electrical infra for factories" },
  { name: "GE Vernova", ticker: "GEV", price: 830.34, sector: "Energy & Grid", tier: "core", note: "Grid turbines/transformers" },
  { name: "Vertiv", ticker: "VRT", price: 243.75, sector: "Energy & Grid", tier: "core", note: "Data center power/cooling" },
  { name: "BWX Technologies", ticker: "BWXT", price: 206.44, sector: "Energy & Grid", tier: "core", note: "Naval nuclear + grid nuclear" },
  // CORE - Tech
  { name: "Apple", ticker: "AAPL", price: 264.58, sector: "Tech Sovereignty", tier: "core", note: "$500B+ US server/mfg expansion" },
  // ADJUSTING examples
  { name: "Civica Rx", ticker: "PRIVATE", price: null, sector: "Pharma Supply Chain", tier: "adjusting", note: "$140M Petersburg VA generics" },
  { name: "Cambrex", ticker: "PRIVATE", price: null, sector: "Pharma Supply Chain", tier: "adjusting", note: "$120M Charles City IA — API" },
  { name: "Lynas Rare Earths", ticker: "LYSDY", price: null, sector: "Critical Minerals", tier: "adjusting", note: "$258M DoD — TX heavy RE" },
  { name: "USA Rare Earth", ticker: "USAR", price: null, sector: "Critical Minerals", tier: "adjusting", note: "Round Top TX mine-to-magnet" },
  { name: "GE Appliances", ticker: "PRIVATE", price: null, sector: "Consumer Reshoring", tier: "adjusting", note: "$3B US manufacturing (Haier)" },
  { name: "Foxconn", ticker: "PRIVATE", price: null, sector: "Tech Sovereignty", tier: "adjusting", note: "Houston/Dallas for NVDA servers" },
  { name: "Hanwha Ocean", ticker: "KRX", price: null, sector: "Shipbuilding & Defense", tier: "adjusting", note: "Nuclear subs — Philly Shipyard" },
  { name: "Fincantieri Marinette", ticker: "PRIVATE", price: null, sector: "Shipbuilding & Defense", tier: "adjusting", note: "LSM contracts — Feb 2026" },
];

const SunburstChart = ({ data, selected, onSelect }) => {
  const svgRef = useRef(null);
  const [tooltip, setTooltip] = useState(null);
  const [hoveredSector, setHoveredSector] = useState(null);
  const cx = 400, cy = 380;
  const rings = [120, 200, 270, 330];

  const sectorNames = Object.keys(SECTORS);
  const bySector = {};
  sectorNames.forEach(s => { bySector[s] = { core: [], adjusting: [], supply_chain: [] }; });
  data.forEach(d => {
    if (bySector[d.sector]) bySector[d.sector][d.tier].push(d);
  });

  const totalCompanies = data.length;
  const sectorAngles = {};
  let startAngle = -Math.PI / 2;
  const gap = 0.03;

  sectorNames.forEach(s => {
    const count = Math.max(
      bySector[s].core.length + bySector[s].adjusting.length + bySector[s].supply_chain.length,
      1
    );
    const sweep = (count / totalCompanies) * (2 * Math.PI - gap * sectorNames.length);
    sectorAngles[s] = { start: startAngle, end: startAngle + sweep, sweep };
    startAngle += sweep + gap;
  });

  const polarToCart = (angle, r) => ({
    x: cx + r * Math.cos(angle),
    y: cy + r * Math.sin(angle),
  });

  const arcPath = (innerR, outerR, startA, endA) => {
    const s1 = polarToCart(startA, innerR);
    const e1 = polarToCart(endA, innerR);
    const s2 = polarToCart(startA, outerR);
    const e2 = polarToCart(endA, outerR);
    const large = endA - startA > Math.PI ? 1 : 0;
    return `M${s2.x},${s2.y} A${outerR},${outerR} 0 ${large} 1 ${e2.x},${e2.y} L${e1.x},${e1.y} A${innerR},${innerR} 0 ${large} 0 ${s1.x},${s1.y} Z`;
  };

  const elements = [];

  // Center circle
  elements.push(
    <circle key="center" cx={cx} cy={cy} r={rings[0] - 10} fill="#0f172a" stroke="#334155" strokeWidth={2} />
  );
  elements.push(
    <text key="center-text1" x={cx} y={cy - 20} textAnchor="middle" fill="#94a3b8" fontSize={11} fontWeight="bold">FGIP</text>
  );
  elements.push(
    <text key="center-text2" x={cx} y={cy + 2} textAnchor="middle" fill="#e2e8f0" fontSize={16} fontWeight="bold">THESIS INDEX</text>
  );
  elements.push(
    <text key="center-text3" x={cx} y={cy + 22} textAnchor="middle" fill="#64748b" fontSize={10}>{data.length} companies</text>
  );
  elements.push(
    <text key="center-text4" x={cx} y={cy + 38} textAnchor="middle" fill="#64748b" fontSize={10}>9 sectors</text>
  );

  sectorNames.forEach(sectorName => {
    const sa = sectorAngles[sectorName];
    const sc = SECTORS[sectorName];
    const allItems = [...bySector[sectorName].core, ...bySector[sectorName].adjusting, ...bySector[sectorName].supply_chain];
    if (allItems.length === 0) return;
    const isHovered = hoveredSector === sectorName;

    // Sector arc (inner ring)
    elements.push(
      <path
        key={`sector-${sectorName}`}
        d={arcPath(rings[0] - 8, rings[0] + 2, sa.start, sa.end)}
        fill={sc.color}
        opacity={isHovered ? 1 : 0.8}
        stroke="#1e293b"
        strokeWidth={1}
      />
    );

    // Sector label
    const midAngle = (sa.start + sa.end) / 2;
    const labelR = rings[0] + 18;
    const lp = polarToCart(midAngle, labelR);
    if (sa.sweep > 0.25) {
      elements.push(
        <text
          key={`slabel-${sectorName}`}
          x={lp.x} y={lp.y}
          textAnchor="middle"
          fill={sc.color}
          fontSize={8}
          fontWeight="bold"
          transform={`rotate(${(midAngle * 180 / Math.PI) + (Math.cos(midAngle) < 0 ? 180 : 0)}, ${lp.x}, ${lp.y})`}
          style={{ textTransform: "uppercase", letterSpacing: "0.5px" }}
        >
          {sc.icon} {sectorName}
        </text>
      );
    }

    // Company nodes by tier
    const tierOrder = ["core", "adjusting", "supply_chain"];
    let itemIndex = 0;

    tierOrder.forEach((tierName, tierIdx) => {
      const items = bySector[sectorName][tierName];
      items.forEach(item => {
        const t = (itemIndex + 0.5) / allItems.length;
        const angle = sa.start + t * sa.sweep;
        const r = rings[tierIdx + 1] - 20;
        const pos = polarToCart(angle, r);
        const isSelected = selected?.ticker === item.ticker && selected?.name === item.name;
        const nodeR = isSelected ? 14 : (tierName === "core" ? 10 : 7);

        elements.push(
          <g key={`node-${item.name}-${item.ticker}`}
            style={{ cursor: "pointer" }}
            onClick={() => onSelect(item)}
            onMouseEnter={(e) => {
              setTooltip({ ...item, x: e.clientX, y: e.clientY });
              setHoveredSector(sectorName);
            }}
            onMouseLeave={() => { setTooltip(null); setHoveredSector(null); }}
          >
            <circle
              cx={pos.x} cy={pos.y} r={nodeR}
              fill={isSelected ? "#fbbf24" : (tierName === "core" ? sc.color : tierName === "adjusting" ? "#374151" : "#1f2937")}
              stroke={tierName === "core" ? "#e2e8f0" : sc.color}
              strokeWidth={isSelected ? 3 : (tierName === "core" ? 2 : 1)}
              opacity={isHovered || isSelected ? 1 : 0.85}
              strokeDasharray={tierName === "supply_chain" ? "3,2" : "none"}
            />
            {(tierName === "core" && sa.sweep / allItems.length > 0.08) && (
              <text
                x={pos.x} y={pos.y + 1}
                textAnchor="middle"
                fill={isSelected ? "#0f172a" : "#fff"}
                fontSize={7}
                fontWeight="bold"
              >
                {item.ticker === "PRIVATE" ? item.name.slice(0, 4) : item.ticker}
              </text>
            )}
          </g>
        );
        itemIndex++;
      });
    });
  });

  return (
    <div style={{ position: "relative" }}>
      <svg ref={svgRef} viewBox="0 0 800 760" style={{ width: "100%", background: "#0f172a", borderRadius: 12 }}>
        {/* Ring guides */}
        {rings.map((r, i) => (
          <circle key={`ring-${i}`} cx={cx} cy={cy} r={r} fill="none" stroke="#1e293b" strokeWidth={1} strokeDasharray={i > 1 ? "4,4" : "none"} />
        ))}
        {elements}
        {/* Legend */}
        {[
          { label: "Core Index (35)", color: "#3b82f6", y: 710 },
          { label: "Adjusting (8+)", color: "#374151", y: 728, stroke: "#3b82f6" },
          { label: "Supply Chain (add yours)", color: "#1f2937", y: 746, stroke: "#64748b", dash: true },
        ].map((l, i) => (
          <g key={`leg-${i}`}>
            <circle cx={260} cy={l.y} r={6} fill={l.color} stroke={l.stroke || "#e2e8f0"} strokeWidth={1.5} strokeDasharray={l.dash ? "3,2" : "none"} />
            <text x={272} y={l.y + 4} fill="#94a3b8" fontSize={10}>{l.label}</text>
          </g>
        ))}
        <text x={400} y={728} fill="#64748b" fontSize={9} textAnchor="middle">Click any node for details • Use form below to add companies</text>
      </svg>
      {tooltip && (
        <div style={{
          position: "fixed", left: tooltip.x + 12, top: tooltip.y - 60,
          background: "#1e293b", border: `2px solid ${SECTORS[tooltip.sector]?.color || "#475569"}`,
          borderRadius: 8, padding: "10px 14px", zIndex: 999, maxWidth: 280,
          boxShadow: "0 8px 32px rgba(0,0,0,0.5)"
        }}>
          <div style={{ color: "#f1f5f9", fontWeight: "bold", fontSize: 14 }}>{tooltip.name}</div>
          <div style={{ color: SECTORS[tooltip.sector]?.color, fontSize: 11, marginTop: 2 }}>
            {tooltip.ticker} • {tooltip.sector}
          </div>
          {tooltip.price && <div style={{ color: "#4ade80", fontSize: 13, marginTop: 4 }}>${tooltip.price.toFixed(2)}</div>}
          <div style={{ color: "#94a3b8", fontSize: 11, marginTop: 4 }}>{tooltip.note}</div>
          <div style={{
            color: "#64748b", fontSize: 9, marginTop: 4, textTransform: "uppercase",
            letterSpacing: "1px"
          }}>
            {TIERS[tooltip.tier]?.label}
          </div>
        </div>
      )}
    </div>
  );
};

export default function FGIPSunburst() {
  const [data, setData] = useState(initialData);
  const [selected, setSelected] = useState(null);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ name: "", ticker: "", sector: "Pharma Supply Chain", tier: "adjusting", price: "", note: "" });
  const [filter, setFilter] = useState("all");

  const filtered = filter === "all" ? data : data.filter(d => d.tier === filter);
  const coreTotal = data.filter(d => d.tier === "core" && d.price).reduce((s, d) => s + d.price, 0);
  const coreCount = data.filter(d => d.tier === "core").length;
  const adjCount = data.filter(d => d.tier === "adjusting").length;
  const scCount = data.filter(d => d.tier === "supply_chain").length;

  const addCompany = () => {
    if (!form.name) return;
    setData([...data, { ...form, price: form.price ? parseFloat(form.price) : null }]);
    setForm({ name: "", ticker: "", sector: form.sector, tier: form.tier, price: "", note: "" });
    setShowAdd(false);
  };

  const removeSelected = () => {
    if (!selected) return;
    setData(data.filter(d => !(d.name === selected.name && d.ticker === selected.ticker)));
    setSelected(null);
  };

  return (
    <div style={{ background: "#0f172a", minHeight: "100vh", color: "#e2e8f0", fontFamily: "system-ui, -apple-system, sans-serif" }}>
      {/* Header */}
      <div style={{ padding: "20px 24px 0", borderBottom: "1px solid #1e293b" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12 }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 22, color: "#f1f5f9", letterSpacing: "-0.5px" }}>
              FGIP Thesis-Mapped Index
            </h1>
            <p style={{ margin: "4px 0 0", color: "#64748b", fontSize: 12 }}>
              Fifth Generation Institute for Prosperity • Living Network Map
            </p>
          </div>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
            {[
              { label: "Core", value: coreCount, color: "#3b82f6" },
              { label: "Adjusting", value: adjCount, color: "#22c55e" },
              { label: "Supply Chain", value: scCount, color: "#a855f7" },
              { label: "Portfolio", value: `$${(coreTotal).toLocaleString(undefined, { minimumFractionDigits: 0 })}`, color: "#fbbf24" },
            ].map(s => (
              <div key={s.label} style={{ textAlign: "center" }}>
                <div style={{ fontSize: 18, fontWeight: "bold", color: s.color }}>{s.value}</div>
                <div style={{ fontSize: 9, color: "#64748b", textTransform: "uppercase", letterSpacing: "1px" }}>{s.label}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Filter buttons */}
        <div style={{ display: "flex", gap: 8, padding: "12px 0" }}>
          {[
            { key: "all", label: "All" },
            { key: "core", label: "Core Index" },
            { key: "adjusting", label: "Adjusting" },
            { key: "supply_chain", label: "Supply Chain" },
          ].map(f => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              style={{
                padding: "5px 14px", borderRadius: 6, border: "1px solid",
                borderColor: filter === f.key ? "#3b82f6" : "#334155",
                background: filter === f.key ? "#1e3a5f" : "transparent",
                color: filter === f.key ? "#60a5fa" : "#94a3b8",
                fontSize: 12, cursor: "pointer", fontWeight: filter === f.key ? "bold" : "normal"
              }}
            >
              {f.label}
            </button>
          ))}
          <div style={{ flex: 1 }} />
          <button
            onClick={() => setShowAdd(!showAdd)}
            style={{
              padding: "5px 16px", borderRadius: 6, border: "1px solid #22c55e",
              background: showAdd ? "#14532d" : "transparent",
              color: "#4ade80", fontSize: 12, cursor: "pointer", fontWeight: "bold"
            }}
          >
            + Add Company
          </button>
        </div>
      </div>

      {/* Add form */}
      {showAdd && (
        <div style={{ padding: "16px 24px", background: "#1e293b", borderBottom: "1px solid #334155" }}>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
            <div>
              <label style={{ fontSize: 10, color: "#64748b", display: "block", marginBottom: 2 }}>Company</label>
              <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
                placeholder="Company name" style={{ padding: "6px 10px", background: "#0f172a", border: "1px solid #334155", borderRadius: 6, color: "#e2e8f0", fontSize: 13, width: 140 }} />
            </div>
            <div>
              <label style={{ fontSize: 10, color: "#64748b", display: "block", marginBottom: 2 }}>Ticker</label>
              <input value={form.ticker} onChange={e => setForm({ ...form, ticker: e.target.value.toUpperCase() })}
                placeholder="TICK" style={{ padding: "6px 10px", background: "#0f172a", border: "1px solid #334155", borderRadius: 6, color: "#e2e8f0", fontSize: 13, width: 70 }} />
            </div>
            <div>
              <label style={{ fontSize: 10, color: "#64748b", display: "block", marginBottom: 2 }}>Price</label>
              <input value={form.price} onChange={e => setForm({ ...form, price: e.target.value })}
                placeholder="$0.00" type="number" style={{ padding: "6px 10px", background: "#0f172a", border: "1px solid #334155", borderRadius: 6, color: "#e2e8f0", fontSize: 13, width: 80 }} />
            </div>
            <div>
              <label style={{ fontSize: 10, color: "#64748b", display: "block", marginBottom: 2 }}>Sector</label>
              <select value={form.sector} onChange={e => setForm({ ...form, sector: e.target.value })}
                style={{ padding: "6px 10px", background: "#0f172a", border: "1px solid #334155", borderRadius: 6, color: "#e2e8f0", fontSize: 12 }}>
                {Object.keys(SECTORS).map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div>
              <label style={{ fontSize: 10, color: "#64748b", display: "block", marginBottom: 2 }}>Tier</label>
              <select value={form.tier} onChange={e => setForm({ ...form, tier: e.target.value })}
                style={{ padding: "6px 10px", background: "#0f172a", border: "1px solid #334155", borderRadius: 6, color: "#e2e8f0", fontSize: 12 }}>
                <option value="core">Core Index</option>
                <option value="adjusting">Adjusting</option>
                <option value="supply_chain">Supply Chain</option>
              </select>
            </div>
            <div style={{ flex: 1, minWidth: 140 }}>
              <label style={{ fontSize: 10, color: "#64748b", display: "block", marginBottom: 2 }}>Thesis Note</label>
              <input value={form.note} onChange={e => setForm({ ...form, note: e.target.value })}
                placeholder="Why this company?" style={{ padding: "6px 10px", background: "#0f172a", border: "1px solid #334155", borderRadius: 6, color: "#e2e8f0", fontSize: 13, width: "100%" }} />
            </div>
            <button onClick={addCompany}
              style={{ padding: "6px 20px", background: "#22c55e", border: "none", borderRadius: 6, color: "#0f172a", fontWeight: "bold", fontSize: 13, cursor: "pointer" }}>
              Add
            </button>
          </div>
        </div>
      )}

      {/* Chart */}
      <div style={{ padding: "12px 16px" }}>
        <SunburstChart data={filtered} selected={selected} onSelect={setSelected} />
      </div>

      {/* Selected detail */}
      {selected && (
        <div style={{ margin: "0 24px 20px", padding: 16, background: "#1e293b", borderRadius: 10, border: `1px solid ${SECTORS[selected.sector]?.color || "#475569"}` }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <div>
              <div style={{ fontSize: 18, fontWeight: "bold" }}>{selected.name}</div>
              <div style={{ fontSize: 13, color: SECTORS[selected.sector]?.color, marginTop: 2 }}>
                {SECTORS[selected.sector]?.icon} {selected.sector} • {selected.ticker}
                <span style={{
                  marginLeft: 8, padding: "2px 8px", borderRadius: 4, fontSize: 10,
                  background: selected.tier === "core" ? "#1e3a5f" : selected.tier === "adjusting" ? "#14532d" : "#3f3f46",
                  color: selected.tier === "core" ? "#60a5fa" : selected.tier === "adjusting" ? "#4ade80" : "#a1a1aa"
                }}>
                  {TIERS[selected.tier]?.label}
                </span>
              </div>
              {selected.price && (
                <div style={{ fontSize: 24, fontWeight: "bold", color: "#4ade80", marginTop: 8 }}>
                  ${selected.price.toFixed(2)}
                </div>
              )}
              {!selected.price && <div style={{ fontSize: 13, color: "#f59e0b", marginTop: 8 }}>Private / OTC — not in 1-share portfolio</div>}
              <div style={{ fontSize: 13, color: "#94a3b8", marginTop: 8, lineHeight: 1.5 }}>{selected.note}</div>
            </div>
            <button onClick={removeSelected}
              style={{ padding: "4px 12px", background: "#7f1d1d", border: "1px solid #991b1b", borderRadius: 6, color: "#fca5a5", fontSize: 11, cursor: "pointer" }}>
              Remove
            </button>
          </div>
        </div>
      )}

      {/* Company list table */}
      <div style={{ padding: "0 24px 24px" }}>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr style={{ borderBottom: "2px solid #334155" }}>
                {["Sector", "Company", "Ticker", "Price", "Tier", "Thesis Connection"].map(h => (
                  <th key={h} style={{ padding: "8px 10px", textAlign: "left", color: "#64748b", fontSize: 10, textTransform: "uppercase", letterSpacing: "1px" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.sort((a, b) => a.sector.localeCompare(b.sector) || (a.tier === "core" ? -1 : 1)).map((d, i) => (
                <tr key={`${d.name}-${i}`}
                  onClick={() => setSelected(d)}
                  style={{ borderBottom: "1px solid #1e293b", cursor: "pointer", background: selected?.name === d.name ? "#1e293b" : "transparent" }}>
                  <td style={{ padding: "6px 10px", color: SECTORS[d.sector]?.color, fontSize: 11 }}>{SECTORS[d.sector]?.icon} {d.sector}</td>
                  <td style={{ padding: "6px 10px", fontWeight: d.tier === "core" ? "bold" : "normal" }}>{d.name}</td>
                  <td style={{ padding: "6px 10px", color: "#94a3b8", fontFamily: "monospace" }}>{d.ticker}</td>
                  <td style={{ padding: "6px 10px", color: d.price ? "#4ade80" : "#f59e0b", fontFamily: "monospace" }}>
                    {d.price ? `$${d.price.toFixed(2)}` : "—"}
                  </td>
                  <td style={{ padding: "6px 10px" }}>
                    <span style={{
                      padding: "2px 8px", borderRadius: 4, fontSize: 10,
                      background: d.tier === "core" ? "#1e3a5f" : d.tier === "adjusting" ? "#14532d" : "#3f3f46",
                      color: d.tier === "core" ? "#60a5fa" : d.tier === "adjusting" ? "#4ade80" : "#a1a1aa"
                    }}>
                      {TIERS[d.tier]?.label}
                    </span>
                  </td>
                  <td style={{ padding: "6px 10px", color: "#94a3b8", fontSize: 11, maxWidth: 250 }}>{d.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
