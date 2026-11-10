#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Static pre-submission scan for the App Store and Google Play.

Reads an app's source, its resolved Expo config and, when given, the native
projects `expo prebuild` generates. Reports store-rule findings, cleanup
findings and the data-collection signals the privacy forms are built from.
Offline: the live rules come from fetch_guidelines.py, whose report.json can be
passed with --facts so deadlines and target API levels are current.

The code rules are ported from Greenlight (github.com/RevylAI/greenlight, MIT)
and the data-collection signals use Google's play-policy-insights scanner
config (github.com/android/skills, Apache-2.0); see THIRD-PARTY-NOTICES.md.

Usage:
    uv run scan.py APP_DIR [--config expo-config.json] [--native DIR] [--facts report.json]
                           [--out scan.json] [--exit-code]

Silence one line with a comment on it, or on the line above:
    // store-submission:ignore <rule-id> <why>
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import plistlib
import re
import struct
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SCANNER_CONFIG = SKILL / "references" / "google-play" / "scanner_config.json"

SEVERITIES = ["INFO", "WARN", "HIGH", "CRITICAL"]
SKIP_DIRS = {
    "node_modules",
    ".git",
    ".expo",
    ".expo-shared",
    "dist",
    "build",
    "Pods",
    ".gradle",
    "coverage",
    "__tests__",
    "__mocks__",
    ".scratch",
    ".idea",
    "web-build",
}
LANGS = {
    ".swift": "swift",
    ".m": "objc",
    ".mm": "objc",
    ".h": "objc",
    ".ts": "ts",
    ".tsx": "ts",
    ".js": "js",
    ".jsx": "js",
    ".mjs": "js",
    ".cjs": "js",
    ".kt": "kotlin",
    ".java": "java",
}
CODE = {"swift", "objc", "ts", "js", "kotlin", "java"}
JS = {"ts", "js"}
APPLE_CODE = {"swift", "objc", "ts", "js"}
TEST_FILE = re.compile(r"\.(test|spec)\.[jt]sx?$|/(test|tests|androidTest)/")
# Tooling config and generated type declarations: never shipped as app copy or behaviour
NOT_APP_CODE = re.compile(r"\.d\.ts$|(^|/)[\w-]+\.config\.[cm]?[jt]s$|(^|/)\.?(babel|metro|jest|eslint)rc")

DOC_TARGET_API = "https://support.google.com/googleplay/android-developer/answer/11926878"
DOC_RESTRICTED = "https://support.google.com/googleplay/android-developer/answer/14115180"
DOC_FGS = "https://support.google.com/googleplay/android-developer/answer/13392821"
DOC_AD_ID = "https://support.google.com/googleplay/android-developer/answer/6048248"
DOC_POLICY = "https://play.google.com/about/developer-content-policy/"
DOC_APPLE = "https://developer.apple.com/app-store/review/guidelines/#"
DOC_REQUIRED_REASON = "https://developer.apple.com/documentation/bundleresources/describing-use-of-required-reason-api"

# Used only when fetch_guidelines.py's facts are not passed; the report says so.
FALLBACK_TARGET_SDK_NEW = 36
FALLBACK_TARGET_SDK_EXISTING = 35


@dataclass
class Finding:
    id: str
    severity: str
    store: str  # apple, play or both
    kind: str  # policy or cleanup
    guideline: str
    title: str
    detail: str
    fix: str = ""
    file: str = ""
    line: int = 0
    code: str = ""
    doc: str = ""


@dataclass
class Rule:
    id: str
    severity: str
    store: str
    guideline: str
    title: str
    detail: str
    fix: str
    langs: set[str]
    patterns: list[str]
    kind: str = "policy"
    anti: list[str] = field(default_factory=list)  # found anywhere in the project: the rule is satisfied
    ignore: list[str] = field(default_factory=list)  # lines matching these are skipped
    once: bool = False  # a project-level fact: report the first hit only
    code_only: bool = False  # match code with strings and comments blanked

    def __post_init__(self):
        self.rx = [re.compile(p) for p in self.patterns]
        self.anti_rx = [re.compile(p) for p in self.anti]
        self.ignore_rx = [re.compile(p) for p in self.ignore]


def _q(words: str) -> list[str]:
    """Patterns matching any of `words` inside a "", '' or `` string literal."""
    return [rf"(?i){q}[^{q}]*\b({words})\b[^{q}]*{q}" for q in ('"', "'", "`")]


