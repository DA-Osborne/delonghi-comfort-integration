"""Local web explorer for one De'Longhi device's cloud properties.

Shows every property live, logs each change with a time, lets you write values to
writable properties, and keeps notes. Meant for working out what properties do.

Credentials come from DELONGHI_USERNAME, DELONGHI_PASSWORD, DELONGHI_LANGUAGE and
DELONGHI_DEVICE_INDEX, or are prompted for. The page only listens on 127.0.0.1 and
needs the one-time token printed at startup. Session data is saved to
scripts/explorer_session.json, which Git ignores.

Writing arbitrary values to a device is at your own risk. Each write is logged with
the previous value so it can be restored.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import importlib
import json
import os
import re
import secrets
import time
import webbrowser
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp import web

import inspect_device as base

SESSION_PATH = Path(__file__).resolve().with_name("explorer_session.json")
API_BASE = "https://ads-eu.aylanetworks.com"
NAME_PATTERN = re.compile(r"[A-Za-z0-9_]+")
MAX_LOG = 2000

const = importlib.import_module(f"{base.PACKAGE_NAME}.const")


def now() -> float:
    return time.time()


def coerce(base_type: str, raw: str, mode: str) -> Any:
    """Convert text from the page into the JSON value to send."""
    text = raw.strip()
    if mode == "string":
        return raw
    if mode == "number" or (mode == "auto" and base_type in ("integer", "decimal")):
        number = float(text)
        return int(number) if number.is_integer() and "." not in text else number
    if mode == "boolean" or (mode == "auto" and base_type == "boolean"):
        lowered = text.lower()
        # The cloud rejects a JSON true (HTTP 422) for these properties but
        # accepts the numbers 1 and 0, so send numbers.
        if lowered in ("1", "true", "on", "yes"):
            return 1
        if lowered in ("0", "false", "off", "no"):
            return 0
        raise ValueError("Boolean needs 1/0, true/false or on/off.")
    return raw


class Explorer:
    def __init__(self, api: Any, dsn: str, interval: float) -> None:
        self.api = api
        self.dsn = dsn
        self.interval = interval
        self.properties: dict[str, dict[str, Any]] = {}
        self.last_change: dict[str, float] = {}
        self.changes: list[dict[str, Any]] = []
        self.writes: list[dict[str, Any]] = []
        self.notes: dict[str, str] = {}
        self.polled_at: float | None = None
        self.last_error: str | None = None
        self.poll_count = 0
        self._wake = asyncio.Event()
        self.stop = asyncio.Event()
        self._load()

    # ---- persistence -----------------------------------------------------
    def _load(self) -> None:
        if SESSION_PATH.is_file():
            try:
                data = json.loads(SESSION_PATH.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return
            self.notes = data.get("notes", {})
            self.changes = data.get("changes", [])[-MAX_LOG:]
            self.writes = data.get("writes", [])[-MAX_LOG:]

    def save(self) -> None:
        payload = base.redact_sensitive(
            {
                "saved_at": now(),
                "notes": self.notes,
                "changes": self.changes[-MAX_LOG:],
                "writes": self.writes[-MAX_LOG:],
                "properties": {
                    name: {
                        key: rec.get(key)
                        for key in (
                            "base_type", "read_only", "direction", "display_name", "value",
                            "data_updated_at",
                        )
                    }
                    for name, rec in self.properties.items()
                },
            }
        )
        try:
            SESSION_PATH.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
                encoding="utf-8",
            )
        except OSError as err:
            print(f"Could not save session ({type(err).__name__}).")

    # ---- polling ---------------------------------------------------------
    async def poll(self) -> None:
        try:
            records = await self.api.get_device_properties(self.dsn)
        except Exception as err:  # keep the page alive and show the problem
            self.last_error = f"{type(err).__name__}: {err}"
            return
        self.last_error = None
        stamp = now()
        first = self.polled_at is None
        change_count = len(self.changes)
        seen: dict[str, dict[str, Any]] = {}
        for record in records:
            record = record.get("property", record)
            if isinstance(record, dict) and "name" in record:
                seen[record["name"]] = record
        for name, record in seen.items():
            old = self.properties.get(name)
            if old is not None and old.get("value") != record.get("value"):
                self.changes.append(
                    {
                        "t": stamp,
                        "name": name,
                        "old": old.get("value"),
                        "new": record.get("value"),
                        "device_updated": record.get("data_updated_at"),
                    }
                )
                self.last_change[name] = stamp
        self.properties = seen
        self.polled_at = stamp
        self.poll_count += 1
        if not first and len(self.changes) != change_count:
            self.save()

    async def run_polling(self) -> None:
        while not self.stop.is_set():
            await self.poll()
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=self.interval)
            except asyncio.TimeoutError:
                pass

    def poll_soon(self) -> None:
        self._wake.set()

    def add_marker(self, text: str) -> None:
        """Add a labelled event (for example an action taken in the app) to the log."""
        text = text.strip()[:300]
        if not text:
            return
        self.changes.append(
            {"t": now(), "name": "marker", "old": None, "new": text,
             "device_updated": None, "marker": True}
        )
        self.save()

    # ---- writing ---------------------------------------------------------
    async def _post(self, name: str, value: Any) -> tuple[int, str]:
        url = f"{API_BASE}/apiv1/dsns/{self.dsn}/properties/{name}/datapoints.json"
        for attempt in (1, 2):
            headers = {
                "User-Agent": const.API_USER_AGENT,
                "Authorization": f"auth_token {self.api.access_token}",
                "Content-Type": "application/json",
            }
            async with self.api.session.post(
                url, headers=headers, json={"datapoint": {"value": value}}
            ) as response:
                body = await response.text()
                if response.status == 401 and attempt == 1:
                    self.api.access_token = await self.api.refresh_access_token()
                    continue
                return response.status, body[:300]
        return 0, "unreachable"

    async def write(self, name: str, raw: str, mode: str) -> dict[str, Any]:
        record = self.properties.get(name)
        if record is None or not NAME_PATTERN.fullmatch(name):
            return {"ok": False, "error": "Unknown property."}
        if record.get("read_only"):
            return {"ok": False, "error": "Property is read-only."}
        try:
            value = coerce(str(record.get("base_type")), raw, mode)
        except ValueError as err:
            return {"ok": False, "error": str(err)}
        old = record.get("value")
        try:
            status, body = await self._post(name, value)
        except aiohttp.ClientError as err:
            status, body = 0, type(err).__name__
        ok = 200 <= status < 300
        self.writes.append(
            {
                "t": now(), "name": name, "old": old, "sent": value,
                "mode": mode, "status": status, "ok": ok, "response": body if not ok else "",
            }
        )
        self.save()
        self.poll_soon()
        return {"ok": ok, "status": status, "sent": value, "response": body}

    # ---- view ------------------------------------------------------------
    def view(self) -> dict[str, Any]:
        return {
            "device": self.dsn[-4:],
            "polled_at": self.polled_at,
            "interval": self.interval,
            "poll_count": self.poll_count,
            "error": self.last_error,
            "properties": [
                {
                    "name": name,
                    "display_name": rec.get("display_name"),
                    "base_type": rec.get("base_type"),
                    "read_only": bool(rec.get("read_only")),
                    "direction": rec.get("direction"),
                    "value": rec.get("value"),
                    "device_updated": rec.get("data_updated_at"),
                    "last_change": self.last_change.get(name),
                    "note": self.notes.get(name, ""),
                }
                for name, rec in sorted(self.properties.items())
            ],
            "changes": self.changes[-300:],
            "writes": self.writes[-100:],
        }


# ---- web layer ---------------------------------------------------------------
def build_app(explorer: Explorer, token: str, port: int) -> web.Application:
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    @web.middleware
    async def guard(request: web.Request, handler: Any) -> web.StreamResponse:
        if request.headers.get("Host") not in allowed_hosts:
            raise web.HTTPForbidden(text="Bad host.")
        supplied = request.headers.get("X-Token") or request.query.get("token")
        if not secrets.compare_digest(supplied or "", token):
            raise web.HTTPForbidden(text="Missing or wrong token.")
        return await handler(request)

    async def index(request: web.Request) -> web.Response:
        return web.Response(
            text=PAGE.replace("__TOKEN__", token), content_type="text/html"
        )

    async def state(request: web.Request) -> web.Response:
        return web.json_response(explorer.view())

    async def write(request: web.Request) -> web.Response:
        body = await request.json()
        result = await explorer.write(
            str(body.get("name", "")), str(body.get("value", "")), str(body.get("mode", "auto"))
        )
        return web.json_response(result)

    async def note(request: web.Request) -> web.Response:
        body = await request.json()
        name = str(body.get("name", ""))
        if name in explorer.properties:
            text = str(body.get("note", ""))[:2000]
            if text:
                explorer.notes[name] = text
            else:
                explorer.notes.pop(name, None)
            explorer.save()
        return web.json_response({"ok": True})

    async def marker(request: web.Request) -> web.Response:
        body = await request.json()
        explorer.add_marker(str(body.get("text", "")))
        return web.json_response({"ok": True})

    async def refresh(request: web.Request) -> web.Response:
        explorer.poll_soon()
        return web.json_response({"ok": True})

    async def interval(request: web.Request) -> web.Response:
        body = await request.json()
        explorer.interval = min(max(float(body.get("seconds", 10)), 3.0), 300.0)
        explorer.poll_soon()
        return web.json_response({"ok": True, "interval": explorer.interval})

    async def shutdown(request: web.Request) -> web.Response:
        explorer.stop.set()
        explorer.poll_soon()
        return web.json_response({"ok": True})

    app = web.Application(middlewares=[guard])
    app.add_routes(
        [
            web.get("/", index),
            web.get("/api/state", state),
            web.post("/api/write", write),
            web.post("/api/note", note),
            web.post("/api/refresh", refresh),
            web.post("/api/marker", marker),
            web.post("/api/interval", interval),
            web.post("/api/shutdown", shutdown),
        ]
    )
    return app


PAGE = r"""<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>De'Longhi explorer</title>
<style>
  * { box-sizing: border-box; }
  body { font: 14px system-ui, sans-serif; margin: 0; background: #f2f4f7; color: #1c1e21; }
  header { position: sticky; top: 0; z-index: 5; background: #fff; border-bottom: 1px solid #d0d4da; padding: 6px 10px; }
  .top { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 12px; }
  .bar { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; margin-top: 4px; }
  .bar label { white-space: nowrap; }
  #filter { flex: 1 1 140px; min-width: 100px; }
  #marker { flex: 1 1 220px; min-width: 120px; }
  #interval { width: 52px; }
  #tabs { display: none; gap: 6px; margin-top: 6px; }
  #tabs button.on { background: #1c1e21; color: #fff; }
  main { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 12px; padding: 10px; }
  main > * { min-width: 0; }
  @media (max-width: 1100px) {
    main { grid-template-columns: minmax(0, 1fr); }
    #tabs { display: flex; }
    body[data-tab="props"] #log { display: none; }
    body[data-tab="log"] #props { display: none; }
  }
  .prop { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 2px 12px; padding: 6px 8px; background: #fff; border-bottom: 1px solid #e3e6ea; }
  .prop.changed { background: #fff3c4; }
  .prop.ro { background-color: #fbfbfc; }
  .prop.ro.changed { background: #fff3c4; }
  .prop .id { overflow-wrap: anywhere; }
  .prop .vals { text-align: right; }
  .prop .ctl { grid-column: 1 / -1; display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
  .prop .ctl .note { flex: 1 1 140px; min-width: 100px; font: inherit; resize: vertical; overflow: hidden; }
  .prop .ctl .writebox { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; }
  .prop .ctl .writebox input { width: 90px; }
  @media (max-width: 560px) {
    .prop { grid-template-columns: minmax(0, 1fr); }
    .prop .vals { text-align: left; }
  }
  code { font-size: 12px; font-weight: 600; }
  .val { font-size: 15px; font-weight: 700; overflow-wrap: anywhere; word-break: normal; }
  .val.empty { color: #9aa0a6; font-weight: 400; }
  .muted { color: #6b7280; font-size: 12px; }
  .chip { display: inline-block; font-size: 11px; line-height: 1; padding: 2px 5px; margin-right: 3px; border-radius: 8px; background: #e8eaee; color: #4b5563; }
  .chip.w { background: #d7f0dd; color: #0f5132; }
  .panel { background: #fff; border: 1px solid #d0d4da; padding: 8px; margin-bottom: 10px; max-height: 44vh; overflow: auto; }
  @media (max-width: 1100px) { .panel { max-height: none; } }
  .panel h3 { margin: 0 0 6px; font-size: 14px; }
  .entry { padding: 2px 0; overflow-wrap: anywhere; border-bottom: 1px solid #f0f1f3; }
  .entry.marker { background: #e8f0fe; font-weight: 600; padding: 3px 4px; }
  .ok { color: #137333; } .bad { color: #b3261e; }
  #toast { position: fixed; bottom: 12px; left: 12px; right: 12px; background: #1c1e21; color: #fff; padding: 8px 12px; display: none; z-index: 9; }
  button { cursor: pointer; }
  input[type=text], input[type=number], select { max-width: 100%; }
</style>
<header>
  <div class="top">
    <b>De'Longhi explorer</b>
    <span class="muted" id="device"></span>
    <span class="muted" id="status"></span>
  </div>
  <div class="bar">
    <label>Poll every <input id="interval" type="number" min="3" max="300" value="10"> s</label>
    <button id="refresh">Poll now</button>
    <input id="filter" type="text" placeholder="Filter name or label">
    <label><input type="checkbox" id="writable"> writable</label>
    <label><input type="checkbox" id="recent"> changed</label>
    <button id="stop">Stop server</button>
  </div>
  <div class="bar">
    <input id="marker" type="text" placeholder="Log what you just did, e.g. app: set timer 2h">
    <button id="mark">Log it</button>
  </div>
  <div id="tabs">
    <button data-tab="props" class="on">Properties</button>
    <button data-tab="log">Log <span id="logcount"></span></button>
  </div>
</header>
<main>
  <section id="props"><div id="rows"></div></section>
  <aside id="log">
    <div class="panel"><h3>Changes (newest first)</h3><div id="changes"></div></div>
    <div class="panel"><h3>Writes</h3><div id="writes"></div></div>
  </aside>
</main>
<div id="toast"></div>
<script>
const TOKEN = "__TOKEN__";
const H = {"X-Token": TOKEN, "Content-Type": "application/json"};
const rows = new Map();
let latest = null;
const fmt = t => t ? new Date(t * 1000).toLocaleTimeString() : "";
const isEmpty = v => v === null || v === undefined || v === "";
const show = v => isEmpty(v) ? "(empty)" : String(v);
function toast(msg, bad) {
  const t = document.getElementById("toast");
  t.textContent = msg; t.style.background = bad ? "#b3261e" : "#1c1e21"; t.style.display = "block";
  clearTimeout(toast.h); toast.h = setTimeout(() => t.style.display = "none", 6000);
}
async function post(path, body) {
  const r = await fetch(path, {method: "POST", headers: H, body: JSON.stringify(body || {})});
  return r.json();
}
function el(tag, props, ...kids) {
  const e = Object.assign(document.createElement(tag), props || {});
  kids.forEach(k => e.append(k)); return e;
}
function chip(text, cls) { return el("span", {className: "chip " + (cls || ""), textContent: text}); }
function makeRow(p) {
  const name = el("code", {textContent: p.name});
  const label = el("div", {className: "muted"});
  const meta = el("div");
  meta.append(chip(p.base_type), chip(p.read_only ? "read-only" : "writable", p.read_only ? "" : "w"));
  if (p.direction) meta.append(chip(p.direction));
  const id = el("div", {className: "id"}, name, label, meta);

  const val = el("div", {className: "val"});
  const changed = el("div", {className: "muted"});
  const vals = el("div", {className: "vals"}, val, changed);

  const ctl = el("div", {className: "ctl"});
  if (!p.read_only) {
    const input = el("input", {type: "text", placeholder: p.base_type});
    const mode = el("select");
    ["auto", "string", "number", "boolean"].forEach(m => mode.append(el("option", {value: m, textContent: m})));
    const send = el("button", {textContent: "Send"});
    send.onclick = async () => {
      if (input.value === "") return toast("Enter a value first.", true);
      if (!confirm(`Write ${p.name} = ${input.value} (${mode.value})?`)) return;
      const res = await post("/api/write", {name: p.name, value: input.value, mode: mode.value});
      toast(res.ok ? `Sent ${JSON.stringify(res.sent)} to ${p.name} (HTTP ${res.status})`
                   : `Failed: ${res.error || res.status + " " + res.response}`, !res.ok);
    };
    ctl.append(el("div", {className: "writebox"}, input, mode, send));
  }
  const note = el("textarea", {className: "note", placeholder: "note", rows: 1});
  note.value = p.note || "";
  const fit = () => { note.style.height = "auto"; note.style.height = (note.scrollHeight + 2) + "px"; };
  note.oninput = fit;
  note.onchange = () => post("/api/note", {name: p.name, note: note.value});
  ctl.append(note);

  const root = el("div", {className: "prop" + (p.read_only ? " ro" : "")}, id, vals, ctl);
  const row = {root, val, label, changed, p, fit};
  rows.set(p.name, row);
  document.getElementById("rows").append(root);
  fit();
  return row;
}
function render(s) {
  latest = s;
  document.getElementById("device").textContent = "…" + s.device;
  document.getElementById("status").textContent =
    (s.error ? "ERROR " + s.error : "polled " + fmt(s.polled_at)) + " · poll #" + s.poll_count;
  const filter = document.getElementById("filter").value.toLowerCase();
  const onlyW = document.getElementById("writable").checked;
  const onlyC = document.getElementById("recent").checked;
  const nowS = Date.now() / 1000;
  s.properties.forEach(p => {
    const row = rows.get(p.name) || makeRow(p);
    row.p = p;
    row.val.textContent = show(p.value); row.val.title = String(p.value ?? "");
    row.val.classList.toggle("empty", isEmpty(p.value));
    row.label.textContent = p.display_name || "";
    row.changed.textContent = p.last_change ? "changed " + fmt(p.last_change) : "";
    row.root.classList.toggle("changed", !!p.last_change && nowS - p.last_change < 60);
    const text = (p.name + " " + (p.display_name || "")).toLowerCase();
    const visible = text.includes(filter) && (!onlyW || !p.read_only) && (!onlyC || p.last_change);
    const wasHidden = row.root.style.display === "none";
    row.root.style.display = visible ? "" : "none";
    if (visible && wasHidden) row.fit();
  });
  document.getElementById("logcount").textContent = s.changes.length ? "(" + s.changes.length + ")" : "";
  const ch = document.getElementById("changes"); ch.replaceChildren();
  s.changes.slice().reverse().forEach(c => {
    if (c.marker) {
      ch.append(el("div", {className: "entry marker"},
        el("span", {className: "muted", textContent: fmt(c.t) + " "}), document.createTextNode("★ " + c.new)));
      return;
    }
    ch.append(el("div", {className: "entry"},
      el("span", {className: "muted", textContent: fmt(c.t) + " "}), el("code", {textContent: c.name}),
      document.createTextNode(` ${show(c.old)} → ${show(c.new)}`)));
  });
  const wr = document.getElementById("writes"); wr.replaceChildren();
  s.writes.slice().reverse().forEach(w => {
    const line = el("div", {className: "entry"},
      el("span", {className: "muted", textContent: fmt(w.t) + " "}), el("code", {textContent: w.name}),
      el("span", {className: w.ok ? "ok" : "bad", textContent: ` ${w.ok ? "ok" : "FAILED " + w.status} `}),
      document.createTextNode(`${show(w.old)} → ${JSON.stringify(w.sent)} `));
    if (w.old !== null && w.old !== "" && w.ok) {
      const back = el("button", {textContent: "restore"});
      back.onclick = async () => {
        if (!confirm(`Write ${w.name} back to ${w.old}?`)) return;
        const res = await post("/api/write", {name: w.name, value: String(w.old), mode: "auto"});
        toast(res.ok ? "Restored." : "Restore failed: " + (res.error || res.status), !res.ok);
      };
      line.append(back);
    }
    wr.append(line);
  });
}
async function tick() {
  let state;
  try { state = await (await fetch("/api/state", {headers: H})).json(); }
  catch (e) { document.getElementById("status").textContent = "server not reachable"; return; }
  try { render(state); }
  catch (e) { document.getElementById("status").textContent = "page error: " + e.message; console.error(e); }
}
document.getElementById("refresh").onclick = () => post("/api/refresh");
const addMarker = async () => {
  const box = document.getElementById("marker");
  if (!box.value.trim()) return;
  await post("/api/marker", {text: box.value});
  box.value = ""; tick();
};
document.getElementById("mark").onclick = addMarker;
document.getElementById("marker").onkeydown = e => { if (e.key === "Enter") addMarker(); };
document.getElementById("interval").onchange = e => post("/api/interval", {seconds: +e.target.value});
document.getElementById("stop").onclick = async () => {
  if (confirm("Stop the explorer server?")) { await post("/api/shutdown"); document.getElementById("status").textContent = "stopped"; }
};
["filter", "writable", "recent"].forEach(id => document.getElementById(id).oninput = () => latest && render(latest));
document.querySelectorAll("#tabs button").forEach(b => b.onclick = () => {
  document.body.dataset.tab = b.dataset.tab;
  document.querySelectorAll("#tabs button").forEach(x => x.classList.toggle("on", x === b));
});
document.body.dataset.tab = "props";
tick(); setInterval(tick, 2000);
</script>
"""


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--interval", type=float, default=10.0, help="Seconds between cloud polls.")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    username = (os.environ.get("DELONGHI_USERNAME") or input("De'Longhi account email: ")).strip()
    password = os.environ.get("DELONGHI_PASSWORD") or getpass.getpass("De'Longhi password (not echoed): ")
    language = os.environ.get("DELONGHI_LANGUAGE") or input("Account language [en-au]: ").strip() or "en-au"

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
        api = base.api_module.DeLonghiAPI(username, password, session, language)
        if not await api.authenticate():
            print(f"Authentication failed ({api.auth_failure or 'unknown reason'}).")
            return
        devices = await api.get_devices()
        if not devices:
            print("The account returned no devices.")
            return
        index = int(os.environ.get("DELONGHI_DEVICE_INDEX") or "0")
        info = base.device_info(devices[index])
        dsn = str(info.get("dsn"))
        print(f"Device: {info.get('product_name') or info.get('model')} (DSN ends {dsn[-4:]})")

        explorer = Explorer(api, dsn, args.interval)
        token = secrets.token_urlsafe(16)
        runner = web.AppRunner(build_app(explorer, token, args.port))
        await runner.setup()
        await web.TCPSite(runner, "127.0.0.1", args.port).start()
        url = f"http://127.0.0.1:{args.port}/?token={token}"
        print(f"Explorer running at {url}")
        print("Press Ctrl+C or use the Stop button to quit.")
        if not args.no_browser:
            webbrowser.open(url)
        poller = asyncio.create_task(explorer.run_polling())
        try:
            await explorer.stop.wait()
        finally:
            poller.cancel()
            explorer.save()
            await runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped.")
