import subprocess
import asyncio
import threading
import sqlite3
from flask import Flask, request, redirect, render_template_string
from pysnmp.hlapi.asyncio import (
    SnmpEngine,
    CommunityData,
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
    Integer,
    set_cmd
)

# ---------------- CONFIG ----------------
SWITCH_IP = "192.168.1.10"
COMMUNITY = "private"
PING_INTERVAL = 10       # seconds
FAIL_THRESHOLD = 3       # consecutive failures
POE_OFF_TIME = 10        # seconds to keep PoE off

DB_FILE = "cameras.db"
app = Flask(__name__)

# ---------------- DATABASE ----------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS cameras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            target_ip TEXT NOT NULL,
            port_index INTEGER NOT NULL,
            fail_count INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

def get_cameras():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, name, target_ip, port_index, fail_count FROM cameras")
    rows = c.fetchall()
    conn.close()
    return rows

# ---------------- NETWORK ----------------
def ping_host(ip):
    # Windows ping
    result = subprocess.run(["ping", "-n", "1", "-w", "2000", ip], stdout=subprocess.DEVNULL)
    return result.returncode == 0

async def set_poe_state(port_index, state):
    oid = f"1.3.6.1.2.1.105.1.1.1.3.{port_index}"

    # CREATE transport and await it
    transport = await UdpTransportTarget.create((SWITCH_IP, 161))

    errorIndication, errorStatus, errorIndex, varBinds = await set_cmd(
        SnmpEngine(),
        CommunityData(COMMUNITY),
        transport,
        ContextData(),
        ObjectType(ObjectIdentity(oid), Integer(state))
    )

    if errorIndication:
        print(f"SNMP Error: {errorIndication}")
    elif errorStatus:
        print(f"SNMP Error: {errorStatus.prettyPrint()}")
    else:
        print(f"Port {port_index} set to {'ON' if state == 1 else 'OFF'}")

async def power_cycle(port_index):
    print(f"Power cycling port {port_index}...")
    await set_poe_state(port_index, 2)  # OFF
    await asyncio.sleep(POE_OFF_TIME)
    await set_poe_state(port_index, 1)  # ON

# ---------------- MONITOR ----------------
async def monitor_loop():
    while True:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id, target_ip, port_index, fail_count FROM cameras")
        cameras = c.fetchall()

        for cam_id, ip, port, fail_count in cameras:
            if ping_host(ip):
                fail_count = 0
                print(f"{ip} OK")
            else:
                fail_count += 1
                print(f"{ip} FAIL ({fail_count})")
                if fail_count >= FAIL_THRESHOLD:
                    await power_cycle(port)
                    fail_count = 0

            c.execute("UPDATE cameras SET fail_count=? WHERE id=?", (fail_count, cam_id))

        conn.commit()
        conn.close()
        await asyncio.sleep(PING_INTERVAL)

# ---------------- WEB UI ----------------
HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>PoE Camera Monitor</title>

<style>
:root {
    --bg: #0f172a;
    --card: #1e293b;
    --accent: #38bdf8;
    --accent-hover: #0ea5e9;
    --danger: #ef4444;
    --text: #e2e8f0;
    --muted: #94a3b8;
    --border: #334155;
}

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    font-family: system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, sans-serif;
    background: linear-gradient(135deg, #0f172a, #111827);
    color: var(--text);
    padding: 40px;
}

h2 {
    margin-top: 0;
    font-size: 2rem;
    letter-spacing: 1px;
}

h3 {
    margin-bottom: 10px;
    color: var(--accent);
}

.card {
    background: var(--card);
    padding: 25px;
    border-radius: 12px;
    box-shadow: 0 10px 25px rgba(0,0,0,0.4);
    margin-bottom: 30px;
    border: 1px solid var(--border);
}

form {
    display: flex;
    gap: 15px;
    flex-wrap: wrap;
    align-items: flex-end;
}

form label {
    display: flex;
    flex-direction: column;
    font-size: 0.85rem;
    color: var(--muted);
}

input {
    padding: 10px 12px;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: #0f172a;
    color: var(--text);
    outline: none;
    transition: 0.2s ease;
}

input:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 2px rgba(56,189,248,0.3);
}

button {
    padding: 10px 18px;
    border-radius: 8px;
    border: none;
    cursor: pointer;
    font-weight: 600;
    background: var(--accent);
    color: #0f172a;
    transition: 0.2s ease;
}

button:hover {
    background: var(--accent-hover);
}

table {
    width: 100%;
    border-collapse: collapse;
    overflow: hidden;
    border-radius: 10px;
}

th, td {
    padding: 12px 14px;
    text-align: left;
}

th {
    background: #0f172a;
    color: var(--accent);
    font-weight: 600;
    border-bottom: 1px solid var(--border);
}

tr {
    border-bottom: 1px solid var(--border);
    transition: 0.15s ease;
}

tr:hover {
    background: rgba(56,189,248,0.08);
}

td {
    color: var(--text);
}

a {
    color: var(--danger);
    text-decoration: none;
    font-weight: 600;
}

a:hover {
    text-decoration: underline;
}
</style>
</head>

<body>

<h2>PoE Camera Monitor</h2>

<div class="card">
    <h3>Add Camera</h3>
    <form method="post" action="/add">
        <label>
            Name
            <input name="name" required>
        </label>
        <label>
            IP
            <input name="target_ip" required>
        </label>
        <label>
            Port Index
            <input name="port_index" required>
        </label>
        <button type="submit">Add</button>
    </form>
</div>

<div class="card">
    <h3>Existing Cameras</h3>
    <table>
        <tr>
            <th>ID</th>
            <th>Name</th>
            <th>IP</th>
            <th>Port</th>
            <th>Fails</th>
            <th>Action</th>
        </tr>
        {% for c in cameras %}
        <tr>
            <td>{{c[0]}}</td>
            <td>{{c[1]}}</td>
            <td>{{c[2]}}</td>
            <td>{{c[3]}}</td>
            <td>{{c[4]}}</td>
            <td><a href="/delete/{{c[0]}}">Delete</a></td>
        </tr>
        {% endfor %}
    </table>
</div>

</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML, cameras=get_cameras())

@app.route("/add", methods=["POST"])
def add():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT INTO cameras (name, target_ip, port_index) VALUES (?, ?, ?)",
        (request.form["name"], request.form["target_ip"], request.form["port_index"])
    )
    conn.commit()
    conn.close()
    return redirect("/")

@app.route("/delete/<int:id>")
def delete(id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM cameras WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect("/")

# ---------------- START ----------------
if __name__ == "__main__":
    init_db()

    # Run asyncio monitor in a separate thread
    def start_asyncio_loop():
        asyncio.run(monitor_loop())

    thread = threading.Thread(target=start_asyncio_loop, daemon=True)
    thread.start()

    app.run(host="0.0.0.0", port=5000)
