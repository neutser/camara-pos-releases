# CAMARA POS installers

Windows installers and automatic update metadata for CAMARA POS.

[Download the latest Windows release](https://github.com/neutser/camara-pos-releases/releases/latest).

Close CAMARA POS and run the installer to update an existing installation. Existing POS data is
preserved. An app that stops at a startup error needs this manual installation once, because it
exits before its automatic updater can start.

The installed app checks this public release channel without requiring GitHub credentials.

Maintainers promote a verified Windows build through the **Publish verified CAMARA POS installer**
workflow. Supply its version, artifact ZIP SHA256, and a short-lived signed artifact ZIP URL.
The workflow accepts only the installer, blockmap, and update metadata; verifies the ZIP and
installer checksums; and verifies the uploaded assets before making the release latest.

Application source and venue databases are not distributed through this repository.
