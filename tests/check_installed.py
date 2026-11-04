"""Verify an installed extension using an isolated BLENDER_USER_RESOURCES profile."""

import importlib
import bpy

module = "bl_ext.user_default.unity_view_controls"
addon = importlib.import_module(module)
entry = bpy.context.preferences.addons.get(module)
assert entry is not None, "Extension was not enabled during installation"
assert entry.preferences is not None, "Namespaced extension preferences did not register"
assert len(addon._keymaps) == 33, "Installed extension did not create expected bindings"
entry.preferences.navigation = False
assert len(addon._keymaps) == 9
entry.preferences.navigation = True
assert len(addon._keymaps) == 33
addon.unregister()
assert not addon._keymaps
addon.register()
assert len(addon._keymaps) == 33
print("INSTALLED EXTENSION CHECK PASSED", bpy.app.version_string, module, flush=True)
