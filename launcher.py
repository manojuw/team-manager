import subprocess
import sys
import os
import signal
import time
import socket
import glob

basedir = os.path.dirname(os.path.abspath(__file__))
processes = []

def port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0

def find_and_kill(pattern):
    for proc_dir in glob.glob("/proc/[0-9]*/cmdline"):
        try:
            pid = int(proc_dir.split("/")[2])
            if pid == os.getpid():
                continue
            with open(proc_dir, "r") as f:
                cmdline = f.read()
                if pattern in cmdline:
                    os.kill(pid, signal.SIGTERM)
        except:
            pass

def cleanup(signum=None, frame=None):
    for p in processes:
        try:
            p.terminate()
        except:
            pass
    time.sleep(1)
    for p in processes:
        try:
            p.kill()
        except:
            pass
    try:
        os.remove("/tmp/teams_kb_started")
    except:
        pass
    sys.exit(0)

signal.signal(signal.SIGTERM, cleanup)
signal.signal(signal.SIGINT, cleanup)

print("[LAUNCHER] Starting Teams Knowledge Base services...", flush=True)

if not port_in_use(3001):
    mgmt = subprocess.Popen(
        ["npx", "tsx", "src/index.ts"],
        cwd=os.path.join(basedir, "backend", "management"),
    )
    processes.append(mgmt)
    print("[LAUNCHER] Started Management API (port 3001)", flush=True)
else:
    print("[LAUNCHER] Management API already running on 3001", flush=True)

if not port_in_use(8001):
    ai = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"],
        cwd=os.path.join(basedir, "backend", "ai-service"),
    )
    processes.append(ai)
    print("[LAUNCHER] Started AI Service (port 8001)", flush=True)
else:
    print("[LAUNCHER] AI Service already running on 8001", flush=True)

time.sleep(3)

if port_in_use(5000):
    print("[LAUNCHER] Killing streamlit to free port 5000...", flush=True)
    find_and_kill("streamlit")
    time.sleep(3)
    find_and_kill("streamlit")
    time.sleep(2)

    for i in range(15):
        if not port_in_use(5000):
            print("[LAUNCHER] Port 5000 is free", flush=True)
            break
        time.sleep(1)
    else:
        print("[LAUNCHER] Warning: Port 5000 still in use after waiting", flush=True)

if not port_in_use(5000):
    frontend = subprocess.Popen(
        ["npx", "next", "dev", "--hostname", "0.0.0.0", "--port", "5000"],
        cwd=os.path.join(basedir, "frontend"),
    )
    processes.append(frontend)
    print("[LAUNCHER] Started Next.js frontend (port 5000)", flush=True)
elif port_in_use(5000):
    print("[LAUNCHER] Port 5000 already in use (Next.js may already be running)", flush=True)

try:
    while True:
        for p in list(processes):
            ret = p.poll()
            if ret is not None:
                processes.remove(p)
        if not processes:
            print("[LAUNCHER] All managed processes exited, shutting down", flush=True)
            break
        time.sleep(5)
except KeyboardInterrupt:
    cleanup()
