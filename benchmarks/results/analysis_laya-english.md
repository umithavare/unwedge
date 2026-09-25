# Kill test — variant `laya-english`

Sessions: {'success': 5, 'burn': 5, 'wrong': 0}

## Design-doc policy replayed, untuned (all sessions)

| mode | caught | false alarms | recovered spend | alarm position | wrong-group alarms |
|---|---|---|---|---|---|
| full | 60% | 0 (0.0%) | 51% | 0.58 | nan% |
| jev_brake | 0% | 0 (0.0%) | 0% | nan | nan% |
| code_tier_only | 60% | 0 (0.0%) | 51% | 0.58 | nan% |
| jev_only | 0% | 0 (0.0%) | 0% | nan | nan% |

Every message the agent would receive in hint mode (hints, escalations, the one-time "verify and finish" and "back to the goal" notes; a gate veto is only logged):

| mode | successful sessions with any message | messages per success | per burn | per wrong |
|---|---|---|---|---|
| full | 0.0% | 0.00 | 2.00 | n/a |
| jev_brake | 0.0% | 0.00 | 0.00 | n/a |
| code_tier_only | 0.0% | 0.00 | 2.00 | n/a |
| jev_only | 0.0% | 0.00 | 0.00 | n/a |

Decision rule on the untuned policies:

- full: {'catch_gain_points': 0.0, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.0, 'continue': False, 'pivot': False}
- jev_brake: {'catch_gain_points': -60.0, 'earlier_turns': nan, 'hybrid_false_alarm': 0.0, 'continue': False, 'pivot': False}

## Tuned by CV, false-alarm cap on training folds = 0%

| detector | caught | false alarms (held out) | recovered spend | alarm position | turns saved |
|---|---|---|---|---|---|
| max_turns | 80% ± 0% | 20.0% ± 0.0% | 48% | 0.74 | 11.0 |
| code | 100% ± 0% | 20.0% ± 0.0% | 90% | 0.30 | 25.7 |
| jev | 44% ± 8% | 24.0% ± 8.0% | 26% | 0.51 | 5.9 |
| hybrid_and | 100% ± 0% | 20.0% ± 0.0% | 90% | 0.30 | 25.7 |
| hybrid_or | 100% ± 0% | 44.0% ± 8.0% | 90% | 0.30 | 25.8 |
| logistic_code | 68% ± 10% | 20.0% ± 0.0% | 66% | 0.23 | 19.4 |
| logistic_code_jev | 56% ± 8% | 24.0% ± 8.0% | 49% | 0.26 | 13.3 |

- decision rule, hybrid_or vs code: {'catch_gain_points': 0.0, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.44, 'continue': False, 'pivot': True}

- decision rule, hybrid_and vs code: {'catch_gain_points': 0.0, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.2, 'continue': False, 'pivot': True}

- decision rule, logistic_code_jev vs logistic_code: {'catch_gain_points': -12.0, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.24, 'continue': False, 'pivot': False}

## Tuned by CV, false-alarm cap on training folds = 1%

| detector | caught | false alarms (held out) | recovered spend | alarm position | turns saved |
|---|---|---|---|---|---|
| max_turns | 80% ± 0% | 20.0% ± 0.0% | 48% | 0.74 | 11.0 |
| code | 100% ± 0% | 20.0% ± 0.0% | 90% | 0.30 | 25.7 |
| jev | 44% ± 8% | 24.0% ± 8.0% | 26% | 0.51 | 5.9 |
| hybrid_and | 100% ± 0% | 20.0% ± 0.0% | 90% | 0.30 | 25.7 |
| hybrid_or | 100% ± 0% | 44.0% ± 8.0% | 90% | 0.30 | 25.8 |
| logistic_code | 68% ± 10% | 20.0% ± 0.0% | 66% | 0.23 | 19.4 |
| logistic_code_jev | 56% ± 8% | 24.0% ± 8.0% | 49% | 0.26 | 13.3 |

- decision rule, hybrid_or vs code: {'catch_gain_points': 0.0, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.44, 'continue': False, 'pivot': True}

- decision rule, hybrid_and vs code: {'catch_gain_points': 0.0, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.2, 'continue': False, 'pivot': True}

- decision rule, logistic_code_jev vs logistic_code: {'catch_gain_points': -12.0, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.24, 'continue': False, 'pivot': False}

## Tuned by CV, false-alarm cap on training folds = 2%

| detector | caught | false alarms (held out) | recovered spend | alarm position | turns saved |
|---|---|---|---|---|---|
| max_turns | 80% ± 0% | 20.0% ± 0.0% | 48% | 0.74 | 11.0 |
| code | 100% ± 0% | 20.0% ± 0.0% | 90% | 0.30 | 25.7 |
| jev | 44% ± 8% | 24.0% ± 8.0% | 26% | 0.51 | 5.9 |
| hybrid_and | 100% ± 0% | 20.0% ± 0.0% | 90% | 0.30 | 25.7 |
| hybrid_or | 100% ± 0% | 44.0% ± 8.0% | 90% | 0.30 | 25.8 |
| logistic_code | 68% ± 10% | 20.0% ± 0.0% | 66% | 0.23 | 19.4 |
| logistic_code_jev | 56% ± 8% | 24.0% ± 8.0% | 49% | 0.26 | 13.3 |

- decision rule, hybrid_or vs code: {'catch_gain_points': 0.0, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.44, 'continue': False, 'pivot': True}

- decision rule, hybrid_and vs code: {'catch_gain_points': 0.0, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.2, 'continue': False, 'pivot': True}

- decision rule, logistic_code_jev vs logistic_code: {'catch_gain_points': -12.0, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.24, 'continue': False, 'pivot': False}

## Tuned by CV, false-alarm cap on training folds = 5%

| detector | caught | false alarms (held out) | recovered spend | alarm position | turns saved |
|---|---|---|---|---|---|
| max_turns | 80% ± 0% | 20.0% ± 0.0% | 48% | 0.74 | 11.0 |
| code | 100% ± 0% | 20.0% ± 0.0% | 90% | 0.30 | 25.7 |
| jev | 44% ± 8% | 24.0% ± 8.0% | 26% | 0.51 | 5.9 |
| hybrid_and | 100% ± 0% | 20.0% ± 0.0% | 90% | 0.30 | 25.7 |
| hybrid_or | 100% ± 0% | 44.0% ± 8.0% | 90% | 0.30 | 25.8 |
| logistic_code | 68% ± 10% | 20.0% ± 0.0% | 66% | 0.23 | 19.4 |
| logistic_code_jev | 56% ± 8% | 24.0% ± 8.0% | 49% | 0.26 | 13.3 |

- decision rule, hybrid_or vs code: {'catch_gain_points': 0.0, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.44, 'continue': False, 'pivot': True}

- decision rule, hybrid_and vs code: {'catch_gain_points': 0.0, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.2, 'continue': False, 'pivot': True}

- decision rule, logistic_code_jev vs logistic_code: {'catch_gain_points': -12.0, 'earlier_turns': 0.0, 'hybrid_false_alarm': 0.24, 'continue': False, 'pivot': False}
