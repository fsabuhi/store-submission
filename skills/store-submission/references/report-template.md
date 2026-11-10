# Store readiness: {app name} {version}

{date}. Rules fetched live {fetched time}; references last checked {baseline date}.

## Verdict

| Store | Verdict | Blocking |
| --- | --- | --- |
| App Store | READY / NOT READY / READY AFTER CONSOLE STEPS | {count} |
| Google Play | ... | {count} |

One or two sentences in plain English: what stops submission today, and what has to happen first.

## Rules that changed since the references were checked

Each changed or new section from `report.json`, what it now says, and whether it affects this app. If none changed, say so. If a source failed to fetch, list it here: its rules were checked against the stored reference only.

## Blocking

Everything CRITICAL or HIGH that applies now and survived the critic, most severe first:

| # | Store | Rule | Finding | Evidence | Fix | Owner |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | both | 5.1.1(v) / Account deletion | ... | `file:line` | ... | a build step / a decision id / cleanup / console / team |

## Coming with later steps

Findings that apply when a step ships, not today: each one's rule, what it will need, the step it applies to and its owner. Most of these are things the spec doesn't cover yet. Raise them before that step is built, not at submission.

## Cleanup done

One line per commit: what was fixed and the finding it closes.

## Console tasks

The items from `store-console.md` that are still open, each with the answer to enter and where that answer came from.

## Privacy answers

### Apple App Privacy

| Data type | Collected | Linked to user | Tracking | Purposes | Evidence |
| --- | --- | --- | --- | --- | --- |

### Google Play Data safety

| Category / data type | Collected | Shared | Optional | Purposes | Encrypted in transit | Deletable | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |

## Needs a person

Flows a static check can't prove and someone has to test on a release build: account deletion really deletes, the reviewer login works, restore purchases, reporting AI output. Also every MANUAL verdict from the critic.

## Upcoming deadlines

Play policy deadlines and Apple requirements from the live fetch that land before the planned release, and what each needs.

## Warnings and suggestions

WARN and INFO findings that weren't cleaned up, grouped by rule.
