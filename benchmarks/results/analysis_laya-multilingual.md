# Kill test — variant `laya-multilingual`

Sessions: {'success': 30, 'burn': 30, 'wrong': 0}

## Design-doc policy replayed, untuned (all sessions)

| mode | caught | false alarms | recovered spend | alarm position | wrong-group alarms |
|---|---|---|---|---|---|
| full | 77% | 0 (0.0%) | 65% | 0.49 | nan% |
| jev_brake | 13% | 0 (0.0%) | 17% | 0.64 | nan% |
| code_tier_only | 77% | 0 (0.0%) | 65% | 0.49 | nan% |
| jev_only | 0% | 0 (0.0%) | 0% | nan | nan% |

Every message the agent would receive in hint mode (hints, escalations, the one-time "verify and finish" and "back to the goal" notes; a gate veto is only logged):

| mode | successful sessions with any message | messages per success | per burn | per wrong |
|---|---|---|---|---|
| full | 0.0% | 0.00 | 4.40 | n/a |
| jev_brake | 0.0% | 0.00 | 1.07 | n/a |
| code_tier_only | 0.0% | 0.00 | 4.40 | n/a |
| jev_only | 0.0% | 0.00 | 0.00 | n/a |

Decision rule on the untuned policies:

- full: {'catch_gain_points': 0.0, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.0, 'continue': False, 'pivot': False}
- jev_brake: {'catch_gain_points': -63.3, 'earlier_turns': -60.5, 'hybrid_false_alarm': 0.0, 'continue': False, 'pivot': False}

## Tuned by CV, false-alarm cap on training folds = 0%

| detector | caught | false alarms (held out) | recovered spend | alarm position | turns saved |
|---|---|---|---|---|---|
| max_turns | 61% ± 1% | 1.3% ± 2.7% | 51% | 0.64 | 22.1 |
| code | 87% ± 1% | 8.7% ± 2.7% | 70% | 0.52 | 30.9 |
| jev | 31% ± 6% | 5.3% ± 1.6% | 29% | 0.27 | 14.8 |
| hybrid_and | 76% ± 5% | 12.0% ± 1.6% | 62% | 0.56 | 28.2 |
| hybrid_or | 96% ± 2% | 12.7% ± 1.3% | 76% | 0.50 | 34.5 |
| logistic_code | 78% ± 3% | 10.7% ± 1.3% | 63% | 0.53 | 28.0 |
| logistic_code_jev | 85% ± 3% | 10.0% ± 2.1% | 66% | 0.53 | 29.4 |

- decision rule, hybrid_or vs code: {'catch_gain_points': 8.7, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.127, 'continue': False, 'pivot': True}

- decision rule, hybrid_and vs code: {'catch_gain_points': -11.3, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.12, 'continue': False, 'pivot': True}

- decision rule, logistic_code_jev vs logistic_code: {'catch_gain_points': 6.7, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.1, 'continue': False, 'pivot': False}

## Tuned by CV, false-alarm cap on training folds = 1%

| detector | caught | false alarms (held out) | recovered spend | alarm position | turns saved |
|---|---|---|---|---|---|
| max_turns | 61% ± 1% | 1.3% ± 2.7% | 51% | 0.64 | 22.1 |
| code | 87% ± 1% | 8.7% ± 2.7% | 70% | 0.52 | 30.9 |
| jev | 31% ± 6% | 5.3% ± 1.6% | 29% | 0.27 | 14.8 |
| hybrid_and | 76% ± 5% | 12.0% ± 1.6% | 62% | 0.56 | 28.2 |
| hybrid_or | 96% ± 2% | 12.7% ± 1.3% | 76% | 0.50 | 34.5 |
| logistic_code | 78% ± 3% | 10.7% ± 1.3% | 63% | 0.53 | 28.0 |
| logistic_code_jev | 85% ± 3% | 10.0% ± 2.1% | 66% | 0.53 | 29.4 |

- decision rule, hybrid_or vs code: {'catch_gain_points': 8.7, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.127, 'continue': False, 'pivot': True}

- decision rule, hybrid_and vs code: {'catch_gain_points': -11.3, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.12, 'continue': False, 'pivot': True}

- decision rule, logistic_code_jev vs logistic_code: {'catch_gain_points': 6.7, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.1, 'continue': False, 'pivot': False}

## Tuned by CV, false-alarm cap on training folds = 2%

| detector | caught | false alarms (held out) | recovered spend | alarm position | turns saved |
|---|---|---|---|---|---|
| max_turns | 61% ± 1% | 1.3% ± 2.7% | 51% | 0.64 | 22.1 |
| code | 87% ± 1% | 8.7% ± 2.7% | 70% | 0.52 | 30.9 |
| jev | 31% ± 6% | 5.3% ± 1.6% | 29% | 0.27 | 14.8 |
| hybrid_and | 76% ± 5% | 12.0% ± 1.6% | 62% | 0.56 | 28.2 |
| hybrid_or | 96% ± 2% | 12.7% ± 1.3% | 76% | 0.50 | 34.5 |
| logistic_code | 78% ± 3% | 10.7% ± 1.3% | 63% | 0.53 | 28.0 |
| logistic_code_jev | 85% ± 3% | 10.0% ± 2.1% | 66% | 0.53 | 29.4 |

- decision rule, hybrid_or vs code: {'catch_gain_points': 8.7, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.127, 'continue': False, 'pivot': True}

- decision rule, hybrid_and vs code: {'catch_gain_points': -11.3, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.12, 'continue': False, 'pivot': True}

- decision rule, logistic_code_jev vs logistic_code: {'catch_gain_points': 6.7, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.1, 'continue': False, 'pivot': False}

## Tuned by CV, false-alarm cap on training folds = 5%

| detector | caught | false alarms (held out) | recovered spend | alarm position | turns saved |
|---|---|---|---|---|---|
| max_turns | 69% ± 4% | 8.0% ± 1.6% | 57% | 0.63 | 24.9 |
| code | 95% ± 2% | 14.0% ± 1.3% | 80% | 0.42 | 36.5 |
| jev | 31% ± 3% | 8.7% ± 1.6% | 31% | 0.27 | 15.5 |
| hybrid_and | 91% ± 2% | 8.7% ± 1.6% | 74% | 0.44 | 33.4 |
| hybrid_or | 99% ± 2% | 18.7% ± 1.6% | 83% | 0.37 | 38.7 |
| logistic_code | 82% ± 2% | 12.0% ± 1.6% | 68% | 0.49 | 30.8 |
| logistic_code_jev | 89% ± 3% | 10.0% ± 2.1% | 73% | 0.48 | 33.5 |

- decision rule, hybrid_or vs code: {'catch_gain_points': 4.0, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.187, 'continue': False, 'pivot': True}

- decision rule, hybrid_and vs code: {'catch_gain_points': -4.0, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.087, 'continue': False, 'pivot': True}

- decision rule, logistic_code_jev vs logistic_code: {'catch_gain_points': 6.7, 'earlier_turns': 0.7, 'hybrid_false_alarm': 0.1, 'continue': False, 'pivot': False}
