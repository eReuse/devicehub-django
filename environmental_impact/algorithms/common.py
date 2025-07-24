"""
Common utility functions for environmental impact algorithms.

This module contains shared operations that can be used across different
environmental impact calculation algorithms.
"""

import os
from device.models import Device
from .docs_renderer import render_docs


def get_power_on_hours_from(device: Device) -> int:
    """
    Extract power-on hours from device evidence.

    This function attempts to retrieve the power-on hours from a device's
    storage components. It handles both legacy workbench and modern inxi-based
    evidence formats.

    Args:
        device (Device): The device object containing evidence and components

    Returns:
        int: Power-on hours, or 0 if unable to determine
    """
    try:
        if not device.last_evidence:
            return 0

        # Check if it's legacy workbench (no inxi data)
        is_legacy_workbench = (
            not hasattr(device.last_evidence, 'inxi') or
            not device.last_evidence.inxi
        )

        if is_legacy_workbench:
            return 0
        else:
            # Try to get components from device
            components = getattr(device, 'components', None)
            if components:
                # Find storage component with usage time
                storage_component = next(
                    (comp for comp in components
                     if comp.get("type") == "Storage"),
                    None
                )
                if storage_component:
                    str_time = storage_component.get("time of used", "")
                    if str_time:
                        return convert_str_time_to_hours(str_time)

            return 0  # Default if no storage found or no time data

    except Exception:
        return 0  # Default fallback for any errors


def convert_str_time_to_hours(time_str: str) -> int:
    """
    Convert a time string to total hours.

    Parses strings like "1y 2d 3h" or "245d 7h" and converts them to
    total hours. Supports years (y), days (d), and hours (h) units.

    Args:
        time_str (str): Time string in format like "1y 2d 3h"

    Returns:
        int: Total hours

    Examples:
        >>> convert_str_time_to_hours("1y 2d 3h")
        8811  # (365*24) + (2*24) + 3
        >>> convert_str_time_to_hours("245d 7h")
        5887  # (245*24) + 7
    """
    if not time_str or not time_str.strip():
        return 0

    try:
        # Define multipliers for each unit
        multipliers = {
            "y": 365 * 24,  # years to hours
            "d": 24,        # days to hours
            "h": 1          # hours to hours
        }

        total_hours = 0
        parts = time_str.strip().split()

        for part in parts:
            if not part:
                continue

            # Extract the unit (last character) and value (everything else)
            unit = part[-1].lower()
            value_str = part[:-1]

            if unit in multipliers and value_str.isdigit():
                value = int(value_str)
                total_hours += value * multipliers[unit]

        return total_hours

    except (ValueError, IndexError, AttributeError):
        # Fallback: try to extract just digits if format is unexpected
        try:
            if "hour" in time_str.lower():
                return int(''.join(filter(str.isdigit, time_str)))
            return 0
        except (ValueError, AttributeError):
            return 0


def render_algorithm_docs(docs_path: str, algorithm_dir: str,
                          fallback_text: str | None = None) -> str:
    """
    Render documentation for an algorithm from a markdown file.

    Args:
        docs_path (str): Relative path to the docs file (e.g., "docs.md")
        algorithm_dir (str): Directory path where the algorithm is located
        fallback_text (str | None): Text to return if docs file doesn't exist

    Returns:
        str: Rendered documentation content
    """
    try:
        docs_full_path = os.path.join(algorithm_dir, docs_path)
        if os.path.exists(docs_full_path):
            return render_docs(docs_full_path)
        else:
            return fallback_text or f"No documentation found at {docs_path}"
    except Exception:
        return fallback_text or "Error loading documentation"


def compute_energy_consumption_kwh(power_on_hours: int,
                                   avg_watts: float) -> float:
    """
    Compute energy consumption in kilowatt-hours.

    Args:
        power_on_hours (int): Total hours the device was powered on
        avg_watts (float): Average power consumption in watts

    Returns:
        float: Energy consumption in kWh
    """
    if power_on_hours < 0:
        return 0.0
    return (power_on_hours * avg_watts) / 1000.0


def compute_co2_emissions(energy_kwh: float, co2_per_kwh: float) -> float:
    """
    Compute CO2 emissions based on energy consumption and carbon intensity.

    Args:
        energy_kwh (float): Energy consumption in kilowatt-hours
        co2_per_kwh (float): Carbon intensity in gCO2/kWh

    Returns:
        float: CO2 emissions in grams
    """
    return energy_kwh * co2_per_kwh
