"""Unity-style view controls, layered over Blender's existing key configuration."""

import math
import time

import bpy
from bpy.props import BoolProperty, FloatProperty, StringProperty
from mathutils import Quaternion, Vector


_keymaps = []
_running = set()
_registered = False
_MODES = {"OBJECT", "EDIT_MESH", "POSE"}
_MODE_MAPS = ("Object Mode", "Mesh", "Pose")


def preferences(context):
    entry = context.preferences.addons.get(__package__)
    return entry.preferences if entry else None


def setting(context, name, default):
    prefs = preferences(context)
    return getattr(prefs, name, default)


def view_available(context):
    return (context.area is not None and context.area.type == "VIEW_3D"
            and context.region is not None and context.region.type == "WINDOW"
            and context.mode in _MODES and context.region_data is not None)


def _remove_keymaps():
    for km, item in reversed(_keymaps):
        km.keymap_items.remove(item)
    _keymaps.clear()


def _add_key(km, operator, key, properties=None, **modifiers):
    item = km.keymap_items.new(operator, key, "PRESS", head=True, **modifiers)
    for name, value in (properties or {}).items():
        setattr(item.properties, name, value)
    _keymaps.append((km, item))


def _install_keymaps(context):
    _remove_keymaps()
    kc = context.window_manager.keyconfigs.addon
    if kc is None:
        return
    if setting(context, "navigation", True):
        # Mode maps are considered before the general 3D View map (e.g. mesh loop select).
        for name in ("3D View",) + _MODE_MAPS:
            km = kc.keymaps.new(name=name, space_type="VIEW_3D" if name == "3D View" else "EMPTY")
            _add_key(km, "view3d.rotate", "LEFTMOUSE", alt=True)
            _add_key(km, "view3d.move", "MIDDLEMOUSE")
            _add_key(km, "view3d.move", "MIDDLEMOUSE", alt=True)
            _add_key(km, "view3d.move", "LEFTMOUSE", alt=True, ctrl=True)
            _add_key(km, "view3d.zoom", "RIGHTMOUSE", alt=True)
            _add_key(km, "view3d.unity_fly", "RIGHTMOUSE")
    if setting(context, "object_tools", True):
        # W lives in 3D View; R lives in Object Mode. Layer over both maps.
        # Operators poll for Object Mode so edit-mode modeling is preserved.
        for name, space in (("3D View", "VIEW_3D"), ("Object Mode", "EMPTY")):
            km = kc.keymaps.new(name=name, space_type=space)
            for key, tool in (("W", "builtin.move"), ("E", "builtin.rotate"),
                              ("R", "builtin.scale")):
                _add_key(km, "view3d.unity_tool", key, {"tool": tool})
            _add_key(km, "view3d.unity_frame", "F")


def _update_keymaps(self, context):
    if _registered:
        for operator in tuple(_running):
            operator.stop(restore=True)
        _install_keymaps(context)


class UnityViewPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    navigation: BoolProperty(name="Unity形式の視点操作", default=True, update=_update_keymaps)
    object_tools: BoolProperty(name="オブジェクトモードでW/E/R・Fを使用", default=True,
                               update=_update_keymaps)
    fly_speed: FloatProperty(name="移動速度", default=5.0, min=0.01, max=10000.0)
    sensitivity: FloatProperty(name="見回し感度", default=0.003, min=0.0001, max=0.03,
                               precision=4)
    boost: FloatProperty(name="Shiftの速度倍率", default=4.0, min=1.0, max=20.0)

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "navigation")
        col.prop(self, "object_tools")
        col.prop(self, "fly_speed")
        col.prop(self, "sensitivity")
        col.prop(self, "boost")


class VIEW3D_OT_unity_tool(bpy.types.Operator):
    bl_idname = "view3d.unity_tool"
    bl_label = "Unity形式のツール切替"
    bl_options = {"INTERNAL"}

    tool: StringProperty()

    @classmethod
    def poll(cls, context):
        return view_available(context) and context.mode == "OBJECT"

    def execute(self, context):
        bpy.ops.wm.tool_set_by_id(name=self.tool)
        context.space_data.show_gizmo = True
        context.space_data.show_gizmo_tool = True
        return {"FINISHED"}


class VIEW3D_OT_unity_frame(bpy.types.Operator):
    bl_idname = "view3d.unity_frame"
    bl_label = "選択物へフォーカス"
    bl_options = {"INTERNAL"}

    @classmethod
    def poll(cls, context):
        return view_available(context) and context.mode == "OBJECT" and bool(context.selected_objects)

    def execute(self, context):
        return bpy.ops.view3d.view_selected("INVOKE_DEFAULT", use_all_regions=False)


