"""Run with Blender --background --factory-startup --python-exit-code 1 --python ..."""

from pathlib import Path
import sys
import unittest

from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from addon.motion import integrate_velocity


class VelocityTests(unittest.TestCase):
    def test_response_is_independent_of_update_frequency(self):
        def travel(rate):
            velocity = Vector((0, 0, 0))
            position = Vector((0, 0, 0))
            # Start, change direction, then release keys.
            for target in (Vector((0, 0, -5)), Vector((5, 0, 0)), Vector((0, 0, 0))):
                for _ in range(rate):
                    velocity, delta = integrate_velocity(velocity, target, 1 / rate, 0.06)
                    position += delta
            return velocity, position

        reference_velocity, reference_position = travel(30)
        for rate in (60, 120, 240):
            velocity, position = travel(rate)
            self.assertLess((velocity - reference_velocity).length, 0.0001)
            self.assertLess((position - reference_position).length, 0.0001)

    def test_acceleration_starts_gently(self):
        velocity, delta = integrate_velocity(Vector((0, 0, 0)), Vector((5, 0, 0)), 1 / 120, 0.06)
        self.assertGreater(velocity.x, 0)
        self.assertLess(velocity.x, 5)
        self.assertGreater(delta.x, 0)
        self.assertLess(delta.x, 5 / 120)

    def test_release_slows_to_rest_without_reversing(self):
        velocity = Vector((5, 0, 0))
        for _ in range(120):
            new_velocity, delta = integrate_velocity(velocity, Vector((0, 0, 0)), 1 / 120, 0.06)
            self.assertGreaterEqual(delta.x, 0)
            self.assertLess(new_velocity.x, velocity.x)
            velocity = new_velocity
        self.assertLess(velocity.length, 0.00001)

    def test_zero_smoothing_is_immediate(self):
        target = Vector((0, 0, -5))
        velocity, delta = integrate_velocity(Vector((5, 0, 0)), target, 0.01, 0)
        self.assertEqual(velocity, target)
        self.assertLess((delta - Vector((0, 0, -0.05))).length, 0.000001)

    def test_higher_rate_produces_smaller_steps(self):
        target = Vector((5, 0, 0))
        _, slow = integrate_velocity(target, target, 1 / 60, 0.06)
        _, fast = integrate_velocity(target, target, 1 / 120, 0.06)
        self.assertAlmostEqual(fast.x * 2, slow.x, places=6)


result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(VelocityTests))
if not result.wasSuccessful():
    raise RuntimeError("Velocity integration tests failed")
