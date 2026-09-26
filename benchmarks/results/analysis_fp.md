# Kill test — variant `fp`

Sessions: {'success': 69, 'burn': 99, 'wrong': 50}

## Design-doc policy replayed, untuned (all sessions)

| mode | caught | false alarms | recovered spend | alarm position | wrong-group alarms |
|---|---|---|---|---|---|
| full | 78% | 5 (7.2%) | 63% | 0.52 | 8% |
| jev_brake | 32% | 3 (4.3%) | 33% | 0.59 | 0% |
| code_tier_only | 78% | 5 (7.2%) | 63% | 0.52 | 8% |
| jev_only | 26% | 2 (2.9%) | 28% | 0.58 | 0% |

Every message the agent would receive in hint mode (hints, escalations, the one-time "verify and finish" and "back to the goal" notes; a gate veto is only logged):

| mode | successful sessions with any message | messages per success | per burn | per wrong |
|---|---|---|---|---|
| full | 15.9% | 0.28 | 3.89 | 0.18 |
| jev_brake | 13.0% | 0.14 | 1.97 | 0.00 |
| code_tier_only | 7.2% | 0.16 | 3.77 | 0.18 |
| jev_only | 11.6% | 0.13 | 1.33 | 0.00 |

Decision rule on the untuned policies:

- full: {'catch_gain_points': 0.0, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.072, 'continue': False, 'pivot': False}
- jev_brake: {'catch_gain_points': -45.5, 'earlier_turns': -6.5, 'hybrid_false_alarm': 0.043, 'continue': False, 'pivot': False}

## Tuned by CV, false-alarm cap on training folds = 0%

| detector | caught | false alarms (held out) | recovered spend | alarm position | turns saved |
|---|---|---|---|---|---|
| max_turns | 29% ± 3% | 1.4% ± 0.0% | 29% | 0.69 | 9.6 |
| code | 44% ± 3% | 3.5% ± 1.5% | 39% | 0.66 | 13.5 |
| jev | 40% ± 2% | 3.8% ± 2.2% | 33% | 0.45 | 12.2 |
| hybrid_and | 53% ± 3% | 4.6% ± 0.6% | 47% | 0.58 | 17.0 |
| hybrid_or | 60% ± 3% | 4.9% ± 1.7% | 51% | 0.55 | 18.6 |
| logistic_code | 58% ± 3% | 4.9% ± 0.7% | 44% | 0.59 | 15.5 |
| logistic_code_jev | 47% ± 2% | 3.5% ± 0.7% | 37% | 0.64 | 13.2 |

- decision rule, hybrid_or vs code: {'catch_gain_points': 15.4, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.049, 'continue': False, 'pivot': False}

- decision rule, hybrid_and vs code: {'catch_gain_points': 8.3, 'earlier_turns': 4.4, 'hybrid_false_alarm': 0.046, 'continue': False, 'pivot': False}

- decision rule, logistic_code_jev vs logistic_code: {'catch_gain_points': -11.7, 'earlier_turns': -0.9, 'hybrid_false_alarm': 0.035, 'continue': False, 'pivot': False}

## Tuned by CV, false-alarm cap on training folds = 1%

| detector | caught | false alarms (held out) | recovered spend | alarm position | turns saved |
|---|---|---|---|---|---|
| max_turns | 29% ± 3% | 1.4% ± 0.0% | 29% | 0.69 | 9.6 |
| code | 44% ± 3% | 3.5% ± 1.5% | 39% | 0.66 | 13.5 |
| jev | 40% ± 2% | 3.8% ± 2.2% | 33% | 0.45 | 12.2 |
| hybrid_and | 53% ± 3% | 4.6% ± 0.6% | 47% | 0.58 | 17.0 |
| hybrid_or | 60% ± 3% | 4.9% ± 1.7% | 51% | 0.55 | 18.6 |
| logistic_code | 58% ± 3% | 4.9% ± 0.7% | 44% | 0.59 | 15.5 |
| logistic_code_jev | 47% ± 2% | 3.5% ± 0.7% | 37% | 0.64 | 13.2 |

- decision rule, hybrid_or vs code: {'catch_gain_points': 15.4, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.049, 'continue': False, 'pivot': False}

- decision rule, hybrid_and vs code: {'catch_gain_points': 8.3, 'earlier_turns': 4.4, 'hybrid_false_alarm': 0.046, 'continue': False, 'pivot': False}

- decision rule, logistic_code_jev vs logistic_code: {'catch_gain_points': -11.7, 'earlier_turns': -0.9, 'hybrid_false_alarm': 0.035, 'continue': False, 'pivot': False}

## Tuned by CV, false-alarm cap on training folds = 2%

| detector | caught | false alarms (held out) | recovered spend | alarm position | turns saved |
|---|---|---|---|---|---|
| max_turns | 55% ± 0% | 1.4% ± 0.0% | 43% | 0.73 | 14.8 |
| code | 64% ± 3% | 8.7% ± 1.3% | 53% | 0.60 | 19.0 |
| jev | 43% ± 3% | 7.5% ± 1.4% | 37% | 0.51 | 13.7 |
| hybrid_and | 77% ± 1% | 7.0% ± 1.1% | 63% | 0.57 | 23.2 |
| hybrid_or | 76% ± 2% | 9.6% ± 1.5% | 61% | 0.56 | 22.5 |
| logistic_code | 65% ± 2% | 6.4% ± 1.2% | 49% | 0.57 | 17.6 |
| logistic_code_jev | 74% ± 4% | 6.1% ± 0.6% | 57% | 0.58 | 20.6 |

- decision rule, hybrid_or vs code: {'catch_gain_points': 11.9, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.096, 'continue': False, 'pivot': False}

- decision rule, hybrid_and vs code: {'catch_gain_points': 12.3, 'earlier_turns': 1.0, 'hybrid_false_alarm': 0.07, 'continue': False, 'pivot': False}

- decision rule, logistic_code_jev vs logistic_code: {'catch_gain_points': 9.5, 'earlier_turns': 0.4, 'hybrid_false_alarm': 0.061, 'continue': False, 'pivot': False}

## Tuned by CV, false-alarm cap on training folds = 5%

| detector | caught | false alarms (held out) | recovered spend | alarm position | turns saved |
|---|---|---|---|---|---|
| max_turns | 59% ± 4% | 3.2% ± 1.4% | 47% | 0.71 | 16.3 |
| code | 76% ± 3% | 9.9% ± 1.9% | 61% | 0.60 | 21.9 |
| jev | 53% ± 2% | 7.0% ± 0.6% | 48% | 0.49 | 18.3 |
| hybrid_and | 82% ± 2% | 10.1% ± 1.6% | 67% | 0.52 | 25.2 |
| hybrid_or | 81% ± 4% | 13.6% ± 1.5% | 66% | 0.52 | 24.5 |
| logistic_code | 68% ± 1% | 7.5% ± 1.7% | 53% | 0.56 | 19.2 |
| logistic_code_jev | 80% ± 3% | 8.4% ± 1.1% | 65% | 0.53 | 23.7 |

- decision rule, hybrid_or vs code: {'catch_gain_points': 4.8, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.136, 'continue': False, 'pivot': False}

- decision rule, hybrid_and vs code: {'catch_gain_points': 5.9, 'earlier_turns': 1.5, 'hybrid_false_alarm': 0.101, 'continue': False, 'pivot': False}

- decision rule, logistic_code_jev vs logistic_code: {'catch_gain_points': 11.7, 'earlier_turns': 0.6, 'hybrid_false_alarm': 0.084, 'continue': False, 'pivot': False}
