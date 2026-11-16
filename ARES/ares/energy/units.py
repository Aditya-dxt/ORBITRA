"""Energy unit conversions and display formatting.

RULE: All internal calculations, state, and ledgers store energy strictly
in Joules (J). Watt-hours (Wh) are used exclusively for display.
1 Wh = 3600 Joules.
"""

JOULES_PER_WATT_HOUR: float = 3600.0


def joules_to_wh(joules: float) -> float:
    """Converts energy from Joules to Watt-hours (Wh) for display."""
    if joules < 0.0:
        raise ValueError(f"Energy cannot be negative: {joules} J")
    return joules / JOULES_PER_WATT_HOUR


def wh_to_joules(wh: float) -> float:
    """Converts energy from Watt-hours (Wh) to Joules."""
    if wh < 0.0:
        raise ValueError(f"Energy cannot be negative: {wh} Wh")
    return wh * JOULES_PER_WATT_HOUR


def format_energy_display(joules: float) -> str:
    """Returns a standardized display string with Joules primary and Wh secondary."""
    wh = joules_to_wh(joules)
    return f"{joules:,.1f} J ({wh:.2f} Wh)"
