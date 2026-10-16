# -*- coding: utf-8 -*-
"""
make_figures.py
Leest results/*.json en results/*.csv van de drie configuratiescripts en maakt
  figures/lcoh_configurations_2025.png      Fig. 4  (gestapelde LCOH per component)
  figures/tornado_<config>.png              Fig. 5, 6, 7 (gelijke grootte en gelijke x-span)
  results/summary_all.csv                   kengetallen per configuratie
  results/latex_tables.tex                  rijen voor Tabel 8, 9, 10, F.4 en de tekst in par. 3.3
Draaien na de drie configuratiescripts:  python make_figures.py
"""
import json
import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

RES, FIG = 'results', 'figures'
os.makedirs(FIG, exist_ok=True)

CONFIGS = [('offshore_decentral', 'Offshore decentral'),
           ('offshore_central', 'Offshore central'),
           ('onshore_central', 'Onshore central')]

# volgorde en opmaak zoals in de huidige Fig. 4
CATS = ['Wind turbines', 'Electrolyser stack', 'Electrolyser BoP', 'Water feed',
        'Storage', 'Hub', 'Transmission', 'Compressor', 'Battery']
LABELS = {'Transmission': 'Transmission'}
COLORS = ['#66c2a5', '#fc8d62', '#8da0cb', '#e78ac3', '#a6d854', '#ffd92f', '#e5c494', '#b3b3b3', '#7570b3']
HATCHES = ['', '//', 'xx', '..', '\\\\', 'oo', '--', '**', '++']

base = {}
for tag, _ in CONFIGS:
    path = os.path.join(RES, f'{tag}_base.json')
    if os.path.exists(path):
        with open(path) as f:
            base[tag] = json.load(f)
if not base:
    raise SystemExit('geen results/*_base.json gevonden; draai eerst de configuratiescripts')
tags = [t for t, _ in CONFIGS if t in base]
names = [n for t, n in CONFIGS if t in base]

# ---------------------------------------------------------------- Fig. 4
M = np.array([[base[t]['LCOH_by_category'].get(c, 0.0) for c in CATS] for t in tags])
use = [i for i, c in enumerate(CATS) if M[:, i].max() > 0]
fig, ax = plt.subplots(figsize=(7, 4))
x = np.arange(len(tags)); bottom = np.zeros(len(tags))
for i in use:
    ax.bar(x, M[:, i], bottom=bottom, color=COLORS[i], edgecolor='black', hatch=HATCHES[i], label=LABELS.get(CATS[i], CATS[i]))
    bottom += M[:, i]
for xi, tot in zip(x, bottom):
    ax.text(xi, tot + 0.05, f'{tot:.1f}', ha='center', va='bottom', fontsize=9)
ax.set_ylabel('EUR$_{2025}$/kg H$_2$', fontsize=10)
ax.set_xticks(x); ax.set_xticklabels(names, fontsize=9)
ax.set_ylim(0, np.ceil(bottom.max() * 2 + 1) / 2)
ax.yaxis.grid(True, linestyle='--', linewidth=0.5, alpha=0.7); ax.set_axisbelow(True)
h, l = ax.get_legend_handles_labels()
ax.legend(h[::-1], l[::-1], fontsize=8, loc='center left', bbox_to_anchor=(1.02, 0.5), frameon=False)
ax.spines[['top', 'right']].set_visible(False)
plt.tight_layout()
fig.savefig(os.path.join(FIG, 'lcoh_configurations_2025.png'), dpi=600, bbox_inches='tight', facecolor='white')
fig.savefig(os.path.join(FIG, 'lcoh_configurations_2025.pdf'), bbox_inches='tight', facecolor='white')
plt.close(fig)

# ---------------------------------------------------------------- tornado's
sa = {t: pd.read_csv(os.path.join(RES, f'{t}_SA.csv')) for t in tags if os.path.exists(os.path.join(RES, f'{t}_SA.csv'))}
if sa:
    span = max((d[['Min', 'Max']].to_numpy() - d['Nominal'].to_numpy()[:, None]).__abs__().max() for d in sa.values())
    span = np.ceil(span * 1.25 * 20) / 20
    n_rows = max(len(d) for d in sa.values())
    for t, name in zip(tags, names):
        if t not in sa:
            continue
        df = sa[t].copy()
        df['Low dev'] = df['Min'] - df['Nominal']; df['High dev'] = df['Max'] - df['Nominal']
        df['Impact'] = (df['High dev'] - df['Low dev']).abs()
        df = df.sort_values('Impact', ascending=True).reset_index(drop=True)
        nom = float(df['Nominal'].iloc[0])
        fig, ax = plt.subplots(figsize=(9, 0.45 * n_rows + 1.2))
        y = np.arange(len(df))
        ax.barh(y, df['High dev'], left=nom, color='#1f77b4', label='+10% input')
        ax.barh(y, df['Low dev'], left=nom, color='#ff7f0e', label='-10% input')
        ax.axvline(nom, color='k', linewidth=1)
        pad = 0.012 * 2 * span
        for i, row in df.iterrows():
            ax.text(nom + row['High dev'] + pad, i, f"{row['pct_max']:+.1f}%", va='center', fontsize=8)
            ax.text(nom + row['Low dev'] - pad, i, f"{row['pct_min']:+.1f}%", va='center', ha='right', fontsize=8)
        ax.set_yticks(y); ax.set_yticklabels(df['Parameter'], fontsize=9)
        ax.set_ylim(-0.7, n_rows - 0.3)
        ax.set_xlim(nom - span, nom + span)
        ax.set_xlabel('LCOH (EUR$_{2025}$/kg)')
        ax.set_title(f'{name} configuration: sensitivity analysis', fontsize=10)
        ax.legend(loc='lower right', fontsize=8, frameon=False)
        ax.spines[['top', 'right']].set_visible(False)
        plt.tight_layout()
        fig.savefig(os.path.join(FIG, f'tornado_{t}.png'), dpi=600, bbox_inches='tight', facecolor='white')
        fig.savefig(os.path.join(FIG, f'tornado_{t}.pdf'), bbox_inches='tight', facecolor='white')
        plt.close(fig)

