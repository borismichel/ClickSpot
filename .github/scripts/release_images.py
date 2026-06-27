#!/usr/bin/env python3
"""Append (or refresh) the "Container images" block in a GitHub release body.

Reads the current release body on stdin and writes the updated body to stdout.
The image references and digests come from the environment, set by the
``docker-publish`` workflow after the multi-arch manifests are pushed:

    OWNER    repository owner (ghcr.io namespace)
    VERSION  release version without the leading "v" (e.g. 0.1.8)
    APP_D    clickspot-app manifest-list digest (sha256:...)
    FE_D     clickspot-frontend manifest-list digest
    DEMO_D   clickspot (demo) manifest-list digest

The block is delimited by HTML comment markers so re-running on the same
release replaces the block in place instead of appending duplicates. Building
the markdown here (rather than in a shell heredoc) keeps the backticks literal.
"""
import os
import re
import sys

START = "<!-- container-images:start -->"
END = "<!-- container-images:end -->"

owner = os.environ["OWNER"]
version = os.environ["VERSION"]
app_d = os.environ["APP_D"]
fe_d = os.environ["FE_D"]
demo_d = os.environ["DEMO_D"]

app = f"ghcr.io/{owner}/clickspot-app"
fe = f"ghcr.io/{owner}/clickspot-frontend"
demo = f"ghcr.io/{owner}/clickspot"

block = f"""{START}
## 📦 Container images

Multi-arch (linux/amd64 + linux/arm64), published to GitHub Container Registry. Pull is public — no login required.

| Image | Tags | Digest |
|-------|------|--------|
| `{app}` | `{version}`, `latest` | `{app_d}` |
| `{fe}` | `{version}`, `latest` | `{fe_d}` |
| `{demo}` (demo) | `demo`, `demo-{version}` | `{demo_d}` |

```bash
docker pull {app}:{version}
docker pull {fe}:{version}
docker pull {demo}:demo
```
{END}"""

body = sys.stdin.read()
# Drop any previous auto-generated block so re-runs replace rather than stack.
body = re.sub(re.escape(START) + r".*?" + re.escape(END) + r"\n?", "", body, flags=re.S).rstrip()

sys.stdout.write(f"{body}\n\n{block}\n")
