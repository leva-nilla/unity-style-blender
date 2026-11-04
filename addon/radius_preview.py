"""Read-only, view-facing guide for the native proportional editing radius."""

import math

import bmesh
import bpy
import gpu
from bpy.app.handlers import persistent
from bpy_extras.view3d_utils import location_3d_to_region_2d
from gpu_extras.batch import batch_for_shader
from mathutils import Vector


MODES = {"EDIT_MESH", "EDIT_CURVE", "EDIT_CURVES", "EDIT_SURFACE",
         "EDIT_METABALL", "EDIT_LATTICE", "EDIT_GREASE_PENCIL"}
_handler = None
_owner = object()
_package = None
_shader = None


def redraw():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def _attribute_points(data):
    position = data.attributes.get("position")
    if position is None:
        return
    selection = data.attributes.get(".selection")
    if selection is None or selection.domain == "POINT":
        for i, point in enumerate(position.data):
            if selection is None or selection.data[i].value:
                yield point.vector
    elif selection.domain == "CURVE":
        offsets = data.curve_offset_data if hasattr(data, "curve_offset_data") else data.curve_offsets
        for i, selected in enumerate(selection.data):
            if selected.value:
                for j in range(offsets[i].value, offsets[i + 1].value):
                    yield position.data[j].vector


def _local_points(obj):
    data = obj.data
    if obj.type == "MESH":
        bm = bmesh.from_edit_mesh(data)
        for vertex in bm.verts:
            if vertex.select and not vertex.hide:
                yield vertex.co
    elif obj.type in {"CURVE", "SURFACE"}:
        for spline in data.splines:
            for point in spline.bezier_points:
                if not point.hide:
                    if point.select_control_point:
                        yield point.co
                    else:
                        if point.select_left_handle:
                            yield point.handle_left
                        if point.select_right_handle:
                            yield point.handle_right
            for point in spline.points:
                if point.select and not point.hide:
                    yield point.co.xyz
    elif obj.type == "LATTICE":
        for point in data.points:
            if point.select:
                yield point.co_deform
    elif obj.type == "META":
        for element in data.elements:
            if element.select and not element.hide:
                yield element.co
    elif obj.type == "CURVES":
        yield from _attribute_points(data)
    elif obj.type == "GREASEPENCIL":
        for layer in data.layers:
            if layer.hide or layer.lock:
                continue
            frame = layer.current_frame()
            if frame:
                for point in _attribute_points(frame.drawing):
                    yield layer.matrix_local @ point


def selection_center(context):
    """Median of visible selected control points, without touching selection or pivot."""
    total = Vector((0, 0, 0))
    count = 0
    # Include linked edit objects separately: each has its own world transform.
    for obj in context.objects_in_mode:
        if not obj.visible_get(view_layer=context.view_layer, viewport=context.space_data):
            continue
        for point in _local_points(obj):
            total += obj.matrix_world @ point
            count += 1
    return total / count if count else None


def preview_circle(context):
    """Return pixel center/radius, or None when a guide should not be shown."""
    entry = context.preferences.addons.get(_package)
    if (entry is None or not entry.preferences.show_proportional_radius
            or context.mode not in MODES or context.region_data is None
            or not context.scene.tool_settings.use_proportional_edit
            or not context.space_data.overlay.show_overlays):
        return None
    # Native transforms already draw their own influence guide.
    if any(op.bl_idname.startswith("TRANSFORM_OT_") for op in context.window.modal_operators):
        return None
    center = selection_center(context)
    if center is None:
        return None
    radius = context.scene.tool_settings.proportional_distance
    right = context.region_data.view_rotation @ Vector((1, 0, 0))
    pixel = location_3d_to_region_2d(context.region, context.region_data, center)
    edge = location_3d_to_region_2d(context.region, context.region_data, center + right * radius)
    if pixel is None or edge is None:
        return None
    return pixel, (edge - pixel).length


def _draw():
    global _shader
    circle = preview_circle(bpy.context)
    if circle is None:
        return
    center, radius = circle
    vertices = [(center.x + radius * math.cos(i * math.tau / 96),
                 center.y + radius * math.sin(i * math.tau / 96), 0) for i in range(97)]
    if _shader is None:
        _shader = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
    batch = batch_for_shader(_shader, "LINE_STRIP", {"pos": vertices})
    previous_blend = gpu.state.blend_get()
    try:
        gpu.state.blend_set("ALPHA")
        _shader.bind()
        _shader.uniform_float("viewportSize", gpu.state.viewport_get()[2:])
        _shader.uniform_float("lineWidth", 1.5)
        _shader.uniform_float("color", (1.0, 0.6, 0.16, 0.9))
        batch.draw(_shader)
    finally:
        gpu.state.blend_set(previous_blend)


@persistent
def _load_post(_unused):
    # Blender clears RNA subscriptions when opening another .blend.
    bpy.msgbus.clear_by_owner(_owner)
    for name in ("proportional_distance", "use_proportional_edit"):
        bpy.msgbus.subscribe_rna(key=(bpy.types.ToolSettings, name), owner=_owner,
                                args=(), notify=redraw, options={"PERSISTENT"})
    redraw()


def register(package):
    global _handler, _package
    if _handler is not None:
        return
    _package = package
    _handler = bpy.types.SpaceView3D.draw_handler_add(_draw, (), "WINDOW", "POST_PIXEL")
    bpy.app.handlers.load_post.append(_load_post)
    _load_post(None)


def unregister():
    global _handler, _shader, _package
    bpy.msgbus.clear_by_owner(_owner)
    if _load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_load_post)
    if _handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handler, "WINDOW")
        _handler = None
    _shader = None
    _package = None
    redraw()
