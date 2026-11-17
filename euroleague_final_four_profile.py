"""What does it take to reach the EuroLeague Final Four? (see final_four_README.md)"""
import os

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ============================================================
# 0. PATHS AND SETTINGS
# ============================================================

try:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    BASE_DIR = os.getcwd()  # fallback when running cell-by-cell (F9) in Spyder

DATA_DIR = os.path.join(BASE_DIR, "..", "csv_euroleague")
IMAGES_DIR = os.path.join(BASE_DIR, "images")
os.makedirs(IMAGES_DIR, exist_ok=True)

N_BOOT = 5000
RNG = np.random.default_rng(42)
MIN_GAMES = 10                     # minimum games for a team-season to enter the comparison
RS_PHASES = ['REGULAR SEASON', 'TOP 16', 'TOP SIXTEEN']
LANE_HALF_WIDTH = 245              # cm
FT_LINE_Y = 580 - 157.5            # cm
BASELINE_Y = -157.5                # cm

plt.rcParams['axes.unicode_minus'] = False
pd.set_option('display.width', 250)
pd.set_option('display.max_columns', 40)
pd.set_option('display.max_rows', 200)

# Light palette (same as the other projects)
BG_COLOR = '#FBFCEE'
BORDER_COLOR = '#D6DFA8'
TEXT_COLOR = '#16233F'
MUTED_COLOR = '#5B6650'
GREEN = '#3E8E4F'
CORAL = '#C6564F'
GOLD = '#B8860B'

# ============================================================
# 1. LOAD DATA
# ============================================================

header = pd.read_csv(os.path.join(DATA_DIR, "euroleague_header.csv"))
box = pd.read_csv(os.path.join(DATA_DIR, "euroleague_box_score.csv"))
comparison = pd.read_csv(os.path.join(DATA_DIR, "euroleague_comparison.csv"))
points = pd.read_csv(
    os.path.join(DATA_DIR, "euroleague_points.csv"),
    usecols=['game_id', 'team_id', 'action_id', 'coord_x', 'coord_y']
)

# ============================================================
# 2. CHAMPIONS: WINNER OF THE FINAL
# ============================================================
# The Final Four has a semifinal round and a final (plus a third place game in most seasons).
# Games are ordered by game_id: the first two are the semifinals, the last one is the final.

ff = header[header['phase'] == 'FINAL FOUR'].sort_values('game_id')
champions = {}
final_four_teams = {}
title_games = []          # semifinals and final (the third place game is not part of the title race)
print("--- CHAMPIONS ---")
for season, games in ff.groupby('season_code'):
    games = games.reset_index(drop=True)
    winner = np.where(games['score_a'] > games['score_b'], games['team_id_a'], games['team_id_b'])
    final = games.iloc[-1]
    semis = games.iloc[:2]
    semi_winners = set(winner[:2])
    consistent = {final['team_id_a'], final['team_id_b']} == semi_winners
    champions[season] = winner[-1]
    final_four_teams[season] = set(games['team_id_a']) | set(games['team_id_b'])
    title_games += list(semis['game_id']) + [final['game_id']]
    print(f"{season}: {len(games)} games, champion {winner[-1]}, finalists are the two semifinal winners: {consistent}")

print(f"\nChampions identified: {len(champions)} seasons (no Final Four in: "
      f"{sorted(set(header['season_code']) - set(champions))})")

# ============================================================
# 3. TEAM-GAME TABLE (box score TOTAL rows, shots from the points file, easy points)
# ============================================================
# The box score has one TOTAL row per team and game: it is the official team line.

team_box = box[box['dorsal'] == 'TOTAL'][[
    'game_id', 'team_id', 'points', 'two_points_made', 'two_points_attempted', 'three_points_made', 'three_points_attempted',
    'free_throws_made', 'free_throws_attempted', 'offensive_rebounds', 'defensive_rebounds', 'turnovers'
]].copy()

tg = team_box.merge(
    header[['game_id', 'season_code', 'phase', 'date', 'team_id_a', 'score_a', 'score_b']], on='game_id', how='left')
tg['venue'] = np.where(tg['team_id'] == tg['team_id_a'], 'Home', 'Away')
tg['pts'] = np.where(tg['venue'] == 'Home', tg['score_a'], tg['score_b'])     # official score
tg = tg.rename(columns={'points': 'box_points'})

# Paint: two-point attempts inside the key. Placeholder coordinates (0, 0) are dropped.
fga = points[points['action_id'].isin(['2FGM', '2FGA', '2FGAB'])].copy()
placeholder = (fga['coord_x'] == 0) & (fga['coord_y'] == 0)
fga = fga[~placeholder & fga[['coord_x', 'coord_y']].notna().all(axis=1)]
in_key = (fga['coord_x'].abs() <= LANE_HALF_WIDTH) & (fga['coord_y'] >= BASELINE_Y) & (fga['coord_y'] <= FT_LINE_Y)
paint = fga[in_key].groupby(['game_id', 'team_id']).agg(
    paint_att=('action_id', 'size'), paint_made=('action_id', lambda s: (s == '2FGM').sum())).reset_index()
tg = tg.merge(paint, on=['game_id', 'team_id'], how='left').fillna({'paint_att': 0, 'paint_made': 0})

# Easy points from the comparison file. Games with 0 for both teams are treated as missing (not real zeros).
easy = []
for side in ['a', 'b']:
    part = comparison[['game_id', f'team_id_{side}', f'fast_break_points_{side}', f'second_chance_points_{side}',
                       f'turnover_points_{side}']].copy()
    part.columns = ['game_id', 'team_id', 'fb', 'sc', 'tp']
    easy.append(part)
easy = pd.concat(easy, ignore_index=True)
for col, a, b in [('fb', 'fast_break_points_a', 'fast_break_points_b'),
                  ('sc', 'second_chance_points_a', 'second_chance_points_b'),
                  ('tp', 'turnover_points_a', 'turnover_points_b')]:
    both_zero = comparison.set_index('game_id')[a] + comparison.set_index('game_id')[b] == 0
    easy.loc[easy['game_id'].map(both_zero), col] = np.nan
tg = tg.merge(easy, on=['game_id', 'team_id'], how='left')

# Attach the opponent's row to each team row
opp_cols = [c for c in tg.columns if c not in ('game_id', 'team_id', 'season_code', 'phase', 'date', 'team_id_a',
                                                'score_a', 'score_b', 'venue')]
opp = tg[['game_id', 'team_id'] + opp_cols].rename(columns={c: c + '_o' for c in opp_cols + ['team_id']})
tg = tg.merge(opp, on='game_id')
tg = tg[tg['team_id'] != tg['team_id_o']].reset_index(drop=True)

# ============================================================
# 3.1 DATA QUALITY CHECKS
# ============================================================

print("\n--- DATA QUALITY CHECKS ---")
print(f"1. Team-game rows: {len(tg):,} for {header['game_id'].nunique():,} games (2 per game)")
mismatch = int((tg['box_points'] != tg['pts']).sum())
print(f"2. TOTAL points different from the official final score: {mismatch} team rows (the official score is used for the margin)")
print(f"3. Shot rows with placeholder coordinates (0, 0), dropped from the paint figures: {int(placeholder.sum())}")
print(f"4. Team-games with missing easy points (both teams at 0): fast break {tg['fb'].isna().sum()}, "
      f"second chance {tg['sc'].isna().sum()}, points off turnovers {tg['tp'].isna().sum()}")
