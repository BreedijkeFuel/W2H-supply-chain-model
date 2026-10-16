# -*- coding: utf-8 -*-
"""
ONSHORE CENTRAL (design 3): 66 kV inter-array kabels, 2 GW HVDC-substation per
park, 250 km HVDC naar de kust, onshore substations, alkalische elektrolyse,
ontzilting en compressie bij de vraag; 250 km nieuwe 36-inch leiding naar de
zoutcaverne. Geen leiding naar de kust.

Draaien:  python Onshore_central.py
Output:   results/onshore_central_{base.json, breakdown.csv, sweep.csv, SA.csv, ScA.csv}
"""
import numpy as np
import w2h_model as m

RUN_SA, RUN_SCA = True, True
P_GRID_MW = np.arange(11.0, 15.01, 0.25)


def make_params():
    p = m.default_params()
    p.update(
        name='Onshore central (design 3)',
        electrolyser='Alk',
        N_converter_steps=5,
        has_interarray=True, L_interarray_per_farm=350.0,
        L_HVAC=0.0, L_HVDC=250.0,
        L_shore=0.0,                       # geen waterstofleiding naar de kust
        L_storage=250.0,                   # nieuwe 36-inch leiding naar de caverne
        storage_from_site=True,            # opslagflow apart van 50 bar naar de leidinginlaat
        L_collect_per_farm=0.0,
        has_island=False,
        offshore_process=False,            # proces-equipment staat onshore
        scale_applies=True,
    )
    return p


def distance_to_shore(p, km):
    p['L_HVDC'] = km                       # leiding naar de caverne blijft 250 km
    p['wind_file'] = m.WIND_FILES[km]
    return p


SA_ITEMS = [
    ('Electrolyser power consumption', ['power_consumption']),
    ('Wind turbine CAPEX', ['wind_capex']),
    ('HVDC CAPEX', ['HVDC_cable_capex', 'HVDC_off_sub_capex', 'HVDC_on_sub_capex']),
    ('Electrolyser CAPEX', ['capex_PEM', 'capex_Alk']),
    ('Salt cavern CAPEX', ['cavern_capex']),
    ('Inter-array cable CAPEX', ['IA_cable_capex']),
    ('Compressor CAPEX', ['comp_capex']),
    ('New 36-inch pipeline CAPEX', ['pipe_new36']),
]

SCENARIOS = m.standard_scenarios(distance_to_shore, has_electrical=True,
                                 has_h2_pipelines=True, scale_applies=True,
                                 offshore_process=False)

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

    m.save_results('results', 'onshore_central', best, sweep, sa, sca)
    print('\nResultaten weggeschreven naar results/onshore_central_*')
