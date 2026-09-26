# Kill test — variant `plain`

Sessions: {'success': 69, 'burn': 99, 'wrong': 50}

## Design-doc policy replayed, untuned (all sessions)

| mode | caught | false alarms | recovered spend | alarm position | wrong-group alarms |
|---|---|---|---|---|---|
| full | 79% | 5 (7.2%) | 64% | 0.52 | 8% |
| jev_brake | 32% | 2 (2.9%) | 32% | 0.60 | 0% |
| code_tier_only | 78% | 5 (7.2%) | 63% | 0.52 | 8% |
| jev_only | 26% | 1 (1.4%) | 27% | 0.58 | 0% |

Every message the agent would receive in hint mode (hints, escalations, the one-time "verify and finish" and "back to the goal" notes; a gate veto is only logged):

| mode | successful sessions with any message | messages per success | per burn | per wrong |
|---|---|---|---|---|
| full | 15.9% | 0.28 | 3.86 | 0.18 |
| jev_brake | 11.6% | 0.13 | 1.88 | 0.00 |
| code_tier_only | 7.2% | 0.16 | 3.77 | 0.18 |
| jev_only | 10.1% | 0.12 | 1.23 | 0.00 |

Decision rule on the untuned policies:

- full: {'catch_gain_points': 1.0, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.072, 'continue': False, 'pivot': False}
- jev_brake: {'catch_gain_points': -45.5, 'earlier_turns': -6.0, 'hybrid_false_alarm': 0.029, 'continue': False, 'pivot': False}

## Tuned by CV, false-alarm cap on training folds = 0%

| detector | caught | false alarms (held out) | recovered spend | alarm position | turns saved |
|---|---|---|---|---|---|
| max_turns | 29% ± 3% | 1.4% ± 0.0% | 29% | 0.69 | 9.6 |
| code | 44% ± 3% | 3.5% ± 1.5% | 39% | 0.66 | 13.5 |
| jev | 32% ± 4% | 4.9% ± 1.5% | 29% | 0.52 | 10.5 |
| hybrid_and | 50% ± 3% | 4.6% ± 0.6% | 46% | 0.56 | 16.5 |
| hybrid_or | 57% ± 4% | 5.2% ± 1.5% | 48% | 0.57 | 17.3 |
| logistic_code | 58% ± 3% | 4.9% ± 0.7% | 44% | 0.59 | 15.5 |
| logistic_code_jev | 46% ± 2% | 3.8% ± 1.2% | 37% | 0.64 | 13.0 |

- decision rule, hybrid_or vs code: {'catch_gain_points': 12.7, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.052, 'continue': False, 'pivot': False}

- decision rule, hybrid_and vs code: {'catch_gain_points': 5.9, 'earlier_turns': 4.3, 'hybrid_false_alarm': 0.046, 'continue': False, 'pivot': False}

- decision rule, logistic_code_jev vs logistic_code: {'catch_gain_points': -12.5, 'earlier_turns': -1.5, 'hybrid_false_alarm': 0.038, 'continue': False, 'pivot': False}

## Tuned by CV, false-alarm cap on training folds = 1%

| detector | caught | false alarms (held out) | recovered spend | alarm position | turns saved |
|---|---|---|---|---|---|
| max_turns | 29% ± 3% | 1.4% ± 0.0% | 29% | 0.69 | 9.6 |
| code | 44% ± 3% | 3.5% ± 1.5% | 39% | 0.66 | 13.5 |
| jev | 32% ± 4% | 4.9% ± 1.5% | 29% | 0.52 | 10.5 |
| hybrid_and | 50% ± 3% | 4.6% ± 0.6% | 46% | 0.56 | 16.5 |
| hybrid_or | 57% ± 4% | 5.2% ± 1.5% | 48% | 0.57 | 17.3 |
| logistic_code | 58% ± 3% | 4.9% ± 0.7% | 44% | 0.59 | 15.5 |
| logistic_code_jev | 46% ± 2% | 3.8% ± 1.2% | 37% | 0.64 | 13.0 |

- decision rule, hybrid_or vs code: {'catch_gain_points': 12.7, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.052, 'continue': False, 'pivot': False}

- decision rule, hybrid_and vs code: {'catch_gain_points': 5.9, 'earlier_turns': 4.3, 'hybrid_false_alarm': 0.046, 'continue': False, 'pivot': False}

- decision rule, logistic_code_jev vs logistic_code: {'catch_gain_points': -12.5, 'earlier_turns': -1.5, 'hybrid_false_alarm': 0.038, 'continue': False, 'pivot': False}

## Tuned by CV, false-alarm cap on training folds = 2%

| detector | caught | false alarms (held out) | recovered spend | alarm position | turns saved |
|---|---|---|---|---|---|
| max_turns | 55% ± 0% | 1.4% ± 0.0% | 43% | 0.73 | 14.8 |
| code | 64% ± 3% | 8.7% ± 1.3% | 53% | 0.60 | 19.0 |
| jev | 38% ± 2% | 7.5% ± 1.1% | 34% | 0.53 | 12.6 |
| hybrid_and | 75% ± 1% | 7.0% ± 1.9% | 62% | 0.55 | 22.9 |
| hybrid_or | 75% ± 3% | 10.1% ± 0.9% | 60% | 0.59 | 21.9 |
| logistic_code | 65% ± 2% | 6.4% ± 1.2% | 49% | 0.57 | 17.6 |
| logistic_code_jev | 74% ± 3% | 6.1% ± 0.6% | 58% | 0.57 | 21.1 |

- decision rule, hybrid_or vs code: {'catch_gain_points': 10.7, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.101, 'continue': False, 'pivot': False}

- decision rule, hybrid_and vs code: {'catch_gain_points': 10.7, 'earlier_turns': 1.5, 'hybrid_false_alarm': 0.07, 'continue': False, 'pivot': False}

- decision rule, logistic_code_jev vs logistic_code: {'catch_gain_points': 9.3, 'earlier_turns': 0.5, 'hybrid_false_alarm': 0.061, 'continue': False, 'pivot': False}

## Tuned by CV, false-alarm cap on training folds = 5%

| detector | caught | false alarms (held out) | recovered spend | alarm position | turns saved |
|---|---|---|---|---|---|
| max_turns | 59% ± 4% | 3.2% ± 1.4% | 47% | 0.71 | 16.3 |
| code | 76% ± 3% | 9.9% ± 1.9% | 61% | 0.60 | 21.9 |
| jev | 49% ± 4% | 8.7% ± 1.6% | 42% | 0.49 | 16.1 |
| hybrid_and | 81% ± 3% | 9.6% ± 2.0% | 66% | 0.55 | 24.5 |
| hybrid_or | 80% ± 2% | 13.3% ± 1.7% | 65% | 0.54 | 24.1 |
| logistic_code | 68% ± 1% | 7.5% ± 1.7% | 53% | 0.56 | 19.2 |
| logistic_code_jev | 82% ± 3% | 9.3% ± 2.0% | 65% | 0.53 | 23.8 |

- decision rule, hybrid_or vs code: {'catch_gain_points': 4.6, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.133, 'continue': False, 'pivot': False}

- decision rule, hybrid_and vs code: {'catch_gain_points': 5.5, 'earlier_turns': 0.6, 'hybrid_false_alarm': 0.096, 'continue': False, 'pivot': False}

- decision rule, logistic_code_jev vs logistic_code: {'catch_gain_points': 13.1, 'earlier_turns': 0.6, 'hybrid_false_alarm': 0.093, 'continue': False, 'pivot': False}