print("   Missing easy points by season (share of team-games):")
print((tg.groupby('season_code')[['fb', 'sc', 'tp']].apply(lambda d: d.isna().mean()) * 100).round(0).T.to_string())

rs = tg[tg['phase'].isin(RS_PHASES)].copy()
print(f"5. Regular season and Top 16 team-games: {len(rs):,}. Phases left out of the comparison: "
      f"{sorted(set(tg['phase']) - set(RS_PHASES))}")


# ============================================================
# 4. TEAM-SEASON STATISTICS
# ============================================================
# Percentages are pooled (sum made / sum attempts). Easy points are per-game means over the games with data.
# 'sign' is +1 when higher is better for the team, -1 when lower is better (stats about the opponent, own turnovers).

STATS = [
    # key, label, group, sign
    ('margin', 'Point differential per game', 'Overall', 1),
    ('efg', 'eFG%', 'Offence', 1),
    ('p2', '2PT%', 'Offence', 1),
    ('p3', '3PT%', 'Offence', 1),
    ('paint', 'Paint FG%', 'Offence', 1),
    ('tov', 'Turnover rate (lower is better)', 'Offence', -1),
    ('orb', 'Offensive rebound %', 'Offence', 1),
    ('ftr', 'FTA per FGA', 'Offence', 1),
    ('efg_o', 'Opponent eFG% (lower is better)', 'Defence', -1),
    ('p2_o', 'Opponent 2PT% (lower is better)', 'Defence', -1),
    ('p3_o', 'Opponent 3PT% (lower is better)', 'Defence', -1),
    ('paint_o', 'Opponent paint FG% (lower is better)', 'Defence', -1),
    ('tov_o', 'Opponent turnover rate', 'Defence', 1),
    ('orb_o', 'Opponent offensive rebound % (lower is better)', 'Defence', -1),
    ('ftr_o', 'Opponent FTA per FGA (lower is better)', 'Defence', -1),
    ('fb', 'Fast break points', 'Easy points', 1),
    ('sc', 'Second chance points', 'Easy points', 1),
    ('tp', 'Points off turnovers', 'Easy points', 1),
    ('fb_o', 'Fast break points allowed (lower is better)', 'Easy points', -1),
    ('sc_o', 'Second chance points allowed (lower is better)', 'Easy points', -1),
    ('tp_o', 'Points off turnovers allowed (lower is better)', 'Easy points', -1),
]
STAT_KEYS = [s[0] for s in STATS]
STAT_LABEL = {s[0]: s[1] for s in STATS}
STAT_GROUP = {s[0]: s[2] for s in STATS}
STAT_SIGN = {s[0]: s[3] for s in STATS}


def team_season_stats(df, min_games=MIN_GAMES):
    """One row per (season, team) from a table of team-games."""
    sums = ['pts', 'two_points_made', 'two_points_attempted', 'three_points_made', 'three_points_attempted',
            'free_throws_attempted', 'offensive_rebounds', 'defensive_rebounds', 'turnovers', 'paint_att', 'paint_made']
    agg = {c: (c, 'sum') for c in sums}
    agg.update({c + '_o': (c + '_o', 'sum') for c in sums})
    agg.update({'score_against': ('pts_o', 'sum'), 'games': ('game_id', 'nunique')})
    for c in ['fb', 'sc', 'tp', 'fb_o', 'sc_o', 'tp_o']:
        agg[c] = (c, 'mean')
        agg[c + '_n'] = (c, 'count')
    g = df.groupby(['season_code', 'team_id']).agg(**agg)
    g = g[g['games'] >= min_games].copy()

    fga_ = g['two_points_attempted'] + g['three_points_attempted']
    fga_o = g['two_points_attempted_o'] + g['three_points_attempted_o']
    out = pd.DataFrame(index=g.index)
    out['games'] = g['games']
    out['margin'] = (g['pts'] - g['score_against']) / g['games']
    out['efg'] = (g['two_points_made'] + 1.5 * g['three_points_made']) / fga_ * 100
    out['efg_o'] = (g['two_points_made_o'] + 1.5 * g['three_points_made_o']) / fga_o * 100
    out['p2'] = g['two_points_made'] / g['two_points_attempted'] * 100
    out['p2_o'] = g['two_points_made_o'] / g['two_points_attempted_o'] * 100
    out['p3'] = g['three_points_made'] / g['three_points_attempted'] * 100
    out['p3_o'] = g['three_points_made_o'] / g['three_points_attempted_o'] * 100
    out['paint'] = g['paint_made'] / g['paint_att'] * 100
    out['paint_o'] = g['paint_made_o'] / g['paint_att_o'] * 100
    out['tov'] = g['turnovers'] / (fga_ + 0.44 * g['free_throws_attempted'] + g['turnovers']) * 100
    out['tov_o'] = g['turnovers_o'] / (fga_o + 0.44 * g['free_throws_attempted_o'] + g['turnovers_o']) * 100
    out['orb'] = g['offensive_rebounds'] / (g['offensive_rebounds'] + g['defensive_rebounds_o']) * 100
    out['orb_o'] = g['offensive_rebounds_o'] / (g['offensive_rebounds_o'] + g['defensive_rebounds']) * 100
    out['ftr'] = g['free_throws_attempted'] / fga_ * 100
    out['ftr_o'] = g['free_throws_attempted_o'] / fga_o * 100
    for c in ['fb', 'sc', 'tp', 'fb_o', 'sc_o', 'tp_o']:
        out[c] = g[c].where(g[c + '_n'] >= 0.8 * g['games'])      # easy points need data for 80% of the games
    return out


season_stats = team_season_stats(rs)
print(f"\nTeam-seasons in the comparison: {len(season_stats)} (at least {MIN_GAMES} games each)")
print("Teams per season:", season_stats.groupby('season_code').size().to_dict())
missing_champ = [(s, t) for s, t in champions.items() if (s, t) not in season_stats.index]
print("Champions missing from the comparison:", missing_champ)


# ============================================================
# 5. HELPERS: z-SCORES WITHIN A SEASON, BOOTSTRAP OVER SEASONS, EXACT TOP-3 TEST
# ============================================================

def season_zscores(stats):
    """z-score and rank of every team within its season, oriented so that positive / rank 1 is the best."""
    z = pd.DataFrame(index=stats.index)
    rk = pd.DataFrame(index=stats.index)
    for key in STAT_KEYS:
        sign = STAT_SIGN[key]
        grp = stats.groupby('season_code')[key]
        z[key] = sign * (stats[key] - grp.transform('mean')) / grp.transform('std')
        rk[key] = (sign * stats[key]).groupby('season_code').rank(ascending=False)
    return z, rk


