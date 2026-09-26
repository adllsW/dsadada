[app]
title = Brawl Arena
package.name = brawlarena
package.domain = org.brawlarena

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf

version = 1.0
requirements = python3,kivy==2.3.0,kivymd==1.2.0,pillow

# Игра рассчитана на альбомную ориентацию (широкая арена)
orientation = landscape
fullscreen = 1

android.permissions = 
android.api = 34
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