# ---------------------------------------------------------------- samenvatting en LaTeX
rows = []
for t, name in zip(tags, names):
    b = base[t]
    rows.append(dict(configuration=name, P_each_MW=b['P_each_MW'], LCOH=b['LCOH'], H2_kt_a=b['H2_kt_a'],
                     baseload_kg_h=b['baseload_kg_h'], storage_GWh=b['storage_GWh'], storage_init_GWh=b['storage_init_GWh'],
                     P_comp_avg_MW=b['P_comp_avg_MW'], P_comp_installed_MW=b['P_comp_installed_MW'],
                     electrical_losses_pct=b['electrical_losses_pct'], electrolyser_load_factor=b['electrolyser_load_factor'],
                     wind_capacity_factor=b['wind_capacity_factor'],
                     **{f'LCOH_{c}': b['LCOH_by_category'].get(c, 0.0) for c in CATS}))
summary = pd.DataFrame(rows)
summary.to_csv(os.path.join(RES, 'summary_all.csv'), index=False)


def fmt(v, nd=1):
    return '-' if (v is None or (isinstance(v, float) and np.isnan(v))) else f'{v:.{nd}f}'


tex = []
tex.append('% ---- Fig. 4 / par. 3.3: LCOH per categorie [EUR2025/kg]')
tex.append('Category & ' + ' & '.join(names) + ' \\\\')
for c in CATS:
    vals = [base[t]['LCOH_by_category'].get(c, 0.0) for t in tags]
    if max(vals) > 0:
        tex.append(f'{c} & ' + ' & '.join(f'{v:.2f}' for v in vals) + ' \\\\')
tex.append('Total & ' + ' & '.join(f"{base[t]['LCOH']:.2f}" for t in tags) + ' \\\\')
tex.append('')
tex.append('% ---- par. 3.3: geinstalleerde elektrolysercapaciteit per turbine [MW]')
tex.append(' & '.join(f"{n}: {base[t]['P_each_MW']:.2f}" for t, n in zip(tags, names)))
tex.append('')
tex.append('% ---- Tabel F.4 (onderste rijen)')
tex.append('Installed compressor capacity & MW & ' + ' & '.join(f"{base[t]['P_comp_installed_MW']:.0f}" for t in tags) + ' \\\\')
tex.append('Average compressor power consumption & MW & ' + ' & '.join(f"{base[t]['P_comp_avg_MW']:.0f}" for t in tags) + ' \\\\')
tex.append('Baseload & kg/h & ' + ' & '.join(fmt(base[t]['baseload_kg_h'], 0) for t in tags) + ' \\\\')
tex.append('Salt cavern working gas capacity & GWh & ' + ' & '.join(f"{base[t]['storage_GWh']:.0f}" for t in tags) + ' \\\\')
tex.append('Electrical losses & \\% & ' + ' & '.join(f"{base[t]['electrical_losses_pct']:.1f}" for t in tags) + ' \\\\')
tex.append('Annual hydrogen production & kt/a & ' + ' & '.join(f"{base[t]['H2_kt_a']:.0f}" for t in tags) + ' \\\\')
tex.append('')
for t, name in zip(tags, names):
    path = os.path.join(RES, f'{t}_ScA.csv')
    if not os.path.exists(path):
        continue
    d = pd.read_csv(path)
    tex.append(f'% ---- Scenario-tabel {name} (Tabel 8/9/10)')
    for grp in d['Group'].unique():
        tex.append(f'\\multicolumn{{4}}{{c}}{{\\textit{{{grp}}}}} \\\\')
        for _, r in d[d['Group'] == grp].iterrows():
            tex.append(f"{r['Parameter']} & {fmt(r['Optimistic'])} & {r['Selected']:.1f} & {fmt(r['Pessimistic'])} \\\\")
    tex.append('')
with open(os.path.join(RES, 'latex_tables.tex'), 'w') as f:
    f.write('\n'.join(tex))

print(summary.T.to_string())
print('\nFiguren in', FIG, '; LaTeX-rijen in', os.path.join(RES, 'latex_tables.tex'))
