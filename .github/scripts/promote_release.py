"""Publish only the three verified Windows distribution files."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
import zipfile


def verify_artifact(archive, digest, version, output):
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Invalid release version")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("Invalid artifact SHA256")
    with archive.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != digest:
            raise ValueError("Artifact ZIP checksum mismatch")
    installer = f"CAMARA-POS-Setup-{version}.exe"
    names = {installer, installer + ".blockmap", "latest.yml"}
    with zipfile.ZipFile(archive) as zipped:
        entries = zipped.infolist()
        if len(entries) != 3 or {item.filename for item in entries} != names:
            raise ValueError("Artifact must contain only the three distribution files")
        if any(item.file_size <= 0 or item.file_size > 1024**3 for item in entries):
            raise ValueError("Invalid distribution file size")
        output.mkdir()
        for name in sorted(names):
            with zipped.open(name) as source, (output / name).open("wb") as target:
                shutil.copyfileobj(source, target)
    metadata = (output / "latest.yml").read_text()
    structure = (
        rf"version: {re.escape(version)}\nfiles:\n"
        rf"  - url: {re.escape(installer)}\n"
        r"    sha512: (?P<checksum>[A-Za-z0-9+/=]+)\n"
        r"    size: (?P<size>\d+)\n"
        rf"path: {re.escape(installer)}\n"
        r"sha512: (?P=checksum)\n"
        r"releaseDate: '\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z'\n?"
    )
    # Match the complete builder metadata; conflicting YAML keys must never pass.
    fields = re.fullmatch(structure, metadata)
    if fields is None:
        raise ValueError("Invalid or conflicting update metadata structure")
    with (output / installer).open("rb") as source:
        sha512 = base64.b64encode(hashlib.file_digest(source, "sha512").digest()).decode()
    if fields["checksum"] != sha512 or fields["size"] != str((output / installer).stat().st_size):
        raise ValueError("Update metadata checksum or size mismatch")
    result = {}
    for name in sorted(names):
        with (output / name).open("rb") as source:
            result[name] = "sha256:" + hashlib.file_digest(source, "sha256").hexdigest()
    return result


def gh(*arguments):
    return subprocess.check_output(["gh", *arguments], text=True)


def main():
    version = os.environ["PUBLISH_VERSION"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Invalid release version")
    artifact_url = os.environ["ARTIFACT_URL"]
    print(f"::add-mask::{artifact_url}", flush=True)
    parsed = urllib.parse.urlparse(artifact_url)
    if parsed.scheme != "https" or not (parsed.hostname or "").endswith(".blob.core.windows.net"):
        raise ValueError("Artifact URL must be a signed GitHub Azure artifact URL")
    tag = "v" + version
    # Abort rather than replace an existing release's installer or metadata.
    existing = subprocess.run(["gh", "release", "view", tag], capture_output=True)
    if existing.returncode == 0:
        raise ValueError("Release already exists; verify it before any manual recovery")
    with tempfile.TemporaryDirectory(prefix="camara-publish-") as temporary:
        root = Path(temporary)
        archive = root / "artifact.zip"
        with urllib.request.urlopen(artifact_url, timeout=120) as response, archive.open("wb") as target:
            shutil.copyfileobj(response, target)
        output = root / "release"
        expected = verify_artifact(archive, os.environ["ARTIFACT_SHA256"], version, output)
        notes = root / "notes.md"
        notes.write_text(
            "Fixes the Windows POS startup failure caused by the missing styled-jsx dependency.\n\n"
            "Includes a clean starter database for new installations and an accessible automatic update feed. "
            "Existing POS data is preserved.\n\n"
            f"If the old app stops at the startup error, close it and run CAMARA-POS-Setup-{version}.exe once. "
            "The failing version exits before its updater can start.\n\n"
            "The Windows installer passed the packaged server, page asset, and database startup checks before publication.\n"
        )
        print(gh("release", "create", tag, *[str(output / name) for name in sorted(expected)],
                 "--draft", "--title", version, "--notes-file", str(notes)), end="")
        releases = json.loads(gh("api", f"repos/{os.environ['GH_REPO']}/releases?per_page=100"))
        matches = [item for item in releases if item["tag_name"] == tag]
        if len(matches) != 1:
            raise ValueError("Draft release could not be identified uniquely")
        release = json.loads(gh("api", f"repos/{os.environ['GH_REPO']}/releases/{matches[0]['id']}"))
        if not release["draft"] or release["prerelease"] or release["tag_name"] != tag:
            raise ValueError("Unexpected draft release state")
        uploaded = {asset["name"]: asset for asset in release["assets"]}
        if set(uploaded) != set(expected):
            raise ValueError("Uploaded distribution file set mismatch")
        for name, digest in expected.items():
            asset = uploaded[name]
            if asset["state"] != "uploaded" or asset["digest"] != digest or asset["size"] != (output / name).stat().st_size:
                raise ValueError("Uploaded distribution checksum or size mismatch")
        print(gh("release", "edit", tag, "--draft=false", "--latest"), end="")


if __name__ == "__main__":
    main()
