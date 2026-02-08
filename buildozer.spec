# Buildozer spec for Sentinel-BIST APK
# Run: buildozer android debug
# Not: Linux üzerinde çalıştırın (WSL veya Linux VM)

[app]
title = Sentinel-BIST
package.name = sentinelbist
package.domain = com.sentinelbist
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0
requirements = python3,kivy,numpy,pandas,yfinance,requests
orientation = portrait
fullscreen = 0

[buildozer]
log_level = 2
warn_on_root = 1

[android]
permissions = INTERNET
android.api = 33
android.minapi = 21
android.sdk = 33
android.ndk = 25b
android.ndk_path =
android.sdk_path =
android.accept_sdk_license = True
p4a.branch = master
p4a.bootstrap = sdl2
android.archs = arm64-v8a, armeabi-v7a
