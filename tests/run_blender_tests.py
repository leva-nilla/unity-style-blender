"""Run in an isolated GUI: blender --factory-startup --enable-event-simulate --python ..."""

import json
import math
from pathlib import Path
import sys
import traceback
from unittest.mock import patch

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
    check(count == 37 and len(addon._keymaps) == count, "register is idempotent (37 bindings)")
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
    check(abs(fly._timer.time_step - 1 / 120) < 0.000001, "default navigation requests 120 Hz updates")
    # The following checks exercise immediate speed mode, independently of easing.
    fly._smoothing = 0
    fly._move_space = "WORLD"
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
    fly._shift = False
    fly._ctrl = True
    start = fly._view.view_location.copy()
    fly._step(1.0)
    check(abs((fly._view.view_location - start).z + 1.25) < 0.0001, "Ctrl enables precise quarter-speed movement")
    fly._ctrl = False
    fly._keys.clear()
    # A press and release entirely between timer ticks must still move the view.
    start = fly._view.view_location.copy()
    now = addon.time.perf_counter()
    fly._last = now
    window, area, region = context()
    from types import SimpleNamespace
    with bpy.context.temp_override(window=window, area=area, region=region):
        with patch.object(addon.time, "perf_counter", return_value=now + 0.004):
            fly.modal(bpy.context, SimpleNamespace(type="W", value="PRESS", shift=False, ctrl=False))
        with patch.object(addon.time, "perf_counter", return_value=now + 0.009):
            fly.modal(bpy.context, SimpleNamespace(type="W", value="RELEASE", shift=False, ctrl=False))
    fly._last = addon.time.perf_counter()
    check(abs((fly._view.view_location - start).length - 0.025) < 0.0001,
          "a 5 ms key tap is integrated even between timer events")
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
    check(bpy.context.mode == "EDIT_MESH" and len(addon._running) == 1
          and not close_to(initial[0], snapshot()[0]), "mesh edit supports RMB and WASD movement")
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


def check_ortho_motion():
    current = snapshot()
    check(current[3] == "ORTHO" and not close_to(initial[0], current[0]),
          "WASD moves the view while retaining orthographic projection")


def press_right():
    event("D")


def release_right():
    event("D", "RELEASE")
    event("RIGHTMOUSE", "RELEASE")


def check_ortho_zoom():
    current = snapshot()
    check(current[3] == "ORTHO" and current[2] < initial[2] and close_to(initial[0], current[0]),
          "orthographic W zooms in around a fixed center")
    release_forward()


def check_ortho_zoom_finished():
    check(not addon._running and snapshot()[3] == "ORTHO" and snapshot()[2] < initial[2],
          "orthographic zoom persists after RMB release")


