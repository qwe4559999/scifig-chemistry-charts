"""SciFigStudio Interactive Visual Editing Workbench — Zero-dependency HTTP Server."""
from __future__ import annotations

import argparse
import json
import mimetypes
import socket
import sys
import threading
import traceback
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from . import __version__, workbench_bridge as bridge


def _resolve_static_dir() -> Path:
    cands: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        mp = Path(meipass)
        cands.extend([mp / "scifig" / "workbench_static", mp / "workbench_static"])
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        cands.extend([
            exe_dir / "scifig" / "workbench_static",
            exe_dir / "workbench_static",
            exe_dir / "_internal" / "scifig" / "workbench_static",
            exe_dir / "_internal" / "workbench_static",
        ])
    cands.append(Path(__file__).resolve().parent / "workbench_static")
    for cand in cands:
        if (cand / "index.html").is_file():
            return cand
    return Path(__file__).resolve().parent / "workbench_static"


STATIC_DIR = _resolve_static_dir()


class WorkbenchHandler(BaseHTTPRequestHandler):
    server_version = f"SciFigWorkbench/{__version__}"

    def log_message(self, fmt: str, *args: Any) -> None:
        if getattr(self.server, "verbose", False):
            super().log_message(fmt, *args)

    def _send_json(self, data: dict, status: int = 200) -> None:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(raw)

    def _send_bytes(self, raw: bytes, content_type: str, filename: str | None = None, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        if filename:
            safe_fn = filename.encode("ascii", "ignore").decode("ascii") or "export"
            self.send_header("Content-Disposition", f'attachment; filename="{safe_fn}"')
        self.end_headers()
        self.wfile.write(raw)

    def _read_json_body(self) -> dict:
        clen = int(self.headers.get("Content-Length", "0") or 0)
        if clen <= 0:
            return {}
        raw = self.rfile.read(clen)
        return json.loads(raw.decode("utf-8"))

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        try:
            if path == "/api/health":
                self._send_json({
                    "ok": True,
                    "version": __version__,
                    "studio_root": str(bridge.STUDIO_ROOT),
                })
                return

            if path == "/api/catalog":
                self._send_json(bridge.get_catalog())
                return

            if path == "/api/spec":
                spec_id = (qs.get("id") or [""])[0]
                if not spec_id:
                    spec_id = bridge.get_catalog().get("default_spec_id", "examples/demo_uvvis_spec")
                state = bridge.load_spec_state(spec_id)
                self._send_json(state)
                return

            if path.startswith("/api/"):
                self._send_json({"ok": False, "error": f"Unknown API endpoint: {path}"}, status=404)
                return

            # Static asset serving from scifig/workbench_static/
            static_root = _resolve_static_dir().resolve()
            rel = path.lstrip("/") or "index.html"
            target = (static_root / rel).resolve()
            if not str(target).startswith(str(static_root)) or not target.exists() or target.is_dir():
                index_p = static_root / "index.html"
                if path in ("/", "") and not index_p.exists():
                    self._send_bytes(
                        b"<html><body><h2>SciFigStudio Workbench Backend Running</h2><p>Static UI not built yet.</p></body></html>",
                        "text/html; charset=utf-8",
                    )
                    return
                self._send_json({"ok": False, "error": f"File not found: {rel}"}, status=404)
                return

            ctype, _ = mimetypes.guess_type(str(target))
            if not ctype:
                ctype = "application/octet-stream"
            elif ctype.startswith("text/") or ctype in ("application/javascript", "application/json", "image/svg+xml"):
                ctype = f"{ctype}; charset=utf-8"
            self._send_bytes(target.read_bytes(), ctype)

        except FileNotFoundError as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=404)
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc), "trace": traceback.format_exc(limit=4)}, status=500)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        try:
            body = self._read_json_body()

            if path == "/api/render":
                spec = body.get("spec")
                if not isinstance(spec, dict):
                    self._send_json({"ok": False, "error": "Missing 'spec' object"}, status=400)
                    return
                state = bridge.render_state(spec, spec_id=body.get("spec_id"))
                self._send_json(state)
                return

            if path == "/api/drag":
                spec = body.get("spec")
                handle_id = body.get("handle_id")
                if not isinstance(spec, dict) or not handle_id:
                    self._send_json({"ok": False, "error": "Missing 'spec' or 'handle_id'"}, status=400)
                    return
                updated, summary = bridge.apply_drag(
                    spec,
                    handle_id=str(handle_id),
                    dx_norm=float(body.get("dx_norm", 0.0)),
                    dy_norm=float(body.get("dy_norm", 0.0)),
                    target_norm=body.get("target_norm"),
                    spec_id=body.get("spec_id"),
                )
                state = bridge.render_state(updated, spec_id=body.get("spec_id"))
                state["patch_summary"] = summary
                self._send_json(state)
                return

            if path == "/api/ai-command":
                spec = body.get("spec")
                instruction = body.get("instruction", "")
                if not isinstance(spec, dict):
                    self._send_json({"ok": False, "error": "Missing 'spec' object"}, status=400)
                    return
                res = bridge.apply_ai_command(
                    spec,
                    instruction=str(instruction),
                    region_norm=body.get("region_norm"),
                    selected=body.get("selected"),
                    spec_id=body.get("spec_id"),
                )
                state = bridge.render_state(res["spec"], spec_id=body.get("spec_id"))
                state["ok"] = res["ok"]
                state["summary"] = res["summary"]
                state["patch_ops"] = res["patch_ops"]
                state["diff_lines"] = res["diff_lines"]
                state["engine_mode"] = res["engine_mode"]
                self._send_json(state)
                return

            if path == "/api/auto-fix":
                spec = body.get("spec")
                if not isinstance(spec, dict):
                    self._send_json({"ok": False, "error": "Missing 'spec' object"}, status=400)
                    return
                before = spec
                fixed, actions = bridge.auto_fix_qa(spec, spec_id=body.get("spec_id"))
                state = bridge.render_state(fixed, spec_id=body.get("spec_id"))
                state["summary"] = "；".join(actions)
                state["actions"] = actions
                state["diff_lines"] = bridge._json_diff_lines(before, fixed)
                self._send_json(state)
                return

            if path == "/api/save":
                spec = body.get("spec")
                if not isinstance(spec, dict):
                    self._send_json({"ok": False, "error": "Missing 'spec' object"}, status=400)
                    return
                res = bridge.save_spec_file(
                    spec,
                    spec_id=body.get("spec_id"),
                    name=body.get("name"),
                    overwrite=bool(body.get("overwrite", False)),
                )
                self._send_json(res)
                return

            if path == "/api/export":
                spec = body.get("spec")
                fmt = body.get("format", "svg")
                dpi = int(body.get("dpi", 600))
                if not isinstance(spec, dict):
                    self._send_json({"ok": False, "error": "Missing 'spec' object"}, status=400)
                    return
                raw, ctype, fname = bridge.export_artifact(spec, fmt=fmt, spec_id=body.get("spec_id"), dpi=dpi)
                self._send_bytes(raw, ctype, filename=fname)
                return

            if path == "/api/blind":
                data_path = body.get("data_path")
                chart_id = body.get("chart_id", "06_single-multi-spectrum")
                if not data_path:
                    self._send_json({"ok": False, "error": "Missing 'data_path'"}, status=400)
                    return
                state = bridge.run_live_blind(
                    data_path=data_path,
                    chart_id=chart_id,
                    theme=body.get("theme") or "origin-times-bold",
                    palette=body.get("palette"),
                    title=body.get("title") or "",
                )
                self._send_json(state)
                return

            self._send_json({"ok": False, "error": f"Unknown API endpoint: {path}"}, status=404)

        except FileNotFoundError as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=404)
        except ValueError as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=400)
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc), "trace": traceback.format_exc(limit=4)}, status=500)


