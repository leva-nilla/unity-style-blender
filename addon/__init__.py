"""Unity-style view controls, layered over Blender's existing key configuration."""

import math
import time

import bpy
from bpy.props import BoolProperty, FloatProperty, IntProperty, StringProperty
from mathutils import Quaternion, Vector

from .motion import integrate_velocity


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


def _add_key(km, operator, key, properties=None, *, value="PRESS", **modifiers):
    item = km.keymap_items.new(operator, key, value, head=True, **modifiers)
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
    if setting(context, "outliner_hierarchy", True):
        km = kc.keymaps.new(name="Outliner", space_type="OUTLINER")
        _add_key(km, "outliner.item_openclose", "LEFTMOUSE", {"all": True},
                 value="CLICK", alt=True)


def _draw_hierarchy(self, context):
    if not setting(context, "outliner_hierarchy", True):
        return
    self.layout.separator()
    col = self.layout.column()
    # select_walk is invoke-only; run against the Outliner window region rather than the menu.
    col.operator_context = "INVOKE_REGION_WIN"
    for direction, text, icon in (("RIGHT", "子をすべて展開", "DISCLOSURE_TRI_DOWN"),
                                  ("LEFT", "子をすべて折りたたみ", "DISCLOSURE_TRI_RIGHT")):
        op = col.operator("outliner.select_walk", text=text, icon=icon)
        op.direction = direction
        op.toggle_all = True


def _update_keymaps(self, context):
    if _registered:
        for operator in tuple(_running):
            operator.stop(restore=True)
        _install_keymaps(context)


def _get_look_sensitivity(self):
    return self.sensitivity / 0.0005


def _set_look_sensitivity(self, value):
    self.sensitivity = value * 0.0005


class UnityViewPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    navigation: BoolProperty(name="Unity形式の視点操作", default=True, update=_update_keymaps)
    object_tools: BoolProperty(name="オブジェクトモードでW/E/R・Fを使用", default=True,
                               update=_update_keymaps)
    outliner_hierarchy: BoolProperty(name="コレクション・オブジェクトの一括開閉", default=True,
                                     update=_update_keymaps)
    fly_speed: FloatProperty(name="移動速度", default=5.0, min=0.01, max=10000.0)
    # Keep the stored radians/pixel value compatible with earlier releases.
    # The UI uses a multiplier so Blender's minimum drag step (0.01) is useful.
    sensitivity: FloatProperty(default=0.00175, min=0.000001, max=0.05, options={"HIDDEN"})
    look_sensitivity: FloatProperty(name="見回し感度", description="1.0を基準とした倍率。Shiftを押しながらドラッグすると微調整できます",
                                    default=3.5, min=0.002, max=100.0, soft_min=0.01, soft_max=10.0,
                                    step=1, precision=3, get=_get_look_sensitivity, set=_set_look_sensitivity)
    boost: FloatProperty(name="Shiftの速度倍率", default=4.0, min=1.0, max=20.0)
    precision_multiplier: FloatProperty(name="Ctrlの微速倍率", default=0.25, min=0.01, max=1.0)
    wheel_factor: FloatProperty(name="ホイールの速度倍率", default=1.2, min=1.01, max=3.0)
    update_rate: IntProperty(name="更新頻度 (Hz)", description="移動更新の要求頻度。実際の描画頻度はシーンの負荷によります",
                             default=120, min=30, max=240)
    smoothing: FloatProperty(name="移動の滑らかさ (秒)", description="加減速の応答時間。0で即座に速度を切り替えます",
                              default=0.06, min=0.0, max=0.5, precision=3)
    invert_y: BoolProperty(name="見回しの上下を反転", default=False)

    def draw(self, context):
        self.layout.use_property_split = True
        self.layout.use_property_decorate = False
        col = self.layout.box().column()
        col.label(text="操作")
        col.prop(self, "navigation")
        col.prop(self, "object_tools")
        col.prop(self, "outliner_hierarchy")
        col = self.layout.box().column()
        col.label(text="フライスルー")
        col.active = self.navigation
        for name in ("fly_speed", "look_sensitivity", "boost", "precision_multiplier",
                     "wheel_factor", "update_rate", "smoothing", "invert_y"):
            col.prop(self, name)


