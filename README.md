# Automated k0s update channels

Fork of [k0sproject/update](https://github.com/k0sproject/update), refreshed daily
at 06:23 UTC from the [k0s GitHub releases](https://github.com/k0sproject/k0s/releases).
Run **Actions → Update channels → Run workflow** to refresh manually.

## Channels and retention

- `stable/v1.MINOR`: newest stable patch and k0s revision in that minor line.
- `stable`: newest stable release overall; this channel can cross minor versions.

Only the **three newest stable k0s minor lines** are retained. This follows the
three-minor retention model in the [Kubernetes support policy](https://kubernetes.io/releases/version-skew-policy/#supported-versions),
using k0s release availability. It is not a claim that k0s release timing or EOL
dates exactly match Kubernetes. When a new stable minor appears, the oldest
minor channel is deleted, so clients on it must deliberately migrate to a
supported minor. A retired channel returns 404; it never redirects to a newer minor.
Drafts and prereleases are excluded. Versions sort numerically, including the
`+k0s.N` revision, independently of publication order.

## Use with Autopilot

For patch-only updates, select your installed minor explicitly:

```yaml
apiVersion: autopilot.k0sproject.io/v1beta2
kind: UpdateConfig
metadata:
  name: k0s-patch-updates
spec:
  updateServer: https://raw.githubusercontent.com/flokoe/update/main/
  channel: stable/v1.36
  upgradeStrategy:
    type: periodic
    periodic:
      days: [Sunday]
      startTime: "04:00"
      length: 2h
```

The example window uses the k0s process's local timezone. Choose your own window.
No Pages setup or custom domain is required. Autopilot fetches
`<updateServer>/<channel>/index.yaml`; binaries and airgap bundles download directly
from upstream GitHub releases. Linux amd64, arm64, and arm are included.

## Generation and validation

The Python standard-library generator paginates the releases API and validates
all three selected releases before writing any feeds. Binary and airgap checksums
come from the exact filename in `sha256sums.txt`; GitHub asset digests must agree
when present. Missing assets, checksums, or mismatches fail the workflow without
publishing partial updates. The next scheduled run retries. The workflow commits
only changed channel files using its built-in token; no extra secrets are required.

```sh
python3 -m unittest discover -s scripts -p 'test_*.py' -v
GH_TOKEN="$(gh auth token)" python3 scripts/update_channels.py
```

Fork workflows must be enabled. GitHub may disable scheduled workflows after
60 days of repository inactivity; monitor Actions and re-enable if necessary.
The inherited `latest`, `unstable`, and upstream `CNAME` are intentionally removed.
