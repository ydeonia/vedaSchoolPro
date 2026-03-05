#!/usr/bin/env python3
"""
White-label build script for VedaSchoolPro mobile app.

Usage:
    python build_school.py --school=dps_gwalior
    python build_school.py --school=dps_gwalior --platform=android
    python build_school.py --school=dps_gwalior --platform=ios
    python build_school.py --school=all  # Build for ALL schools

This script:
1. Reads school_configs/{school_id}.json
2. Copies school logo from school_assets/{school_id}/
3. Patches lib/core/config.dart with school-specific values
4. Updates android/app/build.gradle with school package ID & name
5. Updates ios/Runner/Info.plist with school name
6. Runs flutter build apk/appbundle/ipa
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
CONFIGS_DIR = ROOT / "school_configs"
ASSETS_DIR = ROOT / "school_assets"
CONFIG_DART = ROOT / "lib" / "core" / "config.dart"
BUILD_GRADLE = ROOT / "android" / "app" / "build.gradle"
INFO_PLIST = ROOT / "ios" / "Runner" / "Info.plist"


def load_config(school_id: str) -> dict:
    config_file = CONFIGS_DIR / f"{school_id}.json"
    if not config_file.exists():
        print(f"ERROR: Config not found: {config_file}")
        sys.exit(1)
    with open(config_file) as f:
        return json.load(f)


def patch_config_dart(config: dict):
    """Replace compile-time defaults in config.dart."""
    content = CONFIG_DART.read_text(encoding="utf-8")

    replacements = {
        r"schoolId = '.*?'": f"schoolId = '{config['school_id']}'",
        r"schoolName = '.*?'": f"schoolName = '{config['school_name']}'",
        r"apiBaseUrl = '.*?'": f"apiBaseUrl = '{config['api_base_url']}'",
        r"defaultThemeColor = '.*?'": f"defaultThemeColor = '{config['default_theme_color']}'",
        r"motto = '.*?'": f"motto = '{config.get('motto', '')}'",
        r"language = '.*?'": f"language = '{config.get('language', 'en')}'",
        r"packageId = '.*?'": f"packageId = '{config['package_id']}'",
    }

    for pattern, replacement in replacements.items():
        content = re.sub(pattern, replacement, content)

    CONFIG_DART.write_text(content, encoding="utf-8")
    print(f"  Patched config.dart for {config['school_name']}")


def copy_logo(config: dict):
    """Copy school logo to assets/images/."""
    logo_file = config.get("logo_file", "")
    if not logo_file:
        return

    src = ASSETS_DIR / config["school_id"] / logo_file
    dst = ROOT / "assets" / "images" / "school_logo.png"

    if src.exists():
        shutil.copy2(src, dst)
        print(f"  Copied logo: {src.name}")
    else:
        print(f"  WARNING: Logo not found at {src}, using default")


def patch_android_build_gradle(config: dict):
    """Update applicationId and app label in build.gradle."""
    if not BUILD_GRADLE.exists():
        print("  WARNING: build.gradle not found (run flutter create first)")
        return

    content = BUILD_GRADLE.read_text(encoding="utf-8")

    # Patch applicationId
    content = re.sub(
        r'applicationId ".*?"',
        f'applicationId "{config["package_id"]}"',
        content,
    )

    # Patch resValue for app_name
    if 'resValue' not in content:
        # Add resValue in defaultConfig block
        content = content.replace(
            'versionName flutterVersionName',
            f'versionName flutterVersionName\n        resValue "string", "app_name", "{config["play_store_name"]}"',
        )
    else:
        content = re.sub(
            r'resValue "string", "app_name", ".*?"',
            f'resValue "string", "app_name", "{config["play_store_name"]}"',
            content,
        )

    BUILD_GRADLE.write_text(content, encoding="utf-8")
    print(f"  Patched build.gradle: {config['package_id']}")


def patch_ios_plist(config: dict):
    """Update CFBundleDisplayName in Info.plist."""
    if not INFO_PLIST.exists():
        print("  WARNING: Info.plist not found (run flutter create first)")
        return

    content = INFO_PLIST.read_text(encoding="utf-8")
    content = re.sub(
        r"<key>CFBundleDisplayName</key>\s*<string>.*?</string>",
        f"<key>CFBundleDisplayName</key>\n\t<string>{config['play_store_name']}</string>",
        content,
    )
    INFO_PLIST.write_text(content, encoding="utf-8")
    print(f"  Patched Info.plist: {config['play_store_name']}")


def build_flutter(platform: str, config: dict):
    """Run flutter build."""
    output_dir = ROOT / "builds" / config["school_id"]
    output_dir.mkdir(parents=True, exist_ok=True)

    if platform in ("android", "both"):
        print(f"\n  Building Android APK for {config['school_name']}...")
        result = subprocess.run(
            ["flutter", "build", "apk", "--release", "--split-per-abi"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            # Copy APKs to builds folder
            apk_dir = ROOT / "build" / "app" / "outputs" / "flutter-apk"
            if apk_dir.exists():
                for apk in apk_dir.glob("*.apk"):
                    dst = output_dir / f"{config['school_id']}_{apk.name}"
                    shutil.copy2(apk, dst)
                    print(f"  APK: {dst}")
        else:
            print(f"  BUILD FAILED:\n{result.stderr}")

    if platform in ("ios", "both"):
        print(f"\n  Building iOS for {config['school_name']}...")
        result = subprocess.run(
            ["flutter", "build", "ios", "--release", "--no-codesign"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print("  iOS build succeeded!")
        else:
            print(f"  iOS BUILD FAILED:\n{result.stderr}")


def restore_defaults():
    """Restore config.dart to default values after build."""
    default_config = load_config("default")
    patch_config_dart(default_config)
    print("  Restored config.dart to defaults")


def build_school(school_id: str, platform: str = "android"):
    """Full build pipeline for one school."""
    print(f"\n{'='*60}")
    print(f"Building: {school_id}")
    print(f"{'='*60}")

    config = load_config(school_id)

    # 1. Patch config
    patch_config_dart(config)

    # 2. Copy logo
    copy_logo(config)

    # 3. Patch native configs
    patch_android_build_gradle(config)
    patch_ios_plist(config)

    # 4. Build
    build_flutter(platform, config)

    # 5. Restore defaults
    restore_defaults()

    print(f"\nDone: {config['school_name']}")


def main():
    parser = argparse.ArgumentParser(description="Build white-label school app")
    parser.add_argument(
        "--school", required=True, help='School ID or "all" for all schools'
    )
    parser.add_argument(
        "--platform",
        choices=["android", "ios", "both"],
        default="android",
        help="Target platform (default: android)",
    )
    args = parser.parse_args()

    if args.school == "all":
        # Build for all configured schools
        for config_file in sorted(CONFIGS_DIR.glob("*.json")):
            school_id = config_file.stem
            if school_id == "default":
                continue
            build_school(school_id, args.platform)
    else:
        build_school(args.school, args.platform)

    print("\n" + "=" * 60)
    print("All builds complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