def look_ortho():
    window, area, region = context()
    window.event_simulate(type="MOUSEMOVE", value="NOTHING",
                          x=region.x + region.width // 2 + 80,
                          y=region.y + region.height // 2 + 30)


def check_ortho_look():
    current = snapshot()
    check(current[3] == "ORTHO" and initial[1].rotation_difference(current[1]).angle > 0.01,
          "mouse look retains orthographic projection")
    event("WHEELUPMOUSE")


def check_ortho_scale():
    current = snapshot()
    check(current[3] == "ORTHO" and abs(current[2] - initial[2]) < 0.0001,
          "wheel speed adjustment keeps orthographic projection and scale")


def check_ortho_finish():
    current = snapshot()
    check(not addon._running and current[3] == "ORTHO" and not close_to(initial[0], current[0]),
          "RMB release keeps the moved view in orthographic projection")


def check_ortho_cancel():
    current = snapshot()
    check(not addon._running and current[3] == "ORTHO" and close_to(initial[0], current[0])
          and initial[1].rotation_difference(current[1]).angle < 0.0001
          and abs(initial[2] - current[2]) < 0.0001,
          "Esc restores the complete starting orthographic view")


def disable_ortho():
    addon.unregister()
    current = snapshot()
    check(not addon._running and current[3] == "ORTHO" and close_to(initial[0], current[0])
          and initial[1].rotation_difference(current[1]).angle < 0.0001 and abs(current[2] - initial[2]) < 0.0001,
          "disable during orthographic flight restores the original view")
    addon.register()
    event("MOUSEMOVE", "NOTHING")
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
    check(abs(prefs.look_sensitivity - 3.5) < 0.00001, "new default sensitivity matches the user's DPI1600 setting")
    window, area, region = context()
    with bpy.context.temp_override(window=window, area=area, region=region):
        check(addon.VIEW3D_PT_unity_view.poll(bpy.context), "View sidebar sensitivity is available with the add-on enabled")
    prefs.sensitivity = 0.003  # Previously saved internal angle.
    check(abs(prefs.look_sensitivity - 6.0) < 0.0001, "legacy sensitivity is preserved by the multiplier display")
    prefs.look_sensitivity = 1.0
    baseline = prefs.sensitivity
    prefs.look_sensitivity = 1.01
    check(abs(prefs.sensitivity - baseline - 0.000005) < 0.0000001,
          "a 0.01 sensitivity adjustment changes the internal angle by five millionths")
    prefs.look_sensitivity = 0.01
    check(abs(prefs.sensitivity - 0.000005) < 0.0000001, "very low sensitivity remains selectable")
    prefs.look_sensitivity = 100
    check(abs(prefs.sensitivity - 0.05) < 0.0000001, "high sensitivity remains selectable")
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
    check(len(addon._keymaps) == 37, "preference toggles restore bindings without duplicates")
    bpy.context.preferences.addons.remove(entry)


def configured_fly_start():
    global configured_entry
    configured_entry = bpy.context.preferences.addons.new()
    configured_entry.module = addon.__package__
    prefs = configured_entry.preferences
    prefs.fly_speed = 7
    prefs.update_rate = 240
    prefs.smoothing = 0.12
    prefs.precision_multiplier = 0.1
    prefs.wheel_factor = 1.5
    prefs.invert_y = True
    prefs.move_space = "WORLD"
    prefs.ortho_keymap = "WASD"
    prefs.ortho_zoom_speed = 2
    prefs.fov_compensation = 1
    start_fly()


def check_configured_fly():
    fly = next(iter(addon._running))
    check(abs(fly._timer.time_step - 1 / 240) < 0.000001 and fly._speed == 7
          and abs(fly._smoothing - 0.12) < 0.00001 and abs(fly._precision - 0.1) < 0.00001,
          "custom rate, speed, easing, and precision settings reach live navigation")
    forward_before = (fly._view.view_rotation @ Vector((0, 0, -1))).z
    fly._look(0, 30)
    check((fly._view.view_rotation @ Vector((0, 0, -1))).z < forward_before,
          "invert Y reverses mouse look")
    original = snapshot()
    fly._space_data.lens = 50
    fly._look(100, 0)
    reference = original[1].rotation_difference(fly._view.view_rotation).angle
    fly._view.view_location, fly._view.view_rotation = original[0], original[1]
    fly._space_data.lens = 100
    fly._look(100, 0)
    compensated = original[1].rotation_difference(fly._view.view_rotation).angle
    check(abs(compensated * 2 - reference) < 0.0001,
          "FOV compensation halves look rotation when the lens doubles from 50 to 100 mm")
    fly._view.view_location, fly._view.view_rotation = original[0], original[1]
    fly._space_data.lens = 50
    event("WHEELUPMOUSE")


def check_configured_wheel():
    check(abs(next(iter(addon._running))._speed - 10.5) < 0.0001,
          "configured wheel factor controls navigation speed changes")
    check(abs(configured_entry.preferences.fly_speed - 10.5) < 0.0001,
          "wheel speed is written back to the shared navigation setting")
    event("ESC")


def clear_configured_preferences():
    check(not addon._running, "configured navigation still cancels cleanly")
    bpy.context.preferences.addons.remove(configured_entry)


def restart_without_speed_memory():
    configured_entry.preferences.remember_speed = False
    start_fly()


def check_remembered_speed():
    check(abs(next(iter(addon._running))._speed - 10.5) < 0.0001,
          "the next navigation gesture starts at the previously remembered speed")
    event("WHEELUPMOUSE")


def check_speed_not_saved():
    check(abs(next(iter(addon._running))._speed - 15.75) < 0.0001
          and abs(configured_entry.preferences.fly_speed - 10.5) < 0.0001,
          "disabling speed memory leaves the shared setting unchanged")
    event("ESC")


def start_wasd_ortho():
    ortho()
    start_fly()


def check_wasd_pan():
    current = snapshot()
    check(current[3] == "ORTHO" and not close_to(initial[0], current[0])
          and abs(current[2] - initial[2]) < 0.0001,
          "WASD orthographic layout uses W for pan without zoom")
    event("W", "RELEASE")
    event("Q")


def check_wasd_zoom():
    check(snapshot()[3] == "ORTHO" and snapshot()[2] < initial[2],
          "WASD orthographic layout uses Q for zoom")
    event("ESC")


def finish_wasd_ortho():
    check_ortho_cancel()
    context()[1].spaces.active.region_3d.view_perspective = "PERSP"


def check_fov():
    window, area, region = context()
    space = area.spaces.active
    with bpy.context.temp_override(window=window, area=area, region=region):
        check(abs(bpy.context.window_manager.unity_view_fov - 2 * math.atan(36 / space.lens)) < 0.00001,
              "FOV field follows the native viewport lens")
        bpy.context.window_manager.unity_view_fov = math.radians(90)


def check_fov_projection():
    space = context()[1].spaces.active
    matrix = space.region_3d.window_matrix
    check(abs(space.lens - 36) < 0.0001 and abs(min(abs(matrix[0][0]), abs(matrix[1][1])) - 1) < 0.001,
          "90 degree FOV matches the rendered projection matrix")
    space.lens = 50


def paint_mode(mode):
    window, area, region = context()
    with bpy.context.temp_override(window=window, area=area, region=region):
        if mode == "WEIGHT_PAINT":
            bpy.ops.object.mode_set(mode="OBJECT")
            obj = bpy.context.active_object
            group = obj.vertex_groups.new(name="Navigation regression")
            group.add(list(range(len(obj.data.vertices))), 0.375, "REPLACE")
            group.add([0], 0.875, "REPLACE")
        elif mode == "TEXTURE_PAINT":
            bpy.ops.object.mode_set(mode="OBJECT")
            image = bpy.data.images.new("Navigation regression texture", width=8, height=8,
                                        alpha=True, float_buffer=True)
            image.pixels[:] = [((i % 4) + 1) / 4 for i in range(8 * 8 * 4)]
            material = bpy.data.materials.new("Navigation regression material")
            material.use_nodes = True
            texture = material.node_tree.nodes.new("ShaderNodeTexImage")
            texture.image = image
            material.node_tree.nodes.active = texture
            shader = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
            material.node_tree.links.new(texture.outputs["Color"], shader.inputs["Base Color"])
            bpy.context.active_object.data.materials.clear()
            bpy.context.active_object.data.materials.append(material)
        elif mode == "VERTEX_PAINT":
            bpy.ops.object.mode_set(mode="OBJECT")
            mesh = bpy.context.active_object.data
            colors = mesh.color_attributes.new(name="Navigation regression colors", type="FLOAT_COLOR", domain="CORNER")
            for i, entry in enumerate(colors.data):
                entry.color = ((i % 5) / 4, 0.25, 0.75, 1)
            mesh.color_attributes.active_color_index = len(mesh.color_attributes) - 1
        bpy.ops.object.mode_set(mode=mode)


def paint_snapshot():
    obj = bpy.context.active_object
    textures = [(node.image.name, tuple(node.image.pixels[:]))
                for slot in obj.material_slots if slot.material and slot.material.use_nodes
                for node in slot.material.node_tree.nodes if node.type == "TEX_IMAGE" and node.image]
    colors = [(attr.name, attr.domain, attr.data_type, [tuple(entry.color) for entry in attr.data])
              for attr in obj.data.color_attributes]
    return ([v.co.copy() for v in obj.data.vertices],
            [[(g.group, g.weight) for g in v.groups] for v in obj.data.vertices], textures, colors)


def start_paint_navigation():
    global original_paint_data
    original_paint_data = paint_snapshot()
    start_fly()


def check_paint_navigation(mode):
    check(bpy.context.mode == mode and len(addon._running) == 1 and not close_to(initial[0], snapshot()[0]),
          mode + " supports RMB and WASD without changing mode")
    event("ESC")


def check_paint_cancel(mode):
    check(bpy.context.mode == mode and not addon._running and close_to(initial[0], snapshot()[0])
          and paint_snapshot() == original_paint_data,
          mode + " navigation leaves mesh, weights, texture pixels, and vertex colors intact")
    # A short click must follow the native panel path without exceptions.
    event("RIGHTMOUSE")


def release_click():
    event("RIGHTMOUSE", "RELEASE")


def check_paint_click(mode):
    check(not addon._running and bpy.context.mode == mode, mode + " short click restores the native context UI")
    event("ESC")


def pose_snapshot():
    obj = bpy.context.active_object
    return ([(b.name, tuple(b.head_local), tuple(b.tail_local)) for b in obj.data.bones],
            [(b.name, tuple(tuple(row) for row in b.matrix_basis)) for b in obj.pose.bones])


def setup_pose():
    window, area, region = context()
    with bpy.context.temp_override(window=window, area=area, region=region):
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.armature_add()
        bpy.ops.object.mode_set(mode="POSE")
    bpy.context.active_object.pose.bones[0].rotation_euler.z = 0.2


def start_pose_navigation():
    global original_pose
    original_pose = pose_snapshot()
    start_fly()


def check_pose_navigation():
    check(bpy.context.mode == "POSE" and len(addon._running) == 1
          and not close_to(initial[0], snapshot()[0]), "pose mode supports RMB and WASD movement")
    event("ESC")


def check_pose_cancel():
    check(not addon._running and bpy.context.mode == "POSE"
          and close_to(initial[0], snapshot()[0]) and pose_snapshot() == original_pose,
          "pose navigation restores the view without changing bones or pose channels")
    event("RIGHTMOUSE")


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
         edit_mesh, start_fly, press_forward, check_edit_fly, object_mode,
         lambda: begin_drag("MIDDLEMOUSE"), lambda: drag("MIDDLEMOUSE"), check_pan,
         lambda: begin_drag("RIGHTMOUSE", alt=True), lambda: drag("RIGHTMOUSE", alt=True), check_zoom,
         focus, check_focus, ortho, start_fly, press_right, check_ortho_motion,
         look_ortho, check_ortho_look, check_ortho_scale, release_right, check_ortho_finish,
         start_fly, press_forward, check_ortho_zoom, check_ortho_zoom_finished,
         start_fly, press_forward, look_ortho, lambda: event("ESC"), check_ortho_cancel,
         start_fly, press_forward, disable_ortho,
         check_camera_guard, check_preferences, configured_fly_start, check_configured_fly,
         check_configured_wheel, restart_without_speed_memory, check_remembered_speed, check_speed_not_saved,
         start_wasd_ortho, press_forward, check_wasd_pan, check_wasd_zoom, finish_wasd_ortho,
         clear_configured_preferences, finish]
