#include "kelly.h"

#include <cmath>
#include <random>
#include <vector>

namespace kelly {

double american_to_decimal(long odds) {
    return odds > 0 ? 1.0 + odds / 100.0 : 1.0 + 100.0 / (-odds);
}

double implied_prob(long odds) {
    return odds > 0 ? 100.0 / (odds + 100.0)
                    : static_cast<double>(-odds) / ((-odds) + 100.0);
}

double novig(long odds_a, long odds_b) {
    double a = implied_prob(odds_a);
    double b = implied_prob(odds_b);
    return a / (a + b);
}

double expected_value(double p, long odds) {
    double dec = american_to_decimal(odds);
    return p * (dec - 1.0) - (1.0 - p);
}

double kelly_fraction(double p, long odds) {
    double b = american_to_decimal(odds) - 1.0;
    if (b <= 0.0) return 0.0;
    double f = (p * b - (1.0 - p)) / b;
    return f > 0.0 ? f : 0.0;
}

// Round half to even, matching Python's round() so decimal->american agrees
// with the odds_math.py oracle at .5 boundaries.
static long round_half_even(double x) {
    double r = std::nearbyint(x);  // honors the current (default: to-nearest-even) mode
    return static_cast<long>(r);
}

long decimal_to_american(double dec) {
    double b = dec - 1.0;
    return b >= 1.0 ? round_half_even(b * 100.0) : round_half_even(-100.0 / b);
}

int kelly_tier(double p, long odds) {
    if (expected_value(p, odds) <= 0.0) return 0;  // pass
    double k = kelly_fraction(p, odds);
    if (k >= 0.06) return 3;  // full
    if (k >= 0.03) return 2;  // half
    return 1;                 // quarter
}

LineMove line_move(double open_line, double current_line) {
    double delta = current_line - open_line;
    double steam = std::fabs(delta) * 1.4;
    if (steam > 1.0) steam = 1.0;
    return {delta, steam};
}

double inv_normal_cdf(double p) {
    // Acklam's rational approximation (|error| < 1.15e-9).
    static const double a[] = {-3.969683028665376e+01, 2.209460984245205e+02,
                               -2.759285104469687e+02, 1.383577518672690e+02,
                               -3.066479806614716e+01, 2.506628277459239e+00};
    static const double b[] = {-5.447609879822406e+01, 1.615858368580409e+02,
                               -1.556989798598866e+02, 6.680131188771972e+01,
                               -1.328068155288572e+01};
    static const double c[] = {-7.784894002430293e-03, -3.223964580411365e-01,
                               -2.400758277161838e+00, -2.549732539343734e+00,
                               4.374664141464968e+00, 2.938163982698783e+00};
    static const double d[] = {7.784695709041462e-03, 3.224671290700398e-01,
                               2.445134137142996e+00, 3.754408661907416e+00};
    const double plow = 0.02425, phigh = 1.0 - 0.02425;
    if (p < plow) {
        double q = std::sqrt(-2.0 * std::log(p));
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) /
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1.0);
    }
    if (p > phigh) {
        double q = std::sqrt(-2.0 * std::log(1.0 - p));
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) /
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1.0);
    }
    double q = p - 0.5, r = q * q;
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q /
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1.0);
}

ParlayResult parlay(const double* probs, const long* odds, const int* game_ids,
                    long n, double rho, long nsims) {
    ParlayResult res{};
    double combined_dec = 1.0, naive_prob = 1.0;
    for (long i = 0; i < n; ++i) {
        combined_dec *= american_to_decimal(odds[i]);
        naive_prob *= probs[i];
    }
    res.corr_pairs = 0;
    int max_game = -1;
    for (long i = 0; i < n; ++i) {
        if (game_ids[i] > max_game) max_game = game_ids[i];
        for (long j = i + 1; j < n; ++j)
            if (game_ids[i] == game_ids[j]) ++res.corr_pairs;
    }

    res.american = n ? decimal_to_american(combined_dec) : 0;
    res.naive_prob = n ? naive_prob : 1.0;
    res.naive_ev = n ? naive_prob * (combined_dec - 1.0) - (1.0 - naive_prob) : 0.0;

    // Monte-Carlo correlation adjustment (single-factor Gaussian copula).
    if (n > 0 && nsims > 0 && res.corr_pairs > 0 && rho > 0.0) {
        std::vector<double> z(n);
        for (long i = 0; i < n; ++i) z[i] = inv_normal_cdf(probs[i]);
        double a_load = std::sqrt(rho), b_load = std::sqrt(1.0 - rho);

        std::mt19937_64 rng(42);  // fixed seed => reproducible
        std::normal_distribution<double> norm(0.0, 1.0);
        std::vector<double> game_factor(max_game + 1);

        long hits = 0;
        for (long s = 0; s < nsims; ++s) {
            for (int g = 0; g <= max_game; ++g) game_factor[g] = norm(rng);
            bool all = true;
            for (long i = 0; i < n; ++i) {
                double latent = a_load * game_factor[game_ids[i]] + b_load * norm(rng);
                if (latent > z[i]) { all = false; break; }
            }
            if (all) ++hits;
        }
        res.corr_prob = static_cast<double>(hits) / nsims;
    } else {
        res.corr_prob = res.naive_prob;  // no correlated legs -> independence holds
    }

    res.corr_ev = n ? res.corr_prob * (combined_dec - 1.0) - (1.0 - res.corr_prob) : 0.0;
    res.max_exposure = res.corr_ev > 0.0 ? res.corr_ev / 2.0 : 0.0;
    if (res.max_exposure > 0.02) res.max_exposure = 0.02;
    return res;
}

}  // namespace kelly
