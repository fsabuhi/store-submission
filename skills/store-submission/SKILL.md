---
name: store-submission
description: >
  Get the mobile app ready for the App Store and Google Play. Fetches the
  current official rules from Apple and Google and reports what changed,
  scans the code, Expo config and generated native projects, reviews the app
  against every App Review Guideline and Play policy, drafts the privacy
  label and Data safety answers, lists the console tasks, and cleans up what
  would get the app rejected. Use before any store build or submission, and for
  "will this get rejected", "app store review", "play policy check", "privacy
  labels", "data safety form", "prepare for submission".
---

<!-- Merges three projects; see THIRD-PARTY-NOTICES.md:
     RevylAI/greenlight (MIT): scan rules, ported to scripts/scan.py
     safaiyeh/app-store-review-skill (MIT): references/apple/
     android/skills play-policy-insights (Apache-2.0): references/google-play/, the data-collection signals, the critic step -->

One pass from "is this allowed?" to a report the team can submit from. The
rules come from three places, in this order of trust:

1. **The official pages, fetched live** every run (`references/sources.json`).
2. **The reference files** (`references/apple/`, `references/google-play/`),
   detailed checklists last checked against the live pages on the date in
   `references/baseline.json`.
3. **The scanner** (`scripts/scan.py`), which finds the evidence quickly but
   never decides alone.

Where the live text and a reference disagree, the live text wins and the
report says so.

`SKILL` below is this skill's folder. `APP` is the app's folder: the one
holding `app.json` or `app.config.*` (in a monorepo often `mobile/` or
`apps/<name>`). `T` is a scratch directory outside the repository (the
session scratchpad, or `mktemp -d`). Never write scan output into the
repository.

The skill is built for Expo and React Native apps. A bare React Native or
fully native app already has `ios/` and `android/`: skip prebuild in step 2
and pass `APP` itself as `--native`.

## 1. Fetch the current rules

```
uv run SKILL/scripts/fetch_guidelines.py --out T/guidelines
```

It saves each official page as text in `T/guidelines/<id>.md` and writes
`T/guidelines/report.json`. Read the summary it prints:

- **FAILED source**: say so at the top of the report. Rules from that source
  were checked against the reference file only.
- **changed / added** sections: read the live text of each in
  `T/guidelines/<id>.md`. Use it instead of the matching part of the
  reference file named in the source's `references`.
- **removed** sections: the rule is gone. Don't report findings against it.
- **no baseline yet**: a source added since the baseline. Its live text is the only rule.
- **Apple Developer News** items: read any about guidelines, privacy,
  SDK minimums or age ratings. They often take effect before the guidelines page
  changes.
- **facts**: Play's target API levels and the upcoming Play policy deadlines.
  The scan uses these, and the report lists every deadline before the planned
  release.

## 2. Build the scan inputs

An Expo app using continuous native generation doesn't commit `ios/` and
`android/`, so generate them in a copy, never in `APP` itself. Install
dependencies with the project's package manager if `node_modules` is missing
or stale (`npm ci` below).

```
(
  cd APP && npm ci
  npx expo config --json --type prebuild > T/expo-config.json
  mkdir -p T/native
  tar --exclude=./node_modules --exclude=./.expo --exclude=./ios --exclude=./android -cf - . | tar -xf - -C T/native
  ln -s "$PWD/node_modules" T/native/node_modules
  cd T/native && CI=1 npx expo prebuild --no-install --clean --platform all
)
```

Use absolute paths for `T` and `APP`.

