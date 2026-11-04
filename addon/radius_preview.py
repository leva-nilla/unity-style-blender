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
_BEZIER_TYPE = bpy.ops.curves.curve_type_set.get_rna_type().properties["type"].enum_items["BEZIER"].value


def redraw():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def _attribute_points(data, *, include_handles=False):
    position = data.attributes.get("position")
    if position is None:
        return
    selection = data.attributes.get(".selection")
    if include_handles:
        offsets = data.curve_offset_data
        curve_types = data.attributes.get("curve_type")
        handles = [(data.attributes.get("handle_" + side),
                    data.attributes.get(".selection_handle_" + side)) for side in ("left", "right")]

        def selected(attribute, point, curve):
            if attribute is None:
                return True  # Blender's missing selection attributes mean "all selected".
            return attribute.data[point if attribute.domain == "POINT" else curve].value

        for curve in range(len(offsets) - 1):
            for point in range(offsets[curve].value, offsets[curve + 1].value):
                if selected(selection, point, curve):
                    yield position.data[point].vector
                elif curve_types is not None and curve_types.data[curve].value == _BEZIER_TYPE:
                    for coordinates, handle_selection in handles:
                        if coordinates is not None and selected(handle_selection, point, curve):
                            yield coordinates.data[point].vector
        return
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
        if data.total_vert_sel == 0:
            return
        active = bm.select_history.active
        if data.total_vert_sel == 1 and isinstance(active, bmesh.types.BMVert) and active.select and not active.hide:
            yield active.co
            return
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
        yield from _attribute_points(data, include_handles=True)


def _layer_to_world(obj, layer):
    """Match Blender 4.4's Layer::to_world_space(), including bone parenting."""
    parent = layer.parent
    if parent is None:
        return obj.matrix_world @ layer.matrix_local
    matrix = parent.matrix_world
    if parent.type == "ARMATURE" and layer.parent_bone:
        bone = parent.pose.bones.get(layer.parent_bone)
        if bone is not None:
            matrix = matrix @ bone.matrix
    return matrix @ layer.matrix_parent_inverse @ layer.matrix_local


def _point_groups(obj):
    if obj.type == "GREASEPENCIL":
        data = obj.data
        for layer in data.layers:
            if layer.hide or layer.lock:
                continue
            frame = layer.current_frame()
            if frame:
                yield _layer_to_world(obj, layer), _attribute_points(frame.drawing)
    else:
        yield obj.matrix_world, _local_points(obj)


def _calculate_center(objects):
    total = [0.0, 0.0, 0.0]
    count = 0
    for obj in objects:
        for matrix, points in _point_groups(obj):
            # Python floats avoid accumulating hundreds of thousands of float32 roundoff errors.
            x = y = z = 0.0
            local_count = 0
            for point in points:
                x += point.x
                y += point.y
                z += point.z
                local_count += 1
            if local_count:
                # An affine transform needs applying only once per group, not per vertex.
                center = matrix @ Vector((x / local_count, y / local_count, z / local_count))
                for axis in range(3):
                    total[axis] += center[axis] * local_count
                count += local_count
    return Vector([value / count for value in total]) if count else None


def _matrix_key(matrix):
    return tuple(value for row in matrix for value in row)


def _object_key(obj):
    key = (obj.as_pointer(), obj.data.as_pointer(), obj.mode, _matrix_key(obj.matrix_world))
    if obj.type == "MESH":
        # Native BMesh counters are O(1); never scan vertices to validate the cache.
        key += (obj.data.total_vert_sel, obj.data.total_edge_sel, obj.data.total_face_sel)
    elif obj.type == "GREASEPENCIL":
        key += (tuple((layer.as_pointer(), layer.hide, layer.lock,
                       layer.current_frame().as_pointer() if layer.current_frame() else None,
                       _matrix_key(_layer_to_world(obj, layer))) for layer in obj.data.layers),)
    return key


class _SelectionCache:
    def __init__(self):
        self.clear()

    def clear(self):
        self.key = None
        self.value = None
        self.ids = set()

    def center(self, context):
        # Linked edit objects each contribute with their own world transform.
        objects = [obj for obj in context.objects_in_mode
                   if obj.visible_get(view_layer=context.view_layer, viewport=context.space_data)]
        scene = getattr(context, "scene", None)
        key = (scene.as_pointer() if scene else None, tuple(_object_key(obj) for obj in objects))
        if key != self.key:
            self.value = _calculate_center(objects)
            self.key = key
            self.ids = {item.as_pointer() for obj in objects for item in (obj, obj.data)}
            for obj in objects:
                if obj.type == "GREASEPENCIL":
                    for layer in obj.data.layers:
                        if layer.parent:
                            self.ids.add(layer.parent.as_pointer())
                            if layer.parent.data:
                                self.ids.add(layer.parent.data.as_pointer())
        return self.value.copy() if self.value is not None else None


_center_cache = _SelectionCache()


def selection_center(context):
    """Cached median of visible selected points; preserve geometry, selection, and pivot."""
    return _center_cache.center(context)


@persistent
def _invalidate_center(*_args):
    _center_cache.clear()


@persistent
def _depsgraph_update(_scene, depsgraph):
    # Selection-only updates have both is_updated_geometry/transform false.
    # Inspect the IDs themselves so replacing a selection with the same count works.
    if _center_cache.ids and any(update.id.original.as_pointer() in _center_cache.ids for update in depsgraph.updates):
        _center_cache.clear()


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
    _center_cache.clear()
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
    bpy.app.handlers.depsgraph_update_post.append(_depsgraph_update)
    bpy.app.handlers.undo_post.append(_invalidate_center)
    bpy.app.handlers.redo_post.append(_invalidate_center)
    _load_post(None)


def unregister():
    global _handler, _shader, _package
    bpy.msgbus.clear_by_owner(_owner)
    if _load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_load_post)
    for handlers, callback in ((bpy.app.handlers.depsgraph_update_post, _depsgraph_update),
                               (bpy.app.handlers.undo_post, _invalidate_center),
                               (bpy.app.handlers.redo_post, _invalidate_center)):
        if callback in handlers:
            handlers.remove(callback)
    if _handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handler, "WINDOW")
        _handler = None
    _shader = None
    _package = None
    _center_cache.clear()
    redraw()