class VIEW3D_PT_unity_view(bpy.types.Panel):
    bl_label = "Unity View Controls"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "View"
    bl_parent_id = "VIEW3D_PT_view3d_properties"

    @classmethod
    def poll(cls, context):
        return preferences(context) is not None

    def draw(self, context):
        self.layout.use_property_split = True
        self.layout.use_property_decorate = False
        self.layout.prop(preferences(context), "look_sensitivity")


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
        self._ctrl = event.ctrl
        self._speed = setting(context, "fly_speed", 5.0)
        self._sensitivity = setting(context, "sensitivity", 0.00175)
        self._boost = setting(context, "boost", 4.0)
        self._precision = setting(context, "precision_multiplier", 0.25)
        self._wheel_factor = setting(context, "wheel_factor", 1.2)
        self._smoothing = setting(context, "smoothing", 0.06)
        self._invert_y = setting(context, "invert_y", False)
        self._velocity = Vector((0, 0, 0))
        self._used = False
        self._stopped = False
        self._mode = context.mode
        self._timer = self._wm.event_timer_add(1.0 / setting(context, "update_rate", 120), window=context.window)
        self._wm.modal_handler_add(self)
        _running.add(self)
        self._area.header_text_set("Unity View · RMB: 終了  WASD: 移動  Q/E: 下降/上昇  Shift: 加速  Ctrl: 微速  Esc: 戻す")
        return {"RUNNING_MODAL"}

    def _eye(self):
        return (self._view.view_location
                + self._view.view_rotation @ Vector((0, 0, self._view.view_distance)))

    def _look(self, dx, dy):
        if self._invert_y:
            dy = -dy
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
        speed = self._speed * (self._boost if self._shift else 1) * (self._precision if self._ctrl else 1)
        self._velocity, displacement = integrate_velocity(self._velocity, motion * speed, seconds, self._smoothing)
        self._view.view_location += displacement

    def _advance(self):
        now = time.perf_counter()
        self._step(max(0.0, min(0.1, now - self._last)))
        self._last = now

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
        # Account for the elapsed time using the previous keys/rotation/speed,
        # then apply the new input. This avoids quantizing taps to timer ticks.
        self._advance()
        self._shift = event.shift
        self._ctrl = event.ctrl
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
            elif event.value == "RELEASE":
                self._keys.discard(event.type)
        elif event.type == "MOUSEMOVE":
            x, y = event.mouse_x, event.mouse_y
            dx, dy = x - self._mouse[0], y - self._mouse[1]
            self._mouse = (x, y)
            if not self._used:
                self._used = (x - self._origin[0]) ** 2 + (y - self._origin[1]) ** 2 > 9
            if self._used:
                self._look(dx, dy)
        elif event.type in {"WHEELUPMOUSE", "WHEELDOWNMOUSE"}:
            factor = self._wheel_factor if event.type == "WHEELUPMOUSE" else 1 / self._wheel_factor
            self._speed = max(0.01, min(10000.0, self._speed * factor))
            self._used = True
        self._area.tag_redraw()
        return {"RUNNING_MODAL"}

    def cancel(self, context):
        self.stop(restore=True)


_CLASSES = (UnityViewPreferences, VIEW3D_PT_unity_view, VIEW3D_OT_unity_tool,
            VIEW3D_OT_unity_frame, VIEW3D_OT_unity_fly)


def register():
    global _registered
    if _registered:
        return
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    _registered = True
    _install_keymaps(bpy.context)
    for menu in (bpy.types.OUTLINER_MT_collection, bpy.types.OUTLINER_MT_object):
        menu.append(_draw_hierarchy)


def unregister():
    global _registered
    if not _registered:
        return
    for operator in tuple(_running):
        operator.stop(restore=True)
    _remove_keymaps()
    for menu in (bpy.types.OUTLINER_MT_collection, bpy.types.OUTLINER_MT_object):
        menu.remove(_draw_hierarchy)
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
    _registered = False
