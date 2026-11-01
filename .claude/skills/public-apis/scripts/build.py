"""Rebuild apis.tsv and mcp-servers.tsv from the public-apis README.

Usage: python3 -I build.py PATH/TO/public-apis/README.md OUT_DIR

Reads the category tables (everything after "## Index") and the
"## MCP Servers" table. The sponsored APILayer sections are skipped.
Writes one row per entry, tab separated, with a header row. Standard
library only.
"""

import re
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

LINK = re.compile(r"^\[(?P<name>.+)\]\(\s*(?P<url>\S+?)\s*\)$")
INLINE_LINK = re.compile(r"\[([^\]]+)\]\(\s*(\S+?)\s*\)")
CELL_SPLIT = re.compile(r"(?<!\\)\|")

API_HEADER = ["Category", "Name", "Description", "Auth", "HTTPS", "CORS", "URL"]
MCP_HEADER = ["Name", "Description", "Auth", "Transport", "Install", "URL"]


def strip_tracking(url):
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if not k.startswith("utm_")]
    return urlunsplit(parts._replace(query=urlencode(query)))


def clean(text):
    text = text.replace("\\|", "|").replace("`", "")
    text = INLINE_LINK.sub(lambda m: f"{m[1]} <{strip_tracking(m[2])}>", text)
    return " ".join(text.split())


def cells(line):
    parts = CELL_SPLIT.split(line.strip())
    if parts and parts[0] == "":
        parts = parts[1:]
    return [p.strip() for p in parts]


def parse(readme):
    apis, mcps, skipped = [], [], []
    section = category = None
    for number, line in enumerate(readme.splitlines(), 1):
        if line.startswith("## "):
            title = line[3:].strip()
            if title == "Index":
                section = "categories"
            elif title == "MCP Servers":
                section = "mcp"
            else:
                section = None
            continue
        if section == "categories" and line.startswith("### "):
            category = line[4:].strip()
            continue
        if not line.startswith("| ["):
            continue
        # Some rows carry stray trailing cells; the data is always in the first five.
        row = cells(line)[:5]
        link = LINK.match(row[0]) if row else None
        if section == "categories" and category and link and len(row) == 5:
            name, url = link["name"], strip_tracking(link["url"])
            apis.append([category, name, *row[1:5], url])
        elif section == "mcp" and link and len(row) == 5:
            name, url = link["name"], strip_tracking(link["url"])
            mcps.append([name, *row[1:5], url])
        elif section in ("categories", "mcp"):
            skipped.append(f"line {number}: {line[:120]}")
    return apis, mcps, skipped


def write_tsv(path, header, rows):
    lines = ["\t".join(header)]
    lines += ["\t".join(clean(c) for c in row) for row in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv):
    if len(argv) != 3:
        sys.exit(__doc__)
    readme = Path(argv[1]).read_text(encoding="utf-8")
    out = Path(argv[2])
    apis, mcps, skipped = parse(readme)
    if not apis:
        sys.exit("no API rows found; has the README layout changed?")
    write_tsv(out / "apis.tsv", API_HEADER, apis)
    write_tsv(out / "mcp-servers.tsv", MCP_HEADER, mcps)
    categories = len({row[0] for row in apis})
    print(f"{len(apis)} APIs in {categories} categories, {len(mcps)} MCP servers")
    for line in skipped:
        print(f"skipped {line}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv)
