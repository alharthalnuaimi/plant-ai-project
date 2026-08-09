f = open(r'c:\Users\pc\Downloads\MB_SAVANA_REPORT_IQ.html', encoding='utf-8').read()
checks = [
    ('File size', f'{len(f):,} chars, {f.count(chr(10))} lines'),
    ('acc-hero HTML', 'class="acc-hero"' in f),
    ('Semi-circle gauge', 'acc-gauge-wrap2' in f),
    ('HALF_CIRC in JS', 'HALF_CIRC' in f),
    ('accScoreLabel', 'accScoreLabel' in f),
    ('acc-kpi-card bad', 'acc-kpi-card bad' in f),
    ('acc-kpi-card good', 'acc-kpi-card good' in f),
    ('acc-kpi-card info', 'acc-kpi-card info' in f),
    ('acc-metric-item', 'acc-metric-item' in f),
    ('report-copy-box', 'report-copy-box' in f),
    ('cat-divider', 'cat-divider' in f),
    ('reconcile-box', 'reconcile-box' in f),
    ('rHeader.className JS', 'rHeader.className' in f),
    ('rTitle.className JS', 'rTitle.className' in f),
    ('resultsAcc div', 'id="resultsAcc"' in f),
    ('errAcc div', 'id="errAcc"' in f),
    ('No dup close div bug', 'endary" id="newFileBtnAcc"' not in f),
    ('HTML ends correctly', f.strip().endswith('</html>')),
]
all_ok = True
for name, result in checks:
    if isinstance(result, bool):
        icon = 'OK' if result else 'FAIL'
        if not result:
            all_ok = False
        print(f'  [{icon}] {name}')
    else:
        print(f'  [INFO] {name}: {result}')
print()
print('ALL CHECKS PASSED' if all_ok else 'SOME CHECKS FAILED')
