"""Real-input regression tests for mesh selection chords and axis-view fly navigation."""

import json
from pathlib import Path
import sys
import traceback

import bpy
import bmesh
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Quaternion, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_extended_tests as fixtures
bpy.app.timers.unregister(fixtures.tick)

addon = fixtures.addon
check = fixtures.check
context = fixtures.context
OUTPUT = fixtures.OUTPUT


def event(kind, value="PRESS", point=None, **modifiers):
    window, area, region = context()
    point = point if point is not None else Vector((region.width / 2, region.height / 2))
    window.event_simulate(type=kind, value=value, x=round(region.x + point.x),
                          y=round(region.y + point.y), **modifiers)


def view():
    return context()[1].spaces.active.region_3d


def setup():
    fixtures.setup()
    bpy.context.preferences.view.smooth_view = 0
    window, area, region = context()
    with bpy.context.temp_override(window=window, area=area, region=region):
        window.scene = bpy.data.scenes.new("Navigation input regression")
        mesh = bpy.data.meshes.new("Quad grid")
        vertices = [(x - 3, y - 2, 0) for y in range(5) for x in range(7)]
        faces = [(y * 7 + x, y * 7 + x + 1, (y + 1) * 7 + x + 1, (y + 1) * 7 + x)
                 for y in range(4) for x in range(6)]
        mesh.from_pydata(vertices, [], faces)
        obj = bpy.data.objects.new("Quad grid", mesh)
        window.scene.collection.objects.link(obj)
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.context.scene.tool_settings.mesh_select_mode = (False, True, False)
        bpy.ops.mesh.select_all(action="DESELECT")
        bpy.ops.view3d.view_axis(type="TOP")
        view().view_location = (0, 0, 0)
        view().view_distance = 10
        view().update()
    global original_geometry
    original_geometry = geometry()
    event("MOUSEMOVE", "NOTHING")


def geometry():
    bm = bmesh.from_edit_mesh(bpy.context.object.data)
    return ([tuple(v.co) for v in bm.verts], [tuple(v.index for v in e.verts) for e in bm.edges],
            [tuple(v.index for v in f.verts) for f in bm.faces])


def select_edge(x=0, ctrl=False, shift=False):
    window, area, region = context()
    point = location_3d_to_region_2d(region, view(), Vector((x, 0.5, 0)))
    event("MOUSEMOVE", "NOTHING", point, alt=True, ctrl=ctrl, shift=shift)
    event("LEFTMOUSE", point=point, alt=True, ctrl=ctrl, shift=shift)
    event("LEFTMOUSE", "RELEASE", point, alt=True, ctrl=ctrl, shift=shift)


def selected_edges():
    bm = bmesh.from_edit_mesh(bpy.context.object.data)
    return [tuple(v.co.copy() for v in edge.verts) for edge in bm.edges if edge.select]


def check_loop():
    edges = selected_edges()
    check(len(edges) == 4 and all(abs(a.x) + abs(b.x) < 0.0001 for a, b in edges),
          "Alt LMB selects the native edge loop instead of orbiting")


def check_extended_loop():
    edges = selected_edges()
    check(len(edges) == 8 and all(abs(a.x - b.x) < 0.0001 for a, b in edges),
          "Shift Alt LMB extends native loop selection")


def check_ring():
    edges = selected_edges()
    check(len(edges) == 7 and all(abs(a.x - b.x) < 0.0001 and {round(a.y), round(b.y)} == {0, 1}
                                 for a, b in edges), "Ctrl Alt LMB selects the native edge ring")
    check(geometry() == original_geometry and bpy.context.mode == "EDIT_MESH",
          "loop and ring selection preserve topology, positions, and Edit Mode")


def begin_orbit():
    global orbit_start
    orbit_start = view().view_rotation.copy()
    event("MIDDLEMOUSE", alt=True)


def drag_orbit():
    _, _, region = context()
    event("MOUSEMOVE", "NOTHING", Vector((region.width / 2 + 80, region.height / 2 + 30)), alt=True)
    event("MIDDLEMOUSE", "RELEASE", alt=True)


def check_orbit():
    check(orbit_start.rotation_difference(view().view_rotation).angle > 0.01,
          "Alt MMB orbits in Mesh Edit Mode")
    check(geometry() == original_geometry, "edit-mode orbit preserves mesh geometry")


