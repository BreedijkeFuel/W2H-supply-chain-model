# -*- coding: utf-8 -*-
"""
w2h_model.py
Gedeelde rekenkern voor de drie wind-to-hydrogen configuraties uit
Breedijk, Frowijn, Lukszo: "Offshore-wind based green hydrogen supply chains
comparison" (IJHE, 2026).

De configuratiescripts (Offshore_decentral.py, Offshore_central.py,
Onshore_central.py) bevatten alleen parameters, de SA-lijst en de scenario-
lijst; alle rekenstappen staan hier, één keer.

Rekenstappen
  1. wind      KNMI-uurdata (10 m) -> 60 m (log-wet) -> naafhoogte (machtswet),
               vermogenscurve NREL 15 MW, één windjaar herhaald over de looptijd
  2. elektrisch verliezen converterstappen, HVAC/HVDC-kabels, inter-array
  3. dispatch  elektrolyser (constante efficiëntie), BoP 3% + compressoren,
               optioneel batterij met SoC-grenzen (Appendix C)
  4. leidingen drukval per km (Appendix C), inlaatdruk uit scan
  5. opslag    baseload = gemiddelde productie over de windjaren, caverne = max-min van de
               cumulatieve afwijking (cyclisch), of 'project' (oude methode),
               of 'none' (geen baseload)
  6. compressie isentroop, transport + opslag (1,1 kWh/kg), P_comp geïtereerd
  7. kosten    CAPEX geëscaleerd vanaf bronjaar, CRF per component (of één
               systeem-CRF met vervangingen), OPEX als fractie van CAPEX,
               water als jaarlijkse kostenpost

Verwerkte correcties t.o.v. de eerdere scripts: zie CHANGELOG onderaan.
"""
import copy
import json
import math
import os

import numpy as np
import pandas as pd

HOURS_YEAR = 8760
CATEGORIES = ['Wind turbines', 'Electrolyser stack', 'Electrolyser BoP',
              'Water feed', 'Storage', 'Hub', 'Transmission', 'Compressor',
              'Battery']


# =============================================================================
# 1. PARAMETERS
# =============================================================================
def default_params():
    """Alle parameters die voor de drie configuraties gelijk zijn. De
    configuratiescripts overschrijven wat per ontwerp verschilt."""
    return dict(
        name='unnamed',
        # ---- algemeen
        Years=30, n_project=30, N_turb=665, N_farm=5,
        wind_file='uurgeg_201_2021-2030.txt', wind_years=(2021, 2022),   # herhaald tot Years
        # ---- turbine (NREL 15 MW, Tabel 2)
        P_r=15.0, c_p=0.489, rho=1.2, R_rotor=120.0, U_in=3.0, U_out=25.0,
        z_0=0.0002, h_ref=10.0, h_blend=60.0, h_hub=150.0, alpha=0.11,
        # ---- elektrolyser (Tabel F.4)
        electrolyser='PEM', power_consumption=53.2e3, HHV_H2=39.39e3,
        lifetime_h=125000.0, p_out_PEM=50.0, p_out_Alk=20.0,
        degradation_per_1000h=0.001, degradation_ref_lifetime_h=125000.0,  # 0,1 %/1000 h; vlootgemiddelde = 1 + 0,5*rate*lifetime_h/1000 (gespreide vervanging)
        llr_PEM=0.05, llr_Alk=0.10, bop_power_frac=0.03,
        # ---- elektrische keten
        N_converter_steps=5, eta_converter=0.985,
        HVAC_loss=0.7, HVDC_loss=0.35, IA_loss=0.6,          # %/100 km, %
        has_interarray=True, L_interarray_per_farm=350.0,
        L_HVAC=0.0, L_HVDC=0.0,
        P_HVAC_sub_MW=700.0, P_HVDC_sub_MW=2000.0, subs_per_HVAC_link=2,
        # ---- waterstofketen
        L_shore=250.0, L_shore_reuse_max=75.0, L_storage=20.0,
        L_collect_per_farm=0.0, L_collect_single=21.5,
        p_land=50.0, p_storage=50.0, p_scan=(20.0, 150.0, 0.5),
        has_island=False,
        storage_from_site=False,      # True (design 3): opslagflow apart gecomprimeerd
                                      # van de leverdruk naar de inlaat van de opslagleiding
        offshore_process=True,        # elektrolyser, RO, compressoren offshore?
        scale_applies=False,          # schaalfactor BoP van toepassing?
        # ---- opslag
        storage_mode='cyclic',        # 'cyclic' | 'project' | 'none'
        days_storage_start=19,        # alleen voor 'project'
        E_comp_storage=1100.0,        # Wh/kg
        # ---- batterij (Appendix C)
        E_batt_GWh=0.0, eff_batt=0.95, max_soc_rate=0.3,
        batt_dispatch='appendixC',    # 'appendixC' (alleen tot LLR) | 'fill' (tot nominaal)
        # ---- compressor
        Z=1.03, T_comp=273.0, R_gas=8.314, M_H2=2.0158,
        eta_comp=0.88, N_stages=1, gamma=1.4,
        P_comp_tol_MW=0.2, P_comp_max_iter=20,
        # ---- financieel
        year_now=2025, i_f=0.02, r=0.08,
        crf_method='system',          # 'system' (één CRF over n_project, vervangingen tegen r) | 'component'
        # ---- kosten: basiswaarde, bronjaar, levensduur, OPEX-fractie
        wind_capex=2400.0, wind_fx=0.95, wind_cost_year=2021, wind_life=30, wind_opex=0.03,
        capex_PEM=550.0, capex_Alk=450.0, elec_cost_year=2023, stack_share=0.5,
        BoP_life=20, elec_opex=0.03,
        cavern_capex=334.0, cavern_cost_year=2019, cavern_life=50, cavern_opex=0.04,
        pipe_new36=3.7e6 / 20, pipe_reuse36=0.4e6 / 20, pipe_new12=1.5e6,
        pipe_cost_year=2022, pipe_life=50, pipe_opex=0.001,
        HVAC_sub_capex=120e3, HVAC_sub_fx=1.15, HVAC_sub_cost_year=2019,
        HVDC_off_sub_capex=600e3, HVDC_on_sub_capex=150e3,
        HVDC_cable_capex=1.5e6, HVAC_cable_capex=2.5e6, IA_cable_capex=400e3,
        el_cost_year=2021, sub_life=35, cable_life=40, IA_life=30,
        off_sub_opex=0.02, on_sub_opex=0.007, cable_opex=0.02,
        island_capex_per_500MW=75e6, island_cost_year=2021, island_life=80, island_opex=0.005,   # Tabel F.8: 75 MEUR (2021) -> 81 EUR2025
        island_opex_abs=None,         # zet op 3e6 voor Tabel F.5-variant
        comp_capex=2e6, comp_cost_year=2021, comp_life=12, comp_opex=0.02,   # Tabel F.8: 2 MEUR/MW (2021) -> 2.2 EUR2025
        water_price=0.875, f_water=11.0,
        batt_capex=345.0, batt_fx=0.876, batt_cost_year=2020, batt_life=15, batt_opex=0.025,
        # ---- scenario-schakelaars (1 = basis)
        f_h2_infra=1.0,               # alle pijpleidingen
        f_el_infra=1.0,               # kabels en substations
        f_offshore_capex=1.0,         # offshore proces-equipment (par. 4.1)
        f_bop_scale=1.0,              # schaalfactor BoP (alleen als scale_applies)
        opex_offshore_process=None,   # bv. 0.10: OPEX offshore proces-equipment
    )


