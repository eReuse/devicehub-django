# `eReuse2026` Environmental Impact Algorithm (method v0)

This algorithm estimates the climate impact (GWP100, kg CO₂e) of reusing a
computer. It follows two sources:

- **Roura Salietti (2025)**, *Reuse of ICT devices as commons*, PhD thesis, UPC,
  chapter 6: the scenario model and the use-phase formulas.
- **Recommendation ITU-T L.1410 (11/2024)**: life-cycle stages A–D and, in
  Appendix XV, the depreciation approach for refurbished goods.

It replaces `ereuse2025`, which counted only the electricity used. Counting only
electricity makes a reused device look worse the more it is used; this method
adds manufacturing, transport and the comparison with buying new.

## What it answers

| Question | Result | For whom |
|---|---|---|
| What did reuse avoid, compared with giving the second user a new computer? | `avoided = S3 − S2` | donor, refurbisher |
| What did serving the second user cost? | `cost = S2 − S1` | refurbisher, funder |
| What does the device carry now? | `attributed` (ITU App. XV) | current owner |
| What does each hour of use cost? | g CO₂e per powered-on hour | everyone |

Avoided emissions are a **contribution shared along the reuse chain**. They are
reported apart from any organisation's greenhouse-gas inventory and are never
subtracted from it.

## Lives and evidences

- **Life 1** ends at the evidence where reuse starts. Its hours are that
  evidence's disk power-on hours. Readings under 4 h count as missing (thesis
  Annex C); then the typical first life is used instead (desktop 20,998 h, laptop
  5,673 h).
- **Reuse starts** at a manual mark on an evidence; without one, a device with a
  second evidence is reused from its first evidence (intake). A device with one
  evidence and no mark is *pending*.
- **Life 2** hours are the power-on increases after the start. A span where the
  disk changed cannot be measured and is skipped. If nothing is measured, the
  thesis default applies (desktop 3,600 h over 3 years, laptop 2,880 h over 2).

## Formulas

Energy per powered-on hour, with idle power $P_i$, sleep power $P_s$ and a
sleep share $p$ of the time:

$$e = P_i + P_s \cdot \frac{p}{1-p}$$

Use phase, with grid intensity $FU_1$ (mean of the six years before intake) and
$FU_2$ (mean of the years of the second life):

$$U_1 = Uh_1 \cdot e \cdot FU_1 \qquad U_2 = Uh_2 \cdot e \cdot FU_2$$

Scenarios, with manufacturing $M$, its transport $T$, the refurbisher legs
$L$ and the recycling credit $R$:

$$S_1 = (M+T+U_1) + R + (M+T) + U_2$$
$$S_2 = (M+T+U_1) + L + U_2 + (M+T) + U_2$$
$$S_3 = (M+T+U_1) + R + 2(M+T) + 2U_2$$

so $S_3 - S_2 = M + T + R - L$ and $S_2 - S_1 = L + U_2 - R$.

Unused manufacturing share and what the current owner carries (ITU-T L.1410
App. XV, ADEME):

$$u = \max\left(0,\ 1 - \frac{Uh_1}{D_{typical}}\right) \qquad A = u \cdot M + L$$

A device without a usable life-1 reading is counted as new: $A = M + T$.

## Factor set v0

| Input | Value | Source |
|---|---|---|
| Manufacturing, desktop | A 82.9 + B 10.7 + transport 75.4 kg | ADEME Base Carbone 27003 (Licence Ouverte 2.0) |
| Manufacturing, laptop | A 120 + B 4.54 + transport 31.7 kg | ADEME Base Carbone 27002 |
| Uncertainty band | desktop 185–413 kg, laptop 132–317 kg | Boavizta p10–p90 (ODbL) |
| Power, desktop / laptop | 39 / 16 W idle, 1.6 / 0.5 W sleep, 25.62% asleep | Energy Star (as in ereuse2025) |
| Grid | per country and year | Our World in Data (CC BY 4.0) |
| Refurbisher legs | 400 km by van, 0.842 kg/t·km | thesis Table 13; Base Carbone 43735 |
| Weight, desktop / laptop | 11.3 / 3.15 kg | thesis Table 13 |
| Recycling credit | −4.5 kg (computers only) | thesis Table 13 |
| Manufacturing, smartphone / tablet | 32.8 / 63.2 kg | ADEME Base Carbone 27012 / 27007 |
| Electricity, smartphone / tablet | 7.0 / 14.75 kWh per year | Boavizta median |
| Weight, smartphone / tablet | 0.17 / 0.73 kg | Boavizta median |
| Typical first life, smartphone / tablet | 3 years | ADEME (2022), refurbished products |
| Second life, smartphone / tablet | 2 years | ITU-T L.1410 App. XV / ADEME (2022) |

### Phones and tablets

A phone has no power-on counter. DeviceHub estimates its hours from Android wear
signals (about 18 powered-on hours per battery cycle), so these hours are
**estimates** and the device page says so. For consistency, a phone's
electricity per hour is its yearly energy divided by the same 18 h a day
(6,574.5 h a year), and its lifetimes in years are converted with that figure.

For smartphones the open 2018 Base Carbone value (32.8 kg) is well below the
2025 ADEME/Arcep value (79.3 kg); the uncertainty band shows the spread. There
is no source yet for a recycling credit or refurbishment labour for phones and
tablets, so neither is counted.

The full set, with every source, is in `factors.json`.

## Not modelled in v0

- Refurbishment parts (detected disk swaps are listed, not counted).
- Packaging and cloud use.
- Newer devices drawing less power than old ones.
- Recycling as an outcome: DeviceHub does not detect it yet.
- Servers and loose components.

> This LCA result cannot be compared to the result of another LCA unless all
> assumptions and modelling choices are equal. (ITU-T L.1410, clause 10.2)
