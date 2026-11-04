"""GUI regression checks for configurable extrusion and the read-only radius guide."""

import json
from pathlib import Path
import sys
import traceback

import bpy
import bmesh
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
# Reuse isolated fixture factories and event helpers; replace their scheduled suite.
import run_extended_tests as fixtures
bpy.app.timers.unregister(fixtures.tick)

addon = fixtures.addon
preview = addon.radius_preview
check = fixtures.check
context = fixtures.context
OUTPUT = fixtures.OUTPUT


def event(kind, value="PRESS", **modifiers):
    window, area, region = context()
    window.event_simulate(type=kind, value=value, x=region.x + region.width // 2,
                          y=region.y + region.height // 2, **modifiers)


def bindings():
    return [(km, item) for km, item in addon._keymaps if item.idname == "view3d.unity_extrude"]


def setup():
    fixtures.setup()
    global prefs
    prefs = fixtures.prefs_entry.preferences
    check(not bindings(), "extrude shortcuts are absent when edit WER is off")
    prefs.edit_tools = True
    check(len(bindings()) == 5 and all(item.type == "E" and item.shift for km, item in bindings()),
          "enabling edit WER creates default Shift E bindings in extrusion modes only")
    conflicts = addon.extrude_conflicts(bpy.context, prefs, "EDIT_MESH")
    check(any("Crease" in label for name, label in conflicts), "default Shift E reports native edge crease conflict")
    conflicts = addon.extrude_conflicts(bpy.context, prefs, "EDIT_ARMATURE")
    check(any("Forked" in label for name, label in conflicts), "bone mode reports forked extrusion conflict")
    prefs.extrude_key = "K"
    prefs.extrude_shift = False
    prefs.extrude_alt = True
    prefs.extrude_ctrl = True
    # Merge pending addon changes before authoring a user-map diff, as the UI does.
    bpy.context.window_manager.keyconfigs.update()
    km = bpy.context.window_manager.keyconfigs.user.keymaps["Mesh"]
    item = km.keymap_items.new("mesh.subdivide", "K", "PRESS", ctrl=True, alt=True)
    try:
        check(any(label == item.name for name, label in addon.extrude_conflicts(bpy.context, prefs, "EDIT_MESH")),
              "conflict detection includes user-created shortcuts")
        item.active = False
        check(not any(label == item.name for name, label in addon.extrude_conflicts(bpy.context, prefs, "EDIT_MESH")),
              "disabled user shortcuts are not reported")
    finally:
        km.keymap_items.remove(item)
    bpy.context.window_manager.keyconfigs.update()
    check(all(item.type == "K" and item.ctrl and item.alt and not item.shift for km, item in bindings()),
          "changing key and modifiers replaces the old bindings")
    prefs.extrude_key = "NONE"
    check(not bindings(), "no assignment keeps WER enabled without an extrusion shortcut")
    prefs.extrude_key = "W"
    prefs.extrude_alt = prefs.extrude_ctrl = False
    check(not bindings(), "bare W cannot override the edit Move tool")
    prefs.extrude_key = "K"
    prefs.extrude_shift = prefs.extrude_alt = True
    bpy.context.window_manager.keyconfigs.update()


def geometry_count():
    obj = bpy.context.object
    if obj.type == "MESH":
        return len(bmesh.from_edit_mesh(obj.data).verts)
    if obj.type == "ARMATURE":
        return len(obj.data.edit_bones)
    if obj.type in {"CURVE", "SURFACE"}:
        return sum(len(s.points) + len(s.bezier_points) for s in obj.data.splines)
    if obj.type == "CURVES":
        return len(obj.data.points)
    if obj.type == "GREASEPENCIL":
        return sum(len(layer.current_frame().drawing.attributes["position"].data)
                   for layer in obj.data.layers if layer.current_frame())


def prepare_extrude(expected, mode, create):
    fixtures.prepare_case(expected, mode, create)
    window, area, region = context()
    with bpy.context.temp_override(window=window, area=area, region=region):
        bpy.context.scene.tool_settings.use_proportional_edit = False
        obj = bpy.context.object
        if obj.type == "SURFACE":
            points = obj.data.splines[0].points
            for i, point in enumerate(points):
                point.select = i < 4
        bpy.ops.ed.undo_push(message="Before extrusion")
    global before_count
    before_count = geometry_count()


def extruded(expected):
    check(geometry_count() > before_count, expected + " configurable shortcut invokes native extrusion")
    event("LEFTMOUSE")


def undo_extrude():
    window, area, region = context()
    with bpy.context.temp_override(window=window, area=area, region=region):
        bpy.ops.ed.undo()


def extrusion_restored(expected):
    check(geometry_count() == before_count, expected + " extrusion is restored by one native Undo")


def sidebar_button():
    window, area, region = context()
    area.spaces.active.show_region_ui = True
    ui = next(r for r in area.regions if r.type == "UI")
    prefs.edit_tools = False
    with bpy.context.temp_override(window=window, area=area, region=ui):
        check(bpy.ops.view3d.unity_extrude.poll(), "N-panel button is available with edit WER off")
        bpy.ops.view3d.unity_extrude("EXEC_DEFAULT")


def check_button():
    check(geometry_count() > before_count, "N-panel context starts the native extrusion")
    event("LEFTMOUSE")


def setup_radius():
    fixtures.setup_gizmo()
    prefs.show_proportional_radius = True
    window, area, region = context()
    with bpy.context.temp_override(window=window, area=area, region=region):
        global original_mesh
        original_mesh = [tuple(p) for p in fixtures.mesh_positions()]
        area.spaces.active.region_3d.update()
        circle = preview.preview_circle(bpy.context)
        check(circle is not None and circle[1] > 1, "radius guide is present before a transform starts")
        bpy.context.scene.tool_settings.proportional_distance = 0.75
        smaller = preview.preview_circle(bpy.context)
        check(abs(smaller[1] * 2 - circle[1]) < 0.001, "N-panel radius property immediately changes the guide size")
        area.spaces.active.region_3d.view_distance *= 2
        area.spaces.active.region_3d.update()
        zoomed = preview.preview_circle(bpy.context)
        check(abs(zoomed[1] * 2 - smaller[1]) < 0.001, "orthographic zoom changes the displayed pixel radius")
        area.spaces.active.region_3d.view_perspective = "PERSP"
        area.spaces.active.region_3d.update()
        check(preview.preview_circle(bpy.context) is not None, "radius guide supports perspective projection")
        prefs.show_proportional_radius = False
        check(preview.preview_circle(bpy.context) is None, "radius visibility can be disabled")
        prefs.show_proportional_radius = True
        area.spaces.active.overlay.show_overlays = False
        check(preview.preview_circle(bpy.context) is None, "guide respects the viewport Overlays toggle")
        area.spaces.active.overlay.show_overlays = True
        bm = bmesh.from_edit_mesh(bpy.context.object.data)
        bm.verts.ensure_lookup_table()
        bm.verts[2].select_set(False)
        check(preview.preview_circle(bpy.context) is None, "guide hides with no selected points")
        bm.verts[3].select_set(True)
        check((preview.selection_center(bpy.context) - Vector((1, 0, 0))).length < 0.0001,
              "guide center follows the selected vertex")
        check([tuple(p) for p in fixtures.mesh_positions()] == original_mesh, "radius preview never changes geometry")
        bpy.context.scene.tool_settings.use_proportional_edit = False
        check(preview.preview_circle(bpy.context) is None, "guide hides when proportional editing is off")
        bpy.context.scene.tool_settings.use_proportional_edit = True
        bpy.ops.object.mode_set(mode="OBJECT")
        check(preview.preview_circle(bpy.context) is None, "guide hides outside edit mode")


def check_radius_mode(expected, mode, create):
    fixtures.prepare_case(expected, mode, create)
    window, area, region = context()
    with bpy.context.temp_override(window=window, area=area, region=region):
        bpy.context.scene.tool_settings.use_proportional_edit = True
        if bpy.context.object.type == "LATTICE":
            bpy.ops.lattice.select_all(action="SELECT")
        check(preview.preview_circle(bpy.context) is not None, expected + " selected control points have a radius guide")


def finish():
    prefs.edit_tools = False
    check(not bindings(), "disabling edit WER removes alternative extrusion keys")
    window, area, region = context()
    # Keep an isolated preview scene available for visual inspection.
    fixtures.setup_gizmo()
    area.spaces.active.show_region_ui = True
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT / "editing-config019.blend"))
    addon.unregister()
    check(preview._handler is None and not addon._keymaps and preview._load_post not in bpy.app.handlers.load_post,
          "disable removes radius draw/load handlers and bindings")
    addon.register()
    handler = preview._handler
    preview._load_post(None)
    addon.register()
    check(preview._handler is handler and bpy.app.handlers.load_post.count(preview._load_post) == 1,
          "file-load subscriptions and idempotent registration preserve one radius handler")
    (OUTPUT / "editing-config-results.json").write_text(json.dumps({"passed": len(fixtures.checks),
        "checks": fixtures.checks}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("EDITING CONFIG TESTS PASSED:", len(fixtures.checks), flush=True)


cases = [("EDIT_MESH", "EDIT", lambda: bpy.ops.mesh.primitive_plane_add())]
cases += [(e, m, c) for e, m, c in fixtures.CASES if e in addon._EXTRUDE_MODES]
tasks = [setup]
for expected, mode, create in cases:
    tasks += [lambda e=expected, m=mode, c=create: prepare_extrude(e, m, c),
              lambda: event("K", shift=True, alt=True), lambda e=expected: extruded(e),
              undo_extrude, lambda e=expected: extrusion_restored(e)]
tasks += [lambda: prepare_extrude("EDIT_MESH", "EDIT", lambda: bpy.ops.mesh.primitive_plane_add()),
          sidebar_button, check_button, undo_extrude, lambda: extrusion_restored("N-panel"), setup_radius]
for expected, mode, create in fixtures.CASES:
    if expected in preview.MODES:
        tasks += [lambda e=expected, m=mode, c=create: check_radius_mode(e, m, c)]
tasks += [finish]


def tick():
    try:
        tasks.pop(0)()
    except Exception:
        detail = traceback.format_exc()
        print(detail, flush=True)
        (OUTPUT / "editing-config-results.json").write_text(json.dumps({"failed": detail,
            "checks": fixtures.checks}, indent=2), encoding="utf-8")
        return None
    return 0.3 if tasks else None


bpy.app.timers.register(tick, first_interval=2)
