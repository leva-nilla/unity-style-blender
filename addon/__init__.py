"""Unity-style view controls, layered over Blender's existing key configuration."""

import math
import time

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty
from mathutils import Quaternion, Vector

from .motion import integrate_velocity, movement_axes
from . import radius_preview


_keymaps = []
_running = set()
_registered = False
_MODES = {
    "OBJECT", "EDIT_MESH", "POSE", "SCULPT", "PAINT_VERTEX", "PAINT_WEIGHT", "PAINT_TEXTURE",
    "EDIT_ARMATURE", "EDIT_CURVE", "EDIT_CURVES", "EDIT_SURFACE", "EDIT_TEXT",
    "EDIT_METABALL", "EDIT_LATTICE", "EDIT_POINT_CLOUD", "PARTICLE", "SCULPT_CURVES",
    "EDIT_GREASE_PENCIL", "PAINT_GREASE_PENCIL", "SCULPT_GREASE_PENCIL",
    "WEIGHT_GREASE_PENCIL", "VERTEX_GREASE_PENCIL",
}
_MODE_MAPS = ("Object Mode", "Pose")
_EXTRA_MODE_MAPS = (
    "Mesh", "Sculpt", "Weight Paint", "Image Paint", "Vertex Paint", "Armature", "Curve", "Curves",
    "Font", "Metaball", "Lattice", "Point Cloud", "Particle", "Sculpt Curves",
    "Grease Pencil Edit Mode", "Grease Pencil Paint Mode", "Grease Pencil Sculpt Mode",
    "Grease Pencil Weight Paint", "Grease Pencil Vertex Paint",
)
_EDIT_TOOL_MAPS = ("Mesh", "Armature", "Curve", "Curves", "Metaball", "Lattice", "Grease Pencil Edit Mode")
# Match each mode's native E action; Surface uses the Curve keymap too.
_EDIT_EXTRUDE_KEYS = (
    ("Mesh", "view3d.edit_mesh_extrude_move_normal"),
    ("Armature", "armature.extrude_move"),
    ("Curve", "curve.extrude_move"),
    ("Curves", "curves.extrude_move"),
    ("Grease Pencil Edit Mode", "grease_pencil.extrude_move"),
)
_EXTRUDE_MODES = {"EDIT_MESH": "Mesh", "EDIT_ARMATURE": "Armature", "EDIT_CURVE": "Curve",
                  "EDIT_SURFACE": "Curve", "EDIT_CURVES": "Curves",
                  "EDIT_GREASE_PENCIL": "Grease Pencil Edit Mode"}
_EXTRUDE_KEY_ITEMS = [("NONE", "割当なし", "押し出しボタンのみ使用")]
_EXTRUDE_KEY_ITEMS += [(chr(code), chr(code), "") for code in range(ord("A"), ord("Z") + 1)]
_EXTRUDE_KEY_ITEMS += [(f"F{i}", f"F{i}", "") for i in range(1, 13)]
_EDIT_TOOL_MODES = {"EDIT_MESH", "EDIT_ARMATURE", "EDIT_CURVE", "EDIT_CURVES", "EDIT_SURFACE",
                    "EDIT_METABALL", "EDIT_LATTICE", "EDIT_GREASE_PENCIL"}
