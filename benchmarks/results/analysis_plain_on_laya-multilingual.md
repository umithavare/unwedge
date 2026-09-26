# Kill test — variant `plain_on_laya-multilingual`

Sessions: {'success': 30, 'burn': 30, 'wrong': 0}

## Design-doc policy replayed, untuned (all sessions)

| mode | caught | false alarms | recovered spend | alarm position | wrong-group alarms |
|---|---|---|---|---|---|
| full | 80% | 0 (0.0%) | 67% | 0.48 | nan% |
| jev_brake | 40% | 0 (0.0%) | 43% | 0.43 | nan% |
| code_tier_only | 77% | 0 (0.0%) | 65% | 0.49 | nan% |
| jev_only | 37% | 0 (0.0%) | 42% | 0.39 | nan% |

Every message the agent would receive in hint mode (hints, escalations, the one-time "verify and finish" and "back to the goal" notes; a gate veto is only logged):

| mode | successful sessions with any message | messages per success | per burn | per wrong |
|---|---|---|---|---|
| full | 6.7% | 0.07 | 4.63 | n/a |
| jev_brake | 6.7% | 0.07 | 3.00 | n/a |
| code_tier_only | 0.0% | 0.00 | 4.40 | n/a |
| jev_only | 6.7% | 0.07 | 2.03 | n/a |

Decision rule on the untuned policies:

- full: {'catch_gain_points': 3.3, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.0, 'continue': False, 'pivot': False}
- jev_brake: {'catch_gain_points': -36.7, 'earlier_turns': -7.0, 'hybrid_false_alarm': 0.0, 'continue': False, 'pivot': False}

## Tuned by CV, false-alarm cap on training folds = 0%

| detector | caught | false alarms (held out) | recovered spend | alarm position | turns saved |
|---|---|---|---|---|---|
| max_turns | 61% ± 1% | 1.3% ± 2.7% | 51% | 0.64 | 22.1 |
| code | 87% ± 1% | 8.7% ± 2.7% | 70% | 0.52 | 30.9 |
| jev | 63% ± 5% | 7.3% ± 1.3% | 63% | 0.44 | 30.3 |
| hybrid_and | 83% ± 1% | 8.7% ± 1.6% | 70% | 0.49 | 31.6 |
| hybrid_or | 87% ± 1% | 11.3% ± 3.4% | 77% | 0.47 | 36.2 |
| logistic_code | 78% ± 3% | 10.7% ± 1.3% | 63% | 0.53 | 28.0 |
| logistic_code_jev | 79% ± 1% | 6.0% ± 2.5% | 70% | 0.47 | 32.5 |

- decision rule, hybrid_or vs code: {'catch_gain_points': 0.0, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.113, 'continue': False, 'pivot': True}

- decision rule, hybrid_and vs code: {'catch_gain_points': -4.7, 'earlier_turns': 0.2, 'hybrid_false_alarm': 0.087, 'continue': False, 'pivot': True}

- decision rule, logistic_code_jev vs logistic_code: {'catch_gain_points': 1.3, 'earlier_turns': 1.5, 'hybrid_false_alarm': 0.06, 'continue': False, 'pivot': False}

## Tuned by CV, false-alarm cap on training folds = 1%

| detector | caught | false alarms (held out) | recovered spend | alarm position | turns saved |
|---|---|---|---|---|---|
| max_turns | 61% ± 1% | 1.3% ± 2.7% | 51% | 0.64 | 22.1 |
| code | 87% ± 1% | 8.7% ± 2.7% | 70% | 0.52 | 30.9 |
| jev | 63% ± 5% | 7.3% ± 1.3% | 63% | 0.44 | 30.3 |
| hybrid_and | 83% ± 1% | 8.7% ± 1.6% | 70% | 0.49 | 31.6 |
| hybrid_or | 87% ± 1% | 11.3% ± 3.4% | 77% | 0.47 | 36.2 |
| logistic_code | 78% ± 3% | 10.7% ± 1.3% | 63% | 0.53 | 28.0 |
| logistic_code_jev | 79% ± 1% | 6.0% ± 2.5% | 70% | 0.47 | 32.5 |

- decision rule, hybrid_or vs code: {'catch_gain_points': 0.0, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.113, 'continue': False, 'pivot': True}

- decision rule, hybrid_and vs code: {'catch_gain_points': -4.7, 'earlier_turns': 0.2, 'hybrid_false_alarm': 0.087, 'continue': False, 'pivot': True}

- decision rule, logistic_code_jev vs logistic_code: {'catch_gain_points': 1.3, 'earlier_turns': 1.5, 'hybrid_false_alarm': 0.06, 'continue': False, 'pivot': False}

## Tuned by CV, false-alarm cap on training folds = 2%

| detector | caught | false alarms (held out) | recovered spend | alarm position | turns saved |
|---|---|---|---|---|---|
| max_turns | 61% ± 1% | 1.3% ± 2.7% | 51% | 0.64 | 22.1 |
| code | 87% ± 1% | 8.7% ± 2.7% | 70% | 0.52 | 30.9 |
| jev | 63% ± 5% | 7.3% ± 1.3% | 63% | 0.44 | 30.3 |
| hybrid_and | 83% ± 1% | 8.7% ± 1.6% | 70% | 0.49 | 31.6 |
| hybrid_or | 87% ± 1% | 11.3% ± 3.4% | 77% | 0.47 | 36.2 |
| logistic_code | 78% ± 3% | 10.7% ± 1.3% | 63% | 0.53 | 28.0 |
| logistic_code_jev | 79% ± 1% | 6.0% ± 2.5% | 70% | 0.47 | 32.5 |

- decision rule, hybrid_or vs code: {'catch_gain_points': 0.0, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.113, 'continue': False, 'pivot': True}

- decision rule, hybrid_and vs code: {'catch_gain_points': -4.7, 'earlier_turns': 0.2, 'hybrid_false_alarm': 0.087, 'continue': False, 'pivot': True}

- decision rule, logistic_code_jev vs logistic_code: {'catch_gain_points': 1.3, 'earlier_turns': 1.5, 'hybrid_false_alarm': 0.06, 'continue': False, 'pivot': False}

## Tuned by CV, false-alarm cap on training folds = 5%

| detector | caught | false alarms (held out) | recovered spend | alarm position | turns saved |
|---|---|---|---|---|---|
| max_turns | 69% ± 4% | 8.0% ± 1.6% | 57% | 0.63 | 24.9 |
| code | 95% ± 2% | 14.0% ± 1.3% | 80% | 0.42 | 36.5 |
| jev | 67% ± 2% | 7.3% ± 1.3% | 62% | 0.44 | 29.6 |
| hybrid_and | 95% ± 2% | 13.3% ± 2.1% | 78% | 0.43 | 36.4 |
| hybrid_or | 95% ± 2% | 15.3% ± 1.6% | 83% | 0.38 | 40.1 |
| logistic_code | 82% ± 2% | 12.0% ± 1.6% | 68% | 0.49 | 30.8 |
| logistic_code_jev | 90% ± 2% | 12.7% ± 2.5% | 82% | 0.39 | 39.1 |

- decision rule, hybrid_or vs code: {'catch_gain_points': 0.0, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.153, 'continue': False, 'pivot': True}

- decision rule, hybrid_and vs code: {'catch_gain_points': 0.0, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.133, 'continue': False, 'pivot': True}

- decision rule, logistic_code_jev vs logistic_code: {'catch_gain_points': 8.0, 'earlier_turns': 7.1, 'hybrid_false_alarm': 0.127, 'continue': False, 'pivot': False}
