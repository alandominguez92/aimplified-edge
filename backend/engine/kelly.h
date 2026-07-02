// AimplifiedEdge C++ EV / Kelly engine.
//
// Pure math, mirroring the Python reference in app/engine/odds_math.py (which is
// the oracle the build is verified against). Exposed to Python as a subprocess
// binary (see main.cpp); the same functions could back a pybind11 module.
#pragma once

namespace kelly {

// American odds -> decimal payout multiplier (-120 -> 1.8333, +130 -> 2.30).
double american_to_decimal(long odds);

// Implied probability from American odds, INCLUDING the book's vig.
double implied_prob(long odds);

// Vig-free fair probability for side A of a two-way market.
double novig(long odds_a, long odds_b);

// Expected value per 1 unit staked (0.05 == +5% EV).
double expected_value(double p, long odds);

// Full-Kelly fraction of bankroll; clamped at 0 (never stake -EV).
double kelly_fraction(double p, long odds);

// Decimal odds -> American (Python-compatible round-half-to-even).
long decimal_to_american(double dec);

// Coarse staking tier: 0 pass, 1 quarter, 2 half, 3 full.
int kelly_tier(double p, long odds);

// Line-movement delta + a normalized "steam" magnitude (0..1 at ~1.0 K move).
struct LineMove {
    double delta;
    double steam;
};
LineMove line_move(double open_line, double current_line);

// Inverse standard-normal CDF (Acklam's approximation).
double inv_normal_cdf(double p);

// Parlay evaluation with a Monte-Carlo correlation adjustment.
//
// Legs sharing a game_id are positively correlated (one game script drives both
// strikeout totals). We model this with a single-factor Gaussian copula: each
// leg's latent = sqrt(rho)*gameFactor + sqrt(1-rho)*idiosyncratic, and the leg
// "hits" when latent <= invPhi(p). `nsims` joint draws estimate the TRUE combined
// probability, which independence (the naive product) gets wrong for same-game
// legs. This is the compute-heavy path that justifies C++.
struct ParlayResult {
    long american;      // combined price from the legs' odds
    double naive_prob;  // product of leg probs (independence assumption)
    double corr_prob;   // MC estimate accounting for same-game correlation
    double naive_ev;    // EV under independence
    double corr_ev;     // EV under the correlation-adjusted probability
    int corr_pairs;     // count of same-game leg pairs
    double max_exposure;
};

ParlayResult parlay(const double* probs, const long* odds, const int* game_ids,
                    long n, double rho, long nsims);

}  // namespace kelly
