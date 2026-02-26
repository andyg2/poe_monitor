import subprocess
import asyncio
import threading
import sqlite3
import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
from flask import Flask, request, redirect, render_template_string
from pysnmp.hlapi.asyncio import (
    SnmpEngine,
    CommunityData,
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
    Integer,
    setCmd
)

# ---------------- CONFIG ----------------
SWITCH_IP = "192.168.2.13"
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

    errorIndication, errorStatus, errorIndex, varBinds = await setCmd(
        SnmpEngine(),
        CommunityData(COMMUNITY),
        UdpTransportTarget((SWITCH_IP, 161)),  # ← NO await, NO .create()
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


# load HTML from file
with open("template.html", "r") as f:
    HTML = f.read()

# ---------------- WEB UI ----------------

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
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(monitor_loop())

    thread = threading.Thread(target=start_asyncio_loop, daemon=True)
    thread.start()

    app.run(host="0.0.0.0", port=5000)
