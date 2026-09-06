import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import update_channels as update

DIGEST = "a" * 64


def release(tag, **extra):
    assets = []
    for arch in update.ARCHES:
        for name in (f"k0s-{tag}-{arch}", f"k0s-airgap-bundle-{tag}-linux-{arch}.tar"):
            assets.append({"name": name, "size": 123, "digest": "sha256:" + DIGEST,
                           "browser_download_url": f"https://github.com/k0sproject/k0s/releases/download/{tag}/{name}"})
    assets.append({"name": "sha256sums.txt", "browser_download_url": "https://example.test/sums"})
    return dict(tag_name=tag, draft=False, prerelease=False, assets=assets) | extra


def sums(items):
    return "\n".join(f"{DIGEST} *{a['name']}" for r in items for a in r["assets"] if a["name"] != "sha256sums.txt")


class ChannelsTest(unittest.TestCase):
    def test_version_matches_running_k0s_for_autopilot_completion(self):
        item = release("v1.36.4+k0s.0")
        _, content = update.channel(item, lambda _: sums([item]))
        reported_version = "v1.36.4+k0s.0"
        feed_version = next(line.removeprefix("version: ")
                            for line in content.splitlines() if line.startswith("version: "))
        self.assertEqual(feed_version, reported_version)

    def test_numeric_selection_and_stable_filter(self):
        tags = ["v1.9.9+k0s.0", "v1.34.9+k0s.0", "v1.35.10+k0s.2",
                "v1.35.10+k0s.10", "v1.35.9+k0s.20", "v1.36.0+k0s.0"]
        items = [release(tag) for tag in tags]
        items += [release("v1.37.0+k0s.0", prerelease=True),
                  release("v1.38.0+k0s.0", draft=True), release("v1.39.0-rc.1+k0s.0")]
        self.assertEqual([r["tag_name"] for r in update.select(items)],
                         ["v1.36.0+k0s.0", "v1.35.10+k0s.10", "v1.34.9+k0s.0"])

    def test_pagination(self):
        with patch.object(update, "fetch", side_effect=[json.dumps([{}] * 100), '[{"last": true}]']) as fetch:
            self.assertEqual(len(update.releases()), 101)
            self.assertIn("page=2", fetch.call_args.args[0])

    def test_checksum_format_and_rejection(self):
        self.assertEqual(update.checksums(f"{DIGEST}  binary\n{DIGEST} *bundle"),
                         {"binary": DIGEST, "bundle": DIGEST})
        for contents in ("bad", f"{DIGEST}  binary\n{DIGEST}  binary"):
            with self.assertRaises(ValueError):
                update.checksums(contents)

    def test_asset_validation_and_old_bundle_names(self):
        item = release("v1.35.1+k0s.0")
        for asset in item["assets"]:
            if "airgap-bundle" in asset["name"]:
                asset["name"] = asset["name"].replace("-linux-", "-").removesuffix(".tar")
        name, content = update.channel(item, lambda _: sums([item]))
        self.assertEqual(name, "v1.35")
        self.assertEqual(content.count("  k0sSha256:"), 3)
        self.assertEqual(content.count("  airgapSha256:"), 3)
        item["assets"][0]["digest"] = "sha256:" + "b" * 64
        with self.assertRaises(ValueError):
            update.channel(item, lambda _: sums([item]))

    def test_retention_idempotence_and_failed_release_preserves_files(self):
        items = [release(f"v1.{minor}.1+k0s.0") for minor in (34, 35, 36)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / "stable/v1.29/index.yaml"
            old.parent.mkdir(parents=True)
            old.write_text("old")
            update.generate(root, items, lambda _: sums(items))
            self.assertFalse(old.exists())
            self.assertEqual(len(list((root / "stable").glob("v*/index.yaml"))), 3)
            self.assertEqual((root / "stable/index.yaml").read_text(),
                             (root / "stable/v1.36/index.yaml").read_text())
            snapshot = {str(p): p.read_bytes() for p in root.rglob("*.yaml")}
            update.generate(root, items, lambda _: sums(items))
            self.assertEqual(snapshot, {str(p): p.read_bytes() for p in root.rglob("*.yaml")})
            items.append(release("v1.37.0+k0s.0", assets=[]))
            with self.assertRaises(KeyError):
                update.generate(root, items, lambda _: sums(items))
            self.assertEqual(snapshot, {str(p): p.read_bytes() for p in root.rglob("*.yaml")})

    def test_insufficient_release_data(self):
        with self.assertRaises(ValueError):
            update.select([release("v1.36.1+k0s.0")])


if __name__ == "__main__":
    unittest.main()