tasks[-1:-1] = [check_fov, check_fov_projection,
               lambda: paint_mode("SCULPT"), start_paint_navigation, press_forward,
               lambda: check_paint_navigation("SCULPT"), lambda: check_paint_cancel("SCULPT"),
               release_click, lambda: check_paint_click("SCULPT"),
               lambda: paint_mode("WEIGHT_PAINT"), start_paint_navigation, press_forward,
               lambda: check_paint_navigation("PAINT_WEIGHT"), lambda: check_paint_cancel("PAINT_WEIGHT"),
               release_click, lambda: check_paint_click("PAINT_WEIGHT"),
               lambda: paint_mode("TEXTURE_PAINT"), start_paint_navigation, press_forward,
               lambda: check_paint_navigation("PAINT_TEXTURE"), lambda: check_paint_cancel("PAINT_TEXTURE"),
               release_click, lambda: check_paint_click("PAINT_TEXTURE"),
               lambda: paint_mode("VERTEX_PAINT"), start_paint_navigation, press_forward,
               lambda: check_paint_navigation("PAINT_VERTEX"), lambda: check_paint_cancel("PAINT_VERTEX"),
               release_click, lambda: check_paint_click("PAINT_VERTEX"),
               setup_pose, start_pose_navigation, press_forward, check_pose_navigation, check_pose_cancel,
               release_click, lambda: check_paint_click("POSE"), object_mode]


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
