# Kill test — variant `plain_on_laya-english`

Sessions: {'success': 5, 'burn': 5, 'wrong': 0}

## Design-doc policy replayed, untuned (all sessions)

| mode | caught | false alarms | recovered spend | alarm position | wrong-group alarms |
|---|---|---|---|---|---|
| full | 80% | 0 (0.0%) | 68% | 0.58 | nan% |
| jev_brake | 40% | 0 (0.0%) | 34% | 0.53 | nan% |
| code_tier_only | 80% | 0 (0.0%) | 68% | 0.58 | nan% |
| jev_only | 20% | 0 (0.0%) | 17% | 0.47 | nan% |

Every message the agent would receive in hint mode (hints, escalations, the one-time "verify and finish" and "back to the goal" notes; a gate veto is only logged):

| mode | successful sessions with any message | messages per success | per burn | per wrong |
|---|---|---|---|---|
| full | 0.0% | 0.00 | 3.40 | n/a |
| jev_brake | 0.0% | 0.00 | 1.60 | n/a |
| code_tier_only | 0.0% | 0.00 | 3.40 | n/a |
| jev_only | 0.0% | 0.00 | 0.80 | n/a |

Decision rule on the untuned policies:

- full: {'catch_gain_points': 0.0, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.0, 'continue': False, 'pivot': False}
- jev_brake: {'catch_gain_points': -40.0, 'earlier_turns': -4.5, 'hybrid_false_alarm': 0.0, 'continue': False, 'pivot': False}

## Tuned by CV, false-alarm cap on training folds = 0%

| detector | caught | false alarms (held out) | recovered spend | alarm position | turns saved |
|---|---|---|---|---|---|
| max_turns | 80% ± 0% | 20.0% ± 0.0% | 48% | 0.74 | 11.0 |
| code | 100% ± 0% | 20.0% ± 0.0% | 90% | 0.30 | 25.7 |
| jev | 60% ± 0% | 20.0% ± 0.0% | 58% | 0.25 | 17.0 |
| hybrid_and | 100% ± 0% | 20.0% ± 0.0% | 79% | 0.48 | 22.1 |
| hybrid_or | 100% ± 0% | 20.0% ± 0.0% | 90% | 0.30 | 25.9 |
| logistic_code | 68% ± 10% | 24.0% ± 8.0% | 66% | 0.22 | 19.3 |
| logistic_code_jev | 52% ± 10% | 24.0% ± 8.0% | 44% | 0.38 | 11.6 |

- decision rule, hybrid_or vs code: {'catch_gain_points': 0.0, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.2, 'continue': False, 'pivot': True}

- decision rule, hybrid_and vs code: {'catch_gain_points': 0.0, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.2, 'continue': False, 'pivot': True}

- decision rule, logistic_code_jev vs logistic_code: {'catch_gain_points': -16.0, 'earlier_turns': 0.3, 'hybrid_false_alarm': 0.24, 'continue': False, 'pivot': False}

## Tuned by CV, false-alarm cap on training folds = 1%

| detector | caught | false alarms (held out) | recovered spend | alarm position | turns saved |
|---|---|---|---|---|---|
| max_turns | 80% ± 0% | 20.0% ± 0.0% | 48% | 0.74 | 11.0 |
| code | 100% ± 0% | 20.0% ± 0.0% | 90% | 0.30 | 25.7 |
| jev | 60% ± 0% | 20.0% ± 0.0% | 58% | 0.25 | 17.0 |
| hybrid_and | 100% ± 0% | 20.0% ± 0.0% | 79% | 0.48 | 22.1 |
| hybrid_or | 100% ± 0% | 20.0% ± 0.0% | 90% | 0.30 | 25.9 |
| logistic_code | 68% ± 10% | 24.0% ± 8.0% | 66% | 0.22 | 19.3 |
| logistic_code_jev | 52% ± 10% | 24.0% ± 8.0% | 44% | 0.38 | 11.6 |

- decision rule, hybrid_or vs code: {'catch_gain_points': 0.0, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.2, 'continue': False, 'pivot': True}

- decision rule, hybrid_and vs code: {'catch_gain_points': 0.0, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.2, 'continue': False, 'pivot': True}

- decision rule, logistic_code_jev vs logistic_code: {'catch_gain_points': -16.0, 'earlier_turns': 0.3, 'hybrid_false_alarm': 0.24, 'continue': False, 'pivot': False}

## Tuned by CV, false-alarm cap on training folds = 2%

| detector | caught | false alarms (held out) | recovered spend | alarm position | turns saved |
|---|---|---|---|---|---|
| max_turns | 80% ± 0% | 20.0% ± 0.0% | 48% | 0.74 | 11.0 |
| code | 100% ± 0% | 20.0% ± 0.0% | 90% | 0.30 | 25.7 |
| jev | 60% ± 0% | 20.0% ± 0.0% | 58% | 0.25 | 17.0 |
| hybrid_and | 100% ± 0% | 20.0% ± 0.0% | 79% | 0.48 | 22.1 |
| hybrid_or | 100% ± 0% | 20.0% ± 0.0% | 90% | 0.30 | 25.9 |
| logistic_code | 68% ± 10% | 24.0% ± 8.0% | 66% | 0.22 | 19.3 |
| logistic_code_jev | 52% ± 10% | 24.0% ± 8.0% | 44% | 0.38 | 11.6 |

- decision rule, hybrid_or vs code: {'catch_gain_points': 0.0, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.2, 'continue': False, 'pivot': True}

- decision rule, hybrid_and vs code: {'catch_gain_points': 0.0, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.2, 'continue': False, 'pivot': True}

- decision rule, logistic_code_jev vs logistic_code: {'catch_gain_points': -16.0, 'earlier_turns': 0.3, 'hybrid_false_alarm': 0.24, 'continue': False, 'pivot': False}

## Tuned by CV, false-alarm cap on training folds = 5%

| detector | caught | false alarms (held out) | recovered spend | alarm position | turns saved |
|---|---|---|---|---|---|
| max_turns | 80% ± 0% | 20.0% ± 0.0% | 48% | 0.74 | 11.0 |
| code | 100% ± 0% | 20.0% ± 0.0% | 90% | 0.30 | 25.7 |
| jev | 60% ± 0% | 20.0% ± 0.0% | 58% | 0.25 | 17.0 |
| hybrid_and | 100% ± 0% | 20.0% ± 0.0% | 79% | 0.48 | 22.1 |
| hybrid_or | 100% ± 0% | 20.0% ± 0.0% | 90% | 0.30 | 25.9 |
| logistic_code | 68% ± 10% | 24.0% ± 8.0% | 66% | 0.22 | 19.3 |
| logistic_code_jev | 52% ± 10% | 24.0% ± 8.0% | 44% | 0.38 | 11.6 |

- decision rule, hybrid_or vs code: {'catch_gain_points': 0.0, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.2, 'continue': False, 'pivot': True}

- decision rule, hybrid_and vs code: {'catch_gain_points': 0.0, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.2, 'continue': False, 'pivot': True}

- decision rule, logistic_code_jev vs logistic_code: {'catch_gain_points': -16.0, 'earlier_turns': 0.3, 'hybrid_false_alarm': 0.24, 'continue': False, 'pivot': False}
