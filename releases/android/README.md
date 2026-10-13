# Android release artifact

`mobile/release.py` places the verified signed `TemichevVet-0.1.0.apk` here for the application's fixed download endpoint. Binary artifacts are ignored by Git. The deployment packet includes the APK; a source checkout without a built release returns HTTP 404 for the APK endpoint.

Do not place signing keys or passwords in this directory.
