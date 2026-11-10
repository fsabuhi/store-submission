"""Tests for the store-submission scripts. Run: python -m unittest discover -s .agents/skills/store-submission/scripts"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fetch = load("fetch_guidelines")

MANIFEST = """<manifest xmlns:android="http://schemas.android.com/apk/res/android" xmlns:tools="http://schemas.android.com/tools">
  <uses-permission android:name="android.permission.INTERNET"/>
  <uses-permission android:name="android.permission.SYSTEM_ALERT_WINDOW"/>
  <uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE" tools:node="remove"/>
  <application android:debuggable="true">
    <activity android:name=".MainActivity">
      <intent-filter><action android:name="android.intent.action.MAIN"/></intent-filter>
    </activity>
  </application>
</manifest>
"""


class ScanTest(unittest.TestCase):
    def scan(self, files: dict[str, str], *extra: str, facts: dict | None = None) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel, text in files.items():
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(textwrap.dedent(text))
            args = [
                str(root / "app"),
                "--out",
                str(root / "scan.json"),
                *[a.replace("{root}", str(root)) for a in extra],
            ]
            if facts is not None:
                (root / "report.json").write_text(json.dumps({"facts": facts}))
                args += ["--facts", str(root / "report.json")]
            subprocess.run([sys.executable, str(HERE / "scan.py"), *args], check=True, capture_output=True)
            return json.loads((root / "scan.json").read_text())

    @staticmethod
    def ids(result: dict) -> list[str]:
        return [f["id"] for f in result["findings"]]

    def test_flags_policy_and_cleanup_issues_in_source(self):
        result = self.scan(
            {
                "app/package.json": '{"dependencies": {}}',
                "app/src/a.ts": """
                const key = "sk_live_abcdefghijklmnopqrstuvwx";
                export const privacy = "https://example.com/privacy";
                export const api = "http://192.168.1.20:8000";
                export function signUp() {}
                console.log("token", key);
            """,
            }
        )
        ids = self.ids(result)
        for expected in (
            "hardcoded-secret",
            "placeholder-content",
            "hardcoded-ipv4",
            "http-url",
            "account-without-deletion",
            "console-call",
        ):
            self.assertIn(expected, ids)

    def test_a_safeguard_anywhere_satisfies_the_rule(self):
        result = self.scan(
            {
                "app/src/signup.ts": "export function signUp() {}\n",
                "app/src/settings.ts": "export function deleteAccount() {}\n",
            }
        )
        self.assertNotIn("account-without-deletion", self.ids(result))

    def test_ignore_comment_silences_one_rule_on_the_next_line(self):
        result = self.scan(
            {
                "app/src/a.ts": """
            // store-submission:ignore http-url the emulator's loopback
            const dev = "http://dev.internal/";
            const other = "http://plain.example.net/";
        """
            }
        )
        lines = [f["line"] for f in result["findings"] if f["id"] == "http-url"]
        self.assertEqual(lines, [4])

    def test_asset_paths_enum_values_and_generated_types_are_not_copy(self):
        result = self.scan(
            {
                "app/src/a.ts": """
                const icon = "./assets/android-icon.png";
                type Client = "ios" | "android";
            """,
                "app/src/schema.d.ts": 'client: "Available on Android";\n',
                "app/src/b.tsx": 'const t = "Also on Google Play";\n',
            }
        )
        hits = [f["file"] for f in result["findings"] if f["id"] == "platform-reference"]
        self.assertEqual(hits, ["src/b.tsx"])

    def test_expo_config_and_native_projects(self):
        result = self.scan(
            {
                "app/app.json": json.dumps(
                    {"expo": {"name": "My App", "ios": {"infoPlist": {"NSCameraUsageDescription": ""}}}}
                ),
                "native/android/app/src/main/AndroidManifest.xml": MANIFEST,
                "native/android/gradle.properties": "android.targetSdkVersion=35\n",
            },
            "--native",
            "{root}/native",
            facts={
                "play_target_sdk_new": 36,
                "play_target_sdk_existing": 35,
                "play_target_sdk_new_from": "August 31 2026",
            },
        )
        by_id = {f["id"]: f for f in result["findings"]}
        self.assertEqual(by_id["target-sdk"]["severity"], "CRITICAL")  # the requirement has started
        self.assertIn("below API 36", by_id["target-sdk"]["title"])
        for expected in (
            "app-name",
            "ios-bundle-id",
            "android-package",
            "empty-purpose-string",
            "debuggable",
            "exported",
            "restricted-permission",
        ):
            self.assertIn(expected, by_id)
        self.assertEqual(result["android_target_sdk"], {"value": 35, "from": "gradle.properties"})
        permissions = " ".join(f["title"] for f in result["findings"] if f["id"] == "restricted-permission")
        self.assertIn("SYSTEM_ALERT_WINDOW", permissions)
        self.assertNotIn("READ_EXTERNAL_STORAGE", permissions)  # blocked with tools:node="remove"

    def test_target_sdk_requirement_announced_for_later_is_not_yet_critical(self):
        result = self.scan(
            {
                "native/android/app/src/main/AndroidManifest.xml": MANIFEST,
                "native/android/gradle.properties": "android.targetSdkVersion=35\n",
            },
            "--native",
            "{root}/native",
            facts={
                "play_target_sdk_new": 36,
                "play_target_sdk_existing": 35,
                "play_target_sdk_new_from": "August 31 2099",
            },
        )
        sdk = next(f for f in result["findings"] if f["id"] == "target-sdk")
        self.assertEqual(sdk["severity"], "HIGH")
        self.assertIn("August 31, 2099", sdk["detail"])

    def test_a_comment_is_not_the_safeguard(self):
        result = self.scan(
            {
                "app/src/a.ts": """
            // NOTE: account deletion waits for build step 5.11
            export function signUp() {}
        """
            }
        )
        self.assertIn("account-without-deletion", self.ids(result))

    def test_native_code_hits_are_kept_beside_source_hits(self):
        result = self.scan(
            {
                "app/src/a.ts": 'const a = "http://one.example.net/";\n',
                "native/android/app/src/main/java/M.kt": 'val b = "http://two.example.net/"\n',
            },
            "--native",
            "{root}/native",
        )
        files = sorted(f["file"] for f in result["findings"] if f["id"] == "http-url")
        self.assertEqual(files, ["native/android/app/src/main/java/M.kt", "src/a.ts"])

    def test_a_bare_app_is_its_own_native_dir_and_is_scanned_once(self):
        result = self.scan(
            {
                "app/android/app/src/main/AndroidManifest.xml": MANIFEST,
                "app/android/app/src/main/java/M.kt": 'val b = "http://two.example.net/"\n',
            },
            "--native",
            "{root}/app",
        )
        self.assertEqual(self.ids(result).count("http-url"), 1)
        self.assertIn("debuggable", self.ids(result))

    def test_dev_guarded_console_calls_are_fine(self):
        result = self.scan({"app/src/a.ts": "__DEV__ && console.warn(error);\nif (__DEV__) console.log(x);\n"})
        self.assertNotIn("console-call", self.ids(result))

    def test_eas_needs_a_store_profile(self):
        internal = {"build": {"staging": {"distribution": "internal"}, "dev": {"developmentClient": True}}}
        self.assertIn("eas-store-profile", self.ids(self.scan({"app/eas.json": json.dumps(internal)})))
        internal["build"]["production"] = {"autoIncrement": True}
        self.assertNotIn("eas-store-profile", self.ids(self.scan({"app/eas.json": json.dumps(internal)})))

    def test_data_safety_signals_include_react_native_calls(self):
        result = self.scan({"app/src/client.ts": 'headers["X-Device-Id"] = id;\n'})
        self.assertIn("DEVICE_ID", result["data_safety"]["data_sources"])


APPLE_PAGE = """<html><body><nav>Global nav</nav><h1>App Review Guidelines</h1>
<p>Intro</p><ul><li id="1.1"><strong>1.1</strong> Objectionable content</li>
<li id="1.1.1"><strong>1.1.1</strong> Defamatory content.</li></ul>
<p>Last Updated: <a href="#">October 16, 2026</a></p><footer>Developer Footer</footer></body></html>"""

HELP_PAGE = """<html><body><h1>Policy Deadlines</h1><h2>Upcoming</h2><table>
<tr><td>2099-01-27</td><td>Contacts Permissions policy starts.</td><td>Announced 2026-04-15</td></tr>
<tr><td>2001-01-01</td><td>An old change that already passed.</td></tr></table>
<h2>Was this helpful?</h2><p>9876543210123456</p></body></html>"""


class FetchTest(unittest.TestCase):
    def test_apple_page_splits_by_guideline_id_and_drops_chrome(self):
        text, sections = fetch.html_sections(APPLE_PAGE, "apple-ids")
        self.assertEqual(list(sections), ["(intro)", "1.1", "1.1.1"])
        self.assertNotIn("Global nav", text)
        self.assertNotIn("Developer Footer", text)
        self.assertEqual(
            fetch.extract_facts({"apple-review-guidelines": text})["apple_guidelines_last_updated"], "October 16, 2026"
        )

    def test_help_page_stops_at_help_centre_chrome(self):
        text, sections = fetch.html_sections(HELP_PAGE, "headings")
        self.assertIn("Upcoming", sections)
        self.assertNotIn("9876543210123456", text)

    def test_only_upcoming_play_deadlines_are_facts(self):
        text, _ = fetch.html_sections(HELP_PAGE, "headings")
        deadlines = fetch.extract_facts({"play-policy-deadlines": text})["play_upcoming_deadlines"]
        self.assertEqual([d["deadline"] for d in deadlines], ["2099-01-27"])
        self.assertEqual(deadlines[0]["change"], "Contacts Permissions policy starts.")

    def test_target_sdk_facts(self):
        text = (
            "Starting August 31 2026: New apps and app updates must target Android 16 (API level 36) or higher. "
            "Existing apps must target Android 15 (API level 35) or higher to remain available."
        )
        facts = fetch.extract_facts({"play-target-sdk": text})
        self.assertEqual((facts["play_target_sdk_new"], facts["play_target_sdk_existing"]), (36, 35))
        self.assertEqual(facts["play_target_sdk_new_from"], "August 31 2026")

    def test_digest_ignores_per_request_tokens(self):
        self.assertEqual(
            fetch.digest("Policy 11398003695360486553 text"), fetch.digest("Policy 5370087442651943286  text")
        )
        self.assertNotEqual(fetch.digest("target API 35"), fetch.digest("target API 36"))

    def test_news_keeps_recent_rule_items_only(self):
        now = dt.datetime.now(dt.timezone.utc)
        rss = f"""<rss><channel>
            <item><title>Updated App Review Guidelines now available</title><link>https://a/1</link>
              <pubDate>{now.strftime("%a, %d %b %Y %H:%M:%S +0000")}</pubDate><description>Changes.</description></item>
            <item><title>Swift Student Challenge</title><link>https://a/2</link>
              <pubDate>{now.strftime("%a, %d %b %Y %H:%M:%S +0000")}</pubDate><description>Students.</description></item>
            <item><title>Old review guideline change</title><link>https://a/3</link>
              <pubDate>Mon, 01 Jan 2001 00:00:00 +0000</pubDate><description>Old.</description></item>
        </channel></rss>"""
        _, sections = fetch.rss_sections(rss)
        self.assertEqual([k.split(" ", 1)[1] for k in sections], ["Updated App Review Guidelines now available"])


if __name__ == "__main__":
    unittest.main()
