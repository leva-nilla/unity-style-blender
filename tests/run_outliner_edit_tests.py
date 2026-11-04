"""Regression checks for recursive context-menu actions on edit bones and armature data."""

import json
from pathlib import Path
import sys
import traceback

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_outliner_tests as fixtures
bpy.app.timers.unregister(fixtures.tick)

addon = fixtures.addon
check = fixtures.check
context = fixtures.context
event = fixtures.event
click = fixtures.click
OUTPUT = fixtures.OUTPUT
seen_menus = []


def observe_menu(self, context):
    seen_menus.append(type(self).__name__)


def setup():
    addon.register()
    for menu in (bpy.types.OUTLINER_MT_collection, bpy.types.OUTLINER_MT_object,
                 bpy.types.OUTLINER_MT_context_menu):
        check(addon._draw_hierarchy in menu.draw._draw_funcs,
              menu.__name__ + " contains recursive hierarchy actions")
        menu.append(observe_menu)
    window = bpy.context.window_manager.windows[0]
    scene = bpy.data.scenes.new("Outliner edit regression")
    window.scene = scene
    collection = bpy.data.collections.new("00_Rig")
    scene.collection.children.link(collection)
    data = bpy.data.armatures.new("02_ArmatureData")
    obj = bpy.data.objects.new("01_Rig", data)
    collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    parent = None
    for i, name in enumerate(("03_Root", "04_Child", "05_Grandchild")):
        bone = data.edit_bones.new(name)
        bone.head = (0, 0, i)
        bone.tail = (0, 0, i + 1)
        bone.parent = parent
        parent = bone
    data.edit_bones.active = data.edit_bones[0]
    data.edit_bones[0].select = True
    other = bpy.data.collections.new("99_Other")
    scene.collection.children.link(other)
    other.children.link(bpy.data.collections.new("99_Child"))
    area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
    area.type = "OUTLINER"
    area.spaces.active.display_mode = "VIEW_LAYER"
    global rig, geometry
    rig = obj
    geometry = geometry_snapshot()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT / "outliner-edit010.blend"))


def geometry_snapshot():
    obj = bpy.context.object
    return ([(b.name, b.parent.name if b.parent else None, tuple(b.head), tuple(b.tail), b.roll)
             for b in obj.data.edit_bones],
            fixtures.data_snapshot())


def selection_snapshot():
    data = rig.data
    return (data.edit_bones.active.name if data.edit_bones.active else None,
            [(b.name, b.select, b.select_head, b.select_tail, b.hide) for b in data.edit_bones])


def expand_all():
    window, area, region = context()
    with bpy.context.temp_override(window=window, area=area, region=region):
        for _ in range(8):
            bpy.ops.outliner.show_one_level(open=True)


def open_menu(row):
    seen_menus.clear()
    event("MOUSEMOVE", "NOTHING", row=row)
    event("RIGHTMOUSE", row=row)
    event("RIGHTMOUSE", "RELEASE", row=row)


def check_menu(label, shared=True):
    expected = "OUTLINER_MT_context_menu" if shared else "OUTLINER_MT_object"
    check(expected in seen_menus, label + " native RMB path draws " + expected)
    check(bpy.context.mode == "EDIT_ARMATURE", label + " context menu preserves Edit Mode")
    event("ESC")


def action(expand):
    before = selection_snapshot()
    fixtures.menu_action(expand)
    check(bpy.context.mode == "EDIT_ARMATURE" and bpy.context.object == rig
          and geometry_snapshot() == geometry and selection_snapshot() == before,
          "recursive " + ("expand" if expand else "collapse") + " preserves edit bones, selection, and scene data")


def active_id(expected):
    window, area, region = context()
    with bpy.context.temp_override(window=window, area=area, region=region):
        item = getattr(bpy.context, "id", None)
        check(item is not None and item.name == expected,
              "visible Outliner row targets " + expected + " (actual: " + (item.name if item else "None") + ")")


def active_bone(expected):
    actual = rig.data.edit_bones.active
    check(actual is not None and actual.name == expected,
          "expanded hierarchy exposes " + expected + " (actual: " + (actual.name if actual else "None") + ")")


def finish():
    for menu in (bpy.types.OUTLINER_MT_collection, bpy.types.OUTLINER_MT_object,
                 bpy.types.OUTLINER_MT_context_menu):
        menu.remove(observe_menu)
    addon.unregister()
    check(all(addon._draw_hierarchy not in menu.draw._draw_funcs for menu in (
        bpy.types.OUTLINER_MT_collection, bpy.types.OUTLINER_MT_object, bpy.types.OUTLINER_MT_context_menu)),
        "disable removes all object, collection, and shared-menu callbacks")
    addon.register()
    check(bpy.types.OUTLINER_MT_context_menu.draw._draw_funcs.count(addon._draw_hierarchy) == 1,
          "re-enable installs one shared-menu callback")
    (OUTPUT / "outliner-edit-results.json").write_text(json.dumps({"passed": len(fixtures.checks),
        "checks": fixtures.checks}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("OUTLINER EDIT TESTS PASSED:", len(fixtures.checks), flush=True)


tasks = [setup, expand_all,
         # An armature has a Pose row before its data row, even in Edit Mode.
         lambda: open_menu(4), lambda: check_menu("armature data"), lambda: action(False),
         lambda: click(5), lambda: active_id("99_Other"),
         lambda: open_menu(4), lambda: check_menu("armature data"), lambda: action(True),
         lambda: click(7), lambda: active_bone("05_Grandchild"),
         lambda: open_menu(5), lambda: check_menu("edit bone"), lambda: action(False),
         lambda: click(6), lambda: active_id("99_Other"),
         lambda: open_menu(5), lambda: check_menu("edit bone"), lambda: action(True),
         lambda: click(7), lambda: active_bone("05_Grandchild"),
         lambda: open_menu(2), lambda: check_menu("object in Edit Mode", shared=False), finish]


def tick():
    try:
        tasks.pop(0)()
    except Exception:
        detail = traceback.format_exc()
        print(detail, flush=True)
        window, area, region = context()
        with bpy.context.temp_override(window=window, area=area, region=region):
            bpy.ops.screen.screenshot_area(filepath=str(OUTPUT / "outliner-edit-failure.png"))
        (OUTPUT / "outliner-edit-results.json").write_text(json.dumps({"failed": detail,
            "checks": fixtures.checks}, indent=2), encoding="utf-8")
        return None
    return 0.3 if tasks else None


bpy.app.timers.register(tick, first_interval=2)
