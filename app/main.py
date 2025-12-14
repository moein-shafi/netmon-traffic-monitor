from __future__ import annotations

from datetime import datetime
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from storage import load_windows, Window

app = FastAPI(title="NetMon API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten later if you want
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/windows")
def get_windows():
    windows: List[Window] = load_windows()
    return [w.to_dict() for w in windows]


@app.get("/api/windows/latest")
def get_latest_window():
    windows: List[Window] = load_windows()
    if not windows:
        raise HTTPException(status_code=404, detail="No windows available")

    latest = max(windows, key=lambda w: w.metrics.start_time)
    return latest.to_dict()


@app.get("/")
def landing_page() -> HTMLResponse:
    # A lightweight, self-contained UI that consumes the API without extra build tooling.
    return HTMLResponse(
        """
        <!DOCTYPE html>
        <html lang=\"en\">
        <head>
          <meta charset=\"UTF-8\" />
          <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
          <title>NetMon | AI-Driven Traffic Observatory</title>
          <style>
            :root {
              --bg: #05060a;
              --panel: #0c0f1a;
              --accent: #7df3c0;
              --accent-2: #7dc3f3;
              --text: #e8f2ff;
              --muted: #95a6c8;
              --border: rgba(255, 255, 255, 0.08);
            }
            * { box-sizing: border-box; }
            body {
              margin: 0;
              font-family: "Inter", "SF Pro Display", system-ui, -apple-system, sans-serif;
              background: radial-gradient(circle at 10% 20%, rgba(125,243,192,0.06), transparent 20%),
                          radial-gradient(circle at 90% 10%, rgba(125,195,243,0.05), transparent 25%),
                          radial-gradient(circle at 50% 80%, rgba(125,195,243,0.05), transparent 25%),
                          var(--bg);
              color: var(--text);
              min-height: 100vh;
            }
            header {
              padding: 40px 8vw 10px;
              display: flex;
              flex-direction: column;
              gap: 10px;
            }
            .title {
              font-size: clamp(32px, 5vw, 54px);
              font-weight: 800;
              letter-spacing: -0.03em;
              display: flex;
              align-items: center;
              gap: 12px;
            }
            .pulse {
              width: 14px;
              height: 14px;
              border-radius: 50%;
              background: var(--accent);
              box-shadow: 0 0 0 8px rgba(125, 243, 192, 0.12), 0 0 32px rgba(125, 243, 192, 0.45);
            }
            .subtitle {
              color: var(--muted);
              max-width: 780px;
              line-height: 1.6;
              font-size: 16px;
            }
            .grid {
              display: grid;
              grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
              gap: 18px;
              padding: 16px 8vw 8px;
            }
            .card {
              background: linear-gradient(135deg, rgba(17,22,38,0.95), rgba(12,16,26,0.92));
              border: 1px solid var(--border);
              border-radius: 16px;
              padding: 18px;
              backdrop-filter: blur(12px);
              box-shadow: 0 20px 60px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.04);
            }
            .card h3 {
              margin: 0 0 6px;
              font-size: 16px;
              color: var(--muted);
              text-transform: uppercase;
              letter-spacing: 0.08em;
            }
            .big {
              font-size: 34px;
              font-weight: 800;
            }
            .tag {
              display: inline-flex;
              align-items: center;
              gap: 6px;
              padding: 6px 10px;
              border-radius: 999px;
              background: rgba(125,243,192,0.12);
              color: var(--accent);
              font-weight: 700;
              border: 1px solid rgba(125,243,192,0.25);
            }
            .tag.dot::before {
              content: "";
              width: 8px; height: 8px;
              border-radius: 50%;
              background: currentColor;
              box-shadow: 0 0 16px currentColor;
            }
            section { padding: 12px 8vw 40px; }
            .section-title {
              display: flex;
              align-items: center;
              justify-content: space-between;
              gap: 12px;
              margin-bottom: 16px;
            }
            .section-title h2 {
              margin: 0;
              font-size: 20px;
              letter-spacing: -0.02em;
            }
            .timeline { display: flex; flex-direction: column; gap: 14px; }
            .window {
              border: 1px solid var(--border);
              border-radius: 16px;
              background: rgba(255,255,255,0.02);
              padding: 16px;
              position: relative;
              overflow: hidden;
            }
            .window::after {
              content: "";
              position: absolute;
              inset: 0;
              background: linear-gradient(120deg, rgba(125,243,192,0.05), transparent 40%);
              pointer-events: none;
            }
            .window-head {
              display: flex;
              flex-wrap: wrap;
              gap: 10px 14px;
              align-items: center;
              justify-content: space-between;
              position: relative;
              z-index: 1;
            }
            .window-metrics {
              display: flex;
              flex-wrap: wrap;
              gap: 12px;
              color: var(--muted);
              font-size: 14px;
            }
            .window-metrics span { background: rgba(255,255,255,0.04); padding: 6px 10px; border-radius: 10px; }
            button {
              background: linear-gradient(135deg, var(--accent), #6dd3f0);
              color: #041021;
              border: none;
              padding: 10px 14px;
              border-radius: 12px;
              cursor: pointer;
              font-weight: 700;
              box-shadow: 0 8px 30px rgba(125,243,192,0.35);
              transition: transform 0.12s ease, box-shadow 0.12s ease;
            }
            button:hover { transform: translateY(-1px); box-shadow: 0 10px 40px rgba(125,243,192,0.5); }
            .analysis { margin-top: 12px; border-radius: 12px; border: 1px solid var(--border); padding: 14px; background: rgba(5,6,10,0.6); line-height: 1.6; display: none; }
            .analysis.active { display: block; animation: fade 0.25s ease; }
            .pill-row { display: flex; flex-wrap: wrap; gap: 8px; }
            .pill { padding: 6px 10px; border-radius: 999px; background: rgba(125,195,243,0.14); color: var(--accent-2); border: 1px solid rgba(125,195,243,0.25); font-weight: 700; }
            .dual-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 14px; }
            .list { display: grid; gap: 8px; color: var(--muted); }
            .list strong { color: var(--text); }
            @keyframes fade { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: translateY(0); } }
            @media (max-width: 640px) {
              header { padding: 30px 20px 10px; }
              section, .grid { padding-left: 20px; padding-right: 20px; }
            }
          </style>
        </head>
        <body>
          <header>
            <div class=\"title\"><span class=\"pulse\"></span>NetMon AI Traffic Observatory</div>
            <div class=\"subtitle\">Live, AI-enriched visibility into your network flows. Each 5-minute window is scored, narrated by the LLM, and benchmarked against professional-grade operational lenses.</div>
          </header>

          <div class=\"grid\" id=\"stats\">
            <div class=\"card\">
              <h3>Latest Verdict</h3>
              <div class=\"big\" id=\"latest-risk\">--</div>
              <div class=\"pill-row\">
                <span class=\"tag dot\" id=\"latest-window\">Awaiting data</span>
                <span class=\"pill\" id=\"latest-volume\"></span>
              </div>
            </div>
            <div class=\"card\">
              <h3>Detection Mix</h3>
              <div class=\"big\" id=\"attack-ratio\">--</div>
              <div class=\"subtitle\" style=\"margin:6px 0 0;\" id=\"attack-breakdown\"></div>
            </div>
            <div class=\"card\">
              <h3>AI Oversight</h3>
              <div class=\"big\" id=\"summary-count\">0</div>
              <div class=\"subtitle\" style=\"margin:6px 0 0;\">Expert narratives generated for the past hour of activity.</div>
            </div>
            <div class=\"card\">
              <h3>Operational Pulse</h3>
              <div class=\"big\" id=\"payload-avg\">--</div>
              <div class=\"subtitle\" style=\"margin:6px 0 0;\">Avg payload bytes per 5-minute window.</div>
            </div>
          </div>

          <section>
            <div class=\"section-title\">
              <h2>LLM-Driven Timeline</h2>
              <span class=\"tag\">Every window ships with a clickable AI analysis</span>
            </div>
            <div class=\"timeline\" id=\"timeline\"></div>
          </section>

          <section>
            <div class=\"section-title\"><h2>Professional Ops Lenses</h2><span class=\"tag\">Field-ready</span></div>
            <div class=\"dual-grid\">
              <div class=\"card list\" id=\"intel\">
                <h3>Threat Intelligence Spotlight</h3>
                <div id=\"intel-list\"></div>
              </div>
              <div class=\"card list\" id=\"ops\">
                <h3>Reliability & Risk Posture</h3>
                <div id=\"ops-list\"></div>
              </div>
            </div>
          </section>

          <script>
            const timeline = document.getElementById('timeline');
            const stats = {
              latestRisk: document.getElementById('latest-risk'),
              latestWindow: document.getElementById('latest-window'),
              latestVolume: document.getElementById('latest-volume'),
              attackRatio: document.getElementById('attack-ratio'),
              attackBreakdown: document.getElementById('attack-breakdown'),
              summaryCount: document.getElementById('summary-count'),
              payloadAvg: document.getElementById('payload-avg'),
            };

            function fmt(dateStr) {
              return new Date(dateStr).toLocaleString();
            }

            function ratio(attacks, total) {
              if (!total) return '0%';
              return ((attacks / total) * 100).toFixed(1) + '%';
            }

            function renderIntel(attacksPerLabel) {
              const intel = document.getElementById('intel-list');
              const entries = Object.entries(attacksPerLabel || {});
              if (!entries.length) {
                intel.innerHTML = '<div class="subtitle">No active threat labels in view.</div>';
                return;
              }
              intel.innerHTML = entries
                .sort((a,b) => b[1]-a[1])
                .map(([label,count]) => `<div><strong>${label}</strong> — ${count} sightings</div>`)
                .join('');
            }

            function renderOps(windows) {
              const ops = document.getElementById('ops-list');
              const attackHeavy = windows.filter(w => w.metrics.attack_flows > w.metrics.benign_flows).length;
              const unknowns = windows.reduce((s,w) => s + (w.metrics.unknown_flows || 0), 0);
              const payloadAvg = windows.length ?
                Math.round(windows.reduce((s,w)=>s+w.metrics.total_payload_bytes,0)/windows.length) : 0;

              ops.innerHTML = `
                <div><strong>Windows at risk:</strong> ${attackHeavy}/${windows.length} exceed benign traffic</div>
                <div><strong>Unclassified flows:</strong> ${unknowns} flagged for ML deep dive</div>
                <div><strong>Payload average:</strong> ${payloadAvg.toLocaleString()} bytes</div>
                <div><strong>AI coverage:</strong> ${windows.length} narrative summaries ready for incident review</div>
              `;
            }

            function renderStats(windows) {
              if (!windows.length) return;
              const latest = windows[0];
              const totalFlows = latest.metrics.total_flows || (latest.metrics.benign_flows + latest.metrics.attack_flows);
              stats.latestRisk.textContent = ratio(latest.metrics.attack_flows, totalFlows) + ' attack mix';
              stats.latestWindow.textContent = `Window ${fmt(latest.metrics.start_time)} → ${fmt(latest.metrics.end_time)}`;
              stats.latestVolume.textContent = `${totalFlows.toLocaleString()} flows | ${latest.metrics.total_payload_bytes.toLocaleString()} bytes`;

              const attacks = windows.reduce((s,w)=>s+w.metrics.attack_flows,0);
              const benign = windows.reduce((s,w)=>s+w.metrics.benign_flows,0);
              stats.attackRatio.textContent = ratio(attacks, attacks+benign) + ' across last hour';
              const breakdown = Object.entries(latest.metrics.attacks_per_label || {}).slice(0,3)
                .map(([label,count]) => `${label}: ${count}`)
                .join(' · ');
              stats.attackBreakdown.textContent = breakdown || 'No labeled threats in latest window.';
              stats.summaryCount.textContent = windows.length;
              const payloadAvg = windows.length ? Math.round(windows.reduce((s,w)=>s+w.metrics.total_payload_bytes,0)/windows.length) : 0;
              stats.payloadAvg.textContent = payloadAvg.toLocaleString();
            }

            function renderTimeline(windows) {
              timeline.innerHTML = windows.map((w, idx) => {
                const total = w.metrics.total_flows || (w.metrics.benign_flows + w.metrics.attack_flows);
                const attackShare = ratio(w.metrics.attack_flows, total);
                const pills = [
                  `${w.metrics.benign_flows} benign`,
                  `${w.metrics.attack_flows} attack`,
                  `${w.metrics.unknown_flows || 0} unknown`,
                  `${w.metrics.total_packets} packets`,
                ];
                return `
                  <div class="window" data-index="${idx}">
                    <div class="window-head">
                      <div>
                        <div class="tag dot">${attackShare} risk</div>
                        <div class="subtitle" style="margin-top:6px;">${fmt(w.metrics.start_time)} → ${fmt(w.metrics.end_time)}</div>
                      </div>
                      <div class="window-metrics">${pills.map(p=>`<span>${p}</span>`).join('')}</div>
                      <button class="toggle" data-index="${idx}">View AI Analysis</button>
                    </div>
                    <div class="analysis" id="analysis-${idx}">${(w.llm_summary || 'No LLM summary recorded.').replace(/\n/g,'<br>')}</div>
                  </div>
                `;
              }).join('');

              document.querySelectorAll('.toggle').forEach(btn => {
                btn.addEventListener('click', () => {
                  const idx = btn.getAttribute('data-index');
                  const target = document.getElementById(`analysis-${idx}`);
                  target.classList.toggle('active');
                  btn.textContent = target.classList.contains('active') ? 'Hide AI Analysis' : 'View AI Analysis';
                });
              });
            }

            async function load() {
              try {
                const res = await fetch('/api/windows');
                const windows = await res.json();
                windows.sort((a,b)=> new Date(b.metrics.start_time) - new Date(a.metrics.start_time));
                renderTimeline(windows);
                renderStats(windows);
                const latest = windows[0] || { metrics: { attacks_per_label: {} } };
                renderIntel(latest.metrics.attacks_per_label);
                renderOps(windows);
              } catch (err) {
                timeline.innerHTML = `<div class="subtitle">Failed to load windows: ${err}</div>`;
              }
            }

            load();
          </script>
        </body>
        </html>
        """
    )

