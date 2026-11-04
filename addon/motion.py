"""Time-based velocity response shared by flythrough updates."""

import math


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
