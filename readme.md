# PoE Camera Monitor

This Python project monitors IP cameras and power cycles their PoE port via SNMP if they stop responding to ping.

## Features

- Web interface (Flask) to **add/delete cameras**
- Background monitoring loop that **pings each camera**
- **Power cycles PoE port** using SNMP v2c if consecutive failures reach threshold
- Works with **Netgear FS728TP** and similar managed PoE switches
- Fully compatible with **Python 3.12** + **pysnmp 5.x**

## Requirements

- Python 3.12+
- Windows/Linux
- Managed PoE switch with SNMP enabled

## Installation

1. Clone or download this repo
2. Create a virtual environment:

```bash
python -m venv venv
venv\Scripts\activate   # Windows
source venv/bin/activate # Linux/macOS
````

3. Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

Run the script:

```bash
python poe_monitor.py
```

* Web UI: `http://localhost:5000`
* Add cameras with IP and PoE port index
* Background monitor pings each camera every 10s (configurable)
* Power cycles cameras after 3 consecutive ping failures (configurable)

Press `CTRL+C` to stop.

## Configuration

Edit variables at the top of `poe_monitor.py`:

```python
SWITCH_IP = "192.168.1.10"      # Your PoE switch IP
COMMUNITY = "private"            # SNMP community
PING_INTERVAL = 10               # seconds
FAIL_THRESHOLD = 3               # consecutive failures
POE_OFF_TIME = 10                # seconds to keep PoE off
DB_FILE = "cameras.db"           # SQLite DB file
```

## Notes

* Use **Python 3.12** with pysnmp 5.x

## **Background Execution**

You can run the PoE monitor in the background so it starts automatically or runs at system boot.

### **Windows – Scheduled Task**

1. Open **Task Scheduler**.
2. Click **Create Task…**
3. **General** tab:

   * Name: `PoE Camera Monitor`
   * Select: “Run whether user is logged on or not”
   * Check: “Run with highest privileges”
4. **Triggers** tab:

   * Click **New…**
   * Begin the task: **At startup** (or set a schedule)
5. **Actions** tab:

   * Click **New…**
   * Action: **Start a program**
   * Program/script: `C:\Python312\python.exe`
   * Add arguments: `C:\TEMP\poe_monitor\poe_monitor.py`
   * Start in: `C:\TEMP\poe_monitor`
6. **Conditions** and **Settings** tabs:

   * Adjust as needed (e.g., “Wake the computer to run this task”)
7. Click **OK** and enter your credentials.

Your script will now run automatically in the background.

---

### **Linux/macOS – cronjob**

1. Open a terminal.
2. Edit your crontab:

```bash
crontab -e
```

3. Add a line to run at boot:

```cron
@reboot /usr/bin/python3 /home/user/poe_monitor/poe_monitor.py >> /home/user/poe_monitor/poe_monitor.log 2>&1
```

> Adjust `/usr/bin/python3` and the script path to your environment.
> `>> ... 2>&1` logs output to a file so you can debug errors.

4. Save and exit. The script will start automatically at boot.
