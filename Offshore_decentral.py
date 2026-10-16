# -*- coding: utf-8 -*-
"""
OFFSHORE DECENTRAL (design 1): PEM-elektrolyse aan de voet van elke turbine,
12-inch verzamelleidingen per string, één 36-inch leiding naar de kust
(75 km hergebruikt + 175 km nieuw), 20 km leiding naar de zoutcaverne.

Draaien:  python Offshore_decentral.py
Output:   results/offshore_decentral_{base.json, breakdown.csv, sweep.csv, SA.csv, ScA.csv}
Daarna:   python make_figures.py
"""
import numpy as np
import w2h_model as m

RUN_SA, RUN_SCA = True, True
P_GRID_MW = np.arange(11.0, 15.01, 0.25)


def make_params():
    p = m.default_params()
    p.update(
        name='Offshore decentral (design 1)',
        electrolyser='PEM',
        N_converter_steps=1,              # turbine -> 1000 V DC, één stap
        has_interarray=False, L_interarray_per_farm=0.0,
        L_HVAC=0.0, L_HVDC=0.0,
        L_shore=250.0, L_shore_reuse_max=75.0,
        L_storage=20.0,
        L_collect_per_farm=275.0,         # Tabel F.4: per windpark
        L_collect_single=21.5,            # km, voor de drukval (Fig. F.3)
        has_island=False,
        offshore_process=True,
        scale_applies=False,              # geen schaalvoordeel bij decentrale BoP
    )
    return p


def distance_to_shore(p, km):
    p['L_shore'] = km
    p['wind_file'] = m.WIND_FILES[km]
    return p


SA_ITEMS = [
    ('Electrolyser power consumption', ['power_consumption']),
    ('Wind turbine CAPEX', ['wind_capex']),
    ('Electrolyser CAPEX', ['capex_PEM', 'capex_Alk']),
    ('New 12-inch pipeline CAPEX', ['pipe_new12']),
    ('36-inch pipeline CAPEX', ['pipe_new36', 'pipe_reuse36']),
    ('Salt cavern CAPEX', ['cavern_capex']),
    ('Compressor CAPEX', ['comp_capex']),
]

SCENARIOS = m.standard_scenarios(distance_to_shore, has_electrical=False,
                                 has_h2_pipelines=True, scale_applies=False,
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

    m.save_results('results', 'offshore_decentral', best, sweep, sa, sca)
    print('\nResultaten weggeschreven naar results/offshore_decentral_*')
