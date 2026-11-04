"""Actual selection/transform/Undo events invalidate the radius cache; view changes do not."""

import json
from pathlib import Path
import sys
import traceback
from unittest.mock import patch

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_navigation_input_tests as fixtures
bpy.app.timers.unregister(fixtures.tick)

preview = fixtures.addon.radius_preview
check = fixtures.check
context = fixtures.context
OUTPUT = fixtures.OUTPUT
checks = fixtures.fixtures.checks


def center():
    window, area, region = context()
    with bpy.context.temp_override(window=window, area=area, region=region):
        return preview.selection_center(bpy.context)


def setup():
    fixtures.setup()
    global patcher, calculate
    patcher = patch.object(preview, "_calculate_center", wraps=preview._calculate_center)
    calculate = patcher.start()


def first_center():
    check((center() - Vector((0, 0, 0))).length < 0.0001, "first loop has the expected cached center")
    global calls
    calls = calculate.call_count


def move_view_and_radius():
    for _ in range(100):
        center()
    window, area, region = context()
    view = area.spaces.active.region_3d
    view.view_location.x += 0.25
    view.view_distance *= 1.5
    view.update()
    bpy.context.scene.tool_settings.proportional_distance = 2


def check_view_cache():
    check((center() - Vector((0, 0, 0))).length < 0.0001 and calculate.call_count == calls,
          "repeated reads, pan, zoom, and radius changes do not rescan vertices")


def start_fly():
    bpy.context.scene.tool_settings.use_proportional_edit = True
    fixtures.fixtures.prefs_entry.preferences.axis_view_perspective = False
    fixtures.event("RIGHTMOUSE")
    fixtures.event("D")


def finish_fly():
    fixtures.event("D", "RELEASE")
    fixtures.event("RIGHTMOUSE", "RELEASE")


def check_fly_cache():
    check((center() - Vector((0, 0, 0))).length < 0.0001 and calculate.call_count == calls,
          "actual RMB fly navigation with the radius overlay enabled reuses the cached center")


def second_center():
    check((center() - Vector((1, 0, 0))).length < 0.0001,
          "native same-count selection replacement invalidates the cached center")


def transform():
    window, area, region = context()
    with bpy.context.temp_override(window=window, area=area, region=region):
        bpy.ops.ed.undo_push(message="Before cached center transform")
        bpy.ops.transform.translate(value=(2, 0, 0))
        # Timer-driven EXEC calls need an explicit changed state for Redo to restore.
        bpy.ops.ed.undo_push(message="After cached center transform")


def transformed_center():
    check((center() - Vector((3, 0, 0))).length < 0.0001,
          "native geometry changes invalidate the cached center")


def undo():
    window, area, region = context()
    with bpy.context.temp_override(window=window, area=area, region=region):
        bpy.ops.ed.undo()


def undone_center():
    check((center() - Vector((1, 0, 0))).length < 0.0001, "native Undo restores the preview center")


def redo():
    window, area, region = context()
    with bpy.context.temp_override(window=window, area=area, region=region):
        bpy.ops.ed.redo()


def redone_center():
    check((center() - Vector((3, 0, 0))).length < 0.0001, "native Redo restores the transformed preview center")


def finish():
    patcher.stop()
    bpy.types.VIEW3D_MT_edit_mesh_context_menu.remove(fixtures.observe_context_menu)
    fixtures.addon.unregister()
    check(preview._handler is None and preview._center_cache.key is None
          and preview._depsgraph_update not in bpy.app.handlers.depsgraph_update_post
          and preview._invalidate_center not in bpy.app.handlers.undo_post
          and preview._invalidate_center not in bpy.app.handlers.redo_post,
          "disable clears cached state and removes all preview update handlers")
    (OUTPUT / "radius-cache-results.json").write_text(json.dumps({"passed": len(checks),
        "checks": checks}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("RADIUS CACHE TESTS PASSED:", len(checks), flush=True)


tasks = [setup, fixtures.select_edge, first_center, move_view_and_radius, check_view_cache,
         start_fly, finish_fly, check_fly_cache,
         lambda: fixtures.select_edge(1), second_center, transform, transformed_center,
         undo, undone_center, redo, redone_center, finish]


def tick():
    try:
        tasks.pop(0)()
    except Exception:
        detail = traceback.format_exc()
        print(detail, flush=True)
        (OUTPUT / "radius-cache-results.json").write_text(json.dumps({"failed": detail,
            "checks": checks}, indent=2), encoding="utf-8")
        return None
    return 0.3 if tasks else None


bpy.app.timers.register(tick, first_interval=2)
