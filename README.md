# Offshore wind-to-hydrogen supply chain model for the Dutch North Sea

Hourly techno-economic model that computes the levelised cost of hydrogen (LCOH) for three
offshore wind-to-hydrogen supply chain configurations delivering a continuous hydrogen baseload
to a Dutch industrial port: offshore decentral electrolysis (at each turbine), offshore central
electrolysis (on an energy island) and onshore central electrolysis. The model accompanies the
paper listed under *Citation* and reproduces every number in its results section.

## Citation

If you use this model, please cite the accompanying paper:

> D.L. Breedijk, L.S.F. Frowijn. *Offshore wind-based green hydrogen supply chains comparison for
> the Dutch North Sea region: Combining stakeholder-preference and techno-economic analysis.*
> International Journal of Hydrogen Energy (submitted, 2026).

and the archived source code: `https://doi.org/10.5281/zenodo.XXXXXXX` (DOI is minted on the
first GitHub release; see *Archiving*). A machine-readable citation is in `CITATION.cff`;
GitHub shows it under *Cite this repository*.

## License

MIT, see `LICENSE`. The KNMI wind data in this repository are redistributed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), copyright KNMI.

## Model overview

The model simulates 30 years of hourly operation (two measured wind years, 2021 and 2022,
repeated 15 times) for a 10 GW offshore wind cluster of 665 NREL 15 MW turbines, 250 km from
shore. Per configuration it covers:

- wind speed to hub height (log law to 60 m, power law to 150 m) and turbine power curve
- electrical losses per conversion step, HVAC/HVDC cable and inter-array cable
- electrolyser dispatch with a lower load range, balance-of-plant load and optional battery
- pipeline pressure drop per km and the compressor power needed to reach the inlet pressure
- salt cavern sizing for a constant baseload equal to the mean production (cyclic storage)
- CAPEX and OPEX per component, escalated to EUR2025, annualised with a system-level CRF (30 a, 8 %)
- electrolyser capacity sweep (11 to 15 MW per turbine), sensitivity analysis (±10 %) and
  scenario analysis (Tables 9 to 12 of the paper)

All parameters are documented in Tables 2, F.7 and F.8 of the paper and in `default_params()`
in `w2h_model.py`.

## Requirements and installation

Python 3.10 or later with `numpy`, `pandas` and `matplotlib`:

    pip install -r requirements.txt

A full run of one configuration (sweep, sensitivity and scenarios) takes about one minute on a
laptop.

## Model structure

| File | Role |
|---|---|
| `w2h_model.py` | Shared computational core: parameters, wind, losses, dispatch, pipelines, storage, compression, costs, sweep, sensitivity and scenario routines. Nothing in this file is configuration-specific. |
| `Offshore_decentral.py` | Design 1. Configuration parameters, sensitivity list and scenario list. Writes `results/offshore_decentral_*`. |
| `Offshore_central.py` | Design 2, idem. |
| `Onshore_central.py` | Design 3, idem. |
| `make_figures.py` | Builds Fig. 5 (LCOH breakdown) and Fig. 6 to 8 (tornado charts) as PNG and PDF, plus `results/summary_all.csv` and `results/latex_tables.tex`. |
| `uurgeg_201_2021-2030.txt` | KNMI hourly observations, station 201 (D15-FA-1), base case. |
| `uurgeg_203_2021-2030_75km.txt` | Station 203 (P11-B), used for the 75 km distance-to-shore variant. |
| `uurgeg_205_2021-2030_350km.txt` | Station 205 (A12-CPP), used for the 350 km variant. |
| `results/` | Output of the last run with this code (included for reference). |
| `figures/` | Output of `make_figures.py` (included for reference). |

The three configuration scripts are deliberately short: each one only sets what differs
between the designs (electrolyser technology, converter steps, cable and pipeline lengths,
island, which scenarios apply) and then calls the shared routines. Changing a shared assumption
is therefore done once, in `w2h_model.py`.

## Running the model

    python Offshore_decentral.py
    python Offshore_central.py
    python Onshore_central.py
    python make_figures.py

Each configuration script prints the sizing sweep, the summary of the optimal design and the
LCOH breakdown per component, then writes `results/<config>_base.json`, `_breakdown.csv`,
`_sweep.csv`, `_SA.csv` and `_ScA.csv`. Set `RUN_SA` or `RUN_SCA` to `False` at the top of a
script to skip the sensitivity or scenario analysis.

## Verification

A run with this code should reproduce the base case of the paper exactly:

| | Offshore decentral | Offshore central | Onshore central |
|---|---|---|---|
| LCOH (EUR2025/kg) | 4.601 | 5.391 | 5.957 |
| Electrolyser per turbine (MW) | 14.25 | 13.25 | 13.25 |
| Annual hydrogen (kt/a) | 910.7 | 848.9 | 832.9 |
| Baseload (t/h) | 104.0 | 96.9 | 95.1 |
| Salt cavern working gas (TWh) | 4.12 | 3.83 | 3.92 |
| Compressor, average / installed (MW) | 52 / 99 | 44 / 85 | 72 / 134 |
| Electrical losses (%) | 1.5 | 8.0 | 8.6 |

These values appear in Table F.7 and Section 3.3 of the paper (LCOH rounded to 4.6, 5.4 and 6.0).

## Input data

- **Wind**: KNMI hourly observations (`FH`, hourly mean wind speed at 10 m), stations 201, 203
  and 205, years 2021 and 2022. Source: KNMI, *Uurgegevens van het weer op de Noordzee*,
  https://www.knmi.nl/nederland-nu/klimatologie/uurgegevens_Noordzee. Missing hours are
  interpolated by the model.
- **Turbine**: IEA Wind 15 MW offshore reference turbine (Gaertner et al., NREL, 2020).
- **Costs**: see Table F.8 of the paper for every source value, its year and its source.

## Model outputs

`results/<config>_base.json` holds all scalar outcomes of the optimal design (LCOH, LCOH per
category, production, baseload, cavern size, compressor power, pressures, losses).
`results/<config>_breakdown.csv` lists CAPEX, annualised CAPEX, OPEX and LCOH share per
component. `_sweep.csv`, `_SA.csv` and `_ScA.csv` hold the electrolyser sweep, the ±10 %
sensitivity and the scenario analysis.

## Archiving

To obtain a DOI: enable the GitHub integration on https://zenodo.org (Settings, GitHub,
switch on this repository), then create a release on GitHub (for example `v1.0.0`). Zenodo
archives the release and mints a DOI within minutes. Put that DOI in this README, in
`CITATION.cff` and in the paper's data availability statement. Later releases get their own
DOI; the concept DOI always resolves to the latest.

## About

Developed by David Breedijk at Delft University of Technology, Faculty of Technology, Policy
and Management, for the paper cited above. Corresponding author of the paper: L.S.F. Frowijn
(l.s.f.frowijn@tudelft.nl).