def boot_mean(values, n_boot=N_BOOT):
    """Mean and 95% percentile interval of the mean, resampling seasons with replacement."""
    values = np.asarray(values, dtype=float)
    values = values[~np.isnan(values)]
    idx = RNG.integers(0, len(values), (n_boot, len(values)))
    means = values[idx].mean(axis=1)
    return values.mean(), *np.percentile(means, [2.5, 97.5])


def prob_at_least(k, probs):
    """P(X >= k) when X is a sum of independent Bernoulli variables with the given probabilities."""
    dist = np.array([1.0])
    for p in probs:
        dist = np.convolve(dist, [1 - p, p])
    return dist[k:].sum()


def benjamini_hochberg(pvals):
    p = np.asarray(pvals, dtype=float)
    order = np.argsort(p)
    ranked = p[order] * len(p) / (np.arange(len(p)) + 1)
    q = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(len(p))
    out[order] = np.minimum(q, 1)
    return out


z_all, rk_all = season_zscores(season_stats)
champ_index = [(s, t) for s, t in champions.items()]
champ_z = z_all.loc[champ_index]
champ_rk = rk_all.loc[champ_index]
n_teams = season_stats.groupby('season_code').size()

# ============================================================
# 6. CHAMPIONS vs ALL OTHER TEAMS (REGULAR SEASON + TOP 16)
# ============================================================

rows = []
for key in STAT_KEYS:
    z = champ_z[key].dropna()
    seasons_used = [s for s, _ in z.index]
    rk = champ_rk[key].loc[z.index]
    probs = [min(1, 3 / n_teams[s]) for s in seasons_used]
    k = int((rk <= 3).sum())
    mean, lo, hi = boot_mean(z.values)
    rows.append({
        'stat': key, 'seasons': len(z), 'mean_z': mean, 'ci_low': lo, 'ci_high': hi,
        'above_avg': int((z > 0).sum()), 'top3': k, 'top3_expected': sum(probs),
        'p_top3': prob_at_least(k, probs), 'best': int((rk == 1).sum()), 'median_rank': rk.median(),
    })
vs_league = pd.DataFrame(rows).set_index('stat')
vs_league['q_top3'] = benjamini_hochberg(vs_league['p_top3'].values)

print("\n=== CHAMPIONS vs ALL TEAMS OF THEIR SEASON (regular season + Top 16) ===")
print("z > 0 means better than the average team of that season. 95% interval by bootstrap over seasons.")
print("p_top3: chance of at least that many top-3 finishes if champions were random teams; q: Benjamini-Hochberg over the 21 stats")
print(vs_league.round(2).to_string())

# ============================================================
# 7. CHAMPIONS vs THE OTHER THREE FINAL FOUR TEAMS
# ============================================================
# A champion is also a strong team. The other Final Four teams are strong too, so this isolates
# what the champion has that the other finalists do not.

rows = []
for key in STAT_KEYS:
    diffs = []
    for season, champ_team in champions.items():
        others = [t for t in final_four_teams[season] if t != champ_team and (season, t) in z_all.index]
        zc = z_all.loc[(season, champ_team), key]
        zo = z_all.loc[[(season, t) for t in others], key].mean()
        diffs.append(zc - zo)
    diffs = np.array(diffs, dtype=float)
    ok = ~np.isnan(diffs)
    mean, lo, hi = boot_mean(diffs[ok])
    rows.append({'stat': key, 'seasons': int(ok.sum()), 'mean_diff_z': mean, 'ci_low': lo, 'ci_high': hi,
                 'champion_better': int((diffs[ok] > 0).sum())})
vs_finalists = pd.DataFrame(rows).set_index('stat')
print("\n=== CHAMPION minus THE OTHER THREE FINAL FOUR TEAMS (difference in z) ===")
print(vs_finalists.round(2).to_string())

# ============================================================
# 8. HOME AND AWAY
# ============================================================
# The same z-scores computed separately on home games and on away games (teams with at least 5 of each).

home_stats = team_season_stats(rs[rs['venue'] == 'Home'], min_games=5)
away_stats = team_season_stats(rs[rs['venue'] == 'Away'], min_games=5)
z_home, _ = season_zscores(home_stats)
z_away, _ = season_zscores(away_stats)

rows = []
for key in STAT_KEYS:
    zh = z_home.reindex(champ_index)[key]
    za = z_away.reindex(champ_index)[key]
    ok = zh.notna() & za.notna()
    diff = (za - zh)[ok].values
    mean_d, lo, hi = boot_mean(diff)
    rows.append({'stat': key, 'seasons': int(ok.sum()), 'home_z': zh[ok].mean(), 'away_z': za[ok].mean(),
                 'away_minus_home': mean_d, 'ci_low': lo, 'ci_high': hi})
home_away = pd.DataFrame(rows).set_index('stat')
print("\n=== CHAMPIONS: z AT HOME vs AWAY (regular season + Top 16) ===")
print(home_away.round(2).to_string())

# ============================================================
# 9. FINAL FOUR GAMES: WINNER vs LOSER
# ============================================================
# Semifinals and final, 3 games per season. Statistics of the two teams in the same game.
# Differences are expressed in standard deviations of a single regular season team-game.

GAME_STATS = ['efg', 'p2', 'p3', 'paint', 'tov', 'orb', 'ftr', 'fb', 'sc', 'tp']


def game_level(df):
    out = pd.DataFrame({'game_id': df['game_id'], 'team_id': df['team_id'], 'season_code': df['season_code']})
    fga_ = df['two_points_attempted'] + df['three_points_attempted']
    out['efg'] = (df['two_points_made'] + 1.5 * df['three_points_made']) / fga_ * 100
    out['p2'] = df['two_points_made'] / df['two_points_attempted'] * 100
    out['p3'] = df['three_points_made'] / df['three_points_attempted'] * 100
    out['paint'] = np.where(df['paint_att'] > 0, df['paint_made'] / df['paint_att'] * 100, np.nan)
    out['tov'] = df['turnovers'] / (fga_ + 0.44 * df['free_throws_attempted'] + df['turnovers']) * 100
    out['orb'] = df['offensive_rebounds'] / (df['offensive_rebounds'] + df['defensive_rebounds_o']) * 100
    out['ftr'] = df['free_throws_attempted'] / fga_ * 100
    for c in ['fb', 'sc', 'tp']:
        out[c] = df[c]
    out['margin'] = df['pts'] - df['pts_o']
    return out


games_all = game_level(tg)
games_rs = games_all[games_all['game_id'].isin(rs['game_id'])]
sd_game = games_rs[GAME_STATS].std()

title = games_all[games_all['game_id'].isin(title_games)]
winners = title[title['margin'] > 0].set_index('game_id')
losers = title[title['margin'] < 0].set_index('game_id')
diff_games = (winners[GAME_STATS] - losers[GAME_STATS].reindex(winners.index))
print(f"\n=== FINAL FOUR GAMES (semifinals and final): {len(diff_games)} games ===")
rows = []
for key in GAME_STATS:
    d = diff_games[key].dropna().values
    idx = RNG.integers(0, len(d), (N_BOOT, len(d)))
    means = d[idx].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    rows.append({'stat': key, 'games': len(d), 'winner_minus_loser': d.mean(), 'ci_low': lo, 'ci_high': hi,
                 'in_sd': d.mean() / sd_game[key], 'sd_low': lo / sd_game[key], 'sd_high': hi / sd_game[key],
                 'winner_higher': int((d > 0).sum())})
