#!/usr/bin/env python3
"""Generate Autopilot channels from stable upstream releases (stdlib only)."""
import json
import os
from pathlib import Path
import re
import urllib.request

TAG = re.compile(r"v(\d+)\.(\d+)\.(\d+)\+k0s\.(\d+)")
ARCHES = ("amd64", "arm64", "arm")


def fetch(url, *, api=False):
    headers = {"User-Agent": "k0s-update-channels"}
    if api:
        headers["Accept"] = "application/vnd.github+json"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
        if os.environ.get("GH_TOKEN"):
            headers["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
        return response.read().decode()


def releases():
    # Read every page: publication order is not version order.
    result = []
    page = 1
    while True:
        batch = json.loads(fetch(
            f"https://api.github.com/repos/k0sproject/k0s/releases?per_page=100&page={page}", api=True))
        if not isinstance(batch, list):
            raise ValueError("Expected a release list")
        result.extend(batch)
        if len(batch) < 100:
            return result
        page += 1


def select(items):
    newest = {}
    for release in items:
        match = TAG.fullmatch(release["tag_name"])
        if release.get("draft") or release.get("prerelease") or not match:
            continue
        version = tuple(map(int, match.groups()))
        minor = version[:2]
        if minor not in newest or version > newest[minor][0]:
            newest[minor] = (version, release)
    if len(newest) < 3:
        raise ValueError("Fewer than three stable minor lines; refusing to replace feeds")
    return [newest[key][1] for key in sorted(newest, reverse=True)[:3]]


def checksums(contents):
    result = {}
    for line in contents.splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r"([0-9a-fA-F]{64})\s+\*?(.+)", line)
        if not match or match[2] in result:
            raise ValueError("Malformed or duplicate checksum entry")
        result[match[2]] = match[1].lower()
    return result


def channel(release, download=fetch):
    tag = release["tag_name"]
    version = TAG.fullmatch(tag)
    name = f"v{version[1]}.{version[2]}"
    assets = {asset["name"]: asset for asset in release["assets"]}
    sums = checksums(download(assets["sha256sums.txt"]["browser_download_url"]))

    def payload(filename):
        asset = assets[filename]
        digest = sums[filename]
        if asset.get("size", 0) <= 0:
            raise ValueError(f"Empty asset: {filename}")
        if asset.get("digest") and asset["digest"] != "sha256:" + digest:
            raise ValueError(f"Digest mismatch: {filename}")
        url = asset["browser_download_url"]
        if not url.startswith("https://github.com/k0sproject/k0s/releases/download/"):
            raise ValueError(f"Unexpected asset URL: {url}")
        return url, digest

    lines = [f"channel: {name}", f"version: {tag[1:]}", "downloadURLs:"]
    for arch in ARCHES:
        url, digest = payload(f"k0s-{tag}-{arch}")
        lines.extend([f"- arch: {arch}", "  os: linux", f"  k0s: {url}", f"  k0sSha256: {digest}"])
        # k0s 1.36 changed the airgap asset naming convention.
        candidates = [f"k0s-airgap-bundle-{tag}-linux-{arch}.tar", f"k0s-airgap-bundle-{tag}-{arch}"]
        bundle = next((filename for filename in candidates if filename in assets), None)
        if bundle is None:
            raise ValueError(f"Missing airgap bundle for {arch}")
        url, digest = payload(bundle)
        lines.extend([f"  airgapBundle: {url}", f"  airgapSha256: {digest}"])
    return name, "\n".join(lines) + "\n"


def generate(root, items, download=fetch):
    # Validate every selected release before touching files. An incomplete release
    # fails the job and leaves all published channels intact until the next run.
    feeds = dict(channel(release, download) for release in select(items))
    stable = root / "stable"
    for name, contents in feeds.items():
        directory = stable / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "index.yaml").write_text(contents)
    (stable / "index.yaml").write_text(next(iter(feeds.values())))
    for path in stable.glob("v*/index.yaml"):
        if re.fullmatch(r"v\d+\.\d+", path.parent.name) and path.parent.name not in feeds:
            path.unlink()
            if not any(path.parent.iterdir()):
                path.parent.rmdir()
    print("Published: " + ", ".join(feeds))


if __name__ == "__main__":
    generate(Path(__file__).resolve().parents[1], releases())
