// CLI front-end for the EV/Kelly engine. Whitespace protocol (no JSON dep):
//
//   kelly_engine eval      stdin: "<prob> <odds>" per line
//                          stdout: "<implied> <decimal> <ev> <kelly> <edge> <tier>"
//   kelly_engine parlay    stdin: "<prob> <odds> <gameKey>" per line
//                          stdout: "<american> <prob> <ev> <corrPairs> <maxExposure>"
//   kelly_engine selftest  runs internal checks; prints OK or FAIL
//
// Called once per slate from Python (app/engine/cpp_kelly.py), so a single
// process handles the whole batch.
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <map>
#include <string>
#include <vector>

#include "kelly.h"

static void run_eval() {
    std::cout.setf(std::ios::fixed);
    std::cout.precision(9);
    double p;
    long odds;
    while (std::cin >> p >> odds) {
        std::cout << kelly::implied_prob(odds) << ' '
                  << kelly::american_to_decimal(odds) << ' '
                  << kelly::expected_value(p, odds) << ' '
                  << kelly::kelly_fraction(p, odds) << ' '
                  << (p - kelly::implied_prob(odds)) << ' '
                  << kelly::kelly_tier(p, odds) << '\n';
    }
}

static void run_parlay(double rho, long nsims) {
    std::vector<double> probs;
    std::vector<long> odds_v;
    std::vector<int> game_ids;
    std::map<std::string, int> game_index;

    double p;
    long odds;
    std::string game;
    while (std::cin >> p >> odds >> game) {
        probs.push_back(p);
        odds_v.push_back(odds);
        auto it = game_index.find(game);
        if (it == game_index.end())
            it = game_index.emplace(game, static_cast<int>(game_index.size())).first;
        game_ids.push_back(it->second);
    }

    long n = static_cast<long>(probs.size());
    kelly::ParlayResult r = kelly::parlay(
        n ? probs.data() : nullptr, n ? odds_v.data() : nullptr,
        n ? game_ids.data() : nullptr, n, rho, nsims);

    std::cout.setf(std::ios::fixed);
    std::cout.precision(9);
    std::cout << r.american << ' ' << r.naive_prob << ' ' << r.corr_prob << ' '
              << r.naive_ev << ' ' << r.corr_ev << ' ' << r.corr_pairs << ' '
              << r.max_exposure << '\n';
}

static int run_selftest() {
    bool ok = true;
    auto close = [&](double a, double b) { return std::fabs(a - b) < 1e-6; };
    ok &= close(kelly::american_to_decimal(-120), 1.833333333);
    ok &= close(kelly::implied_prob(-110), 0.523809524);
    ok &= close(kelly::kelly_fraction(0.6, 100), 0.2);
    ok &= (kelly::decimal_to_american(2.0) == 100);
    ok &= close(kelly::expected_value(0.55, -110), 0.05);
    std::cout << (ok ? "OK" : "FAIL") << '\n';
    return ok ? 0 : 1;
}

int main(int argc, char** argv) {
    std::string cmd = argc > 1 ? argv[1] : "eval";
    if (cmd == "eval") {
        run_eval();
    } else if (cmd == "parlay") {
        double rho = argc > 2 ? std::atof(argv[2]) : 0.35;
        long nsims = argc > 3 ? std::atol(argv[3]) : 50000;
        run_parlay(rho, nsims);
    } else if (cmd == "selftest") {
        return run_selftest();
    } else {
        std::cerr << "usage: kelly_engine [eval|parlay|selftest]\n";
        return 2;
    }
    return 0;
}