ff_games = pd.DataFrame(rows).set_index('stat')
print("Easy points exist only from 2016-17 on, so those rows have fewer games.")
print(ff_games.round(2).to_string())

# Did the better regular season team win? Regular season point differential z of each team.
margin_z = z_all['margin']
better_won, total = 0, 0
for gid in diff_games.index:
    season = winners.loc[gid, 'season_code']
    w, l_ = winners.loc[gid, 'team_id'], losers.loc[gid, 'team_id']
    if (season, w) in margin_z.index and (season, l_) in margin_z.index:
        total += 1
        better_won += int(margin_z[(season, w)] > margin_z[(season, l_)])
from math import comb
p_better = sum(comb(total, k) for k in range(better_won, total + 1)) / 2 ** total
print(f"\nFinal Four games won by the team with the better regular season point differential: "
      f"{better_won} of {total} (chance of at least that many if it were a coin flip: {p_better:.3f})")
print("Champions' regular season point differential rank:", champ_rk['margin'].astype(int).value_counts().sort_index().to_dict())


# ============================================================
# 10. CHARTS
# ============================================================
IMG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'images')
RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')          # result tables (csv)
EXTRA_DIR = os.path.join(RESULTS_DIR, 'title_analysis')   # same analysis for the champions only (not in the report)
os.makedirs(EXTRA_DIR, exist_ok=True)

CHART_STATS = ['margin', 'efg', 'p2', 'p3', 'paint', 'tov', 'orb', 'ftr',
               'efg_o', 'p2_o', 'p3_o', 'paint_o', 'tov_o', 'orb_o', 'ftr_o']

# Chart 1: champions vs the average team of their season.
# Point differential is left out on purpose: it is the outcome (winning more than losing), not a characteristic.
# Shown: the statistics furthest from zero, then the ones whose interval crosses zero.
SD_NOTE = {'efg': '1 SD = 2.7 pts', 'p2': '1 SD = 2.7 pts', 'p3': '1 SD = 2.8 pts', 'ftr': '1 SD = 3.7 pts',
           'tov': '1 SD = 1.5 pts', 'orb': '1 SD = 3.0 pts'}
FAR = ['efg', 'p2', 'ftr', 'efg_o', 'p2_o', 'p3', 'tov', 'ftr_o']
CROSS = ['paint', 'orb', 'tov_o', 'orb_o']
SHOWN = FAR + [None] + CROSS
fig, ax = plt.subplots(figsize=(10, 7), facecolor=BG_COLOR)
ax.set_facecolor(BG_COLOR)
ylabels = []
for i, key in enumerate(SHOWN[::-1]):
    if key is None:
        ylabels.append('')
        continue
    # Raw direction: for 'lower is better' statistics the sign is flipped back, so those sit below zero
    sg = STAT_SIGN[key]
    z = sg * champ_z[key].dropna().values
    jitter = (np.random.default_rng(i).random(len(z)) - 0.5) * 0.35
    ax.scatter(z, np.full(len(z), i) + jitter, s=22, color=GREEN, alpha=0.55, zorder=3)
    r = vs_league.loc[key]
    clear = (r.ci_low > 0)   # clearly better than average, whichever direction 'better' is
    lo_, hi_ = sorted([sg * r.ci_low, sg * r.ci_high])
    ax.plot([lo_, hi_], [i, i], color=TEXT_COLOR if clear else CORAL, lw=2.4, zorder=4)
    ax.scatter([sg * r.mean_z], [i], color=TEXT_COLOR if clear else CORAL, s=50, zorder=5)
    ylabels.append(STAT_LABEL[key].replace(' (lower is better)', ''))
ax.axhline(len(CROSS), color=BORDER_COLOR, lw=1)
ax.axvline(0, color=MUTED_COLOR, lw=1, ls='--')
ax.set_yticks(range(len(SHOWN)))
ax.set_yticklabels(ylabels, color=TEXT_COLOR)
ax.set_xlabel('Distance from the average team of the season, in standard deviations (left = lower than average, right = higher)', color=TEXT_COLOR)
ax.set_title('EuroLeague champions vs all other teams, regular season and Top 16\n18 seasons, 2007-08 to 2025-26',
             color=TEXT_COLOR, pad=14, fontsize=12)
from matplotlib.lines import Line2D
handles = [Line2D([], [], marker='o', ls='', color=GREEN, alpha=0.6, markersize=6, label='each champion'),
           Line2D([], [], color=TEXT_COLOR, lw=2.4, label='95% confidence interval of their average'),
           Line2D([], [], marker='o', ls='', color=TEXT_COLOR, markersize=7, label='better than the average'),
           Line2D([], [], marker='o', ls='', color=CORAL, markersize=7, label='not different from the average')]
ax.set_xlim(-2.7, 3.2)
ax.set_xticks(range(-2, 4))
leg = ax.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, -0.09), ncol=2, frameon=True, facecolor=BG_COLOR, edgecolor=BORDER_COLOR,
                fontsize=8.5, labelcolor=TEXT_COLOR)
ax.text(0.01, 0.98, 'Reference: 1 standard deviation\nis about 2.7 points of eFG% or 3PT%', transform=ax.transAxes,
        ha='left', va='top', color=MUTED_COLOR, fontsize=9)
ax.grid(axis='x', color=BORDER_COLOR, lw=0.6)
for sp in ax.spines.values():
    sp.set_color(BORDER_COLOR)
ax.tick_params(colors=TEXT_COLOR)
fig.savefig(os.path.join(EXTRA_DIR, 'champions_vs_league.png'), dpi=160, bbox_inches='tight', facecolor=BG_COLOR)
plt.show()   # shows the chart in the Spyder Plots pane
plt.close(fig)

# Chart 2: Final Four winner minus loser, in standard deviations of a single game
labels = {'efg': 'Effective FG%', 'p2': '2PT%', 'p3': '3PT%', 'paint': 'Paint FG%', 'tov': 'Turnover rate',
          'orb': 'Offensive rebound %', 'ftr': 'FTA per FGA',
          'fb': 'Fast break points', 'sc': 'Second chance points', 'tp': 'Points off turnovers'}
order = list(labels)[::-1]
fig, ax = plt.subplots(figsize=(9.5, 6), facecolor=BG_COLOR)
ax.set_facecolor(BG_COLOR)
for i, key in enumerate(order):
    r = ff_games.loc[key]
    ax.plot([r.sd_low, r.sd_high], [i, i], color=TEXT_COLOR, lw=2.2)
    ax.scatter([r.in_sd], [i], color=GREEN if r.sd_low > 0 else MUTED_COLOR, s=55, zorder=5)
ax.axvline(0, color=MUTED_COLOR, lw=1, ls='--')
ax.set_yticks(range(len(order)))
ax.set_yticklabels([labels[k] for k in order], color=TEXT_COLOR)
ax.set_xlabel('Winner minus loser, in standard deviations of a regular season game', color=TEXT_COLOR)
ax.set_title('Final Four games (54): what winners did better than losers\n'
             'Green = 95% interval above zero', color=TEXT_COLOR, pad=14)
