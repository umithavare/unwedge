# Kill test — variant `fp`

Sessions: {'success': 69, 'burn': 99, 'wrong': 50}

## Design-doc policy replayed, untuned (all sessions)

| mode | caught | false alarms | recovered spend | alarm position | wrong-group alarms |
|---|---|---|---|---|---|
| full | 64% | 5 (7.2%) | 54% | 0.49 | 8% |
| jev_brake | 30% | 3 (4.3%) | 32% | 0.58 | 0% |
| code_tier_only | 60% | 5 (7.2%) | 47% | 0.49 | 8% |
| jev_only | 26% | 2 (2.9%) | 28% | 0.58 | 0% |

Every message the agent would receive in hint mode (hints, escalations, the one-time "verify and finish" and "back to the goal" notes; a gate veto is only logged):

| mode | successful sessions with any message | messages per success | per burn | per wrong |
|---|---|---|---|---|
| full | 15.9% | 0.28 | 3.08 | 0.18 |
| jev_brake | 13.0% | 0.14 | 1.68 | 0.00 |
| code_tier_only | 7.2% | 0.16 | 2.69 | 0.18 |
| jev_only | 11.6% | 0.13 | 1.33 | 0.00 |

Decision rule on the untuned policies:

- full: {'catch_gain_points': 4.0, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.072, 'continue': False, 'pivot': False}
- jev_brake: {'catch_gain_points': -29.3, 'earlier_turns': -7.0, 'hybrid_false_alarm': 0.043, 'continue': False, 'pivot': False}

## Tuned by CV, false-alarm cap on training folds = 0%

| detector | caught | false alarms (held out) | recovered spend | alarm position | turns saved |
|---|---|---|---|---|---|
| max_turns | 29% ± 3% | 1.4% ± 0.0% | 29% | 0.69 | 9.6 |
| code | 44% ± 3% | 3.5% ± 1.5% | 39% | 0.66 | 13.5 |
| jev | 40% ± 2% | 3.8% ± 2.2% | 33% | 0.45 | 12.2 |
| hybrid_and | 53% ± 3% | 4.6% ± 0.6% | 47% | 0.58 | 17.0 |
| hybrid_or | 60% ± 3% | 4.9% ± 1.7% | 51% | 0.55 | 18.6 |
| logistic_code | 57% ± 3% | 4.9% ± 1.2% | 42% | 0.60 | 14.9 |
| logistic_code_jev | 41% ± 5% | 3.5% ± 0.7% | 34% | 0.65 | 12.0 |

- decision rule, hybrid_or vs code: {'catch_gain_points': 15.4, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.049, 'continue': False, 'pivot': False}

- decision rule, hybrid_and vs code: {'catch_gain_points': 8.3, 'earlier_turns': 4.4, 'hybrid_false_alarm': 0.046, 'continue': False, 'pivot': False}

- decision rule, logistic_code_jev vs logistic_code: {'catch_gain_points': -16.2, 'earlier_turns': -2.6, 'hybrid_false_alarm': 0.035, 'continue': False, 'pivot': False}

## Tuned by CV, false-alarm cap on training folds = 1%

| detector | caught | false alarms (held out) | recovered spend | alarm position | turns saved |
|---|---|---|---|---|---|
| max_turns | 29% ± 3% | 1.4% ± 0.0% | 29% | 0.69 | 9.6 |
| code | 44% ± 3% | 3.5% ± 1.5% | 39% | 0.66 | 13.5 |
| jev | 40% ± 2% | 3.8% ± 2.2% | 33% | 0.45 | 12.2 |
| hybrid_and | 53% ± 3% | 4.6% ± 0.6% | 47% | 0.58 | 17.0 |
| hybrid_or | 60% ± 3% | 4.9% ± 1.7% | 51% | 0.55 | 18.6 |
| logistic_code | 57% ± 3% | 4.9% ± 1.2% | 42% | 0.60 | 14.9 |
| logistic_code_jev | 41% ± 5% | 3.5% ± 0.7% | 34% | 0.65 | 12.0 |

- decision rule, hybrid_or vs code: {'catch_gain_points': 15.4, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.049, 'continue': False, 'pivot': False}

- decision rule, hybrid_and vs code: {'catch_gain_points': 8.3, 'earlier_turns': 4.4, 'hybrid_false_alarm': 0.046, 'continue': False, 'pivot': False}

- decision rule, logistic_code_jev vs logistic_code: {'catch_gain_points': -16.2, 'earlier_turns': -2.6, 'hybrid_false_alarm': 0.035, 'continue': False, 'pivot': False}

## Tuned by CV, false-alarm cap on training folds = 2%

| detector | caught | false alarms (held out) | recovered spend | alarm position | turns saved |
|---|---|---|---|---|---|
| max_turns | 55% ± 0% | 1.4% ± 0.0% | 43% | 0.73 | 14.8 |
| code | 64% ± 3% | 8.7% ± 1.3% | 53% | 0.60 | 19.0 |
| jev | 43% ± 3% | 7.5% ± 1.4% | 37% | 0.51 | 13.7 |
| hybrid_and | 77% ± 1% | 7.0% ± 1.1% | 63% | 0.57 | 23.2 |
| hybrid_or | 76% ± 2% | 9.6% ± 1.5% | 61% | 0.56 | 22.5 |
| logistic_code | 61% ± 3% | 5.5% ± 1.1% | 46% | 0.58 | 16.3 |
| logistic_code_jev | 74% ± 3% | 5.5% ± 1.1% | 57% | 0.59 | 20.5 |

- decision rule, hybrid_or vs code: {'catch_gain_points': 11.9, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.096, 'continue': False, 'pivot': False}

- decision rule, hybrid_and vs code: {'catch_gain_points': 12.3, 'earlier_turns': 1.0, 'hybrid_false_alarm': 0.07, 'continue': False, 'pivot': False}

- decision rule, logistic_code_jev vs logistic_code: {'catch_gain_points': 13.3, 'earlier_turns': 0.4, 'hybrid_false_alarm': 0.055, 'continue': False, 'pivot': False}

## Tuned by CV, false-alarm cap on training folds = 5%

| detector | caught | false alarms (held out) | recovered spend | alarm position | turns saved |
|---|---|---|---|---|---|
| max_turns | 59% ± 4% | 3.2% ± 1.4% | 47% | 0.71 | 16.3 |
| code | 76% ± 3% | 9.9% ± 1.9% | 61% | 0.60 | 21.9 |
| jev | 53% ± 2% | 7.0% ± 0.6% | 48% | 0.49 | 18.3 |
| hybrid_and | 82% ± 2% | 10.1% ± 1.6% | 67% | 0.52 | 25.2 |
| hybrid_or | 81% ± 4% | 13.6% ± 1.5% | 66% | 0.52 | 24.5 |
| logistic_code | 67% ± 3% | 7.2% ± 0.9% | 50% | 0.57 | 18.0 |
| logistic_code_jev | 81% ± 3% | 9.0% ± 1.1% | 65% | 0.53 | 23.8 |

- decision rule, hybrid_or vs code: {'catch_gain_points': 4.8, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.136, 'continue': False, 'pivot': False}

- decision rule, hybrid_and vs code: {'catch_gain_points': 5.9, 'earlier_turns': 1.5, 'hybrid_false_alarm': 0.101, 'continue': False, 'pivot': False}

- decision rule, logistic_code_jev vs logistic_code: {'catch_gain_points': 14.3, 'earlier_turns': 1.2, 'hybrid_false_alarm': 0.09, 'continue': False, 'pivot': False}