def _find_available_port(host: str, preferred_port: int, max_tries: int = 30) -> int:
    for p in range(preferred_port, preferred_port + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, p))
                return p
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return int(s.getsockname()[1])


def create_server(host: str = "127.0.0.1", port: int = 8765, verbose: bool = False) -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer((host, port), WorkbenchHandler)
    srv.daemon_threads = True
    srv.verbose = verbose
    return srv


def serve(
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
    verbose: bool = False,
    auto_port: bool = True,
) -> int:
    chosen_port = _find_available_port(host, port) if auto_port else port
    if chosen_port != port:
        print(f"[Notice] Port {port} is busy; switched automatically to port {chosen_port}.", flush=True)
    srv = create_server(host=host, port=chosen_port, verbose=verbose)
    actual_port = srv.server_address[1]
    url = f"http://{host}:{actual_port}/"
    print(f"SciFigStudio Interactive Workbench v{__version__} running at {url}", flush=True)
    print("Press Ctrl+C in this window to stop the workbench server.", flush=True)
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nWorkbench server stopped.", flush=True)
    finally:
        srv.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="scifig-workbench",
        description="Launch SciFigStudio Interactive Human-AI Visual Editing Workbench",
    )
    ap.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    ap.add_argument("--port", type=int, default=8765, help="Preferred port (auto-increments if busy)")
    ap.add_argument("--no-open", action="store_true", help="Do not auto-open browser")
    ap.add_argument("--verbose", action="store_true", help="Print HTTP access logs")
    args = ap.parse_args(argv)
    return serve(host=args.host, port=args.port, open_browser=not args.no_open, verbose=args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
