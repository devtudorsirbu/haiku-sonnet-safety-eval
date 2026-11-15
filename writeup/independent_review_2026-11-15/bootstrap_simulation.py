"""Coverage and power of the repo's crossed bootstrap for the paired mitigation effect (simulated data only).

No API calls. Takes a few minutes.

Run from the repo root:  PYTHONPATH=. python _tests/bootstrap_simulation.py
"""
import numpy as np, pandas as pd
from evals import analyze_results as ar
ar.N_BOOT = 1000
ids = [f"c{c:02d}_a{a:02d}" for c in range(1, 9) for a in range(1, 11)]
rng = np.random.default_rng(1)

def simulate(draw_attack_rates, carrier_sd, keep, reps=400):
    """draw_attack_rates() -> 10 baseline success rates; mitigated rate = keep * baseline rate."""
    true = np.mean([draw_attack_rates().mean() for _ in range(4000)]) * (keep - 1)
    cover = sig_cross = sig_item = 0; widths = []
    for _ in range(reps):
        pa = draw_attack_rates()
        mult = np.exp(rng.normal(0, carrier_sd, 8)); mult /= np.exp(carrier_sd ** 2 / 2)
        p = np.clip(mult[:, None] * pa[None, :], 0, 1)                      # carriers x attacks
        base = rng.binomial(2, p) / 2; mit = rng.binomial(2, keep * p) / 2  # 2 samples per cell
        diff = pd.Series((mit - base).ravel(), index=ids)
        _, lo, hi = ar.crossed_bootstrap(diff, rng)
        _, lo_i, hi_i = ar.bootstrap(diff.to_numpy(), rng)
        cover += lo <= true <= hi; sig_cross += hi < 0; sig_item += hi_i < 0; widths.append(hi - lo)
    return true, cover / reps, sig_cross / reps, sig_item / reps, float(np.mean(widths))

scen = {
 "homogeneous, baseline 30% -> 10%": (lambda: np.full(10, 0.30), 0.0, 1/3),
 "homogeneous, baseline 8% -> 2% (the gate's threshold rate)": (lambda: np.full(10, 0.08), 0.0, 0.25),
 "attacks vary (Beta, mean 20%), mitigation removes 2/3": (lambda: rng.beta(0.5, 2.0, 10), 0.4, 1/3),
 "3 of 10 attacks work at 50%, rest 0; mitigation removes 80%": (lambda: np.r_[np.full(3, 0.5), np.zeros(7)], 0.3, 0.2),
 "5 of 10 attacks work at 40%, rest 0; mitigation removes 80%": (lambda: np.r_[np.full(5, 0.4), np.zeros(5)], 0.3, 0.2),
 "no effect, attacks vary (Beta, mean 20%)": (lambda: rng.beta(0.5, 2.0, 10), 0.4, 1.0),
}
print(f"{'scenario':62s} {'true diff':>9s} {'coverage':>9s} {'power(crossed)':>15s} {'power(item)':>12s} {'CI width':>9s}")
for name, (f, sd, keep) in scen.items():
    t, c, sc, si, w = simulate(f, sd, keep)
    print(f"{name:62s} {t*100:>8.1f}pp {c:>9.0%} {sc:>15.0%} {si:>12.0%} {w*100:>7.0f}pp")
print("P(a given set of k attacks is entirely absent from a resample of 10):", {k: round((1 - k/10) ** 10, 4) for k in (1, 2, 3, 4)})
