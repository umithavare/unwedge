# Multi-source benchmark (code tier)

Sessions: {'nebius': {'success': 69, 'burn': 99, 'wrong': 50, 'submitted': 0, 'limit': 0}, 'swe-smith': {'success': 800, 'burn': 211, 'wrong': 400, 'submitted': 0, 'limit': 0}, 'swe-gym': {'success': 192, 'burn': 600, 'wrong': 300, 'submitted': 0, 'limit': 0}, 'jetbrains': {'success': 0, 'burn': 0, 'wrong': 0, 'submitted': 600, 'limit': 564}}

### Shipped code tier (untuned)

| source | caught | false alarms | recoverable spend | first alert at | normal-submit alarms | wrong-patch alarms |
|---|---|---|---|---|---|---|
| nebius | 78% of 99 | 7.2% of 69 | 63% | 0.52 | n/a | 8% |
| swe-smith | 47% of 211 | 2.5% of 800 | 32% | 0.57 | n/a | 8% |
| swe-gym | 21% of 600 | 16.7% of 192 | 39% | 0.54 | n/a | 20% |
| jetbrains | n/a of 0 | n/a | 0% | nan | 0% | n/a |
| all | 33% of 910 | 5.4% of 1061 | 37% | 0.54 | 0% | 13% |

### max_turns, tuned on the other sources, false-alarm cap 1%

| source | caught | false alarms | recoverable spend | first alert at | normal-submit alarms | wrong-patch alarms |
|---|---|---|---|---|---|---|
| nebius | 0% of 99 | 0.0% of 69 | 0% | nan | n/a | 0% |
| swe-smith | 80% of 211 | 4.9% of 800 | 48% | 0.67 | n/a | 12% |
| swe-gym | 0% of 600 | 0.0% of 192 | 0% | nan | n/a | 0% |
| jetbrains | n/a of 0 | n/a | 0% | nan | 0% | n/a |
| all | 18% of 910 | 3.7% of 1061 | 33% | 0.67 | 0% | 6% |

### code, tuned on the other sources, false-alarm cap 1%

| source | caught | false alarms | recoverable spend | first alert at | normal-submit alarms | wrong-patch alarms |
|---|---|---|---|---|---|---|
| nebius | 38% of 99 | 2.9% of 69 | 36% | 0.51 | n/a | 0% |
| swe-smith | 81% of 211 | 5.0% of 800 | 50% | 0.67 | n/a | 12% |
| swe-gym | 8% of 600 | 3.1% of 192 | 6% | 0.75 | n/a | 4% |
| jetbrains | n/a of 0 | n/a | 0% | nan | 0% | n/a |
| all | 28% of 910 | 4.5% of 1061 | 40% | 0.67 | 0% | 8% |

### logistic_code, tuned on the other sources, false-alarm cap 1%

| source | caught | false alarms | recoverable spend | first alert at | normal-submit alarms | wrong-patch alarms |
|---|---|---|---|---|---|---|
| nebius | 37% of 99 | 1.4% of 69 | 30% | 0.51 | n/a | 6% |
| swe-smith | 7% of 211 | 0.1% of 800 | 4% | 0.45 | n/a | 0% |
| swe-gym | 6% of 600 | 3.1% of 192 | 6% | 0.78 | n/a | 1% |
| jetbrains | n/a of 0 | n/a | 0% | nan | 0% | n/a |
| all | 10% of 910 | 0.8% of 1061 | 7% | 0.67 | 0% | 1% |

### max_turns, tuned on the other sources, false-alarm cap 2%

| source | caught | false alarms | recoverable spend | first alert at | normal-submit alarms | wrong-patch alarms |
|---|---|---|---|---|---|---|
| nebius | 0% of 99 | 0.0% of 69 | 0% | nan | n/a | 0% |
| swe-smith | 80% of 211 | 4.9% of 800 | 48% | 0.67 | n/a | 12% |
| swe-gym | 0% of 600 | 0.0% of 192 | 0% | nan | n/a | 0% |
| jetbrains | n/a of 0 | n/a | 0% | nan | 0% | n/a |
| all | 18% of 910 | 3.7% of 1061 | 33% | 0.67 | 0% | 6% |

