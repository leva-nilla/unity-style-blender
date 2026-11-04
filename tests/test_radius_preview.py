"""Real-data regression checks for cached proportional radius centers in Blender 4.4."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import statistics
import sys
import time
import unittest

import bpy
import bmesh
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import addon
from addon import radius_preview as preview


class RadiusPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        addon.register()

    @classmethod
    def tearDownClass(cls):
        if bpy.context.object and bpy.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        addon.unregister()

    def setUp(self):
        if bpy.context.object and bpy.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        for obj in bpy.context.scene.objects:
            obj.hide_set(True)
        preview._invalidate_center()

    def context(self, *objects):
        return SimpleNamespace(objects_in_mode=objects, view_layer=bpy.context.view_layer,
                               scene=bpy.context.scene, space_data=None)

    def assertVector(self, actual, expected):
        self.assertIsNotNone(actual)
        self.assertLess((actual - Vector(expected)).length, 0.0001)

    def mesh(self, size=5, select_all=False):
        data = bpy.data.meshes.new("Radius cache fixture")
        data.from_pydata([(float(i), 0, 0) for i in range(size)], [], [])
        obj = bpy.data.objects.new("Radius cache fixture", data)
        bpy.context.scene.collection.objects.link(obj)
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        bm = bmesh.from_edit_mesh(data)
        bm.verts.ensure_lookup_table()
        for v in bm.verts:
            v.select_set(select_all)
        bm.verts[0].select_set(True)
        bm.select_history.add(bm.verts[0])
        bmesh.update_edit_mesh(data)
        bpy.context.view_layer.update()
        return obj

    def grease_pencil(self):
        bpy.ops.object.grease_pencil_add(type="STROKE")
        obj = bpy.context.object
        layer = next(layer for layer in obj.data.layers if layer.current_frame()
                     and len(layer.current_frame().drawing.attributes["position"].data))
        for item in obj.data.layers:
            item.hide = item != layer
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.grease_pencil.select_all(action="SELECT")
        bpy.context.view_layer.update()
        return obj, layer

    def test_repeated_centers_use_cache_and_return_copies(self):
        obj = self.mesh()
        context = self.context(obj)
        with patch.object(preview, "_calculate_center", wraps=preview._calculate_center) as calculate:
            center = preview.selection_center(context)
            center.x = 999
            for _ in range(100):
                self.assertVector(preview.selection_center(context), (0, 0, 0))
            self.assertEqual(calculate.call_count, 1)
            bpy.context.scene.tool_settings.proportional_distance = 3
            self.assertVector(preview.selection_center(context), (0, 0, 0))
            self.assertEqual(calculate.call_count, 1)
            obj.location.x = 4
            bpy.context.view_layer.update()
            self.assertVector(preview.selection_center(context), (4, 0, 0))

    def test_no_selection_hides_center(self):
        obj = self.mesh()
        self.assertVector(preview.selection_center(self.context(obj)), (0, 0, 0))
        bpy.ops.mesh.select_all(action="DESELECT")
        self.assertIsNone(preview.selection_center(self.context(obj)))

    def test_layer_parent_inverse_and_parent_motion(self):
        obj, layer = self.grease_pencil()
        context = self.context(obj)
        before = preview.selection_center(context)
        parent = bpy.data.objects.new("GP layer parent", None)
        bpy.context.scene.collection.objects.link(parent)
        parent.location.x = 7
        bpy.context.view_layer.update()
        layer.parent = parent
        bpy.context.view_layer.update()
        self.assertNotAlmostEqual(layer.matrix_parent_inverse.translation.x, 0)
        self.assertVector(preview.selection_center(context), before)
        parent.location.x += 10
        bpy.context.view_layer.update()
        self.assertVector(preview.selection_center(context), before + Vector((10, 0, 0)))
        obj.location.x += 20
        bpy.context.view_layer.update()
        self.assertVector(preview.selection_center(context), before + Vector((10, 0, 0)))

    def test_layer_bone_parent_follows_pose(self):
        bpy.ops.object.armature_add(enter_editmode=True)
        parent = bpy.context.object
        bone = parent.data.edit_bones[0]
        bone.head, bone.tail = (0, 0, 0), (0, 1, 0)
        bone_name = bone.name
        bpy.ops.object.mode_set(mode="OBJECT")
        obj, layer = self.grease_pencil()
        layer.parent = parent
        layer.parent_bone = bone_name
        # Blender 4.4.3 itself reports a 4-byte shutdown allocation for this binding,
        # also reproduced by the native GP bone-parent binding alone, without the addon.
        bpy.context.view_layer.update()
        context = self.context(obj)
        before = preview.selection_center(context)
        parent.pose.bones[bone_name].location.y += 3
        bpy.context.view_layer.update()
        self.assertVector(preview.selection_center(context), before + Vector((0, 3, 0)))

    def test_modern_bezier_handle_only_selection(self):
        bpy.ops.mesh.primitive_plane_add()
        bpy.ops.object.curves_empty_hair_add()
        obj = bpy.context.object
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.curves.add_bezier()
        bpy.ops.curves.select_all(action="DESELECT")
        data = obj.data
        context = self.context(obj)
        self.assertIsNone(preview.selection_center(context))
        for side in ("left", "right"):
            for name in (".selection_handle_left", ".selection_handle_right"):
                for value in data.attributes[name].data:
                    value.value = False
            data.attributes[".selection_handle_" + side].data[0].value = True
            data.update_tag()
            bpy.context.view_layer.update()
            self.assertVector(preview.selection_center(context), data.attributes["handle_" + side].data[0].vector)
        data.attributes[".selection_handle_left"].data[0].value = True
        data.update_tag()
        bpy.context.view_layer.update()
        expected = (data.attributes["handle_left"].data[0].vector + data.attributes["handle_right"].data[0].vector) / 2
        self.assertVector(preview.selection_center(context), expected)
        # Converted non-Bezier curves may retain handle attributes; they have no editable handles.
        data.attributes["curve_type"].data[0].value = (
            bpy.ops.curves.curve_type_set.get_rna_type().properties["type"].enum_items["POLY"].value)
        data.update_tag()
        bpy.context.view_layer.update()
        self.assertIsNone(preview.selection_center(context))

    def test_dense_mesh_warm_reads_do_not_scan_again(self):
        obj = self.mesh(500000, select_all=True)
        context = self.context(obj)
        with patch.object(preview, "_calculate_center", wraps=preview._calculate_center) as calculate:
            begin = time.perf_counter()
            center = preview.selection_center(context)
            cold_ms = (time.perf_counter() - begin) * 1000
            self.assertVector(center, (249999.5, 0, 0))
            timings = []
            for _ in range(20):
                begin = time.perf_counter()
                self.assertVector(preview.selection_center(context), center)
                timings.append((time.perf_counter() - begin) * 1000)
            self.assertEqual(calculate.call_count, 1)
            print("DENSE_RADIUS_CENTER", "cold_ms", round(cold_ms, 3),
                  "warm_median_ms", round(statistics.median(timings), 3), flush=True)

    def test_handler_lifecycle_is_idempotent(self):
        addon.register()
        for handlers, callback in ((bpy.app.handlers.depsgraph_update_post, preview._depsgraph_update),
                                   (bpy.app.handlers.undo_post, preview._invalidate_center),
                                   (bpy.app.handlers.redo_post, preview._invalidate_center)):
            self.assertEqual(handlers.count(callback), 1)
        preview._load_post(None)
        self.assertIsNone(preview._center_cache.key)
        addon.unregister()
        for handlers, callback in ((bpy.app.handlers.depsgraph_update_post, preview._depsgraph_update),
                                   (bpy.app.handlers.undo_post, preview._invalidate_center),
                                   (bpy.app.handlers.redo_post, preview._invalidate_center)):
            self.assertNotIn(callback, handlers)
        addon.register()


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RadiusPreviewTests))
    if not result.wasSuccessful():
        raise SystemExit(1)