ax.grid(axis='x', color=BORDER_COLOR, lw=0.6)
for s in ax.spines.values():
    s.set_color(BORDER_COLOR)
ax.tick_params(colors=TEXT_COLOR)
fig.savefig(os.path.join(EXTRA_DIR, 'final_four_winner_vs_loser.png'), dpi=160, bbox_inches='tight', facecolor=BG_COLOR)
plt.show()   # shows the chart in the Spyder Plots pane
plt.close(fig)

vs_league.to_csv(os.path.join(EXTRA_DIR, 'champions_vs_league.csv'))
vs_finalists.to_csv(os.path.join(EXTRA_DIR, 'champions_vs_finalists.csv'))
print("\nCharts saved in", IMG_DIR, "and result tables in", RESULTS_DIR)


# ============================================================
# 11. LOGISTIC REGRESSION: CHAMPION (1) vs EVERY OTHER TEAM (0)
# ============================================================
# One row per team-season (regular season + Top 16). Predictors are the same within-season z-scores as above,
# oriented so that +1 always means one standard deviation better than the average team of that season.
# Only the "four factors" on both sides of the ball are used (8 predictors): with 18 champions, a larger model
# would be unstable. Easy points are left out because they exist for 9 seasons only.
# Point differential is NOT used as a predictor: it is the outcome of winning, not a characteristic.
import warnings
import statsmodels.api as sm
from sklearn.linear_model import LogisticRegression
warnings.filterwarnings('ignore')

FF = ['efg', 'tov', 'orb', 'ftr', 'efg_o', 'tov_o', 'orb_o', 'ftr_o']
reg = z_all[FF].dropna().copy()
reg['champion'] = [int(champions.get(s) == t) for s, t in reg.index]
reg = reg[reg.index.get_level_values('season_code').isin(champions.keys())]
print(f"\n=== LOGISTIC REGRESSION: {len(reg)} team-seasons, {reg['champion'].sum()} champions ===")

X = reg[FF].values
y = reg['champion'].values

# (a) Plain logistic regression with Wald p-values, for reference
plain = sm.Logit(y, sm.add_constant(X)).fit(disp=0)
plain_tab = pd.DataFrame({'odds_ratio': np.exp(plain.params[1:]), 'ci_low': np.exp(plain.conf_int()[1:, 0]),
                          'ci_high': np.exp(plain.conf_int()[1:, 1]), 'p': plain.pvalues[1:]}, index=FF)
print("\n(a) Plain logistic regression. Odds ratio for +1 SD (better than average), 95% Wald interval")
print(plain_tab.round(2).to_string())

# (b) Ridge-penalised logistic regression, bootstrap over seasons (resample whole seasons)
def fit_ridge(Xm, ym, C=1.0):
    return LogisticRegression(C=C, penalty='l2', max_iter=1000).fit(Xm, ym)

ridge = fit_ridge(X, y)
seasons = reg.index.get_level_values('season_code').values
unique_seasons = np.unique(seasons)
by_season = {s: np.where(seasons == s)[0] for s in unique_seasons}
boot_coefs = []
for _ in range(1000):
    draw = RNG.choice(unique_seasons, len(unique_seasons), replace=True)
    idx = np.concatenate([by_season[s] for s in draw])
    if y[idx].sum() == 0:
        continue
    boot_coefs.append(fit_ridge(X[idx], y[idx]).coef_[0])
boot_coefs = np.array(boot_coefs)
ridge_tab = pd.DataFrame({'odds_ratio': np.exp(ridge.coef_[0]),
                          'ci_low': np.exp(np.percentile(boot_coefs, 2.5, axis=0)),
                          'ci_high': np.exp(np.percentile(boot_coefs, 97.5, axis=0))}, index=FF)
print("\n(b) Ridge logistic regression (C=1), 95% interval by bootstrap over seasons")
print(ridge_tab.round(2).to_string())

# (c) Does the model find the champion? Leave one season out: fit on the other seasons, rank that season's teams
def loso_ranks(features, label):
    Xf = reg[features].values
    ranks = []
    for s in unique_seasons:
        test = by_season[s]
        train = np.setdiff1d(np.arange(len(y)), test)
        prob = fit_ridge(Xf[train], y[train]).predict_proba(Xf[test])[:, 1]
        champ_pos = np.where(y[test] == 1)[0][0]
        ranks.append(1 + (prob > prob[champ_pos]).sum())
    ranks = np.array(ranks)
    n_by_season = np.array([len(by_season[s]) for s in unique_seasons])
    return {'model': label, 'champion_ranked_1st': int((ranks == 1).sum()), 'expected_by_chance': (1 / n_by_season).sum(),
            'in_top_3': int((ranks <= 3).sum()), 'top3_expected': (3 / n_by_season).clip(max=1).sum(),
            'median_rank': float(np.median(ranks))}

print("\n(c) Leave-one-season-out: rank of the true champion among the teams of its season")
loso = pd.DataFrame([
    loso_ranks(FF, 'Four factors, both sides (8)'),
    loso_ranks(['efg', 'efg_o'], 'Shooting only: eFG% and opponent eFG% (2)'),
    loso_ranks(['efg', 'tov', 'orb', 'ftr'], 'Offence only (4)'),
    loso_ranks(['efg_o', 'tov_o', 'orb_o', 'ftr_o'], 'Defence only (4)'),
]).set_index('model')
print(loso.round(1).to_string())

# Chart: odds ratios of the ridge model
FF_LABEL = {'efg': 'eFG%', 'tov': 'Turnover rate', 'orb': 'Offensive rebound %', 'ftr': 'FTA per FGA',
            'efg_o': 'Opponent eFG%', 'tov_o': 'Opponent turnover rate',
            'orb_o': 'Opponent offensive rebound %', 'ftr_o': 'Opponent FTA per FGA'}
fig, ax = plt.subplots(figsize=(9.5, 5.8), facecolor=BG_COLOR)
ax.set_facecolor(BG_COLOR)
order_ff = FF[::-1]
for i, key in enumerate(order_ff):
    r = ridge_tab.loc[key]
    clear = r.ci_low > 1   # clearly better than average, whichever direction 'better' is
    col = TEXT_COLOR if clear else CORAL
    sg = STAT_SIGN[key]
    o_, lo_, hi_ = (r.odds_ratio, r.ci_low, r.ci_high) if sg == 1 else (1 / r.odds_ratio, 1 / r.ci_high, 1 / r.ci_low)
    ax.plot([lo_, hi_], [i, i], color=col, lw=2.4)
    ax.scatter([o_], [i], color=col, s=55, zorder=5)
ax.axvline(1, color=MUTED_COLOR, lw=1, ls='--')
ax.set_xscale('log')
ax.set_xticks([0.25, 0.5, 1, 2, 4])
ax.set_xticklabels(['0.25', '0.5', '1', '2', '4'])
ax.xaxis.set_minor_formatter(plt.NullFormatter())
ax.set_yticks(range(len(order_ff)))
ax.set_yticklabels([FF_LABEL[k] for k in order_ff], color=TEXT_COLOR)
ax.set_xlabel('Odds ratio of being champion for +1 standard deviation above the average team\n'
              '(all eight statistics in the same model; 1 = no effect)', color=TEXT_COLOR)
