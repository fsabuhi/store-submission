# Cleanup before a store build

These are the mechanical fixes the skill makes itself, once the report is out. Each is its own commit under the project's rules: it changes no specified behaviour, and the existing checks pass. Anything that needs a fact the docs don't give, or changes what the app does, is not cleanup. It goes in the report as blocking, with the step or decision that owns it.

| Finding | Fix | Needs the team when |
| --- | --- | --- |
| `console-call` | Delete debug logs. Route real error reporting through the app's one logger, or wrap it in `if (__DEV__)`. Never log tokens, chat text or ids. | Never |
| `dev-endpoint`, `hardcoded-ipv4` | Read the address from `EXPO_PUBLIC_*` build config. Keep a dev fallback only behind `__DEV__`. | The production address isn't in the docs or `eas.json` |
| `http-url` | Use `https://`. | The host has no TLS |
| `placeholder-content` | Put in the final text or link. | The final value isn't decided, or waits on an open decision |
| `unused-asset` | Delete the file, after grepping for a computed name (`require(\`./${x}.png\`)`). | Never |
| `restricted-permission` for Expo defaults (`SYSTEM_ALERT_WINDOW`, `READ_EXTERNAL_STORAGE`, `WRITE_EXTERNAL_STORAGE`) | Add them to `android.blockedPermissions` in the Expo config, unless a shipped feature reads files outside the app. | A feature needs them |
| `export-compliance` | Set `ios.config.usesNonExemptEncryption: false` when the app only uses HTTPS and OS-provided encryption. | The app adds its own encryption |
| `required-reason-api` (the app's own Swift or Objective-C only; modules ship their own manifests) | Add the API type and its approved reason under `ios.privacyManifests` in the Expo config. | Never; pick the reason code that matches the use |
| `vague-purpose-string`, `empty-purpose-string` | Say which feature uses the permission and what for. | The feature's purpose isn't in its spec |
| Prebuild warnings (for example a missing `expo-system-ui` for `userInterfaceStyle`) | Install the module the warning names (`npx expo install <module>`). | The fix would drop or change a setting, which changes how the app behaves |
| `eas-store-profile` | Add a `production` profile: distribution `store`, `autoIncrement`, the production `EXPO_PUBLIC_*` values. | The production values aren't known |
| `dev-client` | Make sure the store profile builds without the dev client. | Never |

Never cleanup, always the team's call:

- Adding a feature a rule requires (account deletion, in-app reporting, Sign in with Apple, a consent screen). That's a build step: name it in the report.
- Changing what data is collected or where it's sent.
- Removing a permission a shipped feature uses.
- Anything in `docs/never.md`.

After the fixes, run `scan.py` again. The run is clean when nothing CRITICAL or HIGH is left that isn't owned by an unfinished step or an open decision.
