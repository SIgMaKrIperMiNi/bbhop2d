[app]

# Основные сведения о приложении
title = BHOP
package.name = bhop
package.domain = com.example
source.dir = .
source.include_exts = py,json,png,jpg,kv,atlas
version = 1.0.0

# Pygame работает через SDL2 bootstrap python-for-android
requirements = python3,pygame,android
p4a.bootstrap = sdl2
p4a.branch = develop
p4a.local_recipes = ./p4a-recipes

# Экран и архитектура
orientation = landscape
fullscreen = 1
android.archs = arm64-v8a
android.minapi = 23
android.api = 35
android.ndk = 28c

# Не запрашиваем доступ к общим файлам: сохранения приватные.
android.permissions =

# Сборка
[buildozer]
log_level = 2
warn_on_root = 1
