"""Run in an isolated GUI: blender --factory-startup --enable-event-simulate --python ..."""

import json
from pathlib import Path
import sys
import traceback

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import addon

OUTPUT = ROOT / "artifacts"
OUTPUT.mkdir(exist_ok=True)
checks = []
tasks = []


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    checks.append(message)
    print("PASS:", message, flush=True)


def context():
    window = bpy.context.window_manager.windows[0]
    area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    return window, area, region


def event(kind, value="PRESS", **kwargs):
    window, area, region = context()
    window.event_simulate(type=kind, value=value,
                          x=region.x + region.width // 2,
                          y=region.y + region.height // 2, **kwargs)


def snapshot():
    view = context()[1].spaces.active.region_3d
    return (view.view_location.copy(), view.view_rotation.copy(), view.view_distance,
            view.view_perspective)


def close_to(a, b):
    return (a - b).length < 0.0001


def user_sentinel():
    km = bpy.context.window_manager.keyconfigs.user.keymaps["Object Mode"]
    return next((item for item in km.keymap_items
                 if item.idname == "wm.search_menu" and item.type == "F19"), None)


def setup():
    addon.register()
    bpy.context.window_manager.keyconfigs.update()
    count = len(addon._keymaps)
    addon.register()
    check(count == 33 and len(addon._keymaps) == count, "register is idempotent (33 bindings)")
    check(not any(km.name == "Mesh" and item.type in {"E", "F", "R", "W"}
                  for km, item in addon._keymaps), "mesh modeling shortcuts are preserved")
    # User-authored item must survive the add-on lifecycle without mutation.
    user_map = bpy.context.window_manager.keyconfigs.user.keymaps["Object Mode"]
    user_map.keymap_items.new("wm.search_menu", "F19", "PRESS")
    bpy.context.window_manager.keyconfigs.update()
    addon.unregister()
    bpy.context.window_manager.keyconfigs.update()
    check(user_sentinel() is not None and user_sentinel().active, "unregister preserves a user key binding")
    check(not addon._keymaps and not addon._running, "unregister removes owned bindings")
    addon.register()
    bpy.context.window_manager.keyconfigs.update()
    window, area, region = context()
    with bpy.context.temp_override(window=window, area=area, region=region):
        bpy.ops.wm.tool_set_by_id(name="builtin.select_box")
    event("MOUSEMOVE", "NOTHING")


def tool_is(name):
    tool = bpy.context.workspace.tools.from_space_view3d_mode("OBJECT", create=False)
    check(tool.idname == name, "real key dispatch selects " + name + " (actual: " + tool.idname + ")")


def start_fly():
    global initial
    initial = snapshot()
    event("RIGHTMOUSE")


def test_fly_motion():
    check(len(addon._running) == 1, "RMB key dispatch starts exactly one fly operator")
    fly = next(iter(addon._running))
    eye = fly._eye()
    fly._look(80, 30)
    check(close_to(fly._eye(), eye), "look rotates around the eye without orbiting")
    start = fly._view.view_location.copy()
    fly._keys = {"E"}
    fly._step(1.0)
    delta = fly._view.view_location - start
    check(abs(delta.z - 5) < 0.0001 and abs(delta.x) + abs(delta.y) < 0.0001,
          "E moves upward in Blender world Z")
    start = fly._view.view_location.copy()
    fly._keys = {"W", "D"}
    fly._step(1.0)
    check(abs((fly._view.view_location - start).length - 5) < 0.0001,
          "diagonal movement keeps configured speed")
    fly._keys = {"Q"}
    fly._shift = True
    start = fly._view.view_location.copy()
    fly._step(1.0)
    check(abs((fly._view.view_location - start).z + 20) < 0.0001, "Shift boosts movement")
    fly._keys.clear()
    event("ESC")


def test_cancel():
    current = snapshot()
    check(not addon._running and close_to(initial[0], current[0])
          and initial[1].rotation_difference(current[1]).angle < 0.0001
          and initial[2:] == current[2:], "Esc restores the entire starting view and cleans timer")


def press_forward():
    event("W")


def release_forward():
    event("W", "RELEASE")
    event("RIGHTMOUSE", "RELEASE")


def test_release():
    check(not addon._running and not close_to(initial[0], snapshot()[0]),
          "RMB release keeps actual WASD movement and cleans timer")
    tool_is("builtin.scale")


def test_unregister_active():
    check(len(addon._running) == 1, "fly starts after previous completion")
    addon.unregister()
    check(not addon._running and not addon._keymaps and close_to(initial[0], snapshot()[0]),
          "disable during navigation restores view and releases all owned resources")
    addon.unregister()
    check(user_sentinel() is not None and user_sentinel().active, "repeated disable still preserves user binding")
    user_map = bpy.context.window_manager.keyconfigs.user.keymaps["Object Mode"]
    user_map.keymap_items.remove(user_sentinel())
    addon.register()
    event("MOUSEMOVE", "NOTHING")


def begin_orbit():
    global initial
    initial = snapshot()
    event("LEFTMOUSE", alt=True)


def drag_orbit():
    window, area, region = context()
    window.event_simulate(type="MOUSEMOVE", value="NOTHING", alt=True,
                          x=region.x + region.width // 2 + 100,
                          y=region.y + region.height // 2 + 40)
    event("LEFTMOUSE", "RELEASE", alt=True)


def check_orbit():
    check(initial[1].rotation_difference(snapshot()[1]).angle > 0.01,
          "Alt LMB dispatch orbits the viewport")


def edit_mesh():
    window, area, region = context()
    with bpy.context.temp_override(window=window, area=area, region=region):
        bpy.ops.object.mode_set(mode="EDIT")
    event("MOUSEMOVE", "NOTHING")


def check_edit_fly():
    check(len(addon._running) == 1, "RMB navigation overrides mesh context-menu keymap")
    event("ESC")


def object_mode():
    window, area, region = context()
    with bpy.context.temp_override(window=window, area=area, region=region):
        bpy.ops.object.mode_set(mode="OBJECT")


def begin_drag(kind, **modifiers):
    global initial
    initial = snapshot()
    event(kind, **modifiers)


def drag(kind, **modifiers):
    window, area, region = context()
    window.event_simulate(type="MOUSEMOVE", value="NOTHING",
                          x=region.x + region.width // 2 + 70,
                          y=region.y + region.height // 2 + 100, **modifiers)
    window.event_simulate(type=kind, value="RELEASE",
                          x=region.x + region.width // 2 + 70,
                          y=region.y + region.height // 2 + 100, **modifiers)


def check_pan():
    current = snapshot()
    check(not close_to(initial[0], current[0])
          and initial[1].rotation_difference(current[1]).angle < 0.0001,
          "MMB pans without changing view rotation")


def check_zoom():
    check(abs(initial[2] - snapshot()[2]) > 0.01 and not addon._running,
          "Alt RMB zooms instead of starting fly mode")


def focus():
    view = context()[1].spaces.active.region_3d
    view.view_location = Vector((50, 50, 50))
    event("F")


def check_focus():
    # Native frame-selected finishes its smooth-view animation before this callback.
    check(snapshot()[0].length < 0.01, "F frames the selected cube at the origin")


def ortho():
    context()[1].spaces.active.region_3d.view_perspective = "ORTHO"


def check_perspective():
    check(snapshot()[3] == "PERSP", "flight from orthographic view switches to perspective")
    event("ESC")


def check_ortho_cancel():
    check(snapshot()[3] == "ORTHO" and close_to(initial[0], snapshot()[0]),
          "Esc restores orthographic projection and position")
    context()[1].spaces.active.region_3d.view_perspective = "PERSP"


def check_camera_guard():
    window, area, region = context()
    view = area.spaces.active.region_3d
    view.view_perspective = "CAMERA"
    with bpy.context.temp_override(window=window, area=area, region=region):
        check(not bpy.ops.view3d.unity_fly.poll(), "camera view cannot start fly navigation")
    view.view_perspective = "PERSP"


def check_preferences():
    entry = bpy.context.preferences.addons.new()
    entry.module = addon.__package__
    prefs = entry.preferences
    prefs.navigation = False
    check(len(addon._keymaps) == 9, "navigation can be disabled independently")
    prefs.object_tools = False
    check(len(addon._keymaps) == 1 and addon._keymaps[0][0].name == "Outliner",
          "viewport options do not disable collection hierarchy")
    prefs.outliner_hierarchy = False
    check(not addon._keymaps, "all options disabled remove all bindings")
    prefs.navigation = True
    prefs.object_tools = True
    prefs.outliner_hierarchy = True
    check(len(addon._keymaps) == 33, "preference toggles restore bindings without duplicates")
    bpy.context.preferences.addons.remove(entry)


def finish():
    window, area, region = context()
    with bpy.context.temp_override(window=window, area=area, region=region):
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.wm.tool_set_by_id(name="builtin.move")
    addon.unregister()
    check(not addon._keymaps and not addon._running, "final cleanup leaves no bindings or timers")
    addon.register()  # Leave this factory-startup window available for a visual check.
    (OUTPUT / "test-results.json").write_text(json.dumps({"passed": len(checks), "checks": checks},
                                                         ensure_ascii=False, indent=2), encoding="utf-8")
    print("ALL TESTS PASSED:", len(checks), flush=True)


tasks = [lambda: event("ESC"), setup, lambda: event("W"), lambda: tool_is("builtin.move"),
         lambda: event("E"), lambda: tool_is("builtin.rotate"),
         lambda: event("R"), lambda: tool_is("builtin.scale"),
         start_fly, test_fly_motion, test_cancel,
         start_fly, press_forward, release_forward, test_release,
         start_fly, test_unregister_active, begin_orbit, drag_orbit, check_orbit,
         edit_mesh, start_fly, check_edit_fly, object_mode,
         lambda: begin_drag("MIDDLEMOUSE"), lambda: drag("MIDDLEMOUSE"), check_pan,
         lambda: begin_drag("RIGHTMOUSE", alt=True), lambda: drag("RIGHTMOUSE", alt=True), check_zoom,
         focus, check_focus, ortho, start_fly, press_forward, check_perspective, check_ortho_cancel,
         check_camera_guard, check_preferences, finish]


def tick():
    try:
        tasks.pop(0)()
    except Exception:
        detail = traceback.format_exc()
        print(detail, flush=True)
        (OUTPUT / "test-results.json").write_text(json.dumps({"failed": detail, "checks": checks},
                                                             indent=2), encoding="utf-8")
        return None
    return 0.3 if tasks else None


bpy.app.timers.register(tick, first_interval=2.0)
