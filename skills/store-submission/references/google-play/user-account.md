<!-- Adapted from github.com/android/skills, play/play-policy-insights/resources/goal_user_account.md (Apache-2.0); see THIRD-PARTY-NOTICES.md. Template tags and the orchestrator output schema are removed. -->

# Google Play: User accounts, reviewer access and account deletion


### Hint: Deducing Account Presence

To determine if an app handles user accounts (even if it uses third-party
providers like Google Sign-In or Firebase Auth), look for:
1. **Login/Auth Screens**: Semantic files or layouts named `login`, `auth`,
   `signin`, or `signup`.
2. **Account Management**: APIs like `AccountManager`, `CredentialManager`, or
   `Firebase.auth`.
3. **User Profile**: UI strings or data models referencing `profile`,
   `my account`, or `user settings`.

### Policies to Verify

#### Play Console Requirements (Policy ID: login_credentials)

- **Goal**: Identify if the app implements a login wall or authentication
  screen.
- **The Policy Spirit**: To ensure Play Store reviewers can successfully test
  and audit apps, developers must submit functional, non-expiring credentials in
  Play Console if the app's features are gated behind a login screen.
  - **Account Files**:
  - **Account Signals**:
- **Common Evaluation Matrix**:
  | App State | Finding / Condition | Severity | Actionable Recommendation |
  | :--- | :--- | :--- | :--- |
  | **Login Screen Detected** | App displays or contains a login screen, registration wall, or authentication interface. | `IMPORTANT` | **Administrative Console Requirements**: Because your app implements a login flow, you MUST complete two manual setup steps in the Play Console dashboard to pass review:<br>1. **Reviewer Demo Credentials**: Submit active, non-expiring test credentials so Google Play reviewers can access your gated features.<br>2. **Account Deletion Link**: Submit a public-facing web link for account deletion to satisfy Google Play's data deletion policies. |

- **Domain-Specific Heuristics (Strictly Bounded)**:
  Look beyond standard native login buttons. Extrapolate using this heuristic:
  1. **Hidden Gatekeepers**: Analyze if certain critical features (e.g.,
     synchronizing local database, checkout forms, or member-only dashboards)
     require authentication even if the app opens directly to a main page. If
     you deduce that functional workflows require a login, treat it as a login
     gate and output the `IMPORTANT` console credentials and deletion link
     reminders.

#### Account Deletion Requirement (Policy ID: account_deletion)

- **Goal**: If the app handles user accounts, it must provide a discoverable
  in-app account deletion mechanism.
- **The Policy Spirit**: Users have a fundamental right to request data erasure.
  If they can create an account in-app, they must be able to delete it in-app.
  Deletion must wipe remote database records, not just sign out.
  - **Account signals (Presence)**:
  - **Deletion signals (Mechanism)**:
- **Common Evaluation Matrix**:
  | App Account Status | Finding / Deletion Evidence | Severity | Actionable Recommendation |
  | :--- | :--- | :--- | :--- |
  | **Handles User Accounts** | App manages user accounts, but NO code, layout, or string suggests an in-app deletion button or process. | `IMPORTANT` | **Implement in-app deletion**: Create a highly discoverable path (e.g., under User Profile/Account Settings) to let users initiate account deletion directly in the app. |

- **Domain-Specific Heuristics (Strictly Bounded)**:
  Do not limit your analysis to basic "Delete" buttons. Actively analyze custom
  and grey-area implementations:
  1. **The Partial Deletion Trap**: Read the implementation of any found
     deletion mechanisms. If the code merely calls `clearPreferences()`, clears
     a local cookie, or triggers a standard `logout()` without sending a remote
     delete/purge network API call to clean up backend user records, flag this
     as a `IMPORTANT` violation of the deletion mandate.
  2. **Indirect User Accounts**: If the app uses third-party sign-in bridges
     (e.g., Google Sign-In, Firebase) but does not store an
     explicit account profile on its own server, it still handles user account
     details if any user preferences or device identifiers are cached remotely.
     If so, a delete link/button is still required.