def esc(p, year):
    """Escalatie van bronjaar naar year_now met inflatie i_f (Eq. F.1)."""
    return (1.0 + p['i_f']) ** (p['year_now'] - year)


def crf(r, n):
    return r * (1 + r) ** n / ((1 + r) ** n - 1)


# =============================================================================
# 2. WIND
# =============================================================================
_WIND_CACHE = {}


def load_wind(path, year):
    """Uurgemiddelde windsnelheid (m/s, 10 m) voor één kalenderjaar uit een
    KNMI-uurgegevensbestand. Werkt met het ruwe bestand (kopregels, '# STN')
    en met een opgeschoond csv. Ontbrekende waarden worden geïnterpoleerd."""
    key = (os.path.abspath(path), year)
    if key in _WIND_CACHE:
        return _WIND_CACHE[key]
    with open(path, 'r', encoding='latin-1') as f:
        lines = f.readlines()
    hdr = next(i for i, l in enumerate(lines) if 'YYYYMMDD' in l)
    df = pd.read_csv(path, skiprows=hdr, encoding='latin-1', skipinitialspace=True)
    df.columns = [c.strip().lstrip('#').strip() for c in df.columns]
    df = df[df['YYYYMMDD'].astype(int) // 10000 == year]
    fh = pd.to_numeric(df['FH'].astype(str).str.strip(), errors='coerce')
    n_missing = int(fh.isna().sum())
    fh = fh.interpolate(limit_direction='both')
    ws = fh.to_numpy(dtype=float) / 10.0
    if len(ws) < HOURS_YEAR:
        raise ValueError(f'{path}: {len(ws)} uren voor {year}, 8760 verwacht')
    ws = ws[:HOURS_YEAR]
    _WIND_CACHE[key] = (ws, n_missing)
    return ws, n_missing


def farm_power(p):
    """Elektrisch vermogen van alle turbines [W], uurreeks over de looptijd."""
    years = tuple(p['wind_years'])
    if p['Years'] % len(years):
        raise ValueError('Years moet een veelvoud zijn van het aantal windjaren')
    parts = [load_wind(p['wind_file'], y) for y in years]
    ws_block = np.concatenate([w for w, _ in parts]); n_missing = sum(n for _, n in parts)
    ws_year = ws_block
    ws = np.tile(ws_block, p['Years'] // len(years))
    U_blend = ws * (math.log(p['h_blend'] / p['z_0']) / math.log(p['h_ref'] / p['z_0']))
    U_hub = U_blend * (p['h_hub'] / p['h_blend']) ** p['alpha']
    A = math.pi * p['R_rotor'] ** 2
    P_rated = p['P_r'] * 1e6
    U_rated = (P_rated / (0.5 * p['rho'] * p['c_p'] * A)) ** (1 / 3)
    P = np.zeros_like(U_hub)
    part = (U_hub >= p['U_in']) & (U_hub < U_rated)
    full = (U_hub >= U_rated) & (U_hub <= p['U_out'])
    P[part] = 0.5 * p['rho'] * p['c_p'] * A * U_hub[part] ** 3
    P[full] = P_rated
    info = dict(U_rated=U_rated, mean_ws_10m=float(ws_year.mean()),
                capacity_factor=float(P.mean() / P_rated), missing_hours=n_missing)
    return P * p['N_turb'], info


# =============================================================================
# 3. ELEKTRISCHE VERLIEZEN EN DISPATCH
# =============================================================================

def fleet_degradation_factor(p):
    """Vlootgemiddelde verbruiksfactor bij gespreide stackvervanging: stacks van alle leeftijden
    tussen 0 en lifetime_h zijn gelijk vertegenwoordigd, dus gemiddeld de halve einde-levensduur-degradatie."""
    L = p.get('degradation_ref_lifetime_h', p['lifetime_h'])   # vaste referentie, zodat het levensduurscenario alleen de vervangingsfrequentie test
    return 1.0 + 0.5 * p.get('degradation_per_1000h', 0.0) * L / 1000.0


def effective_consumption(p):
    """Effectief specifiek verbruik [Wh/kg] = nominaal x vlootgemiddelde degradatiefactor."""
    return p['power_consumption'] * fleet_degradation_factor(p)

def electrical_efficiency(p):
    conv = 1 - p['eta_converter'] ** p['N_converter_steps']
    hvac = p['HVAC_loss'] / 100 * p['L_HVAC'] / 100
    hvdc = p['HVDC_loss'] / 100 * p['L_HVDC'] / 100
    ia = p['IA_loss'] / 100 if p['has_interarray'] else 0.0
    return (1 - conv) * (1 - hvac) * (1 - hvdc) * (1 - ia)


def dispatch(P_in, P_el, P_BoP, llr, p):
    """Elektrolyserbelasting [W] per uur, met of zonder batterij.
    Zonder batterij: vectorieel. Met batterij: de vier bedrijfstoestanden van
    Appendix C, met SoC-grenzen en maximale laad/ontlaadstap per uur."""
    target = P_el * llr + P_BoP
    E_batt = p['E_batt_GWh'] * 1e9                    # Wh
    if E_batt <= 0:
        load = np.clip(P_in - P_BoP, 0.0, P_el)
        load[P_in < target] = 0.0
        return load, np.zeros_like(load), np.maximum(P_in - P_el - P_BoP, 0.0)

    eff, max_step = p['eff_batt'], p['max_soc_rate'] * E_batt
    n = len(P_in)
    load = np.zeros(n); curt = np.zeros(n); soc = np.zeros(n + 1)
    fill = p.get('batt_dispatch', 'appendixC') == 'fill'
    for i in range(n):
        Pi, S = P_in[i], soc[i]
        if fill and target <= Pi < P_el + P_BoP:         # 'fill': ontladen tot nominaal
            dis = min(S, max_step, (P_el + P_BoP - Pi) / eff)
            load[i] = Pi + dis * eff - P_BoP; soc[i + 1] = S - dis
            continue
        if Pi + S * eff < target:                       # A: ook met batterij te weinig
            raw = max(Pi, 0.0) * eff
            ch = min(raw, max_step, E_batt - S)
            soc[i + 1] = S + ch; curt[i] = raw - ch
        elif Pi < target:                               # B: batterij vult aan tot LLR
            needed = target - Pi
            if min(S, max_step) * eff >= needed:
                soc[i + 1] = S - needed / eff
                load[i] = P_el * llr                    # LLR-fix: geen P_BoP eraf
            else:
                soc[i + 1] = S
        elif Pi <= P_el + P_BoP:                        # C: directe productie
            load[i] = Pi - P_BoP; soc[i + 1] = S
        else:                                           # D: overschot laadt batterij
            load[i] = P_el
            raw = (Pi - P_el - P_BoP) * eff
            ch = min(raw, max_step, E_batt - S)
            soc[i + 1] = S + ch; curt[i] = raw - ch
    return load, soc[:-1], curt


# =============================================================================
# 4. LEIDINGEN
# =============================================================================
def dp_36(pbar):  # bar per 100 km (Eq. C.7)
    return 3.0 + (pbar - 20.0) / 8.0


def dp_12(pbar):  # bar per 100 km (Eq. C.4)
    return 11.0 + (pbar - 20.0) * 9.0 / 20.0


def pipeline_inlet_pressure(L_km, p_end_required, dp_fn, p_scan):
    """Laagste inlaatdruk in de scan waarbij na L km (segmenten van 1 km) de
    einddruk nog boven p_end_required ligt."""
    p0 = np.arange(p_scan[0], p_scan[1] + 1e-9, p_scan[2])
    pres = p0.copy()
    for _ in range(int(round(L_km))):
        pres = pres - dp_fn(pres) / 100.0
    ok = np.where(pres >= p_end_required)[0]
    if len(ok) == 0:
        raise ValueError(f'geen inlaatdruk in de scan levert {p_end_required} bar na {L_km} km')
    return float(p0[ok[0]]), float(pres[ok[0]])


def collection_outlet_pressure(p_in, L_km):
    pres = p_in
    for _ in range(int(math.ceil(L_km))):
        pres -= dp_12(pres) / 100.0
    return pres


# =============================================================================
# 5. OPSLAG
# =============================================================================
def size_storage(H2, p):
    """Baseload en cavernegrootte.
    cyclic : baseload = gemiddelde productie; D(t) = cumsum(H2 - B);
             capaciteit = max D - min D; beginvulling = -min D.
    project: oude methode (beginvulling = days_storage_start dagen productie,
             grootste baseload waarbij de caverne nooit leeg raakt).
    none   : geen baseload, H2 wordt geleverd zoals geproduceerd."""
    mode = p['storage_mode']
    if mode == 'none':
        return dict(baseload=None, cap_kg=0.0, init_kg=0.0,
                    storage_in=np.zeros_like(H2), delivered_kg=float(H2.sum()))
    if mode == 'cyclic':
        B = float(H2.mean())
        D = np.concatenate(([0.0], np.cumsum(H2 - B)))
        cap, init = float(D.max() - D.min()), float(-D.min())
    elif mode == 'project':
        S0 = float(H2[:24 * p['days_storage_start']].sum())
        cum = np.cumsum(H2[:-1]); steps = np.arange(1, len(H2), dtype=float)
        B = float(np.min((S0 + cum) / steps))
        prof = S0 + np.concatenate(([0.0], np.cumsum(H2[:-1] - B)))
        cap, init = float(prof.max()), S0
    else:
        raise ValueError(mode)
    return dict(baseload=B, cap_kg=cap, init_kg=init,
                storage_in=np.maximum(H2 - B, 0.0),
                delivered_kg=B * len(H2))


# =============================================================================
# 6. COMPRESSIE
# =============================================================================
def comp_power_MW(m_kg_h, p1, p2, p):
    """Isentroop compressorvermogen [MW] van p1 naar p2, N_stages trappen."""
    if p2 <= p1 or m_kg_h <= 0:
        return 0.0
    g, N = p['gamma'], p['N_stages']
    m_dot = m_kg_h / 3600.0                            # kg/s
    head = (m_dot / p['M_H2']) * p['Z'] * p['R_gas'] * p['T_comp'] * N * g / (g - 1) \
        * ((p2 / p1) ** ((g - 1) / (N * g)) - 1)     # kW (M in g/mol)
    return head / p['eta_comp'] / 1e3


# =============================================================================
# 7. KOSTEN
# =============================================================================
def annualise(capex, life, p):
    """Jaarlijkse kapitaallast [EUR/a] volgens de gekozen CRF-methode."""
    n, r = p['n_project'], p['r']
    if p['crf_method'] == 'component':
        return capex * crf(r, min(life, n))
    if p['crf_method'] == 'system':
        v = 1 / (1 + r)
        k = 1
        npv = capex
        while k * life < n:                             # vervangingen, geen restwaarde
            npv += capex * v ** (k * life)
            k += 1
        return npv * crf(r, n)
    raise ValueError(p['crf_method'])


def build_components(p, s):
    """Lijst met (naam, categorie, CAPEX, levensduur, OPEX-fractie, OPEX-absoluut)."""
    c = []
    off = p['offshore_process']
    f_off = p['f_offshore_capex'] if off else 1.0
    opex_proc = p['opex_offshore_process'] if (off and p['opex_offshore_process']) else p['elec_opex']
    opex_comp = p['opex_offshore_process'] if (off and p['opex_offshore_process']) else p['comp_opex']

    # wind
    capex_wind = p['P_r'] * 1e3 * p['wind_capex'] * p['wind_fx'] * esc(p, p['wind_cost_year']) * p['N_turb']
    c.append(('Wind turbines', 'Wind turbines', capex_wind, p['wind_life'], p['wind_opex'], 0.0))

    # elektrolyser
    spec = (p['capex_PEM'] if p['electrolyser'] == 'PEM' else p['capex_Alk']) * esc(p, p['elec_cost_year'])
    capex_el = spec * s['P_el'] / 1e3 * f_off
    f_scale = p['f_bop_scale'] if p['scale_applies'] else 1.0
    n_stack = p['lifetime_h'] / HOURS_YEAR
    c.append(('Electrolyser stack', 'Electrolyser stack', p['stack_share'] * capex_el, n_stack, opex_proc, 0.0))
    c.append(('Electrolyser BoP', 'Electrolyser BoP', (1 - p['stack_share']) * capex_el * f_scale, p['BoP_life'], opex_proc, 0.0))

    # opslag
    if s['cap_kg'] > 0:
        c.append(('Salt cavern', 'Storage', p['cavern_capex'] * esc(p, p['cavern_cost_year']) * s['cap_kg'] * p['HHV_H2'] / 1e6,
                  p['cavern_life'], p['cavern_opex'], 0.0))

    # pijpleidingen (36 inch per km per GW; 12 inch per km)
    fp = esc(p, p['pipe_cost_year']) * p['f_h2_infra']
    GW = s['H2_GW_max']
    if p['L_shore'] > 0:
        L_reuse = min(p['L_shore_reuse_max'], p['L_shore']); L_new = p['L_shore'] - L_reuse
        c.append(('36-inch to shore, new', 'Transmission', p['pipe_new36'] * fp * L_new * GW, p['pipe_life'], p['pipe_opex'], 0.0))
        c.append(('36-inch to shore, reused', 'Transmission', p['pipe_reuse36'] * fp * L_reuse * GW, p['pipe_life'], p['pipe_opex'], 0.0))
    if p['L_storage'] > 0 and s['H2_GW_storage'] > 0:   # capaciteit = piekflow van of naar de caverne
        c.append(('36-inch to storage, new', 'Transmission', p['pipe_new36'] * fp * p['L_storage'] * s['H2_GW_storage'], p['pipe_life'], p['pipe_opex'], 0.0))
    if p['L_collect_per_farm'] > 0:
        c.append(('12-inch collection', 'Transmission', p['pipe_new12'] * fp * p['L_collect_per_farm'] * p['N_farm'], p['pipe_life'], p['pipe_opex'], 0.0))

    # elektrische infrastructuur
    fe = esc(p, p['el_cost_year']) * p['f_el_infra']
    if p['L_HVAC'] > 0:
        n_links = math.ceil(p['N_turb'] * p['P_r'] / p['P_HVAC_sub_MW'])
        capex_sub = p['HVAC_sub_capex'] * p['HVAC_sub_fx'] * esc(p, p['HVAC_sub_cost_year']) * p['f_el_infra']
        c.append(('HVAC substations', 'Transmission', p['subs_per_HVAC_link'] * n_links * capex_sub * p['P_HVAC_sub_MW'], p['sub_life'], p['off_sub_opex'], 0.0))
        c.append(('HVAC cables', 'Transmission', p['HVAC_cable_capex'] * fe * p['L_HVAC'] * n_links, p['cable_life'], p['cable_opex'], 0.0))
    if p['L_HVDC'] > 0:
        MW = p['P_HVDC_sub_MW'] * p['N_farm']
        c.append(('HVDC offshore substations', 'Transmission', p['HVDC_off_sub_capex'] * fe * MW, p['sub_life'], p['off_sub_opex'], 0.0))
        c.append(('HVDC onshore substations', 'Transmission', p['HVDC_on_sub_capex'] * fe * MW, p['sub_life'], p['on_sub_opex'], 0.0))
        c.append(('HVDC cables', 'Transmission', p['HVDC_cable_capex'] * fe * p['L_HVDC'] * p['N_farm'], p['cable_life'], p['cable_opex'], 0.0))
    if p['has_interarray']:
        c.append(('Inter-array 66 kV cables', 'Transmission', p['IA_cable_capex'] * fe * p['L_interarray_per_farm'] * p['N_farm'], p['IA_life'], p['cable_opex'], 0.0))

    # eiland
    if p['has_island']:
        capex_isl = p['island_capex_per_500MW'] * esc(p, p['island_cost_year']) * (s['P_el'] / 500e6) * f_off
        if p['island_opex_abs'] is not None:
            c.append(('Energy island', 'Hub', capex_isl, p['island_life'], 0.0, p['island_opex_abs']))
        else:
            c.append(('Energy island', 'Hub', capex_isl, p['island_life'], p['island_opex'], 0.0))

    # compressoren
    c.append(('Compressors', 'Compressor', p['comp_capex'] * esc(p, p['comp_cost_year']) * s['P_comp_installed_MW'] * f_off, p['comp_life'], opex_comp, 0.0))

    # batterij
    if p['E_batt_GWh'] > 0:
        capex_b = p['batt_capex'] * p['batt_fx'] * esc(p, p['batt_cost_year']) * p['E_batt_GWh'] * 1e6   # EUR/kWh * kWh
        c.append(('Battery', 'Battery', capex_b, p['batt_life'], p['batt_opex'], 0.0))
    return c


# =============================================================================
# 8. EEN VOLLEDIGE RUN
# =============================================================================
def run(p, P_each_W, P_comp_start_MW=None, verbose=False):
    """Volledige berekening voor één elektrolysergrootte per turbine [W].
    P_comp wordt geïtereerd tot het aangenomen gemiddelde compressorvermogen
    gelijk is aan het berekende."""
    E_farm, wind_info = farm_power(p)
    eff_el = electrical_efficiency(p)
    P_in = E_farm * eff_el
    P_el = P_each_W * p['N_turb']
    pem = p['electrolyser'] == 'PEM'
    llr = p['llr_PEM'] if pem else p['llr_Alk']
    p_out = p['p_out_PEM'] if pem else p['p_out_Alk']
    eff_electrolyser = p['HHV_H2'] / effective_consumption(p)

    # leidingdrukken (onafhankelijk van de flow in dit model)
    if p['L_collect_per_farm'] > 0:
        p1 = collection_outlet_pressure(p_out, p['L_collect_single'])
    else:
        p1 = p_out
    if p['L_shore'] > 0:                 # alle productie naar de inlaat van de leiding naar de kust
        p2, p_end = pipeline_inlet_pressure(p['L_shore'], p['p_land'], dp_36, p['p_scan'])
    else:                                # vraag op locatie: alle productie naar leverdruk
        p2, p_end = p['p_land'], p['p_land']
    if p['storage_from_site'] and p['L_storage'] > 0:
        p2_st, p_end_st = pipeline_inlet_pressure(p['L_storage'], p['p_storage'], dp_36, p['p_scan'])
    else:
        p2_st, p_end_st = None, None

    P_comp_MW = P_comp_start_MW if P_comp_start_MW is not None else 0.0
    for it in range(p['P_comp_max_iter']):
        P_BoP = p['bop_power_frac'] * P_el + P_comp_MW * 1e6
        load, soc, curt = dispatch(P_in, P_el, P_BoP, llr, p)
        H2 = load * eff_electrolyser / p['HHV_H2']                 # kg/h
        st = size_storage(H2, p)
        m_max, m_avg = float(H2.max()), float(H2.mean())
        Pc_tr_inst = comp_power_MW(m_max, p1, p2, p)
        Pc_tr_avg = comp_power_MW(m_avg, p1, p2, p)
        if p2_st is not None:            # design 3: opslagflow van leverdruk naar opslagleiding
            Pc_tr_inst += comp_power_MW(float(st['storage_in'].max()), p2, p2_st, p)
            Pc_tr_avg += comp_power_MW(float(st['storage_in'].mean()), p2, p2_st, p)
        Pc_st_inst = float(st['storage_in'].max()) * p['E_comp_storage'] / 1e6
        Pc_st_avg = float(st['storage_in'].mean()) * p['E_comp_storage'] / 1e6
        P_comp_avg_new = Pc_tr_avg + Pc_st_avg
        converged = abs(P_comp_avg_new - P_comp_MW) < p['P_comp_tol_MW']
        if verbose:
            print(f'   P_comp iteratie {it}: {P_comp_MW:.1f} -> {P_comp_avg_new:.1f} MW')
        P_comp_MW = P_comp_avg_new
        if converged:
            break

    H2_kg_tot = float(H2.sum()); H2_kg_a = H2_kg_tot / p['Years']
    st_out = np.maximum(st['baseload'] - H2, 0.0) if st['baseload'] is not None else np.zeros_like(H2)
    s = dict(P_el=P_el, cap_kg=st['cap_kg'], H2_GW_max=m_max * p['HHV_H2'] / 1e9,
             H2_GW_storage=max(float(st['storage_in'].max()), float(st_out.max())) * p['HHV_H2'] / 1e9,
             P_comp_installed_MW=Pc_tr_inst + Pc_st_inst)
    comps = build_components(p, s)

    rows, by_cat, total = [], {k: 0.0 for k in CATEGORIES}, 0.0
    for name, cat, capex, life, opex_frac, opex_abs in comps:
        capex_a = annualise(capex, life, p)
        opex_a = capex * opex_frac + opex_abs
        rows.append(dict(component=name, category=cat, CAPEX_EUR=capex, lifetime_a=min(life, p['n_project']),
                         CAPEX_a_EUR=capex_a, OPEX_a_EUR=opex_a, LCOH_EUR_kg=(capex_a + opex_a) / H2_kg_a))
        by_cat[cat] += (capex_a + opex_a) / H2_kg_a
        total += capex_a + opex_a
    # water: jaarlijkse kostenpost, geen CRF
    m3_water_a = H2_kg_a * p['f_water'] / 1000.0
    water_a = m3_water_a * p['water_price'] * (p['f_offshore_capex'] if p['offshore_process'] else 1.0)
    rows.append(dict(component='Water feed', category='Water feed', CAPEX_EUR=0.0, lifetime_a=np.nan,
                     CAPEX_a_EUR=0.0, OPEX_a_EUR=water_a, LCOH_EUR_kg=water_a / H2_kg_a))
    by_cat['Water feed'] += water_a / H2_kg_a
    total += water_a

    return dict(
        config=p['name'], P_each_MW=P_each_W / 1e6, LCOH=total / H2_kg_a,
        LCOH_by_category=by_cat, rows=rows,
        H2_kt_a=H2_kg_a / 1e6, H2_delivered_kt_a=st['delivered_kg'] / p['Years'] / 1e6,
        baseload_kg_h=st['baseload'], storage_GWh=st['cap_kg'] * p['HHV_H2'] / 1e9,
        storage_init_GWh=st['init_kg'] * p['HHV_H2'] / 1e9,
        P_comp_avg_MW=P_comp_MW, P_comp_installed_MW=s['P_comp_installed_MW'],
        P_comp_transport_MW=Pc_tr_inst, P_comp_storage_MW=Pc_st_inst,
        P_comp_converged=bool(converged), P_comp_iterations=it + 1,
        p_transport_in_bar=p1, p_pipeline_inlet_bar=p2, p_pipeline_outlet_bar=p_end,
        p_storage_pipeline_inlet_bar=p2_st, H2_GW_storage=s['H2_GW_storage'],
        electrical_losses_pct=(1 - eff_el) * 100, electrolyser_load_factor=float(load.mean() / P_el),
        consumption_nominal_kWh_kg=p['power_consumption'] / 1e3, consumption_effective_kWh_kg=effective_consumption(p) / 1e3,
        curtailment_GWh_a=float(curt.sum()) / p['Years'] / 1e9,
        wind_capacity_factor=wind_info['capacity_factor'], U_rated=wind_info['U_rated'],
        wind_missing_hours=wind_info['missing_hours'],
        H2_GW_max=s['H2_GW_max'], water_Mm3_a=m3_water_a / 1e6,
    )


# =============================================================================
# 9. SWEEP, SA, SCENARIO'S
# =============================================================================
def optimise(p, P_grid_MW, verbose=True):
    results, guess = [], None
    for P in P_grid_MW:
        res = run(p, P * 1e6, P_comp_start_MW=guess)
        guess = res['P_comp_avg_MW']
        results.append(res)
        if verbose:
            print(f"   {P:6.2f} MW/turbine  LCOH {res['LCOH']:.3f}  baseload {res['baseload_kg_h'] or 0:9.0f} kg/h"
                  f"  cavern {res['storage_GWh']:7.0f} GWh  P_comp {res['P_comp_avg_MW']:6.1f} MW")
    best = min(results, key=lambda d: d['LCOH'])
    if best is results[0] or best is results[-1]:
        print('   >> LET OP: optimum ligt op de rand van het bereik; bereik oprekken')
    return best, results


def scaled(p, keys, factor):
    q = copy.deepcopy(p)
    for k in keys:
        q[k] = q[k] * factor
    return q


def run_sensitivity(p, P_each_MW, items, delta=0.10, P_comp_guess=None):
    """items: lijst van (label, [parameterkeys]). Ontwerp vast op P_each_MW."""
    base = run(p, P_each_MW * 1e6, P_comp_start_MW=P_comp_guess)
    out = []
    for label, keys in items:
        lo = run(scaled(p, keys, 1 - delta), P_each_MW * 1e6, P_comp_start_MW=base['P_comp_avg_MW'])
        hi = run(scaled(p, keys, 1 + delta), P_each_MW * 1e6, P_comp_start_MW=base['P_comp_avg_MW'])
        out.append(dict(Parameter=label, Min=lo['LCOH'], Nominal=base['LCOH'], Max=hi['LCOH'],
                        pct_min=(lo['LCOH'] / base['LCOH'] - 1) * 100, pct_max=(hi['LCOH'] / base['LCOH'] - 1) * 100))
        print(f"   SA {label:32s} {lo['LCOH']:.3f} | {base['LCOH']:.3f} | {hi['LCOH']:.3f}")
    return pd.DataFrame(out), base


def run_scenarios(p, P_each_MW, scenarios, P_comp_guess=None):
    """scenarios: lijst van (groep, parameter, optimistisch(p), pessimistisch(p)) met
    functies die een gewijzigde parameterset teruggeven, of None."""
    base = run(p, P_each_MW * 1e6, P_comp_start_MW=P_comp_guess)
    out = []
    for group, label, f_opt, f_pes in scenarios:
        vals = {}
        for tag, f in (('opt', f_opt), ('pes', f_pes)):
            if f is None:
                vals[tag] = np.nan; continue
            q = f(copy.deepcopy(p))
            try:
                r = run(q, P_each_MW * 1e6, P_comp_start_MW=base['P_comp_avg_MW'])
                vals[tag] = r['LCOH']
                vals[tag + '_detail'] = r
            except FileNotFoundError as e:
                print(f'   >> scenario {label} ({tag}) overgeslagen: {e}')
                vals[tag] = np.nan
        out.append(dict(Group=group, Parameter=label, Optimistic=vals['opt'], Selected=base['LCOH'], Pessimistic=vals['pes']))
        print(f"   ScA {label:32s} {vals['opt']:.2f} | {base['LCOH']:.2f} | {vals['pes']:.2f}")
    return pd.DataFrame(out), base


# =============================================================================
# 10. OPSLAAN
# =============================================================================
def save_results(outdir, tag, base, sweep=None, sa=None, sca=None):
    os.makedirs(outdir, exist_ok=True)
    slim = {k: v for k, v in base.items() if k != 'rows'}
    with open(os.path.join(outdir, f'{tag}_base.json'), 'w') as f:
        json.dump(slim, f, indent=2, default=float)
    pd.DataFrame(base['rows']).to_csv(os.path.join(outdir, f'{tag}_breakdown.csv'), index=False)
    if sweep is not None:
        pd.DataFrame([{k: v for k, v in r.items() if k not in ('rows', 'LCOH_by_category')} for r in sweep]) \
            .to_csv(os.path.join(outdir, f'{tag}_sweep.csv'), index=False)
    if sa is not None:
        sa.to_csv(os.path.join(outdir, f'{tag}_SA.csv'), index=False)
    if sca is not None:
        sca.to_csv(os.path.join(outdir, f'{tag}_ScA.csv'), index=False)


def print_summary(res):
    print(f"\n=== {res['config']} ===")
    print(f"Elektrolyser per turbine  : {res['P_each_MW']:.2f} MW")
    print(f"LCOH                      : {res['LCOH']:.3f} EUR2025/kg")
    print(f"H2 geproduceerd / geleverd: {res['H2_kt_a']:.1f} / {res['H2_delivered_kt_a']:.1f} kt/a")
    bl = res['baseload_kg_h']
    print(f"Baseload                  : {bl:.0f} kg/h" if bl else "Baseload                  : geen (geleverd zoals geproduceerd)")
    print(f"Caverne (werkgas)         : {res['storage_GWh']:.0f} GWh, beginvulling {res['storage_init_GWh']:.0f} GWh")
    print(f"Compressoren              : gem. {res['P_comp_avg_MW']:.1f} MW, geïnstalleerd {res['P_comp_installed_MW']:.1f} MW"
          f" (transport {res['P_comp_transport_MW']:.1f}, opslag {res['P_comp_storage_MW']:.1f}); "
          f"{'geconvergeerd' if res['P_comp_converged'] else 'NIET geconvergeerd'} in {res['P_comp_iterations']} iteraties")
    print(f"Leidingdruk               : compressor van {res['p_transport_in_bar']:.1f} naar {res['p_pipeline_inlet_bar']:.1f} bar, uitlaat {res['p_pipeline_outlet_bar']:.1f} bar"
          + (f"; opslagflow verder naar {res['p_storage_pipeline_inlet_bar']:.1f} bar" if res['p_storage_pipeline_inlet_bar'] else ''))
    print(f"Leidingcapaciteit         : productie piek {res['H2_GW_max']:.2f} GW, opslagleiding piek {res['H2_GW_storage']:.2f} GW")
    print(f"Elektrische verliezen     : {res['electrical_losses_pct']:.2f} %   windcapaciteitsfactor {res['wind_capacity_factor']:.3f}"
          f"   loadfactor elektrolyser {res['electrolyser_load_factor']:.3f}")
    if res['wind_missing_hours']:
        print(f"Ontbrekende winduren      : {res['wind_missing_hours']} (geïnterpoleerd)")
    print(f"{'Component':<28}{'n [a]':>7}{'CAPEX [MEUR]':>14}{'CAPEX_a [MEUR]':>16}{'OPEX_a [MEUR]':>15}{'EUR/kg':>9}")
    for r in res['rows']:
        n = '' if np.isnan(r['lifetime_a']) else f"{r['lifetime_a']:.1f}"
        print(f"{r['component']:<28}{n:>7}{r['CAPEX_EUR']/1e6:>14.0f}{r['CAPEX_a_EUR']/1e6:>16.1f}{r['OPEX_a_EUR']/1e6:>15.1f}{r['LCOH_EUR_kg']:>9.3f}")
    print('LCOH per categorie: ' + ', '.join(f'{k} {v:.2f}' for k, v in res['LCOH_by_category'].items() if v > 0))


# =============================================================================
# CHANGELOG t.o.v. de eerdere scripts (final + Vast)
# =============================================================================
# - OPEX = fractie x CAPEX (was: fractie x geannualiseerde CAPEX, factor 1/CRF te laag)
# - degradatie uit; stack-CRF over lifetime_h/8760 jaar; gespreide vervanging
# - opslag cyclisch: baseload = gemiddelde, caverne = max-min van cumulatieve afwijking,
#   geen vrije Storage0 (oude methode blijft beschikbaar als storage_mode='project')
# - verzamelleidingen: L_collect_per_farm x N_farm (Tabel F.4 geeft per park)
# - compressor isentroop: gamma/(gamma-1) en exponent (gamma-1)/(N gamma); van p1 naar p2
#   met p1 = uitlaat verzamelleiding (D1), elektrolyseruitlaat (D2, D3)
# - water: jaarlijkse kostenpost, geen CRF op het 30-jaarsvolume
# - inter-array 350 km per park; verliezen alleen als has_interarray
# - drukval over L segmenten van 1 km (was L-1); scanstap 0,5 bar
# - P_comp automatisch geïtereerd; opslagcompressor op de werkelijke opslagflow
# - vervangingsdubbeltelling verwijderd (CRF per component, of 'system' met vervangingen tegen r)
# - KNMI-inlezing op jaartal in plaats van substring; ontbrekende uren geïnterpoleerd
# - batterij: op LLR is de elektrolyserbelasting P_el x llr (P_BoP werd er dubbel afgetrokken)
# - escalatie vanaf bronjaar behouden (Tabel F.5 toont bronwaarden)
# - twee complete windjaren (2021, 2022) achter elkaar, 15x herhaald
# - CRF standaard op systeemniveau (n_project) met vervangingen verdisconteerd tegen r, geen restwaarde
# - LLR PEM 5 % (was 0), waardoor de batterij in Appendix C-dispatch ook bij PEM kan bijdragen
# - design 3: alle productie naar leverdruk (50 bar), alleen de opslagflow verder naar de inlaat van
#   de 250 km opslagleiding; opslagleiding gedimensioneerd op de piekflow van of naar de caverne


# =============================================================================
# 11. STANDAARD SCENARIOLIJST (Tabel 7) EN HULPFUNCTIES
# =============================================================================
def set_(key, value):
    """Scenariofunctie die één parameter zet."""
    def f(p):
        p[key] = value
        return p
    return f


def set_many(**kv):
    def f(p):
        p.update(kv)
        return p
    return f


def set_elec_capex(value):
    return set_many(capex_PEM=value, capex_Alk=value)


def standard_scenarios(distance_fn, has_electrical=True, has_h2_pipelines=True,
                       scale_applies=True, offshore_process=True):
    """Scenario's uit Tabel 7 plus de offshore-CAPEX x3 run uit par. 4.1.
    distance_fn(p, km) zet afstand tot de kust en het bijbehorende windbestand.
    Elke regel: (groep, parameter, optimistisch, pessimistisch); None = n.v.t."""
    S = [
        ('Technology parameters', 'Electrolyser power consumption',
         set_('power_consumption', 47e3), set_('power_consumption', 69e3)),
        ('Technology parameters', 'Electrolyser CAPEX', set_elec_capex(200.0), set_elec_capex(900.0)),
        ('Technology parameters', 'Electrolyser stack lifetime',
         set_('lifetime_h', 150000.0), set_('lifetime_h', 75000.0)),
        ('Design parameters', 'Distance to shore',
         lambda p: distance_fn(p, 75.0), lambda p: distance_fn(p, 350.0)),
        ('Design parameters', 'Battery capacity', set_('E_batt_GWh', 2.7), set_('E_batt_GWh', 6.7)),
    ]
    if has_h2_pipelines:
        S.append(('Design parameters', 'Hydrogen infrastructure CAPEX', set_('f_h2_infra', 2.0), set_('f_h2_infra', 10.0)))
    if has_electrical:
        S.append(('Design parameters', 'Electrical infrastructure CAPEX', set_('f_el_infra', 0.5), set_('f_el_infra', 2.0)))
    S.append(('Design parameters', 'Baseload', set_('storage_mode', 'none'), None))
    if scale_applies:
        S.append(('Design parameters', 'Economies of scale', set_('f_bop_scale', 0.7), set_('f_bop_scale', 0.9)))
    if offshore_process:
        S.append(('Design parameters', 'Offshore O&M differentiation', None, set_('opex_offshore_process', 0.10)))
        S.append(('Design parameters', 'Offshore process CAPEX x3 (par. 4.1)', None, set_('f_offshore_capex', 3.0)))
    S.append(('Design parameters', 'Discount rate', set_('r', 0.06), set_('r', 0.10)))
    return S


WIND_FILES = {250.0: 'uurgeg_201_2021-2030.txt',
              75.0: 'uurgeg_203_2021-2030_75km.txt',
              350.0: 'uurgeg_205_2021-2030_350km.txt'}
# - batterij: NREL 2021 (Cole et al.), 345 USD2020/kWh, fx 0.876, levensduur 15 j, OPEX 2,5%
# - compressor- en eiland-CAPEX geëscaleerd vanaf 2021 (Tabel F.8: 2.2 EUR2025/MW, 81 MEUR2025 per 500 MW)
# - degradatie als constant vlootgemiddelde: 53,2 x (1 + 0,5 x 0,1%/1000h x 125000h) = 56,5 kWh/kg
