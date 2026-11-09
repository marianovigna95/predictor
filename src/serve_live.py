#!/usr/bin/env python3
"""serve_live.py — server statico per /home/user/sito MA /diretta.html viene rigenerata
ad ogni richiesta (cache 20s) così la diretta è VERAMENTE live.
Uso: python3 src/serve_live.py [--port 8002]
"""
import argparse
import subprocess
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SITO = Path("/home/user/sito")
SRC = Path(__file__).resolve().parent

_cache = {"t": 0.0, "lock": threading.Lock()}
CACHE_S = 20
ROOT = SRC.parent
DATA = ROOT / "data"


def _newest(path, pattern):
    try:
        return max(f.stat().st_mtime for f in path.glob(pattern))
    except ValueError:
        return 0.0


def maybe_regen_all():
    """Se i dati sono più recenti del sito, rigenera TUTTO (make_site + diretta + mirror)."""
    try:
        site_m = (SITO / "index.html").stat().st_mtime if (SITO / "index.html").exists() else 0
        data_m = max(_newest(DATA, "*.csv"), _newest(SRC, "*.py"))
        if data_m > site_m + 1:
            subprocess.run([sys.executable, str(SRC / "make_site.py")], capture_output=True, timeout=600, cwd=ROOT)
            subprocess.run([sys.executable, str(SRC / "step19_diretta.py")], capture_output=True, timeout=600, cwd=ROOT)
            subprocess.run(["cp", str(ROOT / "site" / "*.html"), str(SITO) + "/"], capture_output=False, timeout=60) if False else None
            for f in (ROOT / "site").glob("*.html"):
                subprocess.run(["cp", str(f), str(SITO) + "/"], capture_output=True)
            print(f"♻️ auto-regen sito (dati più recenti)", flush=True)
    except Exception as e:
        print("regen err:", e, flush=True)


def regen_diretta():
    with _cache["lock"]:
        now = time.time()
        if now - _cache["t"] < CACHE_S and (SITO / "diretta.html").exists():
            maybe_regen_all()
            return
        maybe_regen_all()
        subprocess.run([sys.executable, str(SRC / "step19_diretta.py")],
                       capture_output=True, timeout=300)
        _cache["t"] = now


def _watcher():
    while True:
        time.sleep(20)
        maybe_regen_all()
        with _cache["lock"]:
            if time.time() - _cache["t"] >= CACHE_S:
                subprocess.run([sys.executable, str(SRC / "step19_diretta.py")], capture_output=True, timeout=300)
                _cache["t"] = time.time()


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?")[0] in ("/diretta.html", "/"):
            if self.path.split("?")[0] == "/":
                self.path = "/index.html"
            regen_diretta()
        super().do_GET()

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8002)
    a = ap.parse_args()
    import os
    os.chdir(SITO)
    threading.Thread(target=_watcher, daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", a.port), Handler)
    print(f"🔴 live server su 0.0.0.0:{a.port} (diretta ogni {CACHE_S}s + auto-regen sito quando cambiano i dati)")
    srv.serve_forever()