ax.set_title('What goes with winning the EuroLeague, holding the other factors fixed\n'
             '18 seasons, 2007-08 to 2025-26', color=TEXT_COLOR, pad=14, fontsize=12)
handles = [Line2D([], [], color=TEXT_COLOR, lw=2.4, label='95% confidence interval'),
           Line2D([], [], marker='o', ls='', color=TEXT_COLOR, markersize=7, label='better than the average'),
           Line2D([], [], marker='o', ls='', color=CORAL, markersize=7, label='not different from the average')]
ax.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, -0.2), ncol=3, frameon=True, facecolor=BG_COLOR,
          edgecolor=BORDER_COLOR, fontsize=8.5, labelcolor=TEXT_COLOR)
ax.grid(axis='x', color=BORDER_COLOR, lw=0.6)
for sp in ax.spines.values():
    sp.set_color(BORDER_COLOR)
ax.tick_params(colors=TEXT_COLOR)
fig.savefig(os.path.join(EXTRA_DIR, 'champions_regression.png'), dpi=160, bbox_inches='tight', facecolor=BG_COLOR)
plt.show()   # shows the chart in the Spyder Plots pane
plt.close(fig)
ridge_tab.to_csv(os.path.join(EXTRA_DIR, 'champions_regression_ridge.csv'))
plain_tab.to_csv(os.path.join(EXTRA_DIR, 'champions_regression_plain.csv'))


# ============================================================
# 12. LOGISTIC REGRESSION: FINAL FOUR TEAM (1) vs EVERY OTHER TEAM (0)
# ============================================================
# Same predictors and same rows as section 11, but the outcome is reaching the Final Four (4 teams per season,
# 72 events instead of 18). It is a less noisy outcome than winning the title, which also depends on three
# single games in three days.
from sklearn.metrics import roc_auc_score

reg['final_four'] = [int(t in final_four_teams[s]) for s, t in reg.index]
y4 = reg['final_four'].values
print(f"\n=== LOGISTIC REGRESSION, FINAL FOUR: {len(reg)} team-seasons, {y4.sum()} Final Four teams ===")

plain4 = sm.Logit(y4, sm.add_constant(X)).fit(disp=0)
plain4_tab = pd.DataFrame({'odds_ratio': np.exp(plain4.params[1:]), 'ci_low': np.exp(plain4.conf_int()[1:, 0]),
                           'ci_high': np.exp(plain4.conf_int()[1:, 1]), 'p': plain4.pvalues[1:]}, index=FF)
print("\n(a) Plain logistic regression. Odds ratio for +1 SD (better than average), 95% Wald interval")
print(plain4_tab.round(2).to_string())

ridge4 = fit_ridge(X, y4)
boot4 = []
for _ in range(1000):
    draw = RNG.choice(unique_seasons, len(unique_seasons), replace=True)
    idx = np.concatenate([by_season[s] for s in draw])
    boot4.append(fit_ridge(X[idx], y4[idx]).coef_[0])
boot4 = np.array(boot4)
ridge4_tab = pd.DataFrame({'odds_ratio': np.exp(ridge4.coef_[0]),
                           'ci_low': np.exp(np.percentile(boot4, 2.5, axis=0)),
                           'ci_high': np.exp(np.percentile(boot4, 97.5, axis=0))}, index=FF)
print("\n(b) Ridge logistic regression (C=1), 95% interval by bootstrap over seasons")
print(ridge4_tab.round(2).to_string())


def loso_final_four(features, label):
    """Leave one season out: how many of the true four are among the four teams the model ranks highest?"""
    Xf = reg[features].values
    hits, aucs, expected = [], [], []
    for s in unique_seasons:
        test = by_season[s]
        train = np.setdiff1d(np.arange(len(y4)), test)
        prob = fit_ridge(Xf[train], y4[train]).predict_proba(Xf[test])[:, 1]
        top4 = np.argsort(-prob)[:4]
        hits.append(int(y4[test][top4].sum()))
        aucs.append(roc_auc_score(y4[test], prob))
        expected.append(16 / len(test))
    return {'model': label, 'true_four_found_per_season': np.mean(hits), 'expected_by_chance': np.mean(expected),
            'seasons_with_3_or_4_found': int(np.sum(np.array(hits) >= 3)), 'auc': np.mean(aucs)}


print("\n(c) Leave-one-season-out: how many of the 4 real Final Four teams are among the model's top 4")
loso4 = pd.DataFrame([
    loso_final_four(FF, 'Four factors, both sides (8)'),
    loso_final_four(['efg', 'efg_o'], 'Shooting only: eFG% and opponent eFG% (2)'),
    loso_final_four(['efg', 'tov', 'orb', 'ftr'], 'Offence only (4)'),
    loso_final_four(['efg_o', 'tov_o', 'orb_o', 'ftr_o'], 'Defence only (4)'),
]).set_index('model')
print(loso4.round(2).to_string())

fig, ax = plt.subplots(figsize=(9.5, 5.8), facecolor=BG_COLOR)
ax.set_facecolor(BG_COLOR)
for i, key in enumerate(FF[::-1]):
    r = ridge4_tab.loc[key]
    col = TEXT_COLOR if r.ci_low > 1 else CORAL
    sg = STAT_SIGN[key]
    o_, lo_, hi_ = (r.odds_ratio, r.ci_low, r.ci_high) if sg == 1 else (1 / r.odds_ratio, 1 / r.ci_high, 1 / r.ci_low)
    ax.plot([lo_, hi_], [i, i], color=col, lw=2.4)
    ax.scatter([o_], [i], color=col, s=55, zorder=5)
ax.axvline(1, color=MUTED_COLOR, lw=1, ls='--')
ax.set_xscale('log')
ax.set_xticks([0.125, 0.25, 0.5, 1, 2, 4, 8])
ax.set_xticklabels(['0.125', '0.25', '0.5', '1', '2', '4', '8'])
ax.xaxis.set_minor_formatter(plt.NullFormatter())
ax.set_yticks(range(len(FF)))
ax.set_yticklabels([FF_LABEL[k] for k in FF[::-1]], color=TEXT_COLOR)
ax.set_xlabel('Odds ratio of reaching the Final Four for +1 standard deviation above the average team\n'
              '(all eight statistics in the same model; 1 = no effect)', color=TEXT_COLOR)
ax.set_title('What goes with reaching the Final Four, holding the other factors fixed\n'
             '18 seasons, 2007-08 to 2025-26', color=TEXT_COLOR, pad=14, fontsize=12)
ax.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, -0.2), ncol=3, frameon=True, facecolor=BG_COLOR,
          edgecolor=BORDER_COLOR, fontsize=8.5, labelcolor=TEXT_COLOR)
ax.grid(axis='x', color=BORDER_COLOR, lw=0.6)
for sp in ax.spines.values():
    sp.set_color(BORDER_COLOR)
