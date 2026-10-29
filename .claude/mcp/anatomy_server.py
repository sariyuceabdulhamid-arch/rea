#!/usr/bin/env python3
"""MCP server (stdio) for the Anatomy skill (github.com/wheresryan22/anatomy).

Exposes Anatomy's Node scripts (headless Chrome capture and checks, A4 printing,
3D checks) and figure builds as MCP tools. A call takes the script's
command-line arguments as a list and returns its exit code and output.
scripts/publish.mjs is left out: publishing to the community gallery stays a
step the user runs on purpose. Standard library only.

Usage: anatomy_server.py --anatomy DIR [--workdir DIR]
"""
import argparse
import json
import os
import subprocess
import sys

SERVER_NAME = "anatomy"
SERVER_VERSION = "1.0.0"
DEFAULT_PROTOCOL = "2025-06-18"
MAX_OUTPUT = 200_000

SCRIPTS = {
    "anatomy_capture": "scripts/capture.mjs",
    "anatomy_drive": "scripts/drive.mjs",
    "anatomy_lines": "scripts/lines.mjs",
    "anatomy_print": "scripts/print.mjs",
    "anatomy_turn_check": "scripts/turn-check.mjs",
    "anatomy_turn_bench": "scripts/turn-bench.mjs",
}


def discover(anatomy_dir):
    tools = {}
    for name, rel in SCRIPTS.items():
        script = os.path.join(anatomy_dir, rel)
        if os.path.isfile(script):
            tools[name] = {"script": script, "desc": "Runs `node %s <args>` from the Anatomy skill.\n\n%s"
                           % (rel, _help(script))}
    tools["anatomy_build"] = {
        "script": None,
        "desc": ("Runs a figure's build module: `node <args>`, e.g. [\"examples/dial-indicator/build.mjs\", "
                 "\"--light\"] or [\"examples/raptor-engine/build.mjs\", \"--audit\"]. A relative path is "
                 "looked up in `cwd`, then in the Anatomy checkout (%s), whose kit/ and examples/ the "
                 "builds import." % anatomy_dir),
    }
    return tools


def _help(script):
    try:
        proc = subprocess.run(["node", script, "--help"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return ""
    return (proc.stdout + proc.stderr).strip()


def tool_schema(name, info):
    return {
        "name": name,
        "description": info["desc"][:8000],
        "inputSchema": {
            "type": "object",
            "properties": {
                "args": {"type": "array", "items": {"type": "string"},
                         "description": "Command-line arguments, e.g. [\"page.html\", \"--out\", \"shot.png\"]"},
                "cwd": {"type": "string", "description": "Working directory for relative paths"},
                "timeout": {"type": "number", "description": "Seconds before the run is killed (default 600)"},
            },
            "required": ["args"],
        },
    }


def call_tool(info, arguments, default_cwd, anatomy_dir):
    args = arguments.get("args") or []
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        return _result("`args` must be a list of strings", True)
    cwd = os.path.expanduser(arguments.get("cwd") or default_cwd)
    if not os.path.isdir(cwd):
        return _result("cwd does not exist: %s" % cwd, True)
    if info["script"]:
        cmd = ["node", info["script"]] + args
    else:
        if not args:
            return _result("`args` must start with the build module", True)
        module = args[0]
        if not os.path.isabs(module) and not os.path.exists(os.path.join(cwd, module)):
            module = os.path.join(anatomy_dir, module)
        cmd = ["node", module] + args[1:]
    timeout = float(arguments.get("timeout") or 600)
    try:
        proc = subprocess.run(cmd, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return _result("timed out after %gs" % timeout, True)
    except OSError as e:
        return _result("could not start: %s" % e, True)
    out = proc.stdout
    if proc.stderr:
        out += ("\n" if out else "") + "[stderr]\n" + proc.stderr
    if len(out) > MAX_OUTPUT:
        out = out[:MAX_OUTPUT] + "\n[output truncated]"
    return _result("exit code: %d\n%s" % (proc.returncode, out), proc.returncode != 0)


def _result(text, is_error):
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--anatomy", required=True)
    ap.add_argument("--workdir", default=os.getcwd())
    opts = ap.parse_args()
    anatomy_dir = os.path.abspath(os.path.expanduser(opts.anatomy))
    tools = discover(anatomy_dir)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            _send({"jsonrpc": "2.0", "id": None,
                   "error": {"code": -32700, "message": "parse error"}})
            continue
        if "id" not in msg:
            continue  # notification
        method, params, mid = msg.get("method"), msg.get("params") or {}, msg["id"]
        if method == "initialize":
            res = {"protocolVersion": params.get("protocolVersion", DEFAULT_PROTOCOL),
                   "capabilities": {"tools": {}},
                   "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION}}
        elif method == "ping":
            res = {}
        elif method == "tools/list":
            res = {"tools": [tool_schema(n, i) for n, i in tools.items()]}
        elif method == "tools/call":
            info = tools.get(params.get("name"))
            if info is None:
                _send({"jsonrpc": "2.0", "id": mid,
                       "error": {"code": -32602, "message": "unknown tool: %s" % params.get("name")}})
                continue
            res = call_tool(info, params.get("arguments") or {}, opts.workdir, anatomy_dir)
        else:
            _send({"jsonrpc": "2.0", "id": mid,
                   "error": {"code": -32601, "message": "method not found: %s" % method}})
            continue
        _send({"jsonrpc": "2.0", "id": mid, "result": res})


def _send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