_CONTEXT_MENUS = {
    "OBJECT": "VIEW3D_MT_object_context_menu", "EDIT_MESH": "VIEW3D_MT_edit_mesh_context_menu",
    "POSE": "VIEW3D_MT_pose_context_menu", "EDIT_ARMATURE": "VIEW3D_MT_armature_context_menu",
    "EDIT_CURVE": "VIEW3D_MT_edit_curve_context_menu", "EDIT_SURFACE": "VIEW3D_MT_edit_curve_context_menu",
    "EDIT_CURVES": "VIEW3D_MT_edit_curves_context_menu", "EDIT_TEXT": "VIEW3D_MT_edit_font_context_menu",
    "EDIT_METABALL": "VIEW3D_MT_edit_metaball_context_menu", "EDIT_LATTICE": "VIEW3D_MT_edit_lattice_context_menu",
    "PARTICLE": "VIEW3D_MT_particle_context_menu", "EDIT_GREASE_PENCIL": "VIEW3D_MT_greasepencil_edit_context_menu",
}
_PAINT_PANELS = {
    "SCULPT": "VIEW3D_PT_sculpt_context_menu",
    "PAINT_WEIGHT": "VIEW3D_PT_paint_weight_context_menu",
    "PAINT_TEXTURE": "VIEW3D_PT_paint_texture_context_menu",
    "PAINT_VERTEX": "VIEW3D_PT_paint_vertex_context_menu",
    "PAINT_GREASE_PENCIL": "VIEW3D_PT_greasepencil_draw_context_menu",
    "SCULPT_GREASE_PENCIL": "VIEW3D_PT_greasepencil_sculpt_context_menu",
    "WEIGHT_GREASE_PENCIL": "VIEW3D_PT_greasepencil_weight_context_menu",
    "VERTEX_GREASE_PENCIL": "VIEW3D_PT_greasepencil_vertex_paint_context_menu",
}


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
            _add_key(km, "view3d.unity_alt_drag", "LEFTMOUSE", {"action": "ROTATE"}, alt=True)
            _add_key(km, "view3d.move", "MIDDLEMOUSE")
            _add_key(km, "view3d.move", "MIDDLEMOUSE", alt=True)
            _add_key(km, "view3d.unity_alt_drag", "LEFTMOUSE", {"action": "MOVE"}, alt=True, ctrl=True)
            _add_key(km, "view3d.zoom", "RIGHTMOUSE", alt=True)
            _add_key(km, "view3d.unity_fly", "RIGHTMOUSE")
        for name in _EXTRA_MODE_MAPS:
            # Preserve mesh loop/ring and mode-specific Alt-LMB bone selection.
            km = kc.keymaps.new(name=name, space_type="EMPTY")
            _add_key(km, "view3d.unity_fly", "RIGHTMOUSE")
            if name == "Mesh":
                _add_key(km, "view3d.rotate", "MIDDLEMOUSE", alt=True)
    if setting(context, "object_tools", True):
        # W lives in 3D View; R lives in Object Mode. Layer over both maps.
        # Operators poll for Object Mode so edit-mode modeling is preserved.
        for name, space in (("3D View", "VIEW_3D"), ("Object Mode", "EMPTY")):
            km = kc.keymaps.new(name=name, space_type=space)
            for key, tool in (("W", "builtin.move"), ("E", "builtin.rotate"),
                              ("R", "builtin.scale")):
                _add_key(km, "view3d.unity_tool", key, {"tool": tool})
            _add_key(km, "view3d.unity_frame", "F")
    if setting(context, "edit_tools", False):
        for name in ("3D View",) + _EDIT_TOOL_MAPS:
            km = kc.keymaps.new(name=name, space_type="VIEW_3D" if name == "3D View" else "EMPTY")
            for key, tool in (("W", "builtin.move"), ("E", "builtin.rotate"), ("R", "builtin.scale")):
                _add_key(km, "view3d.unity_edit_tool", key, {"tool": tool})
        binding = _extrude_binding(preferences(context))
        if binding is not None:
            key, modifiers = binding
            for name, operator in _EDIT_EXTRUDE_KEYS:
                km = kc.keymaps.new(name=name, space_type="EMPTY")
                _add_key(km, "view3d.unity_extrude", key, **modifiers)
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


def _extrude_binding(prefs):
    key = getattr(prefs, "extrude_key", "E")
    modifiers = {name: getattr(prefs, "extrude_" + name, name == "shift")
                 for name in ("shift", "ctrl", "alt")}
    if key == "NONE" or (key in {"W", "E", "R"} and not any(modifiers.values())):
        return None
    return key, modifiers


def extrude_conflicts(context, prefs, mode=None):
    """Report overlapping effective user bindings; never modify or save them."""
    binding = _extrude_binding(prefs)
    if binding is None:
        return []
    key, modifiers = binding
    maps = {_EXTRUDE_MODES[mode]} if mode in _EXTRUDE_MODES else {name for name, op in _EDIT_EXTRUDE_KEYS}
    maps.update(("3D View", "3D View Generic", "Window", "Screen"))
    conflicts = set()
    kc = context.window_manager.keyconfigs.user
    if kc is None:
        return []
    for km in kc.keymaps:
        if km.name not in maps:
            continue
        for item in km.keymap_items:
            if (not item.active or item.idname == "view3d.unity_extrude" or item.type != key
                    or item.value not in {"PRESS", "ANY"} or item.key_modifier != "NONE"):
                continue
            if item.any or all(getattr(item, name) in {-1, int(value)} for name, value in modifiers.items()):
                if item.any or item.oskey in {-1, 0}:
                    conflicts.add((km.name, item.name))
    return sorted(conflicts)


