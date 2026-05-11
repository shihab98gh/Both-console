import os
import logging
import requests
import threading
import time
from datetime import datetime
from random import uniform
from flask import Flask, jsonify, render_template_string, request
from waitress import serve

# ---------- CONFIGURATION ----------
EMAIL = os.environ.get("EMAIL", "shihab98bc@gmail.com")
PASSWORD = os.environ.get("PASSWORD", "Zxcv1234+-*/")
MNIT_BASE_URL = "https://x.mnitnetwork.com/mapi/v1"
STEX_BASE_URL = "https://stexsms.com/mapi/v1"
MAX_LOGS = 100
POLL_INTERVAL = 10            # 10 seconds between full cycles
INFO_TIMEOUT = 15
MAX_RETRIES = 2
RATE_LIMIT_SLEEP = 10         # wait if 429 occurs
# -----------------------------------

app = Flask(__name__)

# Separate log stores per site
logs_mnit = []
logs_stex = []
seen_mnit = set()
seen_stex = set()

logging.basicConfig(level=logging.WARNING,
                    format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


def poll_site(site_name, base_url, logs_list, seen_ids):
    """Poll a stexsms-compatible API, handle auth, timeouts, 429."""
    session = requests.Session()
    headers = {
        "user-agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36",
        "content-type": "application/json",
        "accept": "application/json, text/plain, */*",
        "origin": "https://stexsms.com"
    }

    def login():
        try:
            resp = session.post(
                f"{base_url}/mauth/login",
                json={"email": EMAIL, "password": PASSWORD},
                headers=headers,
                timeout=10
            )
            if resp.status_code == 200:
                token = resp.json().get("data", {}).get("token")
                if token:
                    headers["mauthtoken"] = token
                    logger.info(f"[{site_name}] Login successful")
                    return True
            logger.warning(f"[{site_name}] Login failed ({resp.status_code})")
        except Exception as e:
            logger.error(f"[{site_name}] Login exception: {e}")
        return False

    if not login():
        return False

    info_url = f"{base_url}/mdashboard/console/info"

    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = session.get(info_url, headers=headers, timeout=INFO_TIMEOUT)

            if resp.status_code == 401:
                logger.warning(f"[{site_name}] Token expired – re‑login")
                if login():
                    continue
                return False

            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                wait = int(retry_after) if retry_after and retry_after.isdigit() else RATE_LIMIT_SLEEP
                wait = min(wait, 30)
                logger.warning(f"[{site_name}] 429 – waiting {wait}s")
                time.sleep(wait)
                return False

            if resp.status_code == 200:
                data = resp.json().get("data", {}).get("logs", [])
                for item in reversed(data):
                    log_id = str(item.get('id', ''))
                    if log_id and log_id not in seen_ids:
                        log_entry = {
                            "id": log_id,
                            "app": item.get('app_name', 'Unknown'),
                            "number": item.get('number', 'N/A'),
                            "range": str(item.get('range', 'N/A')),
                            "country": item.get('country', 'N/A'),
                            "message": item.get('sms', 'No Message'),
                            "received_at": datetime.now().strftime("%H:%M:%S")
                        }
                        logs_list.insert(0, log_entry)
                        seen_ids.add(log_id)
                        if len(logs_list) > MAX_LOGS:
                            logs_list.pop()
                if len(seen_ids) > 1000:
                    keep = list(seen_ids)[-500:]
                    seen_ids.clear()
                    seen_ids.update(keep)
                return True

            logger.warning(f"[{site_name}] Unexpected status {resp.status_code}")
            return False

        except requests.exceptions.Timeout:
            if attempt < MAX_RETRIES:
                logger.info(f"[{site_name}] Timeout, retry {attempt+1}")
                time.sleep(1)
            else:
                logger.warning(f"[{site_name}] Timeout after {MAX_RETRIES+1} attempts")
        except Exception as e:
            logger.error(f"[{site_name}] Exception: {e}")
            break

    return False


def monitor_loop():
    """Poll both sites every POLL_INTERVAL seconds."""
    if not EMAIL or not PASSWORD:
        logger.error("EMAIL and PASSWORD must be set!")
        return

    while True:
        cycle_start = time.time()
        poll_site("Mnitnetwork", MNIT_BASE_URL, logs_mnit, seen_mnit)
        poll_site("Stexsms", STEX_BASE_URL, logs_stex, seen_stex)
        elapsed = time.time() - cycle_start
        sleep_time = max(0, POLL_INTERVAL - elapsed) + uniform(-0.5, 0.5)
        if sleep_time < 0.1:
            sleep_time = 0.1
        time.sleep(sleep_time)


# ---------- FRONTEND (butter-smooth animations) ----------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>TSB Console Zone (Live)</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Inter', sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh; color: #e0e0e0;
        }
        .container { max-width: 680px; margin: auto; padding: 20px 15px; }
        .header { text-align: center; margin-bottom: 20px; }
        .header h1 {
            font-size: 2rem; font-weight: 700;
            background: linear-gradient(to right, #00b4d8, #90e0ef);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            text-transform: uppercase; letter-spacing: 2px;
            animation: fadeInDown 0.6s ease;
        }
        .button-group { display: flex; justify-content: center; gap: 10px; margin-bottom: 15px; flex-wrap: wrap; }
        .btn {
            border: none; border-radius: 50px; padding: 10px 20px;
            font-size: 0.9rem; font-weight: 600; cursor: pointer;
            transition: all 0.25s ease; background: #2a2a4a; color: #aaa;
            box-shadow: 0 4px 10px rgba(0,0,0,0.3); letter-spacing: 0.5px;
            white-space: nowrap;
            will-change: transform, box-shadow;
        }
        .btn:hover { transform: translateY(-2px); box-shadow: 0 8px 20px rgba(0,0,0,0.5); }
        .btn.active { transform: translateY(-2px); }
        .site-btn.active { background: linear-gradient(135deg, #00b4d8, #0077b6); color: white; }
        .filter-btn.active { background: linear-gradient(135deg, #fca311, #ffb703); color: #1a1a2e; }
        .filter-btn[data-filter="instagram"].active {
            background: linear-gradient(135deg, #E1306C, #F77737);
            color: white;
        }

        /* Card animations */
        .card {
            background: rgba(255,255,255,0.05); backdrop-filter: blur(12px);
            border: 1px solid rgba(255,255,255,0.1); border-radius: 16px;
            padding: 16px; margin-bottom: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            animation: fadeInUp 0.35s ease forwards;
            transition: transform 0.2s ease;
            will-change: transform;
        }
        .card:hover { transform: scale(1.02); }
        .row {
            display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 8px; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 6px;
        }
        .app-name { font-weight: 700; color: #00b4d8; font-size: 1rem; }
        .sync-time { font-size: 0.75rem; color: #8d99ae; }
        .data-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 10px; margin-top: 10px; }
        .data-item { background: rgba(0,0,0,0.2); border-radius: 8px; padding: 8px; }
        .label { font-size: 0.65rem; text-transform: uppercase; color: #8d99ae; margin-bottom: 4px; }
        .val { font-size: 0.85rem; font-weight: 600; color: #e0e0e0; word-break: break-all; }
        .copy-number { cursor: pointer; padding: 2px 4px; border-radius: 4px; transition: background-color 0.2s; }
        .copy-number:hover { background-color: rgba(0,180,216,0.25); }
        .sms-box {
            background: rgba(255,70,70,0.1); border: 1px dashed rgba(255,100,100,0.3);
            padding: 12px; border-radius: 10px; margin-top: 12px;
        }
        .sms-text { color: #ff6b6b; font-weight: 700; font-family: 'Courier New', monospace; font-size: 1rem; word-break: break-all; }
        #status { text-align:center; margin-top:30px; color:#6c757d; font-size:0.8rem; animation: fadeIn 0.5s; }
        .no-logs { text-align:center; padding:40px; color:#999; font-style:italic; animation: fadeIn 0.6s; }

        /* Keyframes */
        @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        @keyframes fadeInDown {
            from { opacity: 0; transform: translateY(-20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        @keyframes fadeIn {
            from { opacity: 0; } to { opacity: 1; }
        }
        @media (max-width:480px) {
            .data-grid { grid-template-columns:1fr 1fr; }
            .btn { padding:8px 14px; font-size:0.8rem; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header"><h1>ORBIT lIVE CONSOLE</h1></div>
        <div class="button-group" id="siteButtons">
            <button class="btn site-btn active" data-site="mnitnetwork">Mnitnetwork</button>
            <button class="btn site-btn" data-site="stexsms">Stexsms</button>
        </div>
        <div class="button-group" id="filterButtons">
            <button class="btn filter-btn active" data-filter="all">All</button>
            <button class="btn filter-btn" data-filter="facebook">Facebook</button>
            <button class="btn filter-btn" data-filter="instagram">Instagram</button>
            <button class="btn filter-btn" data-filter="whatsapp">WhatsApp</button>
        </div>
        <div id="logs"></div>
        <div id="status"></div>
    </div>
    <script>
        const REFRESH_MS = 3000;  // faster refresh for real-time feel
        let currentSite = 'mnitnetwork';
        let currentFilter = 'all';

        // Smooth button updates
        function setActiveSite(btn) {
            document.querySelectorAll('.site-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentSite = btn.dataset.site;
            loadLogs();
        }

        function setActiveFilter(btn) {
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentFilter = btn.dataset.filter;
            loadLogs();
        }

        document.getElementById('siteButtons').addEventListener('click', e => {
            const btn = e.target.closest('.site-btn');
            if (btn) setActiveSite(btn);
        });

        document.getElementById('filterButtons').addEventListener('click', e => {
            const btn = e.target.closest('.filter-btn');
            if (btn) setActiveFilter(btn);
        });

        // Efficient rendering: only update if data changed
        let lastLogsKey = '';

        async function loadLogs() {
            try {
                const res = await fetch(`/api/logs?site=${currentSite}&filter=${currentFilter}`);
                const data = await res.json();
                const key = JSON.stringify(data);
                if (key === lastLogsKey) return;  // no new data, skip DOM update
                lastLogsKey = key;

                const container = document.getElementById('logs');
                const status = document.getElementById('status');

                if (!data.length) {
                    container.innerHTML = '<div class="no-logs">Waiting for SMS...</div>';
                } else {
                    container.innerHTML = data.map(log => `
                        <div class="card">
                            <div class="row">
                                <span class="app-name">${log.app}</span>
                                <span class="sync-time">${log.received_at}</span>
                            </div>
                            <div class="data-grid">
                                <div class="data-item">
                                    <div class="label">Number</div>
                                    <div class="val copy-number" title="Click to copy">${log.number}</div>
                                </div>
                                <div class="data-item">
                                    <div class="label">Range</div>
                                    <div class="val">${log.range}</div>
                                </div>
                                <div class="data-item">
                                    <div class="label">Country</div>
                                    <div class="val">${log.country}</div>
                                </div>
                            </div>
                            <div class="sms-box">
                                <div class="label">OTP / SMS Content</div>
                                <div class="sms-text">${log.message}</div>
                            </div>
                        </div>
                    `).join('');
                }
                status.innerText = `Last update: ${new Date().toLocaleTimeString()}`;
            } catch(e) {
                console.error('Load error:', e);
            }
        }

        // Copy number with feedback
        document.getElementById('logs').addEventListener('click', e => {
            const target = e.target.closest('.copy-number');
            if (!target) return;
            const text = target.innerText.trim();
            if (!text) return;
            navigator.clipboard.writeText(text).then(() => {
                target.style.backgroundColor = '#d4edda';
                target.title = 'Copied!';
                setTimeout(() => {
                    target.style.backgroundColor = '';
                    target.title = 'Click to copy';
                }, 800);
            }).catch(() => {
                const inp = document.createElement('input');
                inp.value = text;
                document.body.appendChild(inp);
                inp.select();
                document.execCommand('copy');
                document.body.removeChild(inp);
                target.title = 'Copied!';
                setTimeout(() => { target.title = 'Click to copy'; }, 800);
            });
        });

        loadLogs();
        setInterval(loadLogs, REFRESH_MS);
    </script>
</body>
</html>
"""


@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/logs')
def get_logs():
    site = request.args.get('site', 'mnitnetwork').lower()
    filter_type = request.args.get('filter', 'all').lower()
    logs = logs_stex if site == 'stexsms' else logs_mnit

    if filter_type == 'all':
        return jsonify(logs)

    filtered = []
    for log in logs:
        app_lower = log['app'].lower()
        range_lower = log['range'].lower()
        msg_lower = log['message'].lower()

        if filter_type == 'facebook':
            if 'facebook' in app_lower or 'facebook' in range_lower:
                filtered.append(log)
        elif filter_type == 'instagram':
            if 'instagram' in app_lower or 'instagram' in range_lower or 'instagram' in msg_lower:
                filtered.append(log)
        elif filter_type == 'whatsapp':
            if 'whatsapp' in app_lower or 'whatsapp' in range_lower:
                filtered.append(log)

    return jsonify(filtered)


if __name__ == "__main__":
    threading.Thread(target=monitor_loop, daemon=True).start()
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Server starting on port {port}")
    serve(app, host='0.0.0.0', port=port, threads=4)