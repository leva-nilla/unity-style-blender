"""Verify an installed extension using an isolated BLENDER_USER_RESOURCES profile."""

import importlib
import os
from pathlib import Path
import sys
import bpy

module = "bl_ext.user_default.unity_view_controls"
addon = importlib.import_module(module)
entry = bpy.context.preferences.addons.get(module)
assert entry is not None, "Extension was not enabled during installation"
assert entry.preferences is not None, "Namespaced extension preferences did not register"
values = {"fly_speed": 3.25, "look_sensitivity": 1.5, "boost": 3.0,
          "precision_multiplier": 0.1, "wheel_factor": 1.1,
          "update_rate": 240, "smoothing": 0.12, "invert_y": True,
          "move_space": "WORLD", "ortho_keymap": "WASD", "ortho_zoom_speed": 2.5,
          "remember_speed": False, "fov_compensation": 0.75}
profile = Path(os.environ.get("BLENDER_USER_RESOURCES", "")).resolve()
artifact_root = (Path(__file__).resolve().parents[1] / "artifacts").resolve()
assert artifact_root in profile.parents, "Preference persistence tests require an isolated artifact profile"
prefs = entry.preferences
assert abs(prefs.bl_rna.properties["look_sensitivity"].default - 3.5) < 0.00001
if "--verify-saved" in sys.argv:
    for name, expected in values.items():
        actual = getattr(prefs, name)
        assert (actual == expected if isinstance(expected, str) else abs(actual - expected) < 0.00001), (name, actual, expected)
    print("SAVED CONFIGURATION RELOAD PASSED", flush=True)
    for name in values:
        if name != "look_sensitivity":
            prefs.property_unset(name)
    prefs.property_unset("sensitivity")
    assert abs(prefs.look_sensitivity - 3.5) < 0.00001
else:
    for name, value in values.items():
        setattr(prefs, name, value)
bpy.ops.wm.save_userpref()
assert len(addon._keymaps) == 36, "Installed extension did not create expected bindings"
entry.preferences.navigation = False
assert len(addon._keymaps) == 9
entry.preferences.navigation = True
assert len(addon._keymaps) == 36
addon.unregister()
assert not addon._keymaps
addon.register()
assert len(addon._keymaps) == 36
print("INSTALLED EXTENSION CHECK PASSED", bpy.app.version_string, module, flush=True)