ax.tick_params(colors=TEXT_COLOR)
fig.savefig(os.path.join(IMG_DIR, 'final_four_regression.png'), dpi=160, bbox_inches='tight', facecolor=BG_COLOR)
plt.show()   # shows the chart in the Spyder Plots pane
plt.close(fig)
ridge4_tab.to_csv(os.path.join(RESULTS_DIR, 'final_four_regression_ridge.csv'))


# ============================================================
# 13. FINAL FOUR TEAMS vs ALL OTHER TEAMS (same view as section 6, but for the four qualified teams)
# ============================================================
# The Final Four itself (three single games) is kept as a closed box. Here the question is only which teams get there.
# One value per season = average z of its four Final Four teams; bootstrap over the 18 seasons.
f4_index = [(s, t) for s, teams in final_four_teams.items() for t in teams if (s, t) in z_all.index]
f4_z = z_all.loc[f4_index]
rows = []
for key in CHART_STATS:
    if key == 'margin':
        continue
    per_season = f4_z[key].groupby(level='season_code').mean().dropna()
    mean, lo, hi = boot_mean(per_season.values)
    rows.append({'stat': key, 'teams': int(f4_z[key].notna().sum()), 'mean_z': mean, 'ci_low': lo, 'ci_high': hi,
                 'above_avg': int((f4_z[key] > 0).sum())})
f4_vs_league = pd.DataFrame(rows).set_index('stat')
print("\n=== FINAL FOUR TEAMS vs ALL TEAMS OF THEIR SEASON (regular season + Top 16) ===")
print("z > 0 means better than the average team of that season. Interval by bootstrap over seasons.")
print(f4_vs_league.round(2).to_string())

f4_far = f4_vs_league[f4_vs_league['ci_low'] > 0].sort_values('mean_z', ascending=False).index.tolist()
f4_cross = f4_vs_league[f4_vs_league['ci_low'] <= 0].sort_values('mean_z', ascending=False).index.tolist()
shown = f4_far + ([None] if f4_cross else []) + f4_cross
fig, ax = plt.subplots(figsize=(10, 7.5), facecolor=BG_COLOR)
ax.set_facecolor(BG_COLOR)
for i, key in enumerate(shown[::-1]):
    if key is None:
        continue
    sg = STAT_SIGN[key]
    z = sg * f4_z[key].dropna().values
    jitter = (np.random.default_rng(i).random(len(z)) - 0.5) * 0.4
    ax.scatter(z, np.full(len(z), i) + jitter, s=18, color=GREEN, alpha=0.5, zorder=3)
    r = f4_vs_league.loc[key]
    col = TEXT_COLOR if r.ci_low > 0 else CORAL
    lo_, hi_ = sorted([sg * r.ci_low, sg * r.ci_high])
    ax.plot([lo_, hi_], [i, i], color=col, lw=2.4, zorder=4)
    ax.scatter([sg * r.mean_z], [i], color=col, s=50, zorder=5)
if f4_cross:
    ax.axhline(len(f4_cross), color=BORDER_COLOR, lw=1)
ax.axvline(0, color=MUTED_COLOR, lw=1, ls='--')
ax.set_yticks(range(len(shown)))
ax.set_yticklabels([('' if k is None else STAT_LABEL[k].replace(' (lower is better)', '')) for k in shown[::-1]],
                   color=TEXT_COLOR)
ax.set_xlim(-3.2, 3.2)
ax.set_xticks(range(-3, 4))
ax.set_xlabel('Distance from the average team of the season, in standard deviations (left = lower than average, right = higher)',
              color=TEXT_COLOR)
ax.set_title('EuroLeague Final Four teams vs all other teams, regular season and Top 16\n18 seasons, 2007-08 to 2025-26',
             color=TEXT_COLOR, pad=14, fontsize=12)
handles4 = [Line2D([], [], marker='o', ls='', color=GREEN, alpha=0.6, markersize=6, label='each Final Four team'),
            Line2D([], [], color=TEXT_COLOR, lw=2.4, label='95% confidence interval of their average'),
            Line2D([], [], marker='o', ls='', color=TEXT_COLOR, markersize=7, label='better than the average'),
            ] + ([Line2D([], [], marker='o', ls='', color=CORAL, markersize=7, label='not different from the average')]
                 if f4_cross else [])
ax.legend(handles=handles4, loc='upper center', bbox_to_anchor=(0.5, -0.09), ncol=2, frameon=True, facecolor=BG_COLOR,
          edgecolor=BORDER_COLOR, fontsize=8.5, labelcolor=TEXT_COLOR)
ax.grid(axis='x', color=BORDER_COLOR, lw=0.6)
for sp in ax.spines.values():
    sp.set_color(BORDER_COLOR)
ax.tick_params(colors=TEXT_COLOR)
fig.savefig(os.path.join(IMG_DIR, 'final_four_teams_vs_league.png'), dpi=160, bbox_inches='tight', facecolor=BG_COLOR)
plt.show()   # shows the chart in the Spyder Plots pane
plt.close(fig)
f4_vs_league.to_csv(os.path.join(RESULTS_DIR, 'final_four_teams_vs_league.csv'))


# ============================================================
# 14. HOW ROBUST ARE THE FINAL FOUR RESULTS?
# ============================================================
from scipy import stats as sps

print("\n=== ROBUSTNESS OF THE FINAL FOUR RESULTS ===")

# (a) Test set accuracy against random picks. For each season the model (trained on the 17 other seasons) picks 4 teams;
#     hits = how many of them are real Final Four teams. Random picks: 4 teams drawn at random in each season.
def loso_hits(features):
    Xf = reg[features].values
    hits = []
    for s in unique_seasons:
        test = by_season[s]
        train = np.setdiff1d(np.arange(len(y4)), test)
        prob = fit_ridge(Xf[train], y4[train]).predict_proba(Xf[test])[:, 1]
        hits.append(int(y4[test][np.argsort(-prob)[:4]].sum()))
    return np.array(hits)

hits_full = loso_hits(FF)
hits_shoot = loso_hits(['efg', 'efg_o'])
sizes = np.array([len(by_season[s]) for s in unique_seasons])
null_rng = np.random.default_rng(7)
null_means = np.empty(20000)
for b in range(20000):
    h = [(null_rng.permutation(n)[:4] < 4).sum() for n in sizes]      # first 4 positions = the real four
    null_means[b] = np.mean(h)
p_random = (null_means >= hits_full.mean()).mean()
b_idx = null_rng.integers(0, len(hits_full), (N_BOOT, len(hits_full)))
ci_full = np.percentile(hits_full[b_idx].mean(axis=1), [2.5, 97.5])
diff_boot = (hits_full - hits_shoot)[b_idx].mean(axis=1)
print(f"(a) Test set: full model finds {hits_full.mean():.2f} of 4 per season (95% interval {ci_full[0]:.2f} to {ci_full[1]:.2f}); "
      f"random picks find {null_means.mean():.2f} (95th percentile {np.percentile(null_means, 95):.2f}, "
      f"highest of 20,000 random draws {null_means.max():.2f}); p = {max(p_random, 1/20000):.5f}")
