# Store Submission

Get a mobile app through App Store and Google Play review the first time. Store Submission is an [Agent Skill](https://agentskills.io) for Claude Code, Codex, Copilot, Gemini CLI, Cursor and any other agent that reads skills. It's built for Expo and React Native apps.

Review rules change every few months, and a checklist copied into a prompt goes stale quietly. Store Submission reads the official Apple and Google pages on every run, tells you which rules changed since its checklists were last checked, and lets the live text win.

## What it does

1. **Fetches the current rules** from Apple and Google: the App Review Guidelines, upcoming requirements and developer news, App Privacy Details, Play's policy deadlines, target API level, Data safety, account deletion, restricted permissions and AI-generated content pages. It compares each page section by section with the last checked state and lists what changed.
2. **Scans the app**: source, the resolved Expo config, and the iOS and Android projects `expo prebuild` generates in a scratch copy. That covers hardcoded secrets, external payments, missing account deletion or Sign in with Apple, placeholder content, dev server addresses, purpose strings, required-reason APIs, target SDK against the live requirement, restricted Android permissions, exported components, debuggable builds and more. Each finding cites its guideline or policy.
3. **Reviews against every rule**, area by area: Apple's five guideline sections and Play's data safety, permissions, accounts and AI-content policies. Every finding needs evidence. A critic pass then rechecks each serious one and drops false positives.
4. **Drafts the privacy answers**: the App Store privacy label and the Play Data safety form, built from what the code actually collects and where it sends it.
5. **Lists the console tasks** neither scanner can see: demo accounts, age ratings, the deletion URL, declarations and screenshots.
6. **Cleans up** what's mechanical (debug logs, dev addresses, Expo's default Android permissions, export compliance, missing store build profile), one commit per fix. Anything that would change what the app does stays in the report for you to decide.

You get one report with a verdict for each store, the blocking findings and their owners, the cleanup commits, both privacy tables, what a person still has to test, and the deadlines coming up.

## Install

### Claude Code

```
/plugin marketplace add fsabuhi/store-submission
/plugin install store-submission@store-submission
```

### Codex

```bash
codex plugin marketplace add fsabuhi/store-submission
```

Then open `/plugins` in Codex and install Store Submission.

### GitHub Copilot CLI

```bash
copilot plugin marketplace add fsabuhi/store-submission
copilot plugin install store-submission@store-submission
```

### Gemini CLI

```bash
gemini extensions install https://github.com/fsabuhi/store-submission
```

### Any agent, with the skills CLI

```bash
npx skills add fsabuhi/store-submission
```

### By hand

Copy `skills/store-submission/` into your agent's skills folder, such as `~/.claude/skills/` for Claude Code. If an agent doesn't support skills, tell it: "Read `skills/store-submission/SKILL.md` and follow it."

## Use

Just ask:

- "Will this app get rejected by the App Store or Google Play?"
- "Prepare the app for store submission and clean up what would get it rejected."
- "Draft our App Store privacy labels and Play Data safety answers."

It needs [uv](https://docs.astral.sh/uv/) (or Python 3.11+), Node for `expo prebuild`, and network access to `developer.apple.com`, `support.google.com`, `developer.android.com` and `play.google.com`. Nothing else is installed, and nothing about your app is sent anywhere.

## With a spec

If the project has a [draftsman](https://github.com/fsabuhi/draftsman) spec, the review reads its product, decisions and never-list for the answers the forms need. Each blocking finding is then owned by the build step or open decision it waits on. Without a spec, it asks you, one question at a time, and lists anything left unanswered as open.

## Limits

- The scan proves a pattern exists, not that a flow works. Account deletion, restore purchases and reviewer login still need someone to try them on a release build. The report lists them.
- iOS privacy manifests from CocoaPods are only merged in a real iOS build, so the scan checks the app's own declarations only.
- Some data-collection signals are broad, such as `track`, and the critic step is what prunes them.

## Develop

```bash
uv run python -m unittest discover -s skills/store-submission/scripts -p 'test_*.py'
```

Contributor notes are in [AGENTS.md](AGENTS.md).

## Credits

Store Submission merges and extends three open-source projects: [Greenlight](https://github.com/RevylAI/greenlight) (MIT), whose scan rules are ported to Python here; [app-store-review-skill](https://github.com/safaiyeh/app-store-review-skill) (MIT), the Apple guideline checklists; and Google's [Play Policy Insights](https://github.com/android/skills) (Apache-2.0), the Play policy checklists, data-collection signals and critic step. See [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

## License

[MIT](LICENSE)
