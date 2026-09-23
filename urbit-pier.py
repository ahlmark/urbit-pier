#!/usr/bin/env python3
"""Supervise one local Urbit pier for the Omarchy bar plugin.

Prints a single JSON object on stdout. Vere itself is started by a systemd
user unit so the ship survives omarchy-shell reloads.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

UNIT_NAME = "urbit-pier.service"
DEFAULT_CONFIG = Path.home() / ".config/omarchy/urbit.json"
DEFAULT_BINARY = Path.home() / ".local/share/urbit/urbit"
DEFAULT_PIERS = Path.home() / "urbit"
DEFAULT_HTTP_PORT = 8080
DEFAULT_LOOM = 31
BOOTSTRAP_LAST = "https://bootstrap.urbit.org/vere/live/last"
BOOTSTRAP_BIN = "https://bootstrap.urbit.org/vere/live/v{version}/vere-v{version}-{arch}"
SHIP_RE = re.compile(r"^[a-z]{3}(?:[a-z]{3})?(?:-[a-z]{6})*$")
SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
EXEC_SAFE_RE = re.compile(r"^[A-Za-z0-9_./:=+-]+$")


def fail(error: str, extra: dict[str, Any] | None = None, code: int = 1) -> None:
    payload: dict[str, Any] = {"ok": False, "error": error}
    if extra:
        payload.update(extra)
    print(json.dumps(payload, ensure_ascii=False))
    raise SystemExit(code)


def ok(payload: dict[str, Any]) -> None:
    out = {"ok": True, **payload}
    print(json.dumps(out, ensure_ascii=False))


def expand_home(path: str | Path, home: Path | None = None) -> Path:
    home = home or Path.home()
    text = str(path or "").strip()
    if text == "" or text == "~":
        return home
    if text.startswith("~/"):
        return home / text[2:]
    return Path(text).expanduser()


def normalize_ship(name: str) -> str:
    return str(name or "").strip().lower().lstrip("~")


def valid_ship(name: str) -> bool:
    ship = normalize_ship(name)
    return bool(ship and SHIP_RE.fullmatch(ship))


def safe_id(name: str) -> str:
    value = str(name or "").strip()
    value = value.replace("/", "-").replace(" ", "-")
    if not SAFE_NAME_RE.fullmatch(value):
        fail(f"invalid pier id '{name}'")
    return value


def quote_exec(arg: str) -> str:
    if arg == "":
        return '""'
    if EXEC_SAFE_RE.fullmatch(arg):
        return arg
    return '"' + arg.replace("\\", "\\\\").replace('"', '\\"') + '"'


def atomic_write(path: Path, data: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
        tmp.replace(path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def chmod_private(path: Path) -> None:
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def run(cmd: list[str], timeout: int = 20, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            input=input_text,
        )
    except subprocess.TimeoutExpired as exc:
        fail(f"timed out running {' '.join(cmd)}", {"timeout": timeout, "cmd": cmd[:1]})
        raise exc
    except OSError as exc:
        fail(f"could not run {cmd[0]}: {exc}")
        raise


def unit_path() -> Path:
    return Path.home() / ".config/systemd/user" / UNIT_NAME


def systemctl(*args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return run(["systemctl", "--user", *args], timeout=timeout)


def unit_state() -> str:
    completed = run(["systemctl", "--user", "is-active", UNIT_NAME], timeout=8)
    return (completed.stdout or completed.stderr or "inactive").strip() or "inactive"


def unit_running(state: str | None = None) -> bool:
    value = state if state is not None else unit_state()
    return value in ("active", "activating", "reloading")


def default_config() -> dict[str, Any]:
    return {
        "binary": str(DEFAULT_BINARY),
        "piersDir": str(DEFAULT_PIERS),
        "httpPort": DEFAULT_HTTP_PORT,
        "amesPort": None,
        "loom": DEFAULT_LOOM,
        "active": None,
        "piers": [],
    }


def load_config(path: Path) -> dict[str, Any]:
    cfg = default_config()
    if not path.exists():
        return cfg
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"could not read config: {exc}")
        return cfg
    if not isinstance(raw, dict):
        fail("config must be a JSON object")
    cfg.update(raw)
    piers = cfg.get("piers") or []
    if not isinstance(piers, list):
        fail("config 'piers' must be an array")
    cleaned = []
    for item in piers:
        if isinstance(item, dict) and item.get("id"):
            cleaned.append(item)
    cfg["piers"] = cleaned
    try:
        cfg["httpPort"] = int(cfg.get("httpPort") or DEFAULT_HTTP_PORT)
    except (TypeError, ValueError):
        cfg["httpPort"] = DEFAULT_HTTP_PORT
    loom = cfg.get("loom")
    try:
        cfg["loom"] = int(loom) if loom is not None else DEFAULT_LOOM
    except (TypeError, ValueError):
        cfg["loom"] = DEFAULT_LOOM
    ames = cfg.get("amesPort")
    if ames in ("", None):
        cfg["amesPort"] = None
    else:
        try:
            cfg["amesPort"] = int(ames)
        except (TypeError, ValueError):
            cfg["amesPort"] = None
    return cfg


def save_config(path: Path, cfg: dict[str, Any]) -> None:
    atomic_write(path, json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", 0o600)
    chmod_private(path)


def resolve_binary(cfg: dict[str, Any]) -> Path | None:
    candidates: list[Path] = []
    configured = expand_home(str(cfg.get("binary") or DEFAULT_BINARY))
    candidates.append(configured)
    which = shutil.which("urbit")
    if which:
        candidates.append(Path(which))
    for path in candidates:
        if path.is_file() and os.access(path, os.X_OK):
            return path
    return None


def pier_path(pier: dict[str, Any]) -> Path:
    return expand_home(str(pier.get("path") or "")).resolve()


def pier_ready(path: Path) -> bool:
    return path.is_dir() and (path / ".urb").is_dir()


def docked_run(path: Path) -> Path | None:
    run_path = path / ".run"
    if run_path.exists() and os.access(run_path, os.X_OK):
        return run_path
    return None


def find_pier(cfg: dict[str, Any], pier_id: str | None) -> dict[str, Any] | None:
    if not pier_id:
        return None
    for pier in cfg.get("piers") or []:
        if str(pier.get("id")) == pier_id:
            return pier
    return None


def active_pier(cfg: dict[str, Any]) -> dict[str, Any] | None:
    return find_pier(cfg, cfg.get("active"))


def upsert_pier(cfg: dict[str, Any], pier: dict[str, Any]) -> None:
    piers = list(cfg.get("piers") or [])
    replaced = False
    for index, existing in enumerate(piers):
        if existing.get("id") == pier["id"]:
            piers[index] = pier
            replaced = True
            break
    if not replaced:
        piers.append(pier)
    cfg["piers"] = piers
    cfg["active"] = pier["id"]


def display_ship(pier: dict[str, Any] | None) -> str:
    if not pier:
        return ""
    ship = normalize_ship(str(pier.get("ship") or ""))
    if ship:
        return "~" + ship
    return str(pier.get("id") or "")


def vere_arch() -> str:
    machine = os.uname().machine
    if machine in ("x86_64", "amd64"):
        return "linux-x86_64"
    if machine in ("aarch64", "arm64"):
        return "linux-aarch64"
    fail(f"unsupported architecture '{machine}'")
    return ""


def http_live(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=0.6):
            return True
    except OSError:
        return False


def lock_pid(path: Path) -> int | None:
    lock = path / ".vere.lock"
    if not lock.exists():
        return None
    try:
        text = lock.read_text(encoding="utf-8", errors="replace").strip().split()[0]
        pid = int(text)
        return pid if pid > 0 else None
    except (OSError, ValueError, IndexError):
        return None


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def journal_lines(limit: int = 12) -> list[str]:
    completed = run(
        ["journalctl", "--user", "-u", UNIT_NAME, "-n", str(limit), "--no-pager", "-o", "cat"],
        timeout=8,
    )
    text = ANSI_RE.sub("", completed.stdout or "")
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    return lines[-limit:]


def exec_args(cfg: dict[str, Any], pier: dict[str, Any], binary: Path) -> list[str]:
    path = pier_path(pier)
    port = int(cfg.get("httpPort") or DEFAULT_HTTP_PORT)
    loom = int(cfg.get("loom") or DEFAULT_LOOM)
    flags = ["-t", "--http-port", str(port), "--loom", str(loom)]
    ames = cfg.get("amesPort")
    if ames:
        flags.extend(["-p", str(int(ames))])
    kind = str(pier.get("kind") or "attached")
    if pier_ready(path):
        docked = docked_run(path)
        if docked:
            return [str(docked), *flags]
        return [str(binary), *flags, str(path)]
    if kind == "fake":
        ship = normalize_ship(str(pier.get("ship") or "zod"))
        return [str(binary), "-F", ship, "-c", str(path), *flags]
    if kind == "comet":
        return [str(binary), "-c", str(path), *flags]
    if kind == "real":
        ship = normalize_ship(str(pier.get("ship") or ""))
        key = expand_home(str(pier.get("keyFile") or ""))
        if not ship or not key.is_file():
            fail("keyfile boot needs a ship name and an existing key file")
        return [str(binary), "-w", ship, "-k", str(key), "-c", str(path), *flags]
    fail(f"pier '{pier.get('id')}' is not ready and cannot be created from kind '{kind}'")
    return []


def render_unit(cfg: dict[str, Any], pier: dict[str, Any], binary: Path) -> str:
    args = exec_args(cfg, pier, binary)
    start = " ".join(quote_exec(arg) for arg in args)
    workdir = expand_home(str(cfg.get("piersDir") or DEFAULT_PIERS))
    description = display_ship(pier) or str(pier.get("id") or "pier")
    return (
        "[Unit]\n"
        f"Description=Urbit pier {description}\n"
        "After=network-online.target\n"
        "StartLimitBurst=3\n"
        "StartLimitIntervalSec=180\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        f"WorkingDirectory={quote_exec(str(workdir))}\n"
        f"ExecStart={start}\n"
        "Restart=on-failure\n"
        "RestartSec=10\n"
        "TimeoutStopSec=90\n"
        "KillMode=mixed\n"
        "KillSignal=SIGTERM\n"
        "\n"
    )


def ensure_unit(cfg: dict[str, Any], binary: Path | None = None, reload: bool = True) -> bool:
    pier = active_pier(cfg)
    if not pier:
        return False
    binary = binary or resolve_binary(cfg)
    if not binary:
        return False
    desired = render_unit(cfg, pier, binary)
    path = unit_path()
    current = path.read_text(encoding="utf-8") if path.exists() else None
    if current == desired:
        return False
    atomic_write(path, desired, 0o644)
    if reload:
        completed = systemctl("daemon-reload")
        if completed.returncode != 0:
            fail((completed.stderr or completed.stdout or "systemctl daemon-reload failed").strip())
    return True


def require_stopped() -> None:
    if unit_running():
        fail("stop the running ship before changing piers")


def require_binary(cfg: dict[str, Any]) -> Path:
    binary = resolve_binary(cfg)
    if not binary:
        fail("Vere is not installed")
    return binary


def empty_or_missing(path: Path) -> bool:
    if not path.exists():
        return True
    if not path.is_dir():
        return False
    try:
        next(path.iterdir())
    except StopIteration:
        return True
    return False


def state_from(cfg: dict[str, Any], binary: Path | None) -> tuple[str, str]:
    pier = active_pier(cfg)
    state = unit_state()
    running = unit_running(state)
    port = int(cfg.get("httpPort") or DEFAULT_HTTP_PORT)
    live = running and http_live(port)
    path = pier_path(pier) if pier else None
    locked = pid_alive(lock_pid(path)) if path else False

    if not binary:
        return "missing-runtime", "Vere is not installed"
    if not pier:
        return "no-pier", "No pier configured"
    if state == "failed":
        return "error", "Ship service failed — see logs"
    if running and live:
        return "live", f"{display_ship(pier)} is live on :{port}"
    if running:
        return "starting", f"Booting {display_ship(pier) or pier.get('id')}…"
    if locked:
        return "error", "Pier is locked by another process"
    if state not in ("inactive", "dead", "failed") and state != "inactive":
        if state == "activating":
            return "starting", f"Booting {display_ship(pier) or pier.get('id')}…"
    return "stopped", f"{display_ship(pier) or pier.get('id')} is stopped"


def status_payload(cfg: dict[str, Any]) -> dict[str, Any]:
    binary = resolve_binary(cfg)
    if binary:
        try:
            ensure_unit(cfg, binary)
        except SystemExit:
            raise
        except Exception:
            pass
    pier = active_pier(cfg)
    path = pier_path(pier) if pier else None
    unit = unit_state()
    state, status_text = state_from(cfg, binary)
    port = int(cfg.get("httpPort") or DEFAULT_HTTP_PORT)
    piers = []
    for item in cfg.get("piers") or []:
        item_path = pier_path(item)
        piers.append(
            {
                "id": item.get("id"),
                "kind": item.get("kind"),
                "ship": normalize_ship(str(item.get("ship") or "")),
                "display": display_ship(item),
                "path": str(item_path),
                "ready": pier_ready(item_path),
                "active": item.get("id") == cfg.get("active"),
            }
        )
    return {
        "installed": binary is not None,
        "binary": str(binary) if binary else str(expand_home(str(cfg.get("binary") or DEFAULT_BINARY))),
        "state": state,
        "statusText": status_text,
        "running": unit_running(unit),
        "live": state == "live",
        "unit": unit,
        "httpPort": port,
        "amesPort": cfg.get("amesPort"),
        "loom": int(cfg.get("loom") or DEFAULT_LOOM),
        "piersDir": str(expand_home(str(cfg.get("piersDir") or DEFAULT_PIERS))),
        "active": cfg.get("active"),
        "ship": normalize_ship(str(pier.get("ship") or "")) if pier else "",
        "display": display_ship(pier),
        "kind": pier.get("kind") if pier else "",
        "pierPath": str(path) if path else "",
        "ready": pier_ready(path) if path else False,
        "lockPid": lock_pid(path) if path else None,
        "landscapeUrl": f"http://127.0.0.1:{port}",
        "piers": piers,
        "logs": journal_lines(12),
        "error": "" if state != "error" else status_text,
    }


def cmd_status(cfg: dict[str, Any]) -> None:
    ok(status_payload(cfg))


def download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "ahlmark.urbit"})
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = resp.read()
    except urllib.error.URLError as exc:
        fail(f"download failed: {exc}")
        return b""
    if not data:
        fail(f"empty download from {url}")
    return data


def cmd_install_runtime(cfg: dict[str, Any], config_path: Path) -> None:
    dest = expand_home(str(cfg.get("binary") or DEFAULT_BINARY))
    dest.parent.mkdir(parents=True, exist_ok=True)
    version = download(BOOTSTRAP_LAST).decode("utf-8").strip()
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", version):
        fail(f"unexpected Vere version '{version}'")
    arch = vere_arch()
    url = BOOTSTRAP_BIN.format(version=version, arch=arch)
    blob = download(url)
    if blob[:4] != b"\x7fELF":
        fail("downloaded Vere binary is not an ELF file")
    fd, tmp_name = tempfile.mkstemp(prefix="urbit.", dir=str(dest.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(blob)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o755)
        tmp.replace(dest)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    cfg["binary"] = str(dest)
    save_config(config_path, cfg)
    probe = run([str(dest), "-R"], timeout=12)
    version_line = (probe.stdout or probe.stderr or "").strip().splitlines()
    ok(
        {
            **status_payload(cfg),
            "installed": True,
            "binary": str(dest),
            "vereVersion": version,
            "vereInfo": version_line[0] if version_line else f"vere {version}",
        }
    )


def prepare_new_pier(cfg: dict[str, Any], pier_id: str, dest: Path) -> None:
    require_stopped()
    require_binary(cfg)
    if find_pier(cfg, pier_id):
        fail(f"pier '{pier_id}' is already configured")
    if pier_ready(dest):
        fail(f"a pier already exists at {dest}")
    if dest.exists() and not empty_or_missing(dest):
        fail(f"{dest} already exists and is not empty")
    dest.parent.mkdir(parents=True, exist_ok=True)


def cmd_create_fake(cfg: dict[str, Any], config_path: Path, ship: str) -> None:
    ship = normalize_ship(ship or "zod")
    if not valid_ship(ship):
        fail(f"invalid ship name '{ship}'")
    pier_id = safe_id(ship)
    dest = expand_home(str(cfg.get("piersDir") or DEFAULT_PIERS)) / ship
    prepare_new_pier(cfg, pier_id, dest)
    upsert_pier(
        cfg,
        {"id": pier_id, "kind": "fake", "ship": ship, "path": str(dest)},
    )
    save_config(config_path, cfg)
    ensure_unit(cfg)
    ok(status_payload(cfg))


def cmd_boot_comet(cfg: dict[str, Any], config_path: Path, name: str) -> None:
    pier_id = safe_id(name or "comet")
    dest = expand_home(str(cfg.get("piersDir") or DEFAULT_PIERS)) / pier_id
    prepare_new_pier(cfg, pier_id, dest)
    upsert_pier(
        cfg,
        {"id": pier_id, "kind": "comet", "ship": "", "path": str(dest)},
    )
    save_config(config_path, cfg)
    ensure_unit(cfg)
    ok(status_payload(cfg))


def cmd_boot_key(cfg: dict[str, Any], config_path: Path, ship: str, key: str, name: str | None) -> None:
    ship = normalize_ship(ship)
    if not valid_ship(ship):
        fail(f"invalid ship name '{ship}'")
    key_path = expand_home(key)
    if not key_path.is_file():
        fail(f"key file not found: {key_path}")
    pier_id = safe_id(name or ship)
    dest = expand_home(str(cfg.get("piersDir") or DEFAULT_PIERS)) / pier_id
    prepare_new_pier(cfg, pier_id, dest)
    upsert_pier(
        cfg,
        {
            "id": pier_id,
            "kind": "real",
            "ship": ship,
            "path": str(dest),
            "keyFile": str(key_path),
        },
    )
    save_config(config_path, cfg)
    ensure_unit(cfg)
    ok(status_payload(cfg))


def cmd_attach(cfg: dict[str, Any], config_path: Path, path_text: str) -> None:
    require_stopped()
    dest = expand_home(path_text).resolve()
    if not pier_ready(dest):
        fail(f"no Urbit pier at {dest}")
    pier_id = safe_id(dest.name)
    existing = find_pier(cfg, pier_id)
    if existing and expand_home(str(existing.get("path") or "")).resolve() != dest:
        fail(f"pier id '{pier_id}' already points at {existing.get('path')}")
    upsert_pier(
        cfg,
        {
            "id": pier_id,
            "kind": "attached",
            "ship": normalize_ship(dest.name) if valid_ship(dest.name) else "",
            "path": str(dest),
        },
    )
    save_config(config_path, cfg)
    ensure_unit(cfg)
    ok(status_payload(cfg))


def cmd_select(cfg: dict[str, Any], config_path: Path, pier_id: str) -> None:
    require_stopped()
    pier = find_pier(cfg, pier_id)
    if not pier:
        fail(f"unknown pier '{pier_id}'")
    cfg["active"] = pier["id"]
    save_config(config_path, cfg)
    ensure_unit(cfg)
    ok(status_payload(cfg))


def drop_keyfile_if_ready(cfg: dict[str, Any], config_path: Path) -> None:
    pier = active_pier(cfg)
    if not pier or "keyFile" not in pier:
        return
    if not pier_ready(pier_path(pier)):
        return
    pier = dict(pier)
    pier.pop("keyFile", None)
    upsert_pier(cfg, pier)
    save_config(config_path, cfg)


def cmd_start(cfg: dict[str, Any], config_path: Path) -> None:
    binary = require_binary(cfg)
    pier = active_pier(cfg)
    if not pier:
        fail("no pier configured")
    path = pier_path(pier)
    kind = str(pier.get("kind") or "")
    if not pier_ready(path) and kind not in ("fake", "comet", "real"):
        fail("attach a ready pier, or create a fake ship / comet / keyfile boot")
    if kind == "real" and not pier_ready(path):
        key = expand_home(str(pier.get("keyFile") or ""))
        if not key.is_file():
            fail("key file is missing; re-run boot-key")
    ensure_unit(cfg, binary)
    completed = systemctl("start", UNIT_NAME, timeout=40)
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "systemctl start failed").strip()
        fail(err, {"logs": journal_lines(20)})
    drop_keyfile_if_ready(cfg, config_path)
    ok(status_payload(cfg))


def cmd_stop(cfg: dict[str, Any], config_path: Path) -> None:
    completed = systemctl("stop", UNIT_NAME, timeout=120)
    if completed.returncode != 0 and unit_running():
        err = (completed.stderr or completed.stdout or "systemctl stop failed").strip()
        fail(err, {"logs": journal_lines(20)})
    drop_keyfile_if_ready(cfg, config_path)
    try:
        ensure_unit(cfg)
    except Exception:
        pass
    ok(status_payload(cfg))


def cmd_logs(limit: int) -> None:
    ok({"logs": journal_lines(limit), "unit": unit_state()})


def build_parser() -> argparse.ArgumentParser:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--config", default=str(DEFAULT_CONFIG), help="config JSON path")
    parser = argparse.ArgumentParser(
        description="Manage a local Urbit pier for Omarchy",
        parents=[shared],
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", parents=[shared])
    sub.add_parser("install-runtime", parents=[shared])
    fake = sub.add_parser("create-fake", parents=[shared])
    fake.add_argument("--ship", default="zod")
    comet = sub.add_parser("boot-comet", parents=[shared])
    comet.add_argument("--name", default="comet")
    key = sub.add_parser("boot-key", parents=[shared])
    key.add_argument("--ship", required=True)
    key.add_argument("--key", required=True)
    key.add_argument("--name", default="")
    attach = sub.add_parser("attach", parents=[shared])
    attach.add_argument("--path", required=True)
    select = sub.add_parser("select", parents=[shared])
    select.add_argument("--id", required=True)
    sub.add_parser("start", parents=[shared])
    sub.add_parser("stop", parents=[shared])
    logs = sub.add_parser("logs", parents=[shared])
    logs.add_argument("--lines", type=int, default=40)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    config_path = expand_home(args.config)
    cfg = load_config(config_path)
    command = args.command
    if command == "status":
        cmd_status(cfg)
    elif command == "install-runtime":
        cmd_install_runtime(cfg, config_path)
    elif command == "create-fake":
        cmd_create_fake(cfg, config_path, args.ship)
    elif command == "boot-comet":
        cmd_boot_comet(cfg, config_path, args.name)
    elif command == "boot-key":
        cmd_boot_key(cfg, config_path, args.ship, args.key, args.name or None)
    elif command == "attach":
        cmd_attach(cfg, config_path, args.path)
    elif command == "select":
        cmd_select(cfg, config_path, args.id)
    elif command == "start":
        cmd_start(cfg, config_path)
    elif command == "stop":
        cmd_stop(cfg, config_path)
    elif command == "logs":
        cmd_logs(args.lines)
    else:
        fail(f"unknown command '{command}'")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        fail(str(exc))
