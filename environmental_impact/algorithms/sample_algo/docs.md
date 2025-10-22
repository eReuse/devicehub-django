## _Sample_ Algorithm Docs

This function calculates the **carbon footprint** of a device based on its power consumption and usage time.

### 1. Define Constants
- `avg_watts = 40`: Assumed average power consumption of the device in watts.
- `co2_per_kwh = 0.475`: CO₂ emissions per kilowatt-hour (kg CO₂/kWh), based on an estimated energy mix.

### 2. Retrieve Device Usage
- Calls `get_poh_from_device(device)`, which returns the total **power-on hours** for the device.

### 3. Compute Energy Consumption
- Converts power consumption to **kilowatt-hours (kWh)** using:
  ```
  energy_kwh = (power_on_hours * avg_watts) / 1000
  ```
- This accounts for the total energy used over the recorded operational period.

### 4. Calculate CO₂ Emissions
- Multiplies the **energy consumption (kWh)** by the **CO₂ emission factor**:
  ```
  co2_emissions = energy_kwh * co2_per_kwh
  ```
- This provides the estimated **CO₂ emissions in kilograms**.