class VIEW3D_OT_unity_fly(bpy.types.Operator):
    bl_idname = "view3d.unity_fly"
    bl_label = "Unity形式の見回し・移動"
    bl_description = "右ボタン保持で見回し、WASD/QEで移動。Escで視点を戻す"
    bl_options = {"INTERNAL", "BLOCKING", "GRAB_CURSOR"}

    @classmethod
    def poll(cls, context):
        return (view_available(context) and context.region_data.view_perspective != "CAMERA"
                and not context.region_data.lock_rotation)

    def invoke(self, context, event):
        self._view = context.region_data
        self._area = context.area
        self._window = context.window
        self._wm = context.window_manager
        self._start = (self._view.view_location.copy(), self._view.view_rotation.copy(),
                       self._view.view_distance, self._view.view_perspective)
        self._mouse = (event.mouse_x, event.mouse_y)
        self._origin = self._mouse
        self._last = time.perf_counter()
        self._keys = set()
        self._shift = event.shift
        self._speed = setting(context, "fly_speed", 5.0)
        self._sensitivity = setting(context, "sensitivity", 0.003)
        self._boost = setting(context, "boost", 4.0)
        self._used = False
        self._stopped = False
        self._mode = context.mode
        self._timer = self._wm.event_timer_add(1.0 / 60.0, window=context.window)
        self._wm.modal_handler_add(self)
        _running.add(self)
        self._area.header_text_set("Unity View · RMB: 終了  WASD: 移動  Q/E: 下降/上昇  Shift: 加速  Esc: 戻す")
        return {"RUNNING_MODAL"}

    def _eye(self):
        return (self._view.view_location
                + self._view.view_rotation @ Vector((0, 0, self._view.view_distance)))

    def _look(self, dx, dy):
        eye = self._eye()
        rotation = self._view.view_rotation
        yaw = Quaternion((0, 0, 1), -dx * self._sensitivity)
        forward = rotation @ Vector((0, 0, -1))
        elevation = math.asin(max(-1.0, min(1.0, forward.z)))
        target = max(-math.radians(89), min(math.radians(89), elevation + dy * self._sensitivity))
        pitch = Quaternion((1, 0, 0), target - elevation)
        self._view.view_rotation = yaw @ rotation @ pitch
        self._view.view_location = (eye - self._view.view_rotation
                                   @ Vector((0, 0, self._view.view_distance)))

    def _step(self, seconds):
        local = Vector((int("D" in self._keys) - int("A" in self._keys), 0,
                        int("S" in self._keys) - int("W" in self._keys)))
        motion = self._view.view_rotation @ local
        motion.z += int("E" in self._keys) - int("Q" in self._keys)
        if motion.length_squared:
            # The same speed on diagonals; Q/E use Blender world-up (Z).
            motion.normalize()
            self._view.view_location += motion * self._speed * seconds * (self._boost if self._shift else 1)

    def _perspective(self):
        if self._view.view_perspective == "ORTHO":
            self._view.view_perspective = "PERSP"

    def stop(self, restore=False):
        if self._stopped:
            return
        self._stopped = True
        if self._timer is not None:
            self._wm.event_timer_remove(self._timer)
            self._timer = None
        try:
            if restore:
                location, rotation, distance, perspective = self._start
                self._view.view_location = location
                self._view.view_rotation = rotation
                self._view.view_distance = distance
                self._view.view_perspective = perspective
            self._area.header_text_set(None)
            self._area.tag_redraw()
        except ReferenceError:
            pass  # Window/area closed during the gesture.
        _running.discard(self)

    def modal(self, context, event):
        if self._stopped:
            return {"CANCELLED"}
        if (event.type in {"ESC", "WINDOW_DEACTIVATE"} or context.area != self._area
                or context.mode != self._mode):
            self.stop(restore=True)
            return {"CANCELLED"}
        self._shift = event.shift
        if event.type == "RIGHTMOUSE" and event.value == "RELEASE":
            self.stop()
            if not self._used:
                menu = {"OBJECT": "VIEW3D_MT_object_context_menu",
                        "EDIT_MESH": "VIEW3D_MT_edit_mesh_context_menu",
                        "POSE": "VIEW3D_MT_pose_context_menu"}[self._mode]
                bpy.ops.wm.call_menu(name=menu)
            return {"FINISHED"}
        if event.type in {"W", "A", "S", "D", "Q", "E"}:
            if event.value == "PRESS":
                self._keys.add(event.type)
                self._used = True
                self._perspective()
            elif event.value == "RELEASE":
                self._keys.discard(event.type)
        elif event.type == "MOUSEMOVE":
            x, y = event.mouse_x, event.mouse_y
            dx, dy = x - self._mouse[0], y - self._mouse[1]
            self._mouse = (x, y)
            if not self._used:
                self._used = (x - self._origin[0]) ** 2 + (y - self._origin[1]) ** 2 > 9
            if self._used:
                self._perspective()
                self._look(dx, dy)
        elif event.type in {"WHEELUPMOUSE", "WHEELDOWNMOUSE"}:
            self._speed = max(0.01, min(10000.0, self._speed * (1.2 if event.type == "WHEELUPMOUSE" else 1 / 1.2)))
            self._used = True
        elif event.type == "TIMER":
            now = time.perf_counter()
            self._step(max(0.0, min(0.1, now - self._last)))
            self._last = now
        self._area.tag_redraw()
        return {"RUNNING_MODAL"}

    def cancel(self, context):
        self.stop(restore=True)


_CLASSES = (UnityViewPreferences, VIEW3D_OT_unity_tool, VIEW3D_OT_unity_frame, VIEW3D_OT_unity_fly)


def register():
    global _registered
    if _registered:
        return
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    _registered = True
    _install_keymaps(bpy.context)


def unregister():
    global _registered
    if not _registered:
        return
    for operator in tuple(_running):
        operator.stop(restore=True)
    _remove_keymaps()
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
    _registered = False