def check_axis(label):
    check(view().is_orthographic_side_view and view().view_perspective == "ORTHO",
          label + " numeric key enters a native axis-aligned orthographic view")
    global initial
    initial = fixtures.view_snapshot()


def short_click():
    event("RIGHTMOUSE")
    event("RIGHTMOUSE", "RELEASE")


def check_short_click():
    check(not addon._running and view().view_perspective == "ORTHO" and view().is_orthographic_side_view,
          "a short RMB context click preserves the axis projection")
    event("ESC")


def check_axis_fly():
    check(len(addon._running) == 1 and view().view_perspective == "PERSP",
          "WASD navigation from a numeric axis view switches to perspective")
    check(abs(view().view_distance - initial[2]) < 0.0001
          and (view().view_location - initial[0]).length > 0.0001,
          "axis-view W moves forward instead of orthographic zooming")
    event("W", "RELEASE")
    event("RIGHTMOUSE", "RELEASE")


def check_axis_finished():
    check(not addon._running and view().view_perspective == "PERSP",
          "perspective projection remains after finishing axis-view navigation")


def look():
    _, _, region = context()
    event("MOUSEMOVE", "NOTHING", Vector((region.width / 2 + 80, region.height / 2 + 30)))


def check_axis_look():
    check(view().view_perspective == "PERSP" and view().view_rotation.rotation_difference(initial[1]).angle > 0.01,
          "mouse look from a numeric axis view switches to perspective")
    event("ESC")


def check_restored():
    current = fixtures.view_snapshot()
    check(not addon._running and current[3] == "ORTHO" and view().is_orthographic_side_view
          and (current[0] - initial[0]).length < 0.0001
          and current[1].rotation_difference(initial[1]).angle < 0.0001
          and abs(current[2] - initial[2]) < 0.0001,
          "Esc restores the original axis flag, projection, rotation, position, and scale")


def disable_conversion():
    fixtures.prefs_entry.preferences.axis_view_perspective = False


def check_disabled():
    check(view().view_perspective == "ORTHO" and view().view_distance < initial[2],
          "disabling axis conversion keeps native orthographic pan/zoom navigation")
    event("ESC")


def free_ortho():
    fixtures.prefs_entry.preferences.axis_view_perspective = True
    view().view_rotation = Quaternion((1, 0, 0), 0.3) @ view().view_rotation
    view().view_perspective = "ORTHO"
    check(not view().is_orthographic_side_view, "free orthographic fixture is not an axis view")


def check_free_ortho():
    check(view().view_perspective == "ORTHO", "free orthographic navigation preserves its projection")
    event("ESC")


def finish():
    check(geometry() == original_geometry, "all navigation leaves mesh geometry intact")
    addon.unregister()
    check(not addon._keymaps and not addon._running, "input regression suite cleans up its handlers and bindings")
    (OUTPUT / "navigation-input-results.json").write_text(json.dumps({"passed": len(fixtures.checks),
        "checks": fixtures.checks}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("NAVIGATION INPUT TESTS PASSED:", len(fixtures.checks), flush=True)


tasks = [setup, select_edge, check_loop, lambda: select_edge(1, shift=True), check_extended_loop,
         lambda: select_edge(ctrl=True), check_ring, begin_orbit, drag_orbit, check_orbit,
         lambda: event("NUMPAD_1"), lambda: check_axis("Front"), short_click, check_short_click,
         lambda: event("RIGHTMOUSE"), lambda: event("W"), check_axis_fly, check_axis_finished,
         lambda: event("NUMPAD_3"), lambda: check_axis("Right"), lambda: event("RIGHTMOUSE"),
         look, check_axis_look, check_restored,
         lambda: event("NUMPAD_7"), lambda: check_axis("Top"), lambda: event("RIGHTMOUSE"),
         look, check_axis_look, check_restored,
         disable_conversion, lambda: event("NUMPAD_1"), lambda: check_axis("Front, conversion disabled"),
         lambda: event("RIGHTMOUSE"), lambda: event("W"), check_disabled,
         free_ortho, lambda: event("RIGHTMOUSE"), lambda: event("W"), check_free_ortho, finish]


def tick():
    try:
        tasks.pop(0)()
    except Exception:
        detail = traceback.format_exc()
        print(detail, flush=True)
        (OUTPUT / "navigation-input-results.json").write_text(json.dumps({"failed": detail,
            "checks": fixtures.checks}, indent=2), encoding="utf-8")
        return None
    return 0.3 if tasks else None


bpy.app.timers.register(tick, first_interval=2)