### code, tuned on the other sources, false-alarm cap 2%

| source | caught | false alarms | recoverable spend | first alert at | normal-submit alarms | wrong-patch alarms |
|---|---|---|---|---|---|---|
| nebius | 34% of 99 | 2.9% of 69 | 30% | 0.51 | n/a | 4% |
| swe-smith | 81% of 211 | 5.0% of 800 | 50% | 0.67 | n/a | 12% |
| swe-gym | 18% of 600 | 13.0% of 192 | 28% | 0.57 | n/a | 16% |
| jetbrains | n/a of 0 | n/a | 0% | nan | 0% | n/a |
| all | 34% of 910 | 6.3% of 1061 | 44% | 0.67 | 0% | 13% |

### logistic_code, tuned on the other sources, false-alarm cap 2%

| source | caught | false alarms | recoverable spend | first alert at | normal-submit alarms | wrong-patch alarms |
|---|---|---|---|---|---|---|
| nebius | 41% of 99 | 4.3% of 69 | 28% | 0.54 | n/a | 4% |
| swe-smith | 8% of 211 | 0.2% of 800 | 4% | 0.42 | n/a | 0% |
| swe-gym | 12% of 600 | 5.2% of 192 | 12% | 0.76 | n/a | 3% |
| jetbrains | n/a of 0 | n/a | 0% | nan | 0% | n/a |
| all | 14% of 910 | 1.4% of 1061 | 9% | 0.70 | 0% | 1% |

### max_turns, tuned on the other sources, false-alarm cap 5%

| source | caught | false alarms | recoverable spend | first alert at | normal-submit alarms | wrong-patch alarms |
|---|---|---|---|---|---|---|
| nebius | 28% of 99 | 1.4% of 69 | 32% | 0.66 | n/a | 0% |
| swe-smith | 84% of 211 | 9.1% of 800 | 64% | 0.53 | n/a | 21% |
| swe-gym | 0% of 600 | 0.0% of 192 | 0% | nan | n/a | 0% |
| jetbrains | n/a of 0 | n/a | 0% | nan | 0% | n/a |
| all | 23% of 910 | 7.0% of 1061 | 48% | 0.53 | 0% | 11% |

### code, tuned on the other sources, false-alarm cap 5%

| source | caught | false alarms | recoverable spend | first alert at | normal-submit alarms | wrong-patch alarms |
|---|---|---|---|---|---|---|
| nebius | 59% of 99 | 4.3% of 69 | 52% | 0.61 | n/a | 0% |
| swe-smith | 82% of 211 | 7.0% of 800 | 55% | 0.67 | n/a | 15% |
| swe-gym | 24% of 600 | 15.1% of 192 | 34% | 0.67 | n/a | 18% |
| jetbrains | n/a of 0 | n/a | 0% | nan | 0% | n/a |
| all | 41% of 910 | 8.3% of 1061 | 51% | 0.67 | 0% | 15% |

### logistic_code, tuned on the other sources, false-alarm cap 5%

| source | caught | false alarms | recoverable spend | first alert at | normal-submit alarms | wrong-patch alarms |
|---|---|---|---|---|---|---|
| nebius | 72% of 99 | 15.9% of 69 | 57% | 0.38 | n/a | 16% |
| swe-smith | 9% of 211 | 0.2% of 800 | 5% | 0.44 | n/a | 0% |
| swe-gym | 22% of 600 | 10.9% of 192 | 28% | 0.73 | n/a | 9% |
| jetbrains | n/a of 0 | n/a | 0% | nan | 0% | n/a |
| all | 24% of 910 | 3.2% of 1061 | 16% | 0.60 | 0% | 5% |

