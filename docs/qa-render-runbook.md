# QA render runbook — `qa-render`

This host is shared by many agents. When several run Vite + headless Chrome at
once, two things used to break visual QA for **everyone**:

1. **`ENOSPC` on `/`.** Chromium/Playwright create scratch with `mkdtemp("/tmp/…")`.
   `/tmp` lives on the root filesystem, which routinely fills to ~100% on this box.
   A single render's temp dir landing on a full `/` killed the run with
   `ENOSPC: no space left on device`.
2. **OOM / `net::ERR_INSUFFICIENT_RESOURCES`.** Four+ worktrees each launching a
   browser at the same time exhausted RAM and crashed renders mid-flight.

`qa-render` is the **single wrapper every agent must use** to launch any headless
Chrome / Playwright / Puppeteer render. It fixes both:

- Forces **all** render scratch onto the `/dev/shm` tmpfs (3.8 G, ~3% used) — never `/`.
  Sets `TMPDIR`/`TMP`/`TEMP`, the Chrome `--user-data-dir`, and `XDG_*` dirs under
  `/dev/shm`, and cleans them up on exit. A render's scratch can no longer touch `/`.
- A cross-agent **flock semaphore** caps concurrent headless Chromes (default **2**).
  Extra launches **queue**, they do not crash.

> Background: [CLI-51](/CLI/issues/CLI-51) (host disk hit 100%) → [CLI-52](/CLI/issues/CLI-52) (this hardening).

## The one rule

**Never launch headless Chrome directly. Always go through `qa-render`.**

```bash
# instead of:   node qa-foo.cjs
qa-render node qa-foo.cjs

# instead of:   LD_LIBRARY_PATH=... node qa-screenshots.cjs
qa-render node qa-screenshots.cjs
```

`qa-render` is on `PATH` (`~/.local/bin/qa-render`). It runs your command with the
shm scratch environment in place and holding a render slot, then cleans up.

## Usage

```
qa-render <command> [args...]      # run a render command with a slot + shm scratch
qa-render -- node qa-foo.cjs       # use -- if your command starts with a dash
qa-render -n 3 node qa-foo.cjs     # override max concurrency just for this call
qa-render --timeout 300 node ...   # give up after 300s waiting for a slot (default: wait forever)
qa-render --env                    # advanced: print `export ...` lines to source manually
qa-render -h
```

Exit code is your command's own exit code (or `75` if it timed out waiting for a
slot, `64` for a usage error).

## Configuration (env vars)

| Variable | Default | Meaning |
|---|---|---|
| `QA_RENDER_MAX_CONCURRENCY` | `2` | Max simultaneous renders across all agents. |
| `QA_RENDER_WAIT_TIMEOUT` | `0` | Seconds to wait for a slot; `0` = wait forever (queue). |
| `QA_RENDER_SHM` | `/dev/shm` | tmpfs root used for scratch. |
| `QA_RENDER_LIBDIR` | `/home/linuxbrew/.linuxbrew/lib` | Holds `libnspr4.so` etc. for Chromium. |
| `QA_RENDER_CHROME` | newest `~/.cache/puppeteer/chrome/linux-*/.../chrome` | Chrome executable. |
| `QA_RENDER_MIN_SHM_MB` | `200` | Warn if tmpfs free is below this. |

Inside the wrapped command these are exported for you to use:

| Variable | Use it for |
|---|---|
| `TMPDIR` / `TMP` / `TEMP` | already point at a per-run dir on `/dev/shm` |
| `QA_RENDER_USER_DATA_DIR` | the Chrome user-data-dir to use (on `/dev/shm`) |
| `QA_RENDER_CHROME` | resolved Chrome executable path |
| `QA_RENDER_CHROME_ARGS` | safe launch args (`--no-sandbox`; **no** `--disable-dev-shm-usage` — we have real shm) |
| `QA_RENDER_RUNDIR` | the per-run scratch root (auto-deleted on exit) |
| `LD_LIBRARY_PATH` | already includes the linuxbrew libs |

## Writing a render script (recommended: use the JS helper)

`launch.cjs` wraps Playwright with the right defaults so you don't hand-roll
`chromium.launch`. It reads the env above and works from CommonJS (load it with
`require` even in `"type":"module"` projects — keep the file extension `.cjs`).

```js
// my-qa.cjs   — run with:  qa-render node my-qa.cjs
const { launchContext } = require(
  require('os').homedir() + '/.local/share/qa-render/launch.cjs'
);

(async () => {
  // launchPersistentContext keeps the user-data-dir on /dev/shm
  const ctx  = await launchContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  await page.goto('http://127.0.0.1:8193/');   // your Vite dev/preview port
  await page.screenshot({ path: 'shot.png' }); // write OUTPUT outside TMPDIR (it gets cleaned)
  await ctx.close();
})();
```

Helper API (`require('~/.local/share/qa-render/launch.cjs')`):

- `launchContext(opts)` → Playwright `BrowserContext` (persistent, profile on `/dev/shm`).
  `opts`: `{ viewport, args, headless, contextOptions }`.
- `launchBrowser(opts)` → plain `Browser` (temp profile under `TMPDIR` = `/dev/shm`).
- `resolveChrome()`, `userDataDir()` — the resolution helpers, if you need them.

> **Write screenshots/artifacts to a real output dir** (your workspace), not under
> `TMPDIR`/`QA_RENDER_RUNDIR` — those are deleted when the render exits.

### Already have a bare `chromium.launch({ headless: true })` script?

You don't have to rewrite it. Just run it through the wrapper —
`qa-render node old-script.cjs` — and `TMPDIR=/dev/shm` alone keeps Playwright's
auto-created profile/artifacts off `/`. Migrating to `launch.cjs` additionally
puts the user-data-dir on `/dev/shm` and pins the Chrome binary + libs.

## Install / refresh

The wrapper lives in the ClickSpot repo at `scripts/qa-render/`. To (re)deploy it
to this host so every agent picks it up:

```bash
./scripts/qa-render/install.sh
```

That installs `~/.local/share/qa-render/{qa-render,launch.cjs}` and symlinks
`~/.local/bin/qa-render`. Re-run after pulling changes to the scripts.

## Verify it works

```bash
# launch 4 renders at once; the gate should cap at 2 and / must not fill.
df -Pm /              # note "Available"
for i in 1 2 3 4; do qa-render node my-qa.cjs "$i" & done; wait
df -Pm /              # Available unchanged by the renders (scratch was on /dev/shm)
ls /dev/shm/qa-render/run.* 2>/dev/null || echo "scratch cleaned"
```

Expect: `qa-render: all 2 render slots busy; queueing…` for the 3rd/4th, all four
complete, `/dev/shm` absorbs the scratch, and `/` Available is not reduced by the
renders. (On this shared box `/` may drift a few MB from *other* agents' processes —
compare against an idle `df` sample; the renders themselves contribute nothing.)