RULES: list[Rule] = [
    # CRITICAL
    Rule(
        "private-api",
        "CRITICAL",
        "apple",
        "2.5.1",
        "Private API usage",
        "Private or undocumented Apple APIs are an immediate rejection.",
        "Use the public API instead.",
        {"swift", "objc"},
        [r'NSSelectorFromString\s*\(\s*"_', r'performSelector.*"_', r"\bdlopen\s*\(", r"\bdlsym\s*\("],
    ),
    Rule(
        "hardcoded-secret",
        "CRITICAL",
        "both",
        "1.6",
        "Hardcoded secret or API key",
        "A secret shipped in the app can be read by anyone who downloads it.",
        "Keep secrets on the server. Only publishable client keys (a Firebase web API key, a Stripe publishable key) may ship.",
        CODE,
        [
            r"(sk_live_|sk_test_|rk_live_)[a-zA-Z0-9]{20,}",
            r"(?i)(api[_-]?secret|secret[_-]?key|client[_-]?secret|private[_-]?key)\s*[:=]\s*[\"'][A-Za-z0-9_\-]{16,}[\"']",
            r"AKIA[0-9A-Z]{16}",
            r"gh[pousr]_[a-zA-Z0-9]{36}",
            r"sk-(ant-|proj-)?[A-Za-z0-9_\-]{32,}",
            r"-----BEGIN (RSA |EC )?PRIVATE KEY-----",
        ],
    ),
    Rule(
        "external-payment-digital",
        "CRITICAL",
        "both",
        "3.1.1",
        "External payment that may be for digital goods",
        "Digital goods and subscriptions must use Apple in-app purchase and Google Play Billing; external payment is for physical goods and services.",
        "Use StoreKit and Play Billing (for example through RevenueCat or react-native-iap) for anything unlocked in the app.",
        APPLE_CODE | {"kotlin", "java"},
        [
            r"(?i)stripe.*payment.*intent",
            r"(?i)paypal.*checkout",
            r"(?i)braintree.*payment",
            r"(?i)checkout\.redirect.*url",
        ],
    ),
    Rule(
        "dynamic-code",
        "CRITICAL",
        "apple",
        "2.5.2",
        "Downloaded or dynamic code execution",
        "Apps may not download or run code that changes their features.",
        "Remove the dynamic execution.",
        {"swift", "objc"},
        [r"JSContext\s*\(\s*\).*evaluateScript", r"NSBundle.*\bload\b"],
    ),
    Rule(
        "js-eval",
        "CRITICAL",
        "both",
        "2.5.2",
        "eval or new Function in shipped code",
        "Running strings as code is read as executing downloaded code (Apple 2.5.2; Play Device and Network Abuse).",
        "Remove eval/new Function.",
        JS,
        [r"(?<![\w.])eval\s*\(", r"\bnew Function\s*\("],
        code_only=True,
    ),
    Rule(
        "uiwebview",
        "CRITICAL",
        "apple",
        "2.5.1",
        "UIWebView is no longer accepted",
        "Apple rejects any app that still uses UIWebView.",
        "Move to WKWebView.",
        {"swift", "objc"},
        [r"\bUIWebView\s*[(*]", r"\bUIWebViewDelegate\b", r"[:\[]\s*UIWebView\b"],
        code_only=True,
    ),
    Rule(
        "crypto-mining",
        "CRITICAL",
        "both",
        "3.1.5",
        "Cryptocurrency mining",
        "On-device mining is banned on both stores.",
        "Remove it.",
        CODE,
        [r"(?i)(crypto|coin)\s*miner", r"(?i)mining\s*pool", r"stratum\+tcp"],
    ),
    # HIGH: a missing safeguard somewhere in the project
    Rule(
        "tracking-without-att",
        "HIGH",
        "apple",
        "5.1.2",
        "Tracking or analytics SDK without App Tracking Transparency",
        "Tracking across other companies' apps needs the ATT prompt first. First-party analytics alone does not, so check what the SDK is configured to do.",
        "Ask with expo-tracking-transparency before the SDK starts, or confirm it does no cross-company tracking.",
        APPLE_CODE,
        [
            r"(?i)(firebase.*analytics|google.*analytics|facebook.*sdk|fbsdk|adjust.*sdk|appsflyer|mixpanel|@amplitude/|amplitude-js|@segment/|analytics-react-native|branch\.io|react-native-branch)"
        ],
        anti=[
            r"(?i)(ATTrackingManager|requestTrackingAuthorization|AppTrackingTransparency|expo-tracking-transparency)"
        ],
        once=True,
    ),
    Rule(
        "social-login-without-apple",
        "HIGH",
        "apple",
        "4.8",
        "Third-party login without a privacy-preserving option",
        "An app offering Google, Facebook or similar login must also offer a login meeting 4.8, usually Sign in with Apple.",
        "Add Sign in with Apple (expo-apple-authentication) next to the other logins.",
        APPLE_CODE,
        [
            r"(?i)(google.*sign.*in|GIDSignIn|GoogleSignin|signInWithPopup|GoogleAuthProvider|facebook.*login|FBSDKLoginManager|LoginManager\.logIn)"
        ],
        anti=[
            r"(?i)(ASAuthorizationAppleIDProvider|SignInWithApple|AppleAuthentication|apple.*auth|appleAuth|expo-apple-authentication|OAuthProvider\(['\"]apple\.com)"
        ],
        once=True,
    ),
    Rule(
        "iap-without-restore",
        "HIGH",
        "apple",
        "3.1.1",
        "In-app purchase without Restore Purchases",
        "Apps with restorable purchases must offer a way to restore them.",
        "Add a Restore Purchases button.",
        APPLE_CODE,
        [
            r"(?i)(SKPaymentQueue|Product\.purchase|purchaseProduct|requestPurchase|react-native-iap|react-native-purchases|RevenueCat|expo-in-app-purchases)"
        ],
        anti=[r"(?i)(restoreCompletedTransactions|restore.*purchase|restorePurchase|syncPurchases|AppStore\.sync)"],
        once=True,
    ),
    Rule(
        "account-without-deletion",
        "HIGH",
        "both",
        "5.1.1(v)",
        "Account creation without account deletion",
        "Both stores require that an account created in the app can be deleted from inside the app. Google Play also needs a web deletion link in the Data safety form.",
        "Add account deletion to settings that deletes the data, not just signs out, and publish a web deletion page for Play.",
        CODE,
        [
            r"(?i)(createAccount|createUserWithEmailAndPassword|signUp\b|signUpWith|register.*user|create.*account|auth\(\)\.createUser|linkWithCredential)"
        ],
        anti=[
            r"(?i)(deleteAccount|delete.*account|remove.*account|account.*delet|closeAccount|deleteUser|delete.*my.*data)"
        ],
        once=True,
    ),
    # WARN
    Rule(
        "platform-reference",
        "WARN",
        "apple",
        "2.3.10",
        "Another platform named in user-facing text",
        "Naming Android or Google Play in iOS copy or metadata draws a 2.3.10 rejection (and the reverse on Play).",
        "Keep store-specific wording out of shared copy, or pick it by Platform.OS.",
        APPLE_CODE,
        _q(r"android|google\s*play|play\s*store|windows\s*phone"),
        ignore=[
            r"(?i)(Platform\.|import |require\(|from\s+['\"][\w@./-]+['\"]|@react-native|androidx|\.android\b|/android/|BuildConfig|\.gradle)",
            r"(?i)[\"'`](ios|android|web)[\"'`]",  # an enum value, not copy
            r"(?i)[\w-]+\.(png|jpe?g|svg|webp|json|ttf|otf)\b",
        ],
    ),  # a file path
    Rule(
        "placeholder-content",
        "WARN",
        "both",
        "2.1",
        "Placeholder content",
        "Placeholder text or links are rejected as an incomplete app (Apple 2.1, Play Minimum Functionality).",
        "Replace it with the final text or link.",
        APPLE_CODE | {"kotlin", "java"},
        _q(r"lorem ipsum|coming soon|under construction|tbd")
        + [r"(?i)https?://(www\.)?example\.(com|org)", r"(?i)\blorem ipsum\b"],
        ignore=[r"(?i)placeholder\s*[:=]"],
    ),
    Rule(
        "hardcoded-ipv4",
        "WARN",
        "both",
        "2.5.5",
        "Hardcoded IPv4 address",
        "Apple tests on IPv6-only networks and a dev-machine address is unreachable for reviewers.",
        "Use a hostname from build-time config.",
        CODE,
        [r"\b(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}\b"],
        kind="cleanup",
        ignore=[r"(?i)(version|0\.0\.0\.0|127\.0\.0\.1|localhost)"],
    ),
    Rule(
        "dev-endpoint",
        "WARN",
        "both",
        "2.1",
        "Development server address in app code",
        "Reviewers get the release build; an address that only works on the team's network leaves screens broken.",
        "Read the address from EXPO_PUBLIC_* build config and drop the dev fallback in release builds.",
        JS | {"kotlin", "java", "swift"},
        [r"exp://", r"(?i)\blocalhost:\d+", r"\b10\.0\.2\.2\b", r"(?i)ngrok(-free)?\.(io|app)", r"(?i)\.ts\.net\b"],
        kind="cleanup",
    ),
    Rule(
        "http-url",
        "WARN",
        "both",
        "1.6",
        "Plain HTTP URL",
        "App Transport Security blocks plain HTTP on iOS and Android blocks cleartext by default; both stores expect user data sent encrypted.",
        "Use HTTPS.",
        CODE,
        [r"[\"'`]http://[^\"'`]+[\"'`]"],
        ignore=[
            r"(?i)(localhost|127\.0\.0\.1|0\.0\.0\.0|10\.0\.2\.2|http://example|w3\.org|xmlns|schemas\.android\.com|DTD|doctype)"
        ],
    ),
    Rule(
        "webview-only",
        "WARN",
        "apple",
        "4.2",
        "WebView-only app pattern",
        "An app that only wraps a website fails minimum functionality.",
        "Build the core features natively.",
        APPLE_CODE,
        [r"(?i)(WKWebView|WebView|react-native-webview).*(loadRequest|source=\{\{\s*uri).*https?://"],
    ),
    Rule(
        "custom-review-prompt",
        "WARN",
        "apple",
        "5.6.1",
        "Custom review prompt",
        "Ratings must be requested through the system prompt, and never in exchange for anything.",
        "Use expo-store-review's requestReview().",
        JS,
        [r"(?i)(rate us|leave (us )?a (5|five)[- ]star|rate (this|the) app)"],
    ),
    # INFO / cleanup
    Rule(
        "ota-feature-changes",
        "INFO",
        "apple",
        "2.5.2",
        "Over-the-air updates in use",
        "OTA JS updates may fix bugs, but must not change the app's main purpose or add features that skip review.",
        "Ship feature changes through store builds.",
        JS,
        [r"(?i)(expo-updates|Updates\.fetchUpdateAsync|codePush)"],
        once=True,
    ),
]

