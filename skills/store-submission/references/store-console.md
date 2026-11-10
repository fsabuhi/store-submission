# What the store consoles need

Review checks the console answers as hard as the binary, and none of this lives in the code. The report lists each item with its answer, where that answer comes from (a doc, the scan or the team) and whether it is still missing. These pages change, so check each item against the live text `fetch_guidelines.py` saved before calling it done.

## Both stores

- **Privacy policy URL**: public, final (not a placeholder), and it names the data the app collects and the third parties it goes to, AI model providers included.
- **Support URL or email**: works without logging in.
- **Reviewer access**: if any feature is behind a login, a working, non-expiring demo account, or review notes explaining the guest path. Apple 2.1 and Play's App access both reject an app the reviewer can't get into.
- **Account deletion**: in the app, and for Play also a public web page that deletes the account without the app installed. Its URL goes into the Data safety form.
- **Age rating**: Apple's questionnaire and Play's IARC questionnaire, answered for the app as it really behaves, AI-generated replies and user-written text included. An 18+ product says so in both and in the target audience.
- **Screenshots and description**: show the real app, with no claims it can't back up, no prices in the screenshots and no other platform named (Apple 2.3, Play Store Listing and Promotion).
- **Release build**: a store profile pointing at production, with a version and build number above the last upload.

## App Store Connect

- **App Privacy (nutrition labels)**: every data type the app or its SDKs collect, whether it's linked to the user, whether it's used for tracking, and why. Build it from the scan's `data_safety` signals plus the docs; it must match the privacy policy.
- **Third-party AI disclosure (5.1.2(i))**: personal data sent to a third-party AI service needs a clear in-app disclosure and the user's permission first.
- **Encryption export compliance**: `usesNonExemptEncryption` in the Expo config answers it for every upload.
- **Required-reason APIs**: declared in `ios.privacyManifests`; an upload missing one gets an ITMS-91053 email.
- **Screenshots**: the current largest iPhone size, plus the largest iPad size if `supportsTablet` is true.
- **EU Digital Services Act trader status**: set before the app can be listed in the EU.
- **Review notes**: what the reviewer needs to reach every feature, including guest limits and paywalls.
- **Subscriptions and in-app purchases**: products submitted with the build, each with a review screenshot, plus terms and privacy links in the paywall (3.1.2).

## Google Play Console

- **Data safety form**: every data type collected or shared, whether it's encrypted in transit, whether users can ask for deletion, and the deletion URL. Map each `data_safety.data_sources` key through `references/google-play/policies.json` to the form's category and data type.
- **App access**: login details or instructions for every gated feature.
- **Ads declaration** and **Advertising ID declaration**: whether the app shows ads or reads the advertising ID.
- **Target audience and content**: age groups. Choosing any group under 13 brings in the Families policy; teen groups bring their own content limits.
- **Content rating (IARC)**.
- **AI-generated content**: apps that generate content with AI need in-app reporting or flagging of offensive output, without leaving the app.
- **Sensitive permission declarations**: one form for each restricted permission the manifest keeps (see `google-play/permissions-and-apis.md`).
- **Testing before production**: new personal developer accounts need a closed test with enough testers over enough days before they can apply for production access. Check the live count in Play Console.
- **Store listing assets**: a 512x512 icon, a 1024x500 feature graphic and phone screenshots.
- **Target API level**: the scan checks it against the live requirement.
