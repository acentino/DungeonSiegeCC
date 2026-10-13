"""DS2 GAS template overlay builder backed by a user-owned extracted donor template.

Generates a selectable leaf template, NOT a spawned/recruitable character.
Packing and in-game testing require DS2 tools and the user's game data.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

IDENT = re.compile(r'^[a-z][a-z0-9_]{0,63}$', flags=re.I)
TEMPLATE = re.compile(r'\[\s*t:template\s*,\s*n:([a-z0-9_]+)\s*\]', re.I)


class PipelineError(ValueError):
    pass


def verify_donor(directory, template):
    """Search extracted GAS sources for the selected template ID."""
    if not IDENT.fullmatch(template):
        raise PipelineError('Invalid donor template name')
    root = Path(directory)
    if root.is_file() and root.suffix.lower() == ".zip":
        import logic_inspector
        try:
            found = logic_inspector.verify_donor_in_source(root, template)
        except logic_inspector.LogicAnalysisError as exc:
            raise PipelineError(str(exc)) from exc
        return str(root) + "!" + found["source_file"]
    if not root.is_dir():
        raise PipelineError('Provide a ZIP of Logic references or a directory of extracted GAS files')
    count=0
    for file in root.rglob('*.gas'):
        count+=1
        if count>200_000:raise PipelineError('Too many files in extracted directory')
        try:
            if any(m.group(1).lower() == template.lower()
                   for m in TEMPLATE.finditer(file.read_text(encoding='utf-8-sig', errors='replace'))):
                return file
        except OSError: continue
    raise PipelineError(f'{template!r} was not found in extracted GAS templates')


def gas_string(value):
    if not isinstance(value,str) or not 1 <= len(value) <= 100:
        raise PipelineError('Invalid NPC display name length')
    if any(ord(c)<32 or c in '"\\{};\r\n' for c in value):
        raise PipelineError('Display name contains unsupported GAS characters')
    return '"'+value+'"'


def generate_leaf(identifier, name, donor, hire_cost=0):
    """Create a donor-specialized GAS actor; does not include map placement."""
    if not IDENT.fullmatch(identifier) or not IDENT.fullmatch(donor):
        raise PipelineError('Actor ID and donor template must contain only ASCII letters, digits, underscores')
    if not isinstance(hire_cost,int) or not 0 <= hire_cost <= 2_000_000_000:
        raise PipelineError('Invalid hiring cost')
    name=gas_string(name)
    template='dscc_'+identifier.lower()
    if len(template)>64:raise PipelineError('Actor ID is too long')
    return (f'// DungeonSiegeCC source template. Verify against Dungeon Siege II game build.\n'
            f'// This file alone does NOT spawn an NPC or create recruitment dialogue.\n'
            f'[t:template,n:{template}]\n'
            '{\n'
            f'    specializes = {donor};\n'
            f'    doc = {name};\n'
            '    [common]\n    {\n'
            f'        screen_name = {name};\n'
            '    }\n'
            '    [aspect]\n    {\n'
            f'        gold_value = {hire_cost};\n'
            '    }\n'
            '}\n')


def stage_leaf(directory, identifier, name, donor, extracted_logic, hire_cost=0):
    verified_file = verify_donor(extracted_logic, donor)
    text=generate_leaf(identifier, name, donor, hire_cost)
    target=(Path(directory)/'world'/'contentdb'/'templates'/'regular'/'actors'/'good'/
            ('dscc_'+identifier.lower()+'.gas'))
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(text,encoding='utf-8')
    status={'template': 'dscc_'+identifier.lower(), 'donor':donor,
            'donor_verified_in':str(verified_file),
            'next_required':['Verify GAS schema against DS2 version',
                             'Produce compatible skinned ASP / PRS assets',
                             'Place actor in map/region using Siege Editor 2',
                             'Configure DS2 conversation and recruitment',
                             'Pack game resource with TankCreator2 or DS2 Tank Editor',
                             'Test recruitability in real game']}
    (Path(directory)/'GAME_BUILD_REQUIREMENTS.json').write_text(json.dumps(status,indent=2),encoding='utf-8')
    return target
