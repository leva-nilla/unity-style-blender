"""Outliner event tests in a factory-startup GUI with --enable-event-simulate."""

import json
from pathlib import Path
import sys
import traceback

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import addon

OUTPUT = ROOT / "artifacts"
OUTPUT.mkdir(exist_ok=True)
checks = []
bpy.context.preferences.view.show_splash = False
bpy.context.preferences.use_preferences_save = False


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    checks.append(message)
    print("PASS:", message, flush=True)


def context():
    window = bpy.context.window_manager.windows[0]
    area = max((a for a in window.screen.areas if a.type == "OUTLINER"), key=lambda a: a.width)
    region = next(r for r in area.regions if r.type == "WINDOW")
    return window, area, region


def event(kind, value="PRESS", *, row=1, x=120, **modifiers):
    window, area, region = context()
    scale = bpy.context.preferences.system.ui_scale
    px, py = region.view2d.view_to_region(x * scale, -(row + 0.5) * 20 * scale, clip=False)
    window.event_simulate(type=kind, value=value, x=region.x + px, y=region.y + py, **modifiers)


def click(row, *, triangle=False, alt=False, triangle_x=30):
    x = triangle_x if triangle else 180
    event("MOUSEMOVE", "NOTHING", row=row, x=x, alt=alt)
    event("LEFTMOUSE", row=row, x=x, alt=alt)
    event("LEFTMOUSE", "RELEASE", row=row, x=x, alt=alt)


def selected(name):
    window, area, region = context()
    with bpy.context.temp_override(window=window, area=area, region=region):
        actual = [item.name for item in bpy.context.selected_ids]
    check(actual == [name], "visible row selects " + name + " (actual: " + str(actual) + ")")


def setup():
    addon.register()
    window = bpy.context.window_manager.windows[0]
    scene = bpy.data.scenes.new("Outliner test scene")
    window.scene = scene
    target = bpy.data.collections.new("00_Target")
    child = bpy.data.collections.new("01_Child")
    grandchild = bpy.data.collections.new("02_Grandchild")
    leaf = bpy.data.objects.new("03_Leaf", None)
    scene.collection.children.link(target)
    target.children.link(child)
    child.children.link(grandchild)
    grandchild.objects.link(leaf)
    object_child = bpy.data.objects.new("04_ObjectChild", None)
    object_grandchild = bpy.data.objects.new("05_ObjectGrandchild", None)
    grandchild.objects.link(object_child)
    grandchild.objects.link(object_grandchild)
    object_child.parent = leaf
    object_grandchild.parent = object_child
    other = bpy.data.collections.new("99_Other")
    other_child = bpy.data.collections.new("99_Child")
    scene.collection.children.link(other)
    other.children.link(other_child)
    global original_data
    original_data = data_snapshot()
    area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
    area.type = "OUTLINER"
    area.spaces.active.display_mode = "VIEW_LAYER"
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT / "outliner-test.blend"))


def data_snapshot():
    scene = bpy.context.window_manager.windows[0].scene
    collections = [(c.name, tuple(ch.name for ch in c.children), tuple(o.name for o in c.objects),
                    c.hide_viewport, c.hide_render) for c in scene.collection.children_recursive]
    objects = [(o.name, o.parent.name if o.parent else None, o.hide_viewport, o.hide_render)
               for o in scene.objects]
    return collections, objects


def collapse_all():
    window, area, region = context()
    with bpy.context.temp_override(window=window, area=area, region=region):
        for _ in range(8):
            bpy.ops.outliner.show_one_level(open=False)


def menu_action(expand):
    window, area, region = context()
    with bpy.context.temp_override(window=window, area=area, region=region):
        result = bpy.ops.outliner.select_walk("INVOKE_REGION_WIN", direction="RIGHT" if expand else "LEFT",
                                              toggle_all=True)
    check(result == {"FINISHED"}, "hierarchy menu action " + ("expand" if expand else "collapse"))


def finish():
    check(data_snapshot() == original_data, "hierarchy display leaves membership and visibility intact")
    addon.unregister()
    check(not addon._keymaps, "disable removes Outliner shortcut along with viewport shortcuts")
    addon.register()
    bindings = [item for km, item in addon._keymaps if km.name == "Outliner"]
    check(len(bindings) == 1 and bindings[0].alt and bindings[0].value == "CLICK"
          and bindings[0].properties.all, "re-enable creates one Alt-click recursive binding")
    (OUTPUT / "outliner-results.json").write_text(json.dumps({"passed": len(checks), "checks": checks},
                                                             ensure_ascii=False, indent=2), encoding="utf-8")
    print("OUTLINER TESTS PASSED:", len(checks), flush=True)


tasks = [setup, collapse_all, lambda: click(1), lambda: selected("00_Target"),
         lambda: click(1, triangle=True, alt=True), lambda: click(4), lambda: selected("03_Leaf"),
         lambda: click(7), lambda: selected("99_Other"),
         lambda: click(1, triangle=True, alt=True), lambda: click(2), lambda: selected("99_Other"),
         lambda: click(1), lambda: menu_action(True), lambda: click(4), lambda: selected("03_Leaf"),
         lambda: click(1), lambda: menu_action(False), lambda: click(2), lambda: selected("99_Other"),
         lambda: click(1), lambda: menu_action(True),
         lambda: click(4, triangle=True, alt=True, triangle_x=90),
         lambda: click(5), lambda: selected("99_Other"),
         lambda: click(4, triangle=True, alt=True, triangle_x=90),
         lambda: click(6), lambda: selected("05_ObjectGrandchild"),
         lambda: click(4), lambda: menu_action(False), lambda: click(5), lambda: selected("99_Other"),
         lambda: click(4), lambda: menu_action(True), lambda: click(6), lambda: selected("05_ObjectGrandchild"),
         finish]


def tick():
    try:
        tasks.pop(0)()
    except Exception:
        detail = traceback.format_exc()
        print(detail, flush=True)
        (OUTPUT / "outliner-results.json").write_text(json.dumps({"failed": detail, "checks": checks}, indent=2),
                                                      encoding="utf-8")
        return None
    return 0.3 if tasks else None


bpy.app.timers.register(tick, first_interval=2.0)
