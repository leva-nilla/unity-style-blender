"""Launch with the isolated profile used by tests/check_installed.py; do not save it."""

import bpy

bpy.context.preferences.view.show_splash = False
bpy.context.preferences.use_preferences_save = False


def prepare():
    window = bpy.context.window_manager.windows[0]
    area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    with bpy.context.temp_override(window=window, area=area, region=region):
        bpy.ops.wm.tool_set_by_id(name="builtin.move")
    return None


bpy.app.timers.register(prepare, first_interval=1.0)
