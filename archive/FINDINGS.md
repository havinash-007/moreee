# Findings log

## Submitted
All open at the time of writing; see `prs.json` and `python3 tools/pr_status.py` for live status.

| PR | Fix |
|---|---|
| sktime/skpro#1200 | `_approx_derivative` missing division by step size |
| Kludex/starlette#3643 | `//` path treated as authority (open redirect) |
| The-PR-Agent/pr-agent#3966 | `extend_patch` for zero-length hunks |
| useblocks/sphinx-needs#2103, #2104, #2105 | needservice crash, test-report content repr, tr_link None |
| vitejs/vite-plugin-vue#856 | SFC TypeScript ignored Vite's `tsconfig` option |
| paupino/rust-decimal#869, #870 | serde 128-bit ints, sqrt/ln/log10 of negative zero |
| Rel1cx/eslint-react#2010 | `set-state-in-effect` false positive for callback refs |
| genshinsim/gcsim#3206 | auto-sample waited for the run to finish |
| oras-project/oras#2227 | `fetch-config --output` to special files, modes, symlinks |

Earlier detail:
- **sktime/skpro#1200**: `_approx_derivative` never divided by the step size, so the
  cdf-derived `pdf` was too small by a factor of 1e-7. Issue #1199.
- **Kludex/starlette#3643**: `URL(scope=...)` treated a leading `//` path as an
  authority when the scope had no host, which allowed an open redirect. Closes #3579.

## Checked and dropped
| Lead | Reason |
|---|---|
| sktime bugs (47 open) | every real one already had a PR or claim |
| GMAE returns 0.0 | real, three PRs already open |
| make_mock_estimator on Python 3.14 | reported same day, fix PR open |
| imbalanced-learn, torchmetrics, xarray, statsmodels, dask | PRs or claims everywhere |
| pr-agent, doorstop, rai-toolkit good-first-issues | PRs already open |
| humanize, tabulate, click, jinja, more-itertools | suites pass on Python 3.14 |

## Lessons
- Read the AI policy first, including `.github/AI_POLICY.md`: scikit-image, networkx, django-modern-rest, thanos, OpenTelemetry and others restrict or ban AI-assisted PRs.
- DCO projects need the contributor's real name on `Signed-off-by`; CLAs need the contributor's own signature.
- Watch the first CI run: coverage gates, import-order lint and bot reviewers found real follow-ups.
- Popular repos lose easy issues within hours. Look for bugs by running code.
- Check the repo's AI policy first; several projects ban or restrict AI contributions.
