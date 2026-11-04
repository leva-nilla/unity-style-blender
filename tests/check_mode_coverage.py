"""Audit supported context modes against the target Blender's own enum."""

import json
from pathlib import Path
import sys

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import addon

modes = {item.identifier: item.name for item in bpy.types.Context.bl_rna.properties["mode"].enum_items}
assert modes, "No Blender context modes were discovered"
assert addon._MODES <= modes.keys(), "The add-on declares modes absent from this Blender"
result = {"blender": bpy.app.version_string,
          "supported": {mode: modes[mode] for mode in sorted(addon._MODES)},
          "unsupported": {mode: name for mode, name in modes.items() if mode not in addon._MODES}}
output = ROOT / "artifacts" / "mode-coverage.json"
output.parent.mkdir(exist_ok=True)
output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