CONSOLE = re.compile(r"\bconsole\.(log|debug|info|warn|error|trace)\s*\(")
IGNORE = re.compile(r"store-submission:ignore\b(.*)")
STRING_OR_COMMENT = re.compile(r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`|//.*$|/\*.*?\*/")


def strip_code(line: str) -> str:
    return STRING_OR_COMMENT.sub(lambda m: " " * len(m.group(0)), line)


def ignored(lines: list[str], i: int, rule_id: str) -> bool:
    for j in (i, i - 1):
        if j < 0:
            continue
        m = IGNORE.search(lines[j])
        if not m:
            continue
        if j == i - 1 and not lines[j].strip().startswith(("//", "/*", "*", "#", "<!--", "{/*")):
            continue
        ids = re.split(r"[\s,]+", m.group(1).strip())
        if rule_id in ids:
            return True
    return False


@dataclass
class SourceFile:
    rel: str
    lang: str
    lines: list[str]
    text: str


def walk(root: Path, label: str = "") -> list[SourceFile]:
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        lang = LANGS.get(path.suffix.lower())
        rel = f"{label}{path.relative_to(root).as_posix()}"
        if not lang or TEST_FILE.search("/" + rel) or NOT_APP_CODE.search(rel):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        files.append(SourceFile(rel, lang, text.splitlines(), text))
    return files


def run_rules(files: list[SourceFile]) -> list[Finding]:
    findings: list[Finding] = []
    for rule in RULES:
        # Code only: a comment such as "NOTE: account deletion waits for step 5.11" is not the safeguard
        if rule.anti_rx and any(rx.search(strip_code(line)) for f in files for line in f.lines for rx in rule.anti_rx):
            continue  # the safeguard exists somewhere in the project
        hits: list[Finding] = []
        for f in files:
            if f.lang not in rule.langs:
                continue
            for i, line in enumerate(f.lines):
                stripped = line.strip()
                if stripped.startswith(("//", "/*", "*", "#")):
                    continue
                if any(rx.search(line) for rx in rule.ignore_rx):
                    continue
                target = strip_code(line) if rule.code_only else line
                if any(rx.search(target) for rx in rule.rx) and not ignored(f.lines, i, rule.id):
                    hits.append(
                        Finding(
                            rule.id,
                            rule.severity,
                            rule.store,
                            rule.kind,
                            rule.guideline,
                            rule.title,
                            rule.detail,
                            rule.fix,
                            f.rel,
                            i + 1,
                            stripped[:160],
                            doc_for(rule),
                        )
                    )
                    if rule.once:
                        break
            if rule.once and hits:
                break
        findings.extend(hits)
    findings.extend(console_calls(files))
    return findings


def doc_for(rule: Rule) -> str:
    return DOC_APPLE + rule.guideline.split("(")[0] if rule.store in ("apple", "both") else DOC_POLICY


def console_calls(files: list[SourceFile]) -> list[Finding]:
    out = []
    for f in files:
        if f.lang not in JS:
            continue
        lines = [
            i + 1
            for i, line in enumerate(f.lines)
            if CONSOLE.search(strip_code(line)) and "__DEV__" not in line and not ignored(f.lines, i, "console-call")
        ]
        if lines:
            out.append(
                Finding(
                    "console-call",
                    "INFO",
                    "both",
                    "cleanup",
                    "2.1",
                    f"{len(lines)} console call(s) in shipped code",
                    "Logs run in release builds, slow the JS thread and can leak tokens or chat text to device logs (Apple 1.6, Play User Data).",
                    "Delete debug logs; keep real error reporting behind one logger, or wrap in `if (__DEV__)`.",
                    f.rel,
                    lines[0],
                    f"lines {', '.join(map(str, lines[:15]))}",
                )
            )
    return out


# --- Expo config -------------------------------------------------------------------------------

VAGUE = re.compile(
    r"(?i)^\s*(camera access|location access|microphone access|photo access|needed|required|for the app|to function|for functionality|this app (needs|requires|uses) [^.]{0,30})\s*\.?\s*$"
)


def png_size(path: Path) -> tuple[int, int] | None:
    try:
        head = path.read_bytes()[:24]
    except OSError:
        return None
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", head[16:24])


def check_expo_config(cfg: dict, app_dir: Path, cfg_label: str) -> list[Finding]:
    out: list[Finding] = []

    def add(id_, sev, store, guideline, title, detail, fix, kind="policy"):
        out.append(Finding(id_, sev, store, kind, guideline, title, detail, fix, cfg_label))

    name = (cfg.get("name") or "").strip()
    if not name or name.lower() in {"my app", "new app", "test app", "app"}:
        add(
            "app-name",
            "WARN",
            "both",
            "2.3.7",
            "App name missing or a placeholder",
            f"name is {name!r}.",
            "Set the store name.",
        )
    ios, android = cfg.get("ios") or {}, cfg.get("android") or {}
    if not ios.get("bundleIdentifier"):
        add(
            "ios-bundle-id",
            "HIGH",
            "apple",
            "2.1",
            "No ios.bundleIdentifier",
            "EAS cannot build or submit an iOS app without it.",
            "Set ios.bundleIdentifier.",
        )
    if not android.get("package"):
        add(
            "android-package",
            "HIGH",
            "play",
            "Play Console",
            "No android.package",
            "Play identifies the app by it and it can never change.",
            "Set android.package.",
        )

    icon = cfg.get("icon") or ios.get("icon")
    if not icon:
        add("icon", "HIGH", "both", "2.3", "No app icon", "Both stores need an icon.", "Set icon to a 1024x1024 PNG.")
    elif isinstance(icon, str):
        size = png_size((app_dir / icon).resolve())
        if size and size != (1024, 1024):
            add(
                "icon-size",
                "WARN",
                "apple",
                "2.3",
                f"App icon is {size[0]}x{size[1]}",
                "App Store icons are 1024x1024 with no transparency.",
                "Export the icon at 1024x1024.",
            )

    if not str(cfg.get("version") or "").strip():
        add(
            "version",
            "WARN",
            "both",
            "2.1",
            "No version",
            "Each store build needs a marketing version.",
            "Set version.",
        )

    info = ios.get("infoPlist") or {}
    exempt = (ios.get("config") or {}).get("usesNonExemptEncryption")
    out += check_ios_info(info, exempt is not None, cfg_label)
    return out


def check_ios_info(info: dict, encryption_declared: bool, label: str) -> list[Finding]:
    """Info.plist rules, for an Expo ios.infoPlist or a prebuilt Info.plist."""
    out: list[Finding] = []

    def add(id_, sev, guideline, title, detail, fix):
        out.append(Finding(id_, sev, "apple", "policy", guideline, title, detail, fix, label))

    if not encryption_declared and "ITSAppUsesNonExemptEncryption" not in info:
        add(
            "export-compliance",
            "INFO",
            "Export compliance",
            "No encryption export-compliance answer",
            "App Store Connect asks about encryption on every upload until it is set.",
            "Set ios.config.usesNonExemptEncryption: false if the app only uses HTTPS and OS encryption.",
        )
    for key, value in info.items():
        if key.startswith("NS") and key.endswith("UsageDescription"):
            if not str(value).strip():
                add(
                    "empty-purpose-string",
                    "HIGH",
                    "5.1.1(ii)",
                    f"{key} is empty",
                    "Apple rejects empty purpose strings.",
                    "Say what the app uses it for.",
                )
            elif VAGUE.match(str(value)):
                add(
                    "vague-purpose-string",
                    "WARN",
                    "5.1.1(ii)",
                    f"{key} is vague: {value!r}",
                    "Purpose strings must say what the app does with the data.",
                    "Name the feature and the use.",
                )
    if (info.get("NSAppTransportSecurity") or {}).get("NSAllowsArbitraryLoads"):
        add(
            "ats-disabled",
            "WARN",
            "1.6",
            "App Transport Security disabled",
            "NSAllowsArbitraryLoads needs a written justification in review.",
            "Remove it and use HTTPS, or allow only named domains.",
        )
    for mode in info.get("UIBackgroundModes") or []:
        add(
            "background-mode",
            "INFO",
            "2.5.4",
            f"Background mode {mode!r}",
            "Each background mode must be used for its stated purpose, or review rejects it.",
            "Keep only modes a shipped feature uses.",
        )
    return out


# --- native projects ---------------------------------------------------------------------------

# The app's own Swift and Objective-C only: Expo and React Native modules ship their own manifests
REQUIRED_REASON = {
    "NSPrivacyAccessedAPICategoryUserDefaults": r"\b(NS)?UserDefaults\b",
    "NSPrivacyAccessedAPICategoryFileTimestamp": r"(creationDate|modificationDate|NSFileCreationDate|NSFileModificationDate)",
    "NSPrivacyAccessedAPICategorySystemBootTime": r"(systemUptime|mach_absolute_time|kern\.boottime)",
    "NSPrivacyAccessedAPICategoryDiskSpace": r"(volumeAvailableCapacity|NSFileSystemFreeSize|\bstatfs\s*\()",
    "NSPrivacyAccessedAPICategoryActiveKeyboards": r"activeInputModes",
}


def check_privacy_manifest(files: list[SourceFile], native: Path | None, cfg: dict | None) -> list[Finding]:
    declared: set[str] = set()
    where = ""
    if native:
        for path in native.glob("ios/**/PrivacyInfo.xcprivacy"):
            if "Pods" in path.parts:
                continue
            where = str(path.relative_to(native))
            declared |= set(re.findall(r"NSPrivacyAccessedAPICategory\w+", path.read_text(errors="replace")))
    manifests = ((cfg or {}).get("ios") or {}).get("privacyManifests") or {}
    for entry in manifests.get("NSPrivacyAccessedAPITypes", []):
        declared.add(entry.get("NSPrivacyAccessedAPIType", ""))
        where = where or "expo config ios.privacyManifests"
    out = []
    for category, pattern in REQUIRED_REASON.items():
        rx = re.compile(pattern)
        hit = next((f for f in files if f.lang in {"swift", "objc"} and rx.search(f.text)), None)
        if hit and category not in declared:
            api = category.removeprefix("NSPrivacyAccessedAPICategory")
            note = (
                ""
                if where
                else (" (no app privacy manifest)" if native else " (run with --native to check the generated one)")
            )
            out.append(
                Finding(
                    id="required-reason-api",
                    severity="WARN" if native or where else "INFO",
                    store="apple",
                    kind="policy",
                    guideline="5.1.1",
                    title=f"{api} API used, reason not declared{note}",
                    detail="Apple emails ITMS-91053 and can reject an upload that uses a required-reason API without a declared reason. "
                    "Expo and React Native modules ship their own manifests, so only the app's own use needs declaring here.",
                    fix=f"Declare {category} with its approved reason in ios.privacyManifests in the Expo config.",
                    file=hit.rel,
                    doc=DOC_REQUIRED_REASON,
                )
            )
    return out


RESTRICTED_PERMISSIONS = [
    (
        {"READ_SMS", "SEND_SMS", "RECEIVE_SMS", "RECEIVE_MMS", "RECEIVE_WAP_PUSH", "WRITE_SMS"},
        "HIGH",
        "SMS permission needs an approved core use",
        "Use the SMS Retriever API, or file the Permissions Declaration Form.",
    ),
    (
        {"READ_CALL_LOG", "WRITE_CALL_LOG", "PROCESS_OUTGOING_CALLS"},
        "HIGH",
        "Call Log permission needs an approved core use",
        "Remove it, or file the Permissions Declaration Form.",
    ),
    (
        {"MANAGE_EXTERNAL_STORAGE"},
        "HIGH",
        "All files access needs approval",
        "Use the Storage Access Framework or MediaStore.",
    ),
    (
        {"QUERY_ALL_PACKAGES"},
        "HIGH",
        "QUERY_ALL_PACKAGES needs an approved use",
        "Declare the packages you need in <queries>.",
    ),
    ({"REQUEST_INSTALL_PACKAGES"}, "HIGH", "REQUEST_INSTALL_PACKAGES needs a permitted use", "Remove it."),
    (
        {"ACCESS_BACKGROUND_LOCATION"},
        "HIGH",
        "Background location needs a declaration and demo video",
        "Remove it unless a core feature needs it.",
    ),
    (
        {"READ_MEDIA_IMAGES", "READ_MEDIA_VIDEO"},
        "WARN",
        "Broad photo/video access instead of the Photo Picker",
        "Use the system photo picker (expo-image-picker uses it) and block these permissions.",
    ),
    (
        {"READ_EXTERNAL_STORAGE", "WRITE_EXTERNAL_STORAGE"},
        "WARN",
        "Legacy storage permission",
        "Expo adds these by default; block them with android.blockedPermissions unless a feature needs them.",
    ),
    (
        {"SYSTEM_ALERT_WINDOW"},
        "WARN",
        "Draw-over-other-apps permission",
        "Expo adds it for the dev menu; block it in release with android.blockedPermissions.",
    ),
    (
        {"READ_CONTACTS", "WRITE_CONTACTS"},
        "WARN",
        "Contacts access (Contact Permissions policy)",
        "Use the system Contact Picker.",
    ),
    (
        {"RECORD_AUDIO"},
        "INFO",
        "Microphone permission",
        "Needs a prominent disclosure and a Data safety entry if audio leaves the device.",
    ),
    (
        {"ACCESS_FINE_LOCATION"},
        "INFO",
        "Precise location",
        "Check approximate location or the location button is not enough.",
    ),
    (
        {"USE_EXACT_ALARM", "SCHEDULE_EXACT_ALARM"},
        "WARN",
        "Exact alarm permission",
        "Only alarm and calendar apps qualify; use inexact alarms.",
    ),
]
FGS_PERMISSIONS = {
    "camera": "CAMERA",
    "connectedDevice": "CONNECTED_DEVICE",
    "dataSync": "DATA_SYNC",
    "health": "HEALTH",
    "location": "LOCATION",
    "mediaPlayback": "MEDIA_PLAYBACK",
    "mediaProjection": "MEDIA_PROJECTION",
    "microphone": "MICROPHONE",
    "phoneCall": "PHONE_CALL",
    "remoteMessaging": "REMOTE_MESSAGING",
    "specialUse": "SPECIAL_USE",
    "systemExempted": "SYSTEM_EXEMPTED",
    "mediaProcessing": "MEDIA_PROCESSING",
}
ANDROID = "{http://schemas.android.com/apk/res/android}"
TOOLS = "{http://schemas.android.com/tools}"


def parse_date(text: str) -> dt.date | None:
    for fmt in ("%B %d %Y", "%B %d, %Y"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def target_sdk(native: Path, app_dir: Path, cfg: dict | None) -> tuple[int, str]:
    """targetSdk from expo-build-properties, the Gradle files, or React Native's version catalog."""
    for plugin in (cfg or {}).get("plugins") or []:
        if isinstance(plugin, list) and plugin and plugin[0] == "expo-build-properties":
            value = ((plugin[1] if len(plugin) > 1 else {}).get("android") or {}).get("targetSdkVersion")
            if value:
                return int(value), "expo-build-properties"
    candidates = [
        native / "android/gradle.properties",
        *native.glob("android/**/*.gradle"),
        *native.glob("android/**/*.gradle.kts"),
        app_dir / "node_modules/react-native/gradle/libs.versions.toml",
    ]
    patterns = [
        r"android\.targetSdkVersion\s*=\s*(\d+)",
        r"targetSdk(?:Version)?\s*[=:]?\s*(\d{2})\b",
        r"targetSdkVersion['\"]?\)?\s*\?:\s*['\"](\d{2})",
        r"^targetSdk\s*=\s*\"(\d+)\"",
    ]
    for path in candidates:
        if not path.is_file() or "build" in path.parent.parts[-2:]:
            continue
        text = path.read_text(errors="replace")
        for p in patterns:
            m = re.search(p, text, re.M)
            if m:
                return int(m.group(1)), path.name
    return 0, ""


def check_android(native: Path, app_dir: Path, cfg: dict | None, deps: set[str], facts: dict) -> list[Finding]:
    manifest_path = native / "android/app/src/main/AndroidManifest.xml"
    if not manifest_path.is_file():
        return [
            Finding(
                "android-manifest",
                "INFO",
                "play",
                "policy",
                "-",
                "No android/app/src/main/AndroidManifest.xml under --native",
                "The Play manifest checks did not run.",
                "Run expo prebuild into the --native directory.",
            )
        ]
    rel = "native/android/app/src/main/AndroidManifest.xml"
    root = ET.parse(manifest_path).getroot()
    perms = {
        (el.get(f"{ANDROID}name") or "").split(".")[-1]: el
        for el in root.iter("uses-permission")
        if el.get(f"{TOOLS}node") != "remove"  # android.blockedPermissions writes these
    }
    app = root.find("application")
    out: list[Finding] = []

    def add(id_, sev, guideline, title, detail, fix, doc=DOC_POLICY, file=rel):
        out.append(Finding(id_, sev, "play", "policy", guideline, title, detail, fix, file, 0, "", doc))

    sdk, sdk_file = target_sdk(native, app_dir, cfg)
    need_new = facts.get("play_target_sdk_new", FALLBACK_TARGET_SDK_NEW)
    need_existing = facts.get("play_target_sdk_existing", FALLBACK_TARGET_SDK_EXISTING)
    live = (
        ""
        if "play_target_sdk_new" in facts
        else " (fallback values; run fetch_guidelines.py and pass --facts for the live ones)"
    )
    if not sdk:
        add(
            "target-sdk",
            "WARN",
            "Target API level",
            "Could not read targetSdk",
            f"Play requires API {need_new}+ for new apps and updates{live}.",
            "Check it with expo-build-properties or after prebuild.",
            DOC_TARGET_API,
        )
    elif sdk < need_existing:
        add(
            "target-sdk",
            "CRITICAL",
            "Target API level",
            f"targetSdk {sdk} is below API {need_existing}",
            f"Below the floor for existing apps; new apps and updates need API {need_new}{live}.",
            f"Target API {need_new}.",
            DOC_TARGET_API,
            sdk_file,
        )
    elif sdk < need_new:
        starts = parse_date(facts.get("play_target_sdk_new_from", ""))
        upcoming = starts is not None and starts > dt.date.today()
        add(
            "target-sdk",
            "HIGH" if upcoming else "CRITICAL",
            "Target API level",
            f"targetSdk {sdk} is below API {need_new}",
            f"New apps and updates must target API {need_new}"
            + (f" from {starts:%B %d, %Y}" if upcoming else "; Play refuses the upload")
            + f"{live}.",
            f"Target API {need_new}.",
            DOC_TARGET_API,
            sdk_file,
        )

    for names, sev, title, fix in RESTRICTED_PERMISSIONS:
        hit = sorted(n for n in names if n in perms)
        if hit:
            add(
                "restricted-permission",
                sev,
                "Permissions and APIs",
                f"{title}: {', '.join(hit)}",
                "Play reviews this permission against the app's core purpose; see references/google-play/permissions-and-apis.md.",
                fix,
                DOC_RESTRICTED,
            )

    if app is not None:
        if (app.get(f"{ANDROID}debuggable") or "").lower() == "true":
            add(
                "debuggable",
                "CRITICAL",
                "Malicious Behavior",
                "android:debuggable=true in the main manifest",
                "Play rejects debuggable uploads.",
                "Remove it; the build type sets it.",
            )
        if (app.get(f"{ANDROID}usesCleartextTraffic") or "").lower() == "true":
            add(
                "cleartext",
                "WARN",
                "User Data",
                "usesCleartextTraffic=true in the main manifest",
                "User data must be sent encrypted.",
                "Remove it; allow only named dev hosts in a debug network security config.",
            )
        if sdk == 0 or sdk >= 31:
            missing = [
                c.get(f"{ANDROID}name")
                for c in app
                if c.tag in ("activity", "service", "receiver")
                and c.find("intent-filter") is not None
                and c.get(f"{ANDROID}exported") is None
            ]
            if missing:
                add(
                    "exported",
                    "CRITICAL",
                    "Manifest",
                    "Component with an intent filter lacks android:exported",
                    f"API 31+ installs fail without it: {', '.join(map(str, missing[:5]))}.",
                    "Set android:exported on each.",
                )
        services = [s for s in app.iter("service") if s.get(f"{ANDROID}foregroundServiceType")]
        if services and "FOREGROUND_SERVICE" not in perms:
            add(
                "foreground-service",
                "CRITICAL",
                "Foreground services",
                "Foreground service without FOREGROUND_SERVICE permission",
                "startForeground() throws.",
                "Add the permission.",
                DOC_FGS,
            )
        for svc in services:
            for kind in svc.get(f"{ANDROID}foregroundServiceType", "").split("|"):
                need = FGS_PERMISSIONS.get(kind.strip())
                if need and f"FOREGROUND_SERVICE_{need}" not in perms:
                    add(
                        "foreground-service",
                        "CRITICAL",
                        "Foreground services",
                        f"Foreground service type {kind} lacks FOREGROUND_SERVICE_{need}",
                        "Android 14+ throws on startForeground().",
                        f"Add FOREGROUND_SERVICE_{need}.",
                        DOC_FGS,
                    )
                if kind.strip() == "specialUse":
                    add(
                        "foreground-service",
                        "HIGH",
                        "Foreground services",
                        "specialUse foreground service",
                        "Needs a written Play Console declaration.",
                        "Declare it, or use a defined type.",
                        DOC_FGS,
                    )

    ads = {
        d
        for d in deps
        if re.search(r"(?i)(google-mobile-ads|admob|applovin|unity-ads|ironsource|facebook-ads|appsflyer|adjust)", d)
    }
    if ads and "AD_ID" not in perms:
        add(
            "ad-id",
            "HIGH",
            "Advertising ID",
            "Ads or attribution SDK without the AD_ID permission",
            f"{', '.join(sorted(ads))} reads the advertising ID, which needs AD_ID on API 33+ and the Advertising ID declaration.",
            "Add com.google.android.gms.permission.AD_ID and complete the declaration.",
            DOC_AD_ID,
        )
    return out


def check_info_plist(native: Path) -> list[Finding]:
    out = []
    for path in native.glob("ios/*/Info.plist"):
        try:
            info = plistlib.loads(path.read_bytes())
        except Exception:
            continue
        out += check_ios_info(info, False, "native/" + str(path.relative_to(native)))
    return out


# --- dependencies, assets, data-collection signals ---------------------------------------------


def check_eas(app_dir: Path) -> list[Finding]:
    """A store binary needs a build profile whose distribution is store (EAS's default)."""
    path = app_dir / "eas.json"
    if not path.exists():
        return []
    profiles = json.loads(path.read_text()).get("build", {})
    store = [
        name
        for name, p in profiles.items()
        if p.get("distribution", "store") == "store" and not p.get("developmentClient")
    ]
    if store:
        return []
    return [
        Finding(
            id="eas-store-profile",
            severity="HIGH",
            store="both",
            kind="cleanup",
            guideline="2.1",
            title="No EAS build profile for the stores",
            detail=f"Profiles {', '.join(profiles) or '(none)'} all build for internal distribution or a dev client; "
            "eas submit needs a store build, and reviewers must get the production API and settings.",
            fix="Add a production profile (distribution store, autoIncrement) with the production EXPO_PUBLIC_* values.",
            file="eas.json",
        )
    ]


def check_dependencies(deps: set[str]) -> list[Finding]:
    out = []
    if any("expo-dev-client" == d for d in deps):
        out.append(
            Finding(
                "dev-client",
                "INFO",
                "both",
                "cleanup",
                "2.1",
                "expo-dev-client is a dependency",
                "It is left out of release builds by EAS, but confirm the store profile is not a development build.",
                "Build store binaries with a production profile (developmentClient: false).",
                "package.json",
            )
        )
    return out


def unused_assets(app_dir: Path, files: list[SourceFile], config_text: str) -> list[Finding]:
    assets = app_dir / "assets"
    if not assets.is_dir():
        return []
    corpus = config_text + "\n".join(f.text for f in files)
    out = []
    for path in sorted(p for p in assets.rglob("*") if p.is_file() and not p.name.startswith(".")):
        stem = re.sub(r"@\dx$", "", path.stem)
        if stem not in corpus:
            out.append(
                Finding(
                    "unused-asset",
                    "INFO",
                    "both",
                    "cleanup",
                    "-",
                    f"Asset not referenced: {path.relative_to(app_dir)}",
                    "Unused assets add to the download size.",
                    "Delete it if nothing loads it by a computed name.",
                    str(path.relative_to(app_dir)),
                )
            )
    return out


# React Native and Expo calls Google's Android-first config misses; same data-type keys as policies.json
RN_SIGNALS = {
    "DEVICE_ID": [
        "X-Device-Id",
        "deviceId",
        "getIosIdForVendorAsync",
        "getAndroidId",
        "getExpoPushTokenAsync",
        "getDevicePushTokenAsync",
    ],
    "APP_INTERACTIONS": ["posthog", "trackEvent", "/events", "logEvent"],
    "CRASH_LOGS": ["@sentry/react-native", "sentry-expo", "@bugsnag/expo", "@react-native-firebase/crashlytics"],
    "USER_GENERATED_CONTENT": ["<TextInput", "multiline"],
    "PHOTOS": ["launchImageLibraryAsync", "launchCameraAsync", "expo-camera"],
    "AUDIO": ["expo-av", "expo-audio", "Audio.Recording"],
    "PRECISE_LOCATION": ["expo-location", "getCurrentPositionAsync"],
    "CONTACTS": ["expo-contacts"],
}


def data_signals(files: list[SourceFile]) -> dict:
    """Google's data-safety signals: which data types the code touches, and where."""
    config = json.loads(SCANNER_CONFIG.read_text())
    signals: dict[str, dict[str, list[str]]] = {}
    categories = config["signal_categories"]
    categories["data_sources"] = {k: v + RN_SIGNALS.get(k, []) for k, v in categories["data_sources"].items()}
    for category, groups in categories.items():
        for signal, patterns in groups.items():
            for f in files:
                if f.lang not in CODE:
                    continue
                code = "\n".join(
                    STRING_OR_COMMENT.sub(lambda m: m.group(0) if m.group(0)[0] in "\"'`" else "", line)
                    for line in f.lines
                )
                p = next((p for p in patterns if p in code), None)
                if p:
                    signals.setdefault(category, {}).setdefault(signal, []).append(f"{f.rel} ({p})")
    semantic: dict[str, list[str]] = {}
    for category, needles in config["file_patterns"].items():
        for f in files:
            if any(n in Path(f.rel).name.lower() for n in needles):
                semantic.setdefault(category, []).append(f.rel)
    urls = sorted(
        {
            u
            for f in files
            for u in re.findall(r"https?://[^\s\"'`)]+", f.text)
            if re.search(r"(?i)privacy|terms|support|delete|policy|legal", u)
        }
    )
    return {
        "data_sources": signals.get("data_sources", {}),
        "other_signals": {k: v for k, v in signals.items() if k != "data_sources"},
        "files_of_interest": semantic,
        "policy_urls": urls,
    }


