"""Local-only catalogue of DS2 GAS templates, including zipped Logic references.

The scanner reads textual GAS resources, reports potential recruitable actors,
and identifies donor-template relationships. It does not create working NPCs.
The analysis report deliberately excludes original GAS/Skrit source contents.
"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

MAX_FILES = 80000
MAX_ARCHIVE_SIZE = 512 * 1024 * 1024
MAX_GAS_SIZE = 8 * 1024 * 1024
TEMPLATE_TAG = re.compile(r"\[\s*t\s*:\s*template\s*,\s*n\s*:\s*([a-z_][a-z0-9_]*)\s*\]", re.I)
ASSIGN = re.compile(r'(?i)\b([a-z_][a-z_0-9]*)\s*=\s*("(?:[^"\\]|\\.)*"|[^;\r\n{}]+)\s*;')
BASE_PM = re.compile(r"^base_pm(?:_|$)", re.I)


class LogicAnalysisError(ValueError):
    pass


def safe_member(info):
    name = info.filename.replace("\\", "/")
    if (not name or name.startswith("/") or "\0" in name or ":" in name
            or any(x in ("..", ".") for x in name.split("/"))):
        raise LogicAnalysisError("Unsafe ZIP entry path")
    mode = (info.external_attr >> 16) & 0o170000
    if mode == 0o120000:
        raise LogicAnalysisError("Symbolic links not permitted")
    return name


def _clean_comments(source):
    """Replace comments with spaces while leaving quoted values unmodified."""
    result = []
    i = 0
    quoted = False
    while i < len(source):
        c = source[i]
        d = source[i+1] if i+1 < len(source) else ""
        if quoted:
            result.append(c)
            if c == "\\" and i+1 < len(source):
                i += 1
                result.append(source[i])
            elif c == '"':
                quoted = False
        elif c == '"':
            quoted = True
            result.append(c)
        elif c == "/" and d == "/":
            result.extend("  ")
            i += 2
            while i < len(source) and source[i] not in "\r\n":
                result.append(" ")
                i += 1
            continue
        elif c == "/" and d == "*":
            result.extend("  ")
            i += 2
            while i < len(source):
                if source[i:i+2] == "*/":
                    result.extend("  ")
                    i += 2
                    break
                result.append("\n" if source[i] == "\n" else " ")
                i += 1
            continue
        else:
            result.append(c)
        i += 1
    return "".join(result)


def _find_block_end(source, start):
    depth = 0
    quoted = False
    for i in range(start, len(source)):
        ch = source[i]
        if ch == '"' and (i == 0 or source[i-1] != "\\"):
            quoted = not quoted
        if quoted:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return None


def parse_templates(source, filename=""):
    """Extract template metadata from multi-template GAS scripts."""
    cleaned = _clean_comments(source)
    found = []
    for match in TEMPLATE_TAG.finditer(cleaned):
        brace = cleaned.find("{", match.end())
        if brace < 0 or cleaned[match.end():brace].strip():
            continue
        end = _find_block_end(cleaned, brace)
        if end is None:
            continue
        body = cleaned[brace+1:end]
        attrs = {}
        for key, value in ASSIGN.findall(body):
            attrs.setdefault(key.lower(), value.strip().strip('"'))
        name = match.group(1)
        found.append({
            "template": name,
            "source_file": filename,
            "specializes": attrs.get("specializes", ""),
            "screen_name": attrs.get("screen_name", ""),
            "gold_value": attrs.get("gold_value", ""),
            "can_sell_self_explicit": attrs.get("can_sell_self", ""),
            "talk_job": attrs.get("jat_talk", ""),
        })
    return found


def _zip_entries(source):
    with zipfile.ZipFile(source, "r") as archive:
        items = archive.infolist()
        if len(items) > MAX_FILES or sum(i.file_size for i in items) > MAX_ARCHIVE_SIZE:
            raise LogicAnalysisError("ZIP exceeds analysis safety limit")
        files = []
        for info in items:
            name = safe_member(info)
            if info.is_dir() or not name.casefold().endswith(".gas"):
                continue
            if info.file_size > MAX_GAS_SIZE:
                continue
            files.append((info, name))
        for info, name in files:
            with archive.open(info) as stream:
                body = stream.read(MAX_GAS_SIZE + 1)
            if len(body) > MAX_GAS_SIZE:
                continue
            yield name, body.decode("utf-8-sig", errors="replace")


def _directory_entries(directory):
    root = Path(directory)
    count = 0
    for file in root.rglob("*"):
        if not file.is_file() or file.suffix.casefold() != ".gas":
            continue
        count += 1
        if count > MAX_FILES:
            raise LogicAnalysisError("Too many GAS files")
        if file.stat().st_size > MAX_GAS_SIZE:
            continue
        yield file.relative_to(root).as_posix(), file.read_text(encoding="utf-8-sig", errors="replace")


def load_templates(source):
    path = Path(source)
    if path.is_file() and path.suffix.lower() == ".zip":
        entries = _zip_entries(path)
    elif path.is_dir():
        entries = _directory_entries(path)
    else:
        raise LogicAnalysisError("Choose a Logic reference ZIP or extracted GAS directory")
    templates = {}
    gas_files = 0
    for filename, body in entries:
        gas_files += 1
        for item in parse_templates(body, filename):
            templates.setdefault(item["template"].lower(), item)
    return templates, gas_files



# Screening signals, not proof an actor can join the player's party.
# DS2's inheritance and dialogue scripts vary across game resources.
ACTOR_DIR = re.compile(r"(?:^|/)(?:actors|characters|mercenaries|companions)(?:/|$)", re.I)
GOOD_DIR = re.compile(r"(?:^|/)(?:good|friendly|heroes|party|hirelings|mercenaries)(?:/|$)", re.I)
STRONG_HIRE = re.compile(r"(?:hire|recruit|companion|party_member|mercenary|henchman|follower)", re.I)
NPC_NAME = re.compile(r"(?:human|npc|fighter|warrior|mage|ranger|hero|actor|character|farmer|town|villager)", re.I)


def rank_donor(item, chain):
    """Return a transparent compatibility score, not a recruitability claim."""
    filename = item.get("source_file", "").replace("\\\\", "/")
    names = " ".join(chain)
    score = 0
    reasons = []
    if ACTOR_DIR.search(filename):
        score += 40
        reasons.append("actor directory")
    if GOOD_DIR.search(filename):
        score += 20
        reasons.append("friendly/human directory")
    if any(BASE_PM.match(value) for value in chain):
        score += 50
        reasons.append("base_pm lineage")
    if STRONG_HIRE.search(names):
        score += 25
        reasons.append("hire/party naming")
    if NPC_NAME.search(names):
        score += 8
        reasons.append("NPC/human naming")
    if item.get("can_sell_self_explicit", "").lower() in ("true", "1", "yes"):
        score += 25
        reasons.append("can_sell_self flag")
    if item.get("talk_job"):
        score += 12
        reasons.append("dialogue job")
    if item.get("screen_name"):
        score += 6
        reasons.append("display name")
    return score, reasons



def inspect_logic_source(source, max_candidates=300):
    templates, gas_files = load_templates(source)

    def lineage(name):
        chain = []
        seen = set()
        while name and name.lower() in templates and name.lower() not in seen:
            item = templates[name.lower()]
            seen.add(name.lower())
            chain.append(item["template"])
            name = item["specializes"]
            if len(chain) > 100:
                break
        if name:
            chain.append(name)
        return chain

    candidates = []
    donor_candidates = []
    missing_parents = {}
    from collections import Counter
    root_types = Counter()
    for item in templates.values():
        chain = lineage(item["template"])
        inherited = any(BASE_PM.match(part) for part in chain)
        if inherited:
            candidate = dict(item)
            candidate["template_chain"] = chain
            candidate["recruitment_status"] = "candidate_only_not_in_game_verified"
            candidates.append(candidate)
        score, reasons = rank_donor(item, chain)
        parent = item.get("specializes", "")
        if parent and parent.lower() not in templates:
            missing_parents[parent] = missing_parents.get(parent, 0) + 1
        root_types[chain[-1].lower() if chain else "(unknown)"] += 1
        # Only actor-ish templates make reasonable donor prospects. Never
        # automatically choose an arbitrary weapon/item template.
        if score >= 35:
            candidate = dict(item)
            candidate["template_chain"] = chain
            candidate["donor_score"] = score
            candidate["donor_reasons"] = reasons
            candidate["recruitment_status"] = "unverified_donor_candidate"
            candidate["inheritance_complete"] = not bool(
                parent and parent.lower() not in templates)
            donor_candidates.append(candidate)
    candidates.sort(key=lambda x: (not bool(x["screen_name"]), x["template"].lower()))
    donor_candidates.sort(key=lambda x: (-x["donor_score"], not bool(x["screen_name"]), x["template"].lower()))
    # Include a small catalogue when the extraction is partial / nothing
    # matches: the user needs actionable reference names and diagnostics.
    fallback = sorted(
        templates.values(),
        key=lambda x: (not bool(ACTOR_DIR.search(x["source_file"].replace("\\\\", "/"))),
                       not bool(x["screen_name"]), x["template"].lower()),
    )[:min(max_candidates, 50)]
    return {
        "source_type": "zip" if Path(source).suffix.lower() == ".zip" else "folder",
        "gas_file_count": gas_files,
        "template_count": len(templates),
        "potential_recruitable_count": len(candidates),
        "potential_recruitable": candidates[:max_candidates],
        "truncated_candidates": len(candidates) > max_candidates,
        "donor_candidate_count": len(donor_candidates),
        "donor_candidates": donor_candidates[:max_candidates],
        "truncated_donor_candidates": len(donor_candidates) > max_candidates,
        "diagnostics": {
            "base_pm_templates_found": sum(bool(BASE_PM.match(x["template"])) for x in templates.values()),
            "unresolved_specialization_count": sum(missing_parents.values()),
            "unresolved_specialization_examples": [
                {"template": name, "count": count}
                for name, count in sorted(missing_parents.items(), key=lambda x: -x[1])[:30]],
            "root_lineage_examples": [
                {"root": name, "count": count}
                for name, count in root_types.most_common(20)],
            "template_examples_if_no_match": [
                {"template": x["template"], "source_file": x["source_file"],
                 "specializes": x["specializes"], "screen_name": x["screen_name"]}
                for x in fallback
            ] if not donor_candidates else [],
        },
        "notes": [
            "base_pm lineage is only one possible convention, not a prerequisite for a DS2 actor.",
            "Donor scores are inspection hints based on template paths/names/properties, NOT proof the game can recruit that NPC.",
            "Missing base templates can prevent tracing a complete inheritance chain.",
            "Game-owned GAS/Skrit bodies and character assets are excluded from this report.",
            "NPC placement, dialogue, animation compatibility, and save-game persistence remain unverified.",
        ],
    }

def verify_donor_in_source(source, template):
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,63}", template, re.I):
        raise LogicAnalysisError("Invalid donor template name")
    templates, _ = load_templates(source)
    item = templates.get(template.lower())
    if item is None:
        raise LogicAnalysisError(f"Template '{template}' not found in selected Logic resources")
    return item


def write_report(source, output):
    result = inspect_logic_source(source)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return output


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Locally inspect extracted DS2 Logic GAS ZIP or folder")
    parser.add_argument("source")
    parser.add_argument("--report", default="logic_template_report.json")
    args = parser.parse_args()
    report = write_report(args.source, args.report)
    print(str(report))
