"""GUI event tests for extended modes and native proportional transform gizmos."""

import json
from pathlib import Path
import sys
import traceback

import bpy
import bmesh
from mathutils import Quaternion, Vector
from bpy_extras.view3d_utils import location_3d_to_region_2d

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import addon

OUTPUT = ROOT / "artifacts"
OUTPUT.mkdir(exist_ok=True)
checks = []
bpy.context.preferences.view.show_splash = False
bpy.context.preferences.use_preferences_save = False


def check(value, message):
    if not value:
        raise AssertionError(message)
    checks.append(message)
    print("PASS:", message, flush=True)


def context():
    window = bpy.context.window_manager.windows[0]
    area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    return window, area, region


def event(kind, value="PRESS", x=None, y=None):
    window, area, region = context()
    window.event_simulate(type=kind, value=value,
                          x=region.x + (region.width // 2 if x is None else round(x)),
                          y=region.y + (region.height // 2 if y is None else round(y)))


def view_snapshot():
    view = context()[1].spaces.active.region_3d
    return view.view_location.copy(), view.view_rotation.copy(), view.view_distance, view.view_perspective


def object_snapshot():
    obj = bpy.context.active_object
    data = obj.data
    result = [obj.type, tuple(tuple(row) for row in obj.matrix_world)]
    if obj.type == "ARMATURE":
        result.append([(b.name, tuple(b.head), tuple(b.tail), b.roll) for b in data.edit_bones])
    elif obj.type in {"CURVE", "SURFACE"}:
        result.append([([tuple(p.co) for p in s.points],
                        [(tuple(p.co), tuple(p.handle_left), tuple(p.handle_right)) for p in s.bezier_points])
                       for s in data.splines])
    elif obj.type == "FONT":
        result.append(data.body)
    elif obj.type == "META":
        result.append([(tuple(e.co), e.radius) for e in data.elements])
    elif obj.type == "LATTICE":
        result.append([tuple(p.co_deform) for p in data.points])
    elif obj.type in {"CURVES", "POINTCLOUD"}:
        position = data.attributes.get("position")
        result.append([tuple(p.vector) for p in position.data] if position else [])
    elif obj.type == "GREASEPENCIL":
        for layer in data.layers:
            for frame in layer.frames:
                position = frame.drawing.attributes.get("position")
                result.append((layer.name, frame.frame_number,
                               [tuple(p.vector) for p in position.data] if position else []))
    if obj.particle_systems:
        result.append([[[tuple(key.co) for key in particle.hair_keys] for particle in system.particles]
                       for system in obj.particle_systems])
    return result


def hair():
    bpy.ops.mesh.primitive_plane_add()
    bpy.ops.object.curves_empty_hair_add()
    data = bpy.context.object.data
    data.add_curves([3])
    data.attributes['position'].data.foreach_set('vector', [0, 0, 0, 0, 0, 0.5, 0.2, 0, 1])


def particle():
    bpy.ops.mesh.primitive_plane_add()
    bpy.ops.object.particle_system_add()
    settings = bpy.context.object.particle_systems[-1].settings
    settings.type = "HAIR"
    settings.count = 3


CASES = [
    ("EDIT_ARMATURE", "EDIT", lambda: bpy.ops.object.armature_add()),
    ("EDIT_CURVE", "EDIT", lambda: bpy.ops.curve.primitive_bezier_curve_add()),
    ("EDIT_SURFACE", "EDIT", lambda: bpy.ops.surface.primitive_nurbs_surface_surface_add()),
    ("EDIT_TEXT", "EDIT", lambda: bpy.ops.object.text_add()),
    ("EDIT_METABALL", "EDIT", lambda: bpy.ops.object.metaball_add()),
    ("EDIT_LATTICE", "EDIT", lambda: bpy.ops.object.add(type="LATTICE")),
    ("EDIT_POINT_CLOUD", "EDIT", lambda: bpy.ops.object.add(type="POINTCLOUD")),
    ("EDIT_CURVES", "EDIT", hair),
    ("SCULPT_CURVES", "SCULPT_CURVES", hair),
    ("PARTICLE", "PARTICLE_EDIT", particle),
]
for expected, mode in (("EDIT_GREASE_PENCIL", "EDIT"),
                       ("PAINT_GREASE_PENCIL", "PAINT_GREASE_PENCIL"),
                       ("SCULPT_GREASE_PENCIL", "SCULPT_GREASE_PENCIL"),
                       ("WEIGHT_GREASE_PENCIL", "WEIGHT_GREASE_PENCIL"),
                       ("VERTEX_GREASE_PENCIL", "VERTEX_GREASE_PENCIL")):
    CASES.append((expected, mode, lambda: bpy.ops.object.grease_pencil_add(type="STROKE")))


def setup():
    addon.register()
    global prefs_entry
    prefs_entry = bpy.context.preferences.addons.new()
    prefs_entry.module = addon.__package__
    check(not prefs_entry.preferences.edit_tools, "edit WER replacement defaults to off")
    missing = [name for name in (*addon._CONTEXT_MENUS.values(), *addon._PAINT_PANELS.values())
               if not hasattr(bpy.types, name)]
    check(not missing, "every referenced native menu and panel exists: " + str(missing))


def prepare_case(expected, mode, create):
    window, area, region = context()
    with bpy.context.temp_override(window=window, area=area, region=region):
        if bpy.context.object and bpy.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        for obj in list(bpy.context.scene.objects):
            obj.hide_set(True)
        create()
        bpy.ops.object.mode_set(mode=mode)
    check(bpy.context.mode == expected, "fixture enters " + expected)
    global original_data, original_view
    original_data = object_snapshot()
    area.spaces.active.region_3d.view_perspective = "PERSP"
    original_view = view_snapshot()
    event("MOUSEMOVE", "NOTHING")


def check_moved(expected):
    check(bpy.context.mode == expected and len(addon._running) == 1
          and (view_snapshot()[0] - original_view[0]).length > 0.0001,
          expected + " accepts native RMB/WASD event dispatch")
    event("ESC")


def check_cancel(expected):
    check(not addon._running and bpy.context.mode == expected
          and (view_snapshot()[0] - original_view[0]).length < 0.0001
          and object_snapshot() == original_data, expected + " preserves geometry and restores the view")
    event("RIGHTMOUSE")


def check_click(expected):
    check(not addon._running and bpy.context.mode == expected, expected + " short RMB completes cleanly")
    event("ESC")


def mesh_positions():
    bm = bmesh.from_edit_mesh(bpy.context.active_object.data)
    bm.verts.ensure_lookup_table()
    return [v.co.copy() for v in bm.verts]


def setup_gizmo():
    window, area, region = context()
    with bpy.context.temp_override(window=window, area=area, region=region):
        bpy.ops.object.mode_set(mode="OBJECT")
        for obj in list(bpy.context.scene.objects):
            obj.hide_set(True)
        mesh = bpy.data.meshes.new("Proportional gizmo fixture")
        mesh.from_pydata([(x, 0, 0) for x in (-2, -1, 0, 1, 2)], [(i, i + 1) for i in range(4)], [])
        obj = bpy.data.objects.new("Proportional gizmo fixture", mesh)
        bpy.context.scene.collection.objects.link(obj)
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()
        for v in bm.verts:
            v.select = False
        for edge in bm.edges:
            edge.select = False
        bm.verts[2].select_set(True)
        bm.select_history.clear()
        bm.select_history.add(bm.verts[2])
        bm.select_flush_mode()
        bmesh.update_edit_mesh(mesh)
        bpy.context.scene.tool_settings.mesh_select_mode = (True, False, False)
        settings = bpy.context.scene.tool_settings
        settings.use_proportional_edit = True
        settings.proportional_edit_falloff = "SMOOTH"
        settings.proportional_size = 1.5
        settings.use_proportional_connected = False
        bpy.context.scene.transform_orientation_slots[0].type = "GLOBAL"
        view = area.spaces.active.region_3d
        view.view_rotation = Quaternion((1, 0, 0, 0))
        view.view_location = (0, 0, 0)
        view.view_distance = 6
        view.view_perspective = "ORTHO"
        bpy.ops.view3d.unity_edit_tool(tool="builtin.move")
        bpy.ops.ed.undo_push(message="Before proportional gizmo")
        print('SELECTED VERTICES', [v.index for v in bm.verts if v.select], flush=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT / "gizmo017.blend"))
    global gizmo_original
    gizmo_original = mesh_positions()
    check(bpy.context.mode == "EDIT_MESH" and settings.use_proportional_edit,
          "edit Move button selects the native gizmo and preserves proportional editing")


def hover_axis():
    window, area, region = context()
    point = location_3d_to_region_2d(region, area.spaces.active.region_3d, Vector((0, 0, 0)))
    global gizmo_point
    gizmo_point = point + Vector((50, 0))
    event("MOUSEMOVE", "NOTHING", *gizmo_point)


def check_proportional_drag():
    positions = mesh_positions()
    selected_delta = positions[2] - gizmo_original[2]
    neighbor_delta = positions[1] - gizmo_original[1]
    far_delta = positions[0] - gizmo_original[0]
    print('GIZMO POSITIONS', [list(p) for p in positions], flush=True)
    check(selected_delta.x > 0.001 and abs(selected_delta.y) + abs(selected_delta.z) < 0.0001,
          "native X gizmo moves the selected vertex only along X")
    check(0.0001 < neighbor_delta.x < selected_delta.x and far_delta.length < 0.0001,
          "proportional gizmo affects nearby vertices with falloff and leaves distant vertices fixed")
    window, area, region = context()
    with bpy.context.temp_override(window=window, area=area, region=region):
        bpy.ops.ed.undo()


def check_gizmo_undo():
    check(all((a - b).length < 0.0001 for a, b in zip(mesh_positions(), gizmo_original)),
          "one native Undo restores the proportional gizmo edit")
    prefs_entry.preferences.edit_tools = True
    event("MOUSEMOVE", "NOTHING")


def check_edit_tool(tool):
    active = bpy.context.workspace.tools.from_space_view3d_mode("EDIT_MESH", create=False)
    check(active.idname == tool, "edit WER dispatch selects " + tool)


def finish():
    prefs_entry.preferences.edit_tools = False
    check(not any(km.name == "Mesh" and item.idname == "view3d.unity_edit_tool" for km, item in addon._keymaps),
          "disabling edit WER removes its overrides")
    addon.unregister()
    check(not addon._keymaps and not addon._running, "extended navigation and tools clean up on disable")
    (OUTPUT / "extended-results.json").write_text(json.dumps({"passed": len(checks), "checks": checks},
                                                             ensure_ascii=False, indent=2), encoding="utf-8")
    print("EXTENDED TESTS PASSED:", len(checks), flush=True)


tasks = [setup]
for expected, mode, create in CASES:
    tasks.extend([lambda e=expected, m=mode, c=create: prepare_case(e, m, c),
                  lambda: event("RIGHTMOUSE"), lambda: event("W"),
                  lambda e=expected: check_moved(e), lambda e=expected: check_cancel(e),
                  lambda: event("RIGHTMOUSE", "RELEASE"), lambda e=expected: check_click(e)])
gizmo_tasks = [setup_gizmo, hover_axis,
              lambda: event("LEFTMOUSE", "PRESS", *gizmo_point),
              lambda: event("MOUSEMOVE", "NOTHING", gizmo_point.x + 50, gizmo_point.y),
              lambda: event("MOUSEMOVE", "NOTHING", gizmo_point.x + 100, gizmo_point.y),
              lambda: event("LEFTMOUSE", "RELEASE", gizmo_point.x + 100, gizmo_point.y),
              check_proportional_drag, check_gizmo_undo,
              lambda: event("W"), lambda: check_edit_tool("builtin.move"),
              lambda: event("E"), lambda: check_edit_tool("builtin.rotate"),
              lambda: event("R"), lambda: check_edit_tool("builtin.scale"), finish]
tasks.extend(gizmo_tasks)
if "--gizmo-only" in sys.argv:
    tasks = [setup] + gizmo_tasks


def tick():
    try:
        tasks.pop(0)()
    except Exception:
        detail = traceback.format_exc()
        print(detail, flush=True)
        (OUTPUT / "extended-results.json").write_text(json.dumps({"failed": detail, "checks": checks}, indent=2),
                                                      encoding="utf-8")
        return None
    return 0.2 if tasks else None


bpy.app.timers.register(tick, first_interval=2)