def _draw_extrude_settings(layout, context, prefs, mode=None):
    col = layout.column()
    col.active = prefs.edit_tools
    col.prop(prefs, "extrude_key", text="代替キー")
    row = col.row(align=True)
    for name in ("shift", "ctrl", "alt"):
        row.prop(prefs, "extrude_" + name, toggle=True)
    if prefs.edit_tools and prefs.extrude_key != "NONE":
        if _extrude_binding(prefs) is None:
            col.label(text="W/E/Rには修飾キーを付けてください", icon="ERROR")
        else:
            for keymap, label in extrude_conflicts(context, prefs, mode):
                col.label(text="競合: " + label, icon="ERROR")


def _update_radius_preview(self, context):
    radius_preview.redraw()


def _get_look_sensitivity(self):
    return self.sensitivity / 0.0005


def _set_look_sensitivity(self, value):
    self.sensitivity = value * 0.0005


def _get_view_fov(self):
    # Blender 4.4 uses a 36 mm sensor and 2x viewport zoom on the fitted axis.
    space = bpy.context.space_data
    lens = space.lens if space is not None and space.type == "VIEW_3D" else 50.0
    return 2 * math.atan(36.0 / lens)


def _set_view_fov(self, value):
    space = bpy.context.space_data
    if space is not None and space.type == "VIEW_3D":
        space.lens = max(1.0, min(250.0, 36.0 / math.tan(value / 2)))


def _draw_navigation_settings(layout, prefs, space=None):
    layout.use_property_split = True
    layout.use_property_decorate = False
    col = layout.column()
    for name in ("fly_speed", "remember_speed", "look_sensitivity", "smoothing"):
        col.prop(prefs, name)
    col.prop(prefs, "move_space", expand=True)
    col.separator()
    col.prop(prefs, "ortho_keymap")
    col.prop(prefs, "ortho_zoom_speed")
    col.prop(prefs, "axis_view_perspective")
    col.separator()
    if space is not None:
        row = col.row()
        row.enabled = space.region_3d is not None and space.region_3d.view_perspective == "PERSP"
        row.prop(bpy.context.window_manager, "unity_view_fov")
    col.prop(prefs, "fov_compensation")
    box = layout.box()
    box.prop(prefs, "show_advanced", text="詳細設定", emboss=False,
             icon="TRIA_DOWN" if prefs.show_advanced else "TRIA_RIGHT")
    if prefs.show_advanced:
        for name in ("boost", "precision_multiplier", "wheel_factor", "update_rate", "invert_y"):
            box.prop(prefs, name)


def _draw_edit_tools(layout, context, prefs):
    if context.mode not in _EDIT_TOOL_MODES:
        return
    box = layout.box()
    row = box.row(align=True)
    for tool, label in (("builtin.move", "移動"), ("builtin.rotate", "回転"), ("builtin.scale", "拡縮")):
        row.operator("view3d.unity_edit_tool", text=label).tool = tool
    if context.mode in _EXTRUDE_MODES:
        row = box.row()
        row.operator_context = "INVOKE_REGION_WIN"
        row.operator("view3d.unity_extrude", text="押し出し")
    box.prop(prefs, "edit_tools")
    if context.mode in _EXTRUDE_MODES:
        _draw_extrude_settings(box, context, prefs, context.mode)
    box.prop(context.scene.transform_orientation_slots[0], "type", text="ギズモ座標")
    if context.mode != "EDIT_ARMATURE":
        settings = context.scene.tool_settings
        box.prop(settings, "use_proportional_edit", text="プロポーショナル編集")
        col = box.column()
        col.active = settings.use_proportional_edit
        col.prop(settings, "proportional_distance", text="影響半径")
        col.prop(prefs, "show_proportional_radius")
        col.prop(settings, "proportional_edit_falloff", text="減衰")
        col.prop(settings, "use_proportional_connected", text="接続のみ")
        col.prop(settings, "use_proportional_projected", text="投影")


class UnityViewPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    navigation: BoolProperty(name="Unity形式の視点操作", default=True, update=_update_keymaps)
    object_tools: BoolProperty(name="オブジェクトモードでW/E/R・Fを使用", default=True,
                               update=_update_keymaps)
    edit_tools: BoolProperty(name="編集モードでW/E/Rを使用", description="W/E/Rでギズモを切り替えます。押し出しの代替キーを下で設定できます",
                             default=False, update=_update_keymaps)
    extrude_key: EnumProperty(name="押し出しの代替キー", items=_EXTRUDE_KEY_ITEMS,
                              default="E", update=_update_keymaps)
    extrude_shift: BoolProperty(name="Shift", default=True, update=_update_keymaps)
    extrude_ctrl: BoolProperty(name="Ctrl", default=False, update=_update_keymaps)
    extrude_alt: BoolProperty(name="Alt", default=False, update=_update_keymaps)
    show_proportional_radius: BoolProperty(name="影響範囲を表示", default=True,
        description="選択点の中心に半径の目安を表示。接続・投影・複数点選択による実際の影響領域とは異なります",
        update=_update_radius_preview)
    outliner_hierarchy: BoolProperty(name="コレクション・オブジェクトの一括開閉", default=True,
                                     update=_update_keymaps)
    fly_speed: FloatProperty(name="移動速度", default=5.0, min=0.01, max=10000.0)
    remember_speed: BoolProperty(name="ホイール調整した速度を記憶", default=True)
    move_space: EnumProperty(name="移動座標", items=(("VIEW", "視点基準", "画面の向きに沿って移動"),
                                                  ("WORLD", "ワールド基準", "世界座標に沿って移動")), default="VIEW")
    ortho_keymap: EnumProperty(name="平行投影のキー配置", items=(
        ("QEAD", "QEADでパン・W/Sでズーム", "E/Qで上下、A/Dで左右、W/Sで拡大縮小"),
        ("WASD", "WASDでパン・Q/Eでズーム", "W/Sで上下、A/Dで左右、Q/Eで拡大縮小")), default="QEAD")
    ortho_zoom_speed: FloatProperty(name="平行投影ズーム倍率", default=3.0, min=0.01, max=20.0)
    axis_view_perspective: BoolProperty(name="軸方向からは透視で移動", default=True,
        description="正面・側面・上面などの軸方向平行投影では、移動や見回しを始めると透視投影へ切り替えます")
    fov_compensation: FloatProperty(name="FOV感度補正", description="0は補正なし、1は50mmより長い焦点距離で見回し感度を下げます",
                                    default=0.0, min=0.0, max=1.0, step=1)
    show_advanced: BoolProperty(name="詳細設定", default=False)
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
        col.prop(self, "edit_tools")
        _draw_extrude_settings(col, context, self)
        col.prop(self, "show_proportional_radius")
        col.prop(self, "outliner_hierarchy")
        box = self.layout.box()
        box.label(text="フライスルー")
        box.active = self.navigation
        _draw_navigation_settings(box, self)


class VIEW3D_PT_unity_view(bpy.types.Panel):
    bl_label = "Unity View Controls"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "View"
    bl_order = -10

    @classmethod
    def poll(cls, context):
        return preferences(context) is not None

    def draw(self, context):
        _draw_edit_tools(self.layout, context, preferences(context))
        _draw_navigation_settings(self.layout, preferences(context), context.space_data)


class VIEW3D_OT_unity_alt_drag(bpy.types.Operator):
    bl_idname = "view3d.unity_alt_drag"
    bl_label = "Unity形式のAltドラッグ"
    bl_options = {"INTERNAL"}

    action: EnumProperty(items=(("ROTATE", "周回", ""), ("MOVE", "平行移動", "")), default="ROTATE")

    @classmethod
    def poll(cls, context):
        # Native mesh loop/ring selection fires on CLICK; a global PRESS binding
        # would consume it before the Mesh map gets a chance to handle the click.
        return view_available(context) and context.mode != "EDIT_MESH"

    def execute(self, context):
        operator = bpy.ops.view3d.rotate if self.action == "ROTATE" else bpy.ops.view3d.move
        if not operator.poll():
            return {"CANCELLED"}
        result = operator("INVOKE_DEFAULT")
        return {"CANCELLED"} if "CANCELLED" in result else {"FINISHED"}


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


