# -*- coding: utf-8 -*-
"""
OFFSHORE CENTRAL (design 2): 66 kV inter-array kabels naar HVAC-substations
(700 MW, 3 per park), 20 km HVAC-kabels naar een energie-eiland met PEM-
elektrolyse, ontzilting en compressie; één 36-inch leiding naar de kust
(75 km hergebruikt + 175 km nieuw), 20 km leiding naar de zoutcaverne.

Draaien:  python Offshore_central.py
Output:   results/offshore_central_{base.json, breakdown.csv, sweep.csv, SA.csv, ScA.csv}
"""
import numpy as np
import w2h_model as m

RUN_SA, RUN_SCA = True, True
P_GRID_MW = np.arange(11.0, 15.01, 0.25)


def make_params():
    p = m.default_params()
    p.update(
        name='Offshore central (design 2)',
        electrolyser='PEM',
        N_converter_steps=5,
        has_interarray=True, L_interarray_per_farm=350.0,   # par. 3.2.2
        L_HVAC=20.0, L_HVDC=0.0,
        L_shore=250.0, L_shore_reuse_max=75.0,
        L_storage=20.0,
        L_collect_per_farm=0.0,
        has_island=True,
        offshore_process=True,
        scale_applies=True,
    )
    return p


def distance_to_shore(p, km):
    p['L_shore'] = km                      # HVAC naar het eiland blijft 20 km
    p['wind_file'] = m.WIND_FILES[km]
    return p


SA_ITEMS = [
    ('Electrolyser power consumption', ['power_consumption']),
    ('Wind turbine CAPEX', ['wind_capex']),
    ('Electrolyser CAPEX', ['capex_PEM', 'capex_Alk']),
    ('HVAC CAPEX', ['HVAC_cable_capex', 'HVAC_sub_capex']),
    ('Island CAPEX', ['island_capex_per_500MW']),
    ('Salt cavern CAPEX', ['cavern_capex']),
    ('Inter-array cable CAPEX', ['IA_cable_capex']),
    ('Compressor CAPEX', ['comp_capex']),
    ('New 36-inch pipeline CAPEX', ['pipe_new36', 'pipe_reuse36']),
]

SCENARIOS = m.standard_scenarios(distance_to_shore, has_electrical=True,
                                 has_h2_pipelines=True, scale_applies=True,
                                 offshore_process=True)

if __name__ == '__main__':
    p = make_params()
    print(f"\n### {p['name']}: sizing sweep")
    best, sweep = m.optimise(p, P_GRID_MW)
    m.print_summary(best)

    sa = sca = None
    if RUN_SA:
        print('\n### Sensitivity analysis (+/-10 %), ontwerp vast')
        sa, _ = m.run_sensitivity(p, best['P_each_MW'], SA_ITEMS, P_comp_guess=best['P_comp_avg_MW'])
    if RUN_SCA:
        print('\n### Scenario analysis (Tabel 7), ontwerp vast')
        sca, _ = m.run_scenarios(p, best['P_each_MW'], SCENARIOS, P_comp_guess=best['P_comp_avg_MW'])

    m.save_results('results', 'offshore_central', best, sweep, sa, sca)
    print('\nResultaten weggeschreven naar results/offshore_central_*')
