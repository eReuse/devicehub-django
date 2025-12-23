# `eReuse2025` Environmental Impact Algorithm

This algorithm calculates the environmental impact of devices using the eReuse2025 methodology.

## Overview

The eReuse2025 algorithm estimates the environmental impact (CO2 emissions) of electronic devices based on their actual usage patterns. It focuses on the "use phase" of the device lifecycle, calculating emissions from power consumption during active use and sleep modes.

## Key Requirements

### Power-On Hours Data

**Critical**: This algorithm requires valid power-on hours data to produce meaningful results.

- **Data Source**: Extracted from storage component evidence (e.g., "time of used" field)
- **Minimum Requirement**: `power_on_hours > 0`
- **Behavior**: If `power_on_hours = 0`, the environmental impact calculation is considered unavailable

### Data Sources

The algorithm extracts data from:

- **Storage Components**: Power-on hours from disk usage statistics
- **Device Type**: Used to determine power consumption profiles
- **Evidence**: Requires devices with inxi-based evidence (modern snapshots)

## Calculation Methodology

### Mathematical Formulation

The algorithm is based on the generic formula for environmental impact calculation:

$$U_{i}=FU_{i}\sum_{m}^{l}P_{i}\cdot t_{i}\cdot Uh_{i}$$

Where:

- $FU_{i}$: Carbon intensity factor of electricity generation
- $l$: Set of all operating modes (idle and sleep)
- $m$: Operating mode
- $P_{i}$: Power consumption of each device in each operating mode
- $t_{i}$: Percentage of the time that a user spends in each operating mode
- $Uh_{i}$: Hours in use (power-on hours)

### Simplified Implementation

For practical implementation, the formula is simplified to compute kgCO2e/year:

$$U=FU\cdot(P_{idle}+P_{sleep})=FU\cdot(KWh_{idle}\cdot Poh+KW_{sleep}\cdot T_s)$$

Where:

- $U$: Environmental impact in kgCO2/year
- $FU$: Carbon intensity factor (from Our World in Data, ISO 3166 normalized)
- $KWh_{idle}$: Power consumption in idle mode (kW)
- $Poh$: Power-on hours (from workbench data)
- $KW_{sleep}$: Power consumption in sleep mode (kW)
- $T_s$: Time in sleep mode (hours)

### Sleep Time Calculation

The sleep time is calculated using a system of two equations:

- $T_{T}=T_{S}+T_{i}$ (Total time = Sleep time + Idle time)
- $T_{S}=T_{T}\cdot P_{cts}$ (Sleep time = Total time × Sleep percentage)

Where $P_{cts}$ is the percentage in sleep mode (0.2562 from Energy Star DB).

Solving by substitution:
$$T_{T}=T_{S}+T_{i}=T_{S}+Poh=T_{T}\cdot P_{cts}+Poh$$
$$T_{T}(1-P_{cts})=Poh$$
$$T_{T}=\frac{Poh}{1-P_{cts}}$$

Therefore:
$$T_{S}=T_{T}\cdot P_{cts}=\frac{Poh}{1-P_{cts}}\cdot P_{cts}=\frac{P_{cts}}{1-P_{cts}}\cdot Poh$$

### Final Formula

The complete formula for environmental impact calculation is:

$$U=FU\cdot(KWh_{idle}\cdot Poh+KW_{sleep}\cdot\frac{P_{cts}}{1-P_{cts}}\cdot Poh)$$

### Implementation Verification

The mathematical formulation described above has been verified against the actual implementation:

**Sleep Time Calculation:**

```python
time_in_sleep_mode = (
    MEAN_PERCENTAGE_DEVICE_IS_SLEEPING * power_on_hours
) / (1 - MEAN_PERCENTAGE_DEVICE_IS_SLEEPING)
```

This correctly implements: $T_{S}=\frac{P_{cts}}{1-P_{cts}}\cdot Poh$

**Final CO2 Calculation:**

```python
kgco2e_consumption_in_use = (
    carbon_intensity_factor * (energy_kwh_idle + energy_kwh_sleeping) / 1000
)
```

This correctly implements: $U=FU\cdot(KWh_{idle}\cdot Poh+KW_{sleep}\cdot T_s)$

The implementation uses the constants defined in the algorithm and matches the mathematical formulation exactly.

### Energy Consumption

1. **Active Use**: `power_on_hours × device_watts_idle`
2. **Sleep Mode**: `sleep_hours × device_watts_sleep`
3. **Total Energy**: Sum of active and sleep consumption (kWh)

### CO2 Emissions

- **Formula**: `energy_kwh × carbon_intensity_factor / 1000`
- **Carbon Intensity**: Currently defaults to Spain (250 g CO2/kWh)
- **Result**: Annual CO2 emissions in kg CO2e

### Device Type Constants

Different device types have specific power consumption profiles:

**Idle Mode Power Consumption:**

- **Desktop**: 0.039 kW
- **Laptop**: 0.016 kW
- **Default**: 0.02 kW

**Sleep Mode Power Consumption:**

- **Desktop**: 0.0016 kW
- **Laptop**: 0.0005 kW
- **Default**: 0.001 kW

**Operating Mode Distribution:**

- **Sleep Mode Percentage**: 25.62% (from Energy Star DB)
- **Idle Mode Percentage**: 74.38%

## Implementation Notes

- **Legacy Support**: Automatically detects and handles legacy workbench data
- **Time Parsing**: Supports various time formats (e.g., "2y 7d 14h", "1095h")
- **Component Validation**: Checks multiple storage components for best data quality

## Limitations

- **Geographic Scope**: Carbon intensity currently fixed to Spain
- **Device Coverage**: Requires modern evidence with inxi data
- **Usage Patterns**: Assumes standard active/sleep ratios
- **Power Models**: Uses simplified power consumption estimates

## Future Enhancements

- Dynamic carbon intensity based on device location
- More granular device-specific power profiles
- Integration with real-time energy grid data
- Support for additional lifecycle phases (manufacturing, disposal)