print(f"    Shooting only finds {hits_shoot.mean():.2f}. Full minus shooting only: {np.mean(hits_full - hits_shoot):+.2f} "
      f"(95% interval {np.percentile(diff_boot, 2.5):+.2f} to {np.percentile(diff_boot, 97.5):+.2f})")

# (b) Do the six other statistics add anything to the two shooting statistics? Likelihood ratio test.
full_fit = sm.Logit(y4, sm.add_constant(reg[FF].values)).fit(disp=0)
shoot_fit = sm.Logit(y4, sm.add_constant(reg[['efg', 'efg_o']].values)).fit(disp=0)
lr = 2 * (full_fit.llf - shoot_fit.llf)
print(f"(b) Likelihood ratio test, 6 added statistics vs shooting only: chi2 = {lr:.1f}, df = 6, p = {sps.chi2.sf(lr, 6):.5f}")
# Same, one added statistic at a time on top of the two shooting statistics
for k in ['tov', 'orb', 'ftr', 'tov_o', 'orb_o', 'ftr_o']:
    f1 = sm.Logit(y4, sm.add_constant(reg[['efg', 'efg_o', k]].values)).fit(disp=0)
    lr1 = 2 * (f1.llf - shoot_fit.llf)
    print(f"    adding {FF_LABEL[k]:30s} chi2 = {lr1:5.1f}, p = {sps.chi2.sf(lr1, 1):.4f}")

# (c) Two eras: 2007-08 to 2015-16 (24 teams, Top 16) and 2016-17 to 2025-26 (16 to 20 teams, regular season and play-offs)
era = np.array([int(s[1:]) <= 2015 for s in seasons])
print("\n(c) Odds ratios (ridge, +1 SD better than average) fitted separately on the two eras")
rows = []
for name, mask in [('2007-08 to 2015-16', era), ('2016-17 to 2025-26', ~era)]:
    m = fit_ridge(X[mask], y4[mask])
    rows.append(pd.Series(np.exp(m.coef_[0]), index=FF, name=f"{name} ({int(y4[mask].sum())} Final Four teams)"))
print(pd.concat(rows, axis=1).round(2).to_string())

# (d) Drop one season at a time: range of the odds ratio
jack = []
for s in unique_seasons:
    keep = seasons != s
    jack.append(np.exp(fit_ridge(X[keep], y4[keep]).coef_[0]))
jack = np.array(jack)
jt = pd.DataFrame({'full_sample': ridge4_tab['odds_ratio'], 'min_without_one_season': jack.min(axis=0),
                   'max_without_one_season': jack.max(axis=0)}, index=FF)
print("\n(d) Odds ratio (+1 SD better than average) dropping one season at a time")
print(jt.round(2).to_string())

# (e) Size of the gaps in real units: season average standard deviation of each statistic across teams
print("\n(e) Gap of the Final Four teams in the units of each statistic (mean difference from the season average)")
real_units = []
for key in ['efg', 'p2', 'p3', 'tov', 'orb', 'ftr', 'efg_o', 'tov_o', 'orb_o', 'ftr_o']:
    f4_vals = season_stats.loc[f4_index, key]
    season_mean = season_stats.groupby('season_code')[key].transform('mean').loc[f4_index]
    per_season = (f4_vals - season_mean).groupby(level='season_code').mean()
    m, lo, hi = boot_mean(per_season.values)
    real_units.append({'stat': key, 'gap_points': m, 'ci_low': lo, 'ci_high': hi,
                       'one_sd_points': season_stats.groupby('season_code')[key].std().mean()})
real_units = pd.DataFrame(real_units).set_index('stat')
print(real_units.round(2).to_string())
real_units.to_csv(os.path.join(RESULTS_DIR, 'final_four_gaps_in_real_units.csv'))


# ============================================================
# 15. PREDICTION TEST IN DETAIL, PRACTICAL MEANING OF THE ODDS RATIOS, CHAMPIONS IN REAL UNITS
# ============================================================
from scipy.stats import hypergeom

print("\n=== PREDICTION TEST IN DETAIL ===")
dist_model = pd.Series(hits_full).value_counts().reindex(range(5), fill_value=0)
exp_random = np.array([sum(hypergeom.pmf(k, n, 4, 4) for n in sizes) for k in range(5)])
print("Seasons by number of real Final Four teams found among the model's 4 picks (model vs random expectation):")
print(pd.DataFrame({'model': dist_model.values, 'random_expected': exp_random.round(2)}, index=range(5)).T.to_string())
p_3plus_random = np.mean([hypergeom.sf(2, n, 4, 4) for n in sizes])
print(f"Chance that 4 random picks find 3 or more in one season: {p_3plus_random:.3f} (about 1 in {1 / p_3plus_random:.0f})")

# Picks of the model in each season (trained on the other 17), to give examples
picks = {}
for s in unique_seasons:
    test = by_season[s]
    train = np.setdiff1d(np.arange(len(y4)), test)
    prob = fit_ridge(X[train], y4[train]).predict_proba(X[test])[:, 1]
    teams_s = reg.index.get_level_values('team_id').values[test]
    top4 = teams_s[np.argsort(-prob)[:4]]
    picks[s] = (list(top4), sorted(final_four_teams[s]))
for s in unique_seasons[-4:]:
    print(s, 'model picks:', picks[s][0], '| real Final Four:', picks[s][1],
          '| found:', len(set(picks[s][0]) & set(picks[s][1])))

# Practical meaning of the odds ratios, for a team that is average on all eight statistics
b0 = ridge4.intercept_[0]
coef = dict(zip(FF, ridge4.coef_[0]))
sig = lambda v: 1 / (1 + np.exp(-v))
print(f"\nProbability for a team average on all 8 statistics: {sig(b0):.3f}")
for k in ['efg', 'efg_o', 'orb', 'tov', 'tov_o']:
    print(f"  +1 SD better on {k}: {sig(b0 + coef[k]):.3f};  +2 SD: {sig(b0 + 2 * coef[k]):.3f};  1 SD worse: {sig(b0 - coef[k]):.3f}")
for p0 in [0.05, 0.20, 0.50]:
    o = p0 / (1 - p0)
    print(f"  start {p0:.0%}: x4.94 -> {o * 4.94 / (1 + o * 4.94):.3f};  x0.18 -> {o * 0.18 / (1 + o * 0.18):.3f}")

# Champions in real units
print("\n=== CHAMPIONS: gap from the season average in real units (percentage points) ===")
champ_units = []
for key in ['efg', 'p2', 'p3', 'tov', 'orb', 'ftr', 'efg_o', 'tov_o', 'orb_o', 'ftr_o']:
    vals = season_stats.loc[champ_index, key]
    sm_ = season_stats.groupby('season_code')[key].transform('mean').loc[champ_index]
    d = (vals - sm_).dropna().values
    m, lo, hi = boot_mean(d)
    champ_units.append({'stat': key, 'gap_points': m, 'ci_low': lo, 'ci_high': hi})
champ_units = pd.DataFrame(champ_units).set_index('stat')
print(champ_units.round(2).to_string())
champ_units.to_csv(os.path.join(EXTRA_DIR, 'champions_gaps_in_real_units.csv'))
