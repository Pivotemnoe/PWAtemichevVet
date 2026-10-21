# Android release artifact

`mobile/release.py` places the verified signed APK here for its fixed versioned download endpoint. The current candidate is `TemichevVet-0.1.2.apk`; the 0.1.1 endpoint remains available for existing links. Binary artifacts are ignored by Git. A source checkout without a built release returns HTTP 404 for the APK endpoint. The release output contains signatures, checksums and the exact source manifest.

Do not place signing keys or passwords in this directory.