class VIEW3D_OT_unity_edit_tool(bpy.types.Operator):
    bl_idname = "view3d.unity_edit_tool"
    bl_label = "編集ギズモ切替"
    bl_options = {"INTERNAL"}

    tool: StringProperty()

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == "VIEW_3D" and context.mode in _EDIT_TOOL_MODES

    def execute(self, context):
        bpy.ops.wm.tool_set_by_id(name=self.tool)
        context.space_data.show_gizmo = True
        context.space_data.show_gizmo_tool = True
        return {"FINISHED"}


class VIEW3D_OT_unity_extrude(bpy.types.Operator):
    bl_idname = "view3d.unity_extrude"
    bl_label = "押し出し"
    bl_description = "このモードのBlender標準の押し出しを開始します"
    bl_options = {"INTERNAL"}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == "VIEW_3D" and context.mode in _EXTRUDE_MODES

    def execute(self, context):
        operator = dict(_EDIT_EXTRUDE_KEYS)[_EXTRUDE_MODES[context.mode]]
        module, name = operator.split(".")
        region = next(r for r in context.area.regions if r.type == "WINDOW")
        with context.temp_override(region=region):
            result = getattr(getattr(bpy.ops, module), name)("INVOKE_DEFAULT")
        # The native operator owns the modal transform and its Undo entry.
        return {"CANCELLED"} if "CANCELLED" in result else {"FINISHED"}


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
        self._space_data = context.space_data
        self._prefs = preferences(context)
        self._area = context.area
        self._window = context.window
        self._wm = context.window_manager
        self._start = (self._view.view_location.copy(), self._view.view_rotation.copy(),
                       self._view.view_distance, self._view.view_perspective)
        self._start_axis = self._view.is_orthographic_side_view
        self._axis_ortho = (self._start_axis and self._view.view_perspective == "ORTHO"
                            and setting(context, "axis_view_perspective", True))
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
        self._move_space = setting(context, "move_space", "VIEW")
        self._ortho_keymap = setting(context, "ortho_keymap", "QEAD")
        self._ortho_zoom_speed = setting(context, "ortho_zoom_speed", 3.0)
        self._remember_speed = setting(context, "remember_speed", True)
        self._fov_compensation = setting(context, "fov_compensation", 0.0)
        self._velocity = Vector((0, 0, 0))
        self._zoom_velocity = Vector((0, 0, 0))
        self._used = False
        self._stopped = False
        self._mode = context.mode
        self._timer = self._wm.event_timer_add(1.0 / setting(context, "update_rate", 120), window=context.window)
        self._wm.modal_handler_add(self)
        _running.add(self)
        self._area.header_text_set("Unity View · RMB: 終了  WASD: 移動  Q/E: 下降/上昇  Shift: 加速  Ctrl: 微速  Esc: 戻す")
        return {"RUNNING_MODAL"}

    def _use_navigation(self):
        self._used = True
        if self._axis_ortho:
            self._view.view_perspective = "PERSP"
            self._view.is_orthographic_side_view = False
            self._axis_ortho = False

    def _eye(self):
        return (self._view.view_location
                + self._view.view_rotation @ Vector((0, 0, self._view.view_distance)))

    def _look(self, dx, dy):
        if self._invert_y:
            dy = -dy
        if self._view.view_perspective == "PERSP":
            factor = 1 + self._fov_compensation * (min(1.0, 50.0 / self._space_data.lens) - 1)
            dx *= factor
            dy *= factor
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
        ortho = self._view.view_perspective == "ORTHO"
        right, up, forward = movement_axes(self._view.view_rotation, self._move_space, ortho)
        vertical_up, vertical_down = ("E", "Q") if not ortho or self._ortho_keymap == "QEAD" else ("W", "S")
        motion = right * (int("D" in self._keys) - int("A" in self._keys))
        motion += up * (int(vertical_up in self._keys) - int(vertical_down in self._keys))
        if not ortho:
            motion += forward * (int("W" in self._keys) - int("S" in self._keys))
        if motion.length_squared:
            # Keep diagonal movement at the same configured speed.
            motion.normalize()
        speed = self._speed * (self._boost if self._shift else 1) * (self._precision if self._ctrl else 1)
        self._velocity, displacement = integrate_velocity(self._velocity, motion * speed, seconds, self._smoothing)
        self._view.view_location += displacement
        if ortho:
            zoom_in, zoom_out = ("W", "S") if self._ortho_keymap == "QEAD" else ("Q", "E")
            zoom = (int(zoom_out in self._keys) - int(zoom_in in self._keys)) * speed * self._ortho_zoom_speed * 0.1
            self._zoom_velocity, delta = integrate_velocity(self._zoom_velocity, Vector((zoom, 0, 0)), seconds, self._smoothing)
            self._view.view_distance = max(0.001, min(1e6, self._view.view_distance * math.exp(max(-50, min(50, delta.x)))))

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
                self._view.is_orthographic_side_view = self._start_axis
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
                if self._mode in _PAINT_PANELS:
                    bpy.ops.wm.call_panel(name=_PAINT_PANELS[self._mode])
                elif self._mode in _CONTEXT_MENUS:
                    bpy.ops.wm.call_menu(name=_CONTEXT_MENUS[self._mode])
            return {"FINISHED"}
        if event.type in {"W", "A", "S", "D", "Q", "E"}:
            if event.value == "PRESS":
                self._use_navigation()
                self._keys.add(event.type)
            elif event.value == "RELEASE":
                self._keys.discard(event.type)
        elif event.type == "MOUSEMOVE":
            x, y = event.mouse_x, event.mouse_y
            dx, dy = x - self._mouse[0], y - self._mouse[1]
            self._mouse = (x, y)
            if not self._used:
                if (x - self._origin[0]) ** 2 + (y - self._origin[1]) ** 2 > 9:
                    self._use_navigation()
            if self._used:
                self._look(dx, dy)
        elif event.type in {"WHEELUPMOUSE", "WHEELDOWNMOUSE"}:
            self._use_navigation()
            factor = self._wheel_factor if event.type == "WHEELUPMOUSE" else 1 / self._wheel_factor
            self._speed = max(0.01, min(10000.0, self._speed * factor))
            if self._remember_speed and self._prefs is not None:
                self._prefs.fly_speed = self._speed
        self._area.tag_redraw()
        return {"RUNNING_MODAL"}

    def cancel(self, context):
        self.stop(restore=True)


