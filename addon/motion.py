"""Time-based velocity response shared by flythrough updates."""

import math

from mathutils import Vector


def movement_axes(rotation, space, orthographic=False):
    """Return view axes, or world axes with orthographic pan snapped to a plane."""
    right = rotation @ Vector((1, 0, 0))
    up = rotation @ Vector((0, 1, 0))
    forward = rotation @ Vector((0, 0, -1))
    if space == "VIEW":
        return right, up, forward
    world_up = Vector((0, 0, 1))
    if orthographic:
        axes = [Vector((1, 0, 0)), Vector((0, 1, 0)), world_up]
        normal = max(range(3), key=lambda i: abs(axes[i].dot(forward)))
        planar = [axis for i, axis in enumerate(axes) if i != normal]
        right_index = max(range(2), key=lambda i: abs(planar[i].dot(right)))
        world_right, world_screen_up = planar[right_index], planar[1 - right_index]
        if world_right.dot(right) < 0:
            world_right = -world_right
        if world_screen_up.dot(up) < 0:
            world_screen_up = -world_screen_up
        return world_right, world_screen_up, forward
    horizontal = Vector((forward.x, forward.y, 0))
    if horizontal.length_squared < 1e-10:
        horizontal = world_up.cross(right)
    horizontal.normalize()
    return horizontal.cross(world_up).normalized(), world_up, horizontal


def integrate_velocity(velocity, target, seconds, response_time):
    """Return end velocity and exact displacement for a constant target velocity."""
    if response_time <= 0:
        return target.copy(), target * seconds
    # Integrate the exponential response exactly: splitting an interval does not
    # change the traveled distance or acceleration when the target stays fixed.
    blend = -math.expm1(-seconds / response_time)
    difference = velocity - target
    displacement = target * seconds + difference * (response_time * blend)
    return velocity - difference * blend, displacement