Every warning prebuild prints is a finding (for example, a config option that needs a
module that isn't installed). If prebuild fails, report that and run the scan
without `--native`.

## 3. Scan

```
uv run SKILL/scripts/scan.py APP --config T/expo-config.json --native T/native \
  --facts T/guidelines/report.json --out T/scan.json
```

`T/scan.json` holds:

- `findings`: rule hits with a severity, store, guideline and evidence.
  `kind: cleanup` marks a mechanical fix.
- `data_safety.data_sources`: every data type the code touches, with the files
  that touch it, keyed like `references/google-play/policies.json`.
- `data_safety.files_of_interest`, `other_signals.disclosure`, `policy_urls`:
  the starting points for consent, legal and account checks.

A line that is deliberately fine carries `// store-submission:ignore <rule-id> <why>`.

## 4. Review against every rule

A scan only proves that a pattern exists. This step decides what it means. Work the
domains below, each against its reference file and the live text from step 1,
and read the product docs before you judge intent (see [Project context](#project-context)).
If you can start subagents, give each domain its own, at most three at a time,
each writing `T/review-<domain>.json`. If you can't, do them yourself, one by
one.

| Domain | Reference | Live source | Look hardest at |
| --- | --- | --- | --- |
| apple-safety | `apple/1-safety.md` | apple-review-guidelines 1.x | User-generated and AI-generated content (1.2): filtering, reporting, blocking; age-appropriateness |
| apple-performance | `apple/2-performance.md` | 2.x, apple-upcoming-requirements | Completeness, demo access, accurate metadata, hidden or OTA-switched features, SDK minimums |
| apple-business | `apple/3-business.md` | 3.x | Paywalls, subscriptions, any non-IAP purchase path |
| apple-design | `apple/4-design.md` | 4.x | Minimum functionality, login options (4.8), copycat or spam patterns |
| apple-legal | `apple/5-legal.md` | 5.x, apple-privacy-details | Consent before collection, data minimisation, account deletion, third-party AI disclosure (5.1.2(i)) |
| play-data-safety | `google-play/data-safety.md` | play-data-safety | Trace every `data_sources` entry to where it leaves the device; prominent disclosure |
| play-permissions | `google-play/permissions-and-apis.md` | play-restricted-permissions | Each permission in the generated manifest against the app's core purpose |
| play-account-and-ai | `google-play/user-account.md` | play-account-deletion, play-ai-generated-content, play-age-restricted, play-policy-center | Reviewer access, in-app and web deletion, in-app reporting of AI output, target audience and age restrictions |

Judge the app as it's built today. Only code that ships in the next build can
get it rejected now. A planned feature (an unticked build step in a draftsman
spec, or backend code no screen calls yet) gives a finding that applies "when
that step ships": report it, but never as blocking today.

Every finding needs evidence: a `file:line`, a config key, or a check that
something required is missing (for example, a search that found no deletion flow).
Without evidence it isn't a finding. When the code can't settle a question
(server behaviour, what a reviewer will see), record it as MANUAL with what
someone has to check.

Write each finding as JSON: `store`, `rule` (guideline number or Play
policy), `severity` (CRITICAL, HIGH, WARN or INFO: Google's IMPORTANT maps
to HIGH and SUGGESTION to INFO), `applies` (`now`, or `when <step> ships`),
`title`, `evidence`, `fix`, and `owner`. The owner is one of: `cleanup`
(mechanical, see `references/cleanup.md`), `console`, a build step id, a
decision id, or `team`. Use a build step only when that step really covers the work,
and `team` when nothing in the spec does. Something no guideline or policy requires
(a build profile, say) is a submission prerequisite: cite it as such, not under a
guideline number. Also record the high-risk rules you checked and found met, as
INFO titled "OK: …", so the report can say they were checked.

While reviewing, also draft both privacy answers: the Apple App Privacy table
and the Play Data safety table. Use the scan's `data_sources`, what the backend
does with the data (read the backend code and docs, not only the app), and
`google-play/policies.json` for Play's categories.

## 5. Critic

Adapted from play-policy-insights. Give every CRITICAL and HIGH finding, from the
scan and from the review, a second look with fresh eyes: a fresh subagent if you
can start one, or yourself, rereading the code at the evidence. Mark each one:

- **VERIFIED**: the code confirms it.
- **PRUNED**: false positive. The safeguard exists, the pattern is test or
  dead code, or the rule doesn't apply. Drop it and keep a one-line reason.
- **MANUAL**: it can't be settled statically. It goes to "Needs a person".

While checking, also correct the finding itself. Check that the cited rule really
says what the finding claims, using the live text. Check that `applies` and
`severity` fit the app as built today. Check that the owner exists and really
covers the work. Merge duplicates: the scan and several reviewers often report
the same issue, so keep one entry and list what it merges.

## 6. Report

Fill `references/report-template.md` into `T/store-readiness.md` and give the
user the verdict, the blocking table and the file's path. List the open
console items from `references/store-console.md` with their answers.

## 7. Clean up

Fix the findings `references/cleanup.md` lists as mechanical. Follow the
project's own rules for branches, commits and checks (its `AGENTS.md` or
`CONTRIBUTING.md`): one commit per fix, named like the project's history, with
the checks passing. If the project has no rules, work on a new branch. Don't
fix anything that changes specified behaviour, needs a fact the docs don't
give, or adds a feature. Those stay in the report with their owner, and
questions go to the team one at a time.

Then run step 3 again and update the report's "Cleanup done" and verdict.

## Keeping the skill current

When step 1 reports changed sections, the live text already wins for that
run, so users don't need to do anything. Maintainers make the change stick in
the store-submission repository: edit the matching reference file, then accept
the live pages as the new baseline and commit both:

```
uv run SKILL/scripts/fetch_guidelines.py --out T/guidelines --update-baseline
```

To watch a new official page, add it to `references/sources.json` (with
`references` naming the file it backs) and update the baseline. Rules
the scanner should catch go in `scripts/scan.py` with a test in
`scripts/test_store_submission.py`:

```
uv run python -m unittest discover -s SKILL/scripts -p 'test_*.py'
```

## Project context

The answers the review needs come from the project, never from guesses. Read
them before step 4, and cite where each answer came from.

- **A draftsman spec** (`docs/product.md`, `docs/decisions.md`,
  `docs/never.md`, `docs/features/`, `docs/shared/`): read who the users are, what is
  collected and why, which AI or other third parties get data, and the build
  steps that own missing features such as account deletion. Any `open` or
  `proposed` decision a finding depends on owns that finding: report it as
  blocking under the decision's id, and never make up the answer. If a rule could
  only be met by something in `docs/never.md`, ask the team.
- **Any other docs** (a PRD, a README, a privacy policy draft): use what
  they state, and cite the file.
- **Nothing written down**: ask the user, one question at a time, for what the
  forms need: the audience and age, what data leaves the device and to whom, and
  whether accounts and purchases exist. Put every answer you didn't get in the report
  as open.