_CLASSES = (UnityViewPreferences, VIEW3D_PT_unity_view, VIEW3D_OT_unity_alt_drag, VIEW3D_OT_unity_tool,
            VIEW3D_OT_unity_frame, VIEW3D_OT_unity_edit_tool, VIEW3D_OT_unity_extrude, VIEW3D_OT_unity_fly)


def register():
    global _registered
    if _registered:
        return
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.unity_view_fov = FloatProperty(
        name="FOV（長辺）", description="ビューポート長辺方向の画角。実カメラには適用しません",
        subtype="ANGLE", default=2 * math.atan(36 / 50),
        min=2 * math.atan(36 / 250), max=2 * math.atan(36), soft_max=math.radians(120),
        get=_get_view_fov, set=_set_view_fov)
    _registered = True
    _install_keymaps(bpy.context)
    radius_preview.register(__package__)
    # Bone/data operations draw the shared menu, including while editing an armature.
    for menu in (bpy.types.OUTLINER_MT_collection, bpy.types.OUTLINER_MT_object,
                 bpy.types.OUTLINER_MT_context_menu):
        menu.append(_draw_hierarchy)


def unregister():
    global _registered
    if not _registered:
        return
    for operator in tuple(_running):
        operator.stop(restore=True)
    _remove_keymaps()
    radius_preview.unregister()
    for menu in (bpy.types.OUTLINER_MT_collection, bpy.types.OUTLINER_MT_object,
                 bpy.types.OUTLINER_MT_context_menu):
        menu.remove(_draw_hierarchy)
    del bpy.types.WindowManager.unity_view_fov
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
    _registered = False
