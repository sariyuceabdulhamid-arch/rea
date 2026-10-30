#!/usr/bin/env python3
"""MCP server (stdio) for the Console skill pack.

Exposes each console-*/<tool>.py script of github.com/Jakeschincariol/console-skill
as one MCP tool. A call takes the script's command-line arguments as a list and
returns its exit code and output. Standard library only.

Usage: server.py [--skills DIR] [--workdir DIR]
  --skills   checkout of console-skill (default: $CONSOLE_SKILL_DIR or ~/.claude/skills)
  --workdir  default working directory for tool runs (default: current directory)
"""
import argparse
import json
import os
import subprocess
import sys

SERVER_NAME = "console-skill"
SERVER_VERSION = "1.0.0"
DEFAULT_PROTOCOL = "2025-06-18"
MAX_OUTPUT = 200_000


def discover(skills_dir):
    tools = {}
    for skill in sorted(os.listdir(skills_dir)):
        sdir = os.path.join(skills_dir, skill)
        if not skill.startswith("console-") or not os.path.isdir(sdir):
            continue
        for fname in sorted(os.listdir(sdir)):
            if not fname.endswith(".py"):
                continue
            script = os.path.join(sdir, fname)
            name = (skill + "_" + fname[:-3]).replace("-", "_")
            tools[name] = {"script": script, "skill": skill, "help": _help(script)}
    return tools


def _help(script):
    try:
        out = subprocess.run(
            [sys.executable, script, "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        out = ""
    return out.strip()


def tool_schema(name, info):
    rel = os.path.join(info["skill"], os.path.basename(info["script"]))
    desc = (
        "Runs `python3 %s <args>` from the %s skill. Pass a subcommand and its flags "
        'in `args`; use ["<subcommand>", "--help"] for a subcommand\'s flags. Most '
        "subcommands accept --json. Exit codes: 0 ok, 1 needs attention, 2 bad input.\n\n%s"
        % (rel, info["skill"], info["help"])
    )
    return {
        "name": name,
        "description": desc[:8000],
        "inputSchema": {
            "type": "object",
            "properties": {
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": 'Command-line arguments, e.g. ["boot", "game.iso"]',
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory (the game workspace that holds console/)",
                },
                "timeout": {
                    "type": "number",
                    "description": "Seconds before the run is killed (default 600)",
                },
            },
            "required": ["args"],
        },
    }


def call_tool(info, arguments, default_cwd):
    args = arguments.get("args") or []
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        return _result("`args` must be a list of strings", True)
    cwd = os.path.expanduser(arguments.get("cwd") or default_cwd)
    if not os.path.isdir(cwd):
        return _result("cwd does not exist: %s" % cwd, True)
    timeout = float(arguments.get("timeout") or 600)
    try:
        proc = subprocess.run(
            [sys.executable, info["script"]] + args,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return _result("timed out after %gs" % timeout, True)
    except OSError as e:
        return _result("could not start: %s" % e, True)
    out = proc.stdout
    if proc.stderr:
        out += ("\n" if out else "") + "[stderr]\n" + proc.stderr
    if len(out) > MAX_OUTPUT:
        out = out[:MAX_OUTPUT] + "\n[output truncated]"
    return _result("exit code: %d\n%s" % (proc.returncode, out), proc.returncode == 2)


def _result(text, is_error):
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--skills",
        default=os.environ.get(
            "CONSOLE_SKILL_DIR", os.path.expanduser("~/.claude/skills")
        ),
    )
    ap.add_argument("--workdir", default=os.getcwd())
    opts = ap.parse_args()
    tools = discover(os.path.expanduser(opts.skills))

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            _send(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "parse error"},
                }
            )
            continue
        if "id" not in msg:
            continue  # notification
        method, params, mid = msg.get("method"), msg.get("params") or {}, msg["id"]
        if method == "initialize":
            res = {
                "protocolVersion": params.get("protocolVersion", DEFAULT_PROTOCOL),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            }
        elif method == "ping":
            res = {}
        elif method == "tools/list":
            res = {"tools": [tool_schema(n, i) for n, i in tools.items()]}
        elif method == "tools/call":
            info = tools.get(params.get("name"))
            if info is None:
                _send(
                    {
                        "jsonrpc": "2.0",
                        "id": mid,
                        "error": {
                            "code": -32602,
                            "message": "unknown tool: %s" % params.get("name"),
                        },
                    }
                )
                continue
            res = call_tool(info, params.get("arguments") or {}, opts.workdir)
        else:
            _send(
                {
                    "jsonrpc": "2.0",
                    "id": mid,
                    "error": {
                        "code": -32601,
                        "message": "method not found: %s" % method,
                    },
                }
            )
            continue
        _send({"jsonrpc": "2.0", "id": mid, "result": res})


def _send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