# --- main --------------------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("app_dir", type=Path)
    ap.add_argument("--config", type=Path, help="resolved Expo config: npx expo config --json --type prebuild")
    ap.add_argument("--native", type=Path, help="directory holding the ios/ and android/ that expo prebuild made")
    ap.add_argument("--facts", type=Path, help="report.json from fetch_guidelines.py")
    ap.add_argument("--out", type=Path, help="write the full result as JSON here")
    ap.add_argument("--exit-code", action="store_true", help="exit 1 on any CRITICAL or HIGH finding")
    args = ap.parse_args()

    app_dir = args.app_dir.resolve()
    files = walk(app_dir)
    # Only the generated native projects: the rest of --native is a copy of APP_DIR.
    # A bare app passes APP_DIR itself, whose ios/ and android/ were walked above.
    bare = args.native is not None and args.native.resolve() == app_dir
    native_files = [
        f
        for d in ("ios", "android")
        if args.native and not bare and (args.native / d).is_dir()
        for f in walk(args.native / d, f"native/{d}/")
    ]
    facts = json.loads(args.facts.read_text()).get("facts", {}) if args.facts else {}

    cfg = None
    cfg_label = ""
    config_text = ""
    if args.config:
        cfg = json.loads(args.config.read_text())
        cfg = cfg.get("exp", cfg)  # `expo config --json` nests it under exp in some versions
        cfg_label = (
            "expo config ("
            + next((n for n in ("app.config.ts", "app.config.js", "app.json") if (app_dir / n).exists()), "app.json")
            + ")"
        )
        config_text = json.dumps(cfg)
    elif (app_dir / "app.json").exists():
        cfg = json.loads((app_dir / "app.json").read_text()).get("expo")
        cfg_label, config_text = "app.json", (app_dir / "app.json").read_text()

    pkg = app_dir / "package.json"
    deps: set[str] = set()
    if pkg.exists():
        data = json.loads(pkg.read_text())
        deps = set(data.get("dependencies", {}))

    findings = run_rules(files + native_files)
    if cfg is not None:
        findings += check_expo_config(cfg, app_dir, cfg_label)
    findings += check_privacy_manifest(files + native_files, args.native, cfg)
    if args.native:
        findings += check_info_plist(args.native)
        findings += check_android(args.native, app_dir, cfg, deps, facts)
    findings += check_dependencies(deps)
    findings += check_eas(app_dir)
    for name in ("app.config.ts", "app.config.js"):
        if (app_dir / name).exists():
            config_text += (app_dir / name).read_text(errors="replace")
    findings += unused_assets(app_dir, files, config_text)
    # The generated Info.plist repeats what the Expo config says; report it once, at the config
    seen = {(f.id, f.title) for f in findings if not f.file.startswith("native/")}
    findings = [f for f in findings if not (f.file.startswith("native/") and not f.line and (f.id, f.title) in seen)]
    findings.sort(key=lambda f: (-SEVERITIES.index(f.severity), f.kind, f.store, f.file, f.line))

    counts = {s: sum(f.severity == s for f in findings) for s in reversed(SEVERITIES)}
    result = {
        "app_dir": str(app_dir),
        "native": str(args.native) if args.native else None,
        "facts_live": bool(facts),
        "android_target_sdk": dict(zip(("value", "from"), target_sdk(args.native, app_dir, cfg), strict=True))
        if args.native
        else None,
        "summary": counts,
        "findings": [asdict(f) for f in findings],
        "data_safety": data_signals(files + native_files),
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2))

    print(f"store-submission scan of {app_dir}: " + ", ".join(f"{n} {s}" for s, n in counts.items()))
    if not args.native:
        print("  (no --native: Info.plist, privacy manifest and Android manifest checks were skipped)")
    for f in findings:
        where = f"{f.file}:{f.line}" if f.line else f.file
        print(f"[{f.severity}] {f.store} {f.guideline} {f.title} ({f.id}) {where}")
    print("Data types the code touches: " + (", ".join(sorted(result["data_safety"]["data_sources"])) or "none found"))
    return 1 if args.exit_code and (counts["CRITICAL"] or counts["HIGH"]) else 0


if __name__ == "__main__":
    sys.exit(main())
