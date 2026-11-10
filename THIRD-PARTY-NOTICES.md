# Third-party notices

Work copied or adapted from other projects, with its licence.

## Greenlight

- Source: https://github.com/RevylAI/greenlight, commit fcb36e3
- Licence: MIT
- Used in: `skills/store-submission/scripts/scan.py`, which ports its code-scan, Expo config, privacy-manifest and Play manifest rules from Go to Python and adapts them to Expo's generated native projects

```
MIT License

Copyright (c) 2025 Revyl

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## App Store Review Guidelines skill

- Source: https://github.com/safaiyeh/app-store-review-skill, commit 7197cff
- Licence: MIT
- Used in: `skills/store-submission/references/apple/`, copied unchanged

```
MIT License

Copyright (c) 2026 safaiyeh

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Play Policy Insights

- Source: https://github.com/android/skills, `play/play-policy-insights`, commit 5815d27, Copyright 2026 The Android Open Source Project
- Licence: Apache License 2.0, full text in `skills/store-submission/LICENSE-Apache-2.0.txt`
- Used in: `skills/store-submission/references/google-play/` (`policies.json` and `scanner_config.json` unchanged; the three `.md` files adapted from its `goal_*.md` prompts with the template tags and output schema removed, each marked at the top), the data-collection signal scan in `scripts/scan.py`, and the critic step in `SKILL.md`
