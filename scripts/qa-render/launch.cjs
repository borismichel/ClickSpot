/*
 * qa-render launch helper — standardized headless-Chrome launch for QA/visual-render
 * scripts on this shared host. Use this instead of hand-rolling chromium.launch().
 *
 * It honors the environment that the `qa-render` wrapper sets up (TMPDIR=/dev/shm,
 * QA_RENDER_USER_DATA_DIR under /dev/shm, resolved Chrome path, linuxbrew libs), and
 * works standalone too (it resolves sane defaults if the wrapper wasn't used) — but
 * the concurrency gate and shm scratch only apply when launched via `qa-render`.
 *
 *   ALWAYS run your script through the wrapper:  qa-render node my-qa.cjs
 *
 * Usage (CommonJS; load with require even from "type":"module" projects via .cjs):
 *
 *   const { launchContext } = require('<path>/launch.cjs');
 *   const ctx  = await launchContext({ viewport: { width: 1440, height: 900 } });
 *   const page = await ctx.newPage();
 *   await page.goto('http://127.0.0.1:8193/');
 *   await page.screenshot({ path: 'out.png' });
 *   await ctx.close();
 *
 * launchContext() uses launchPersistentContext so the Chrome user-data-dir lands on
 * /dev/shm. launchBrowser() returns a plain Browser (its profile is created under
 * TMPDIR, which the wrapper points at /dev/shm).
 */
'use strict';

const fs = require('fs');
const path = require('path');

const PLAYWRIGHT =
  process.env.QA_RENDER_PLAYWRIGHT ||
  '/home/linuxbrew/.linuxbrew/lib/node_modules/playwright';
const LIBDIR = process.env.QA_RENDER_LIBDIR || '/home/linuxbrew/.linuxbrew/lib';

function resolveChrome() {
  if (process.env.QA_RENDER_CHROME && fs.existsSync(process.env.QA_RENDER_CHROME)) {
    return process.env.QA_RENDER_CHROME;
  }
  const base = path.join(process.env.HOME || '/home/clawdbot', '.cache/puppeteer/chrome');
  try {
    const builds = fs
      .readdirSync(base)
      .filter((d) => d.startsWith('linux-'))
      .sort()
      .reverse(); // newest first
    for (const d of builds) {
      const p = path.join(base, d, 'chrome-linux64', 'chrome');
      if (fs.existsSync(p)) return p;
    }
  } catch {
    /* fall through to Playwright's bundled chromium */
  }
  return undefined;
}

function userDataDir() {
  const dir =
    process.env.QA_RENDER_USER_DATA_DIR ||
    path.join(process.env.TMPDIR || '/dev/shm', `qa-render-profile-${process.pid}`);
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

function baseArgs(extra) {
  // --no-sandbox is required in this sandbox. We deliberately do NOT add
  // --disable-dev-shm-usage: this host has a real 3.8G /dev/shm tmpfs and using
  // it is faster + avoids /tmp (which lives on the often-full root fs).
  const fromEnv = (process.env.QA_RENDER_CHROME_ARGS || '--no-sandbox').split(/\s+/).filter(Boolean);
  return [...new Set([...fromEnv, ...(extra || [])])];
}

function launchEnv() {
  return {
    ...process.env,
    LD_LIBRARY_PATH: `${LIBDIR}${process.env.LD_LIBRARY_PATH ? ':' + process.env.LD_LIBRARY_PATH : ''}`,
  };
}

function warnIfNotWrapped() {
  if (!process.env.QA_RENDER_RUNDIR) {
    process.stderr.write(
      'qa-render/launch.cjs: not launched via the `qa-render` wrapper — ' +
        'scratch may not be on /dev/shm and the concurrency gate is NOT applied. ' +
        'Prefer:  qa-render node <your-script>\n'
    );
  }
}

/**
 * Launch a persistent browser context with a /dev/shm user-data-dir.
 * Returns a BrowserContext — call ctx.newPage() / ctx.close().
 */
async function launchContext(opts = {}) {
  warnIfNotWrapped();
  const { chromium } = require(PLAYWRIGHT);
  const exe = resolveChrome();
  const launchOpts = {
    headless: opts.headless !== false,
    args: baseArgs(opts.args),
    env: launchEnv(),
    viewport: opts.viewport || { width: 1440, height: 900 },
    ...(opts.contextOptions || {}),
  };
  if (exe) launchOpts.executablePath = exe;
  return chromium.launchPersistentContext(userDataDir(), launchOpts);
}

/**
 * Launch a plain Browser (non-persistent). Its temp profile is created under
 * TMPDIR, which the wrapper points at /dev/shm.
 */
async function launchBrowser(opts = {}) {
  warnIfNotWrapped();
  const { chromium } = require(PLAYWRIGHT);
  const exe = resolveChrome();
  const launchOpts = {
    headless: opts.headless !== false,
    args: baseArgs(opts.args),
    env: launchEnv(),
    ...(opts.launchOptions || {}),
  };
  if (exe) launchOpts.executablePath = exe;
  return chromium.launch(launchOpts);
}

module.exports = { launchContext, launchBrowser, resolveChrome, userDataDir, PLAYWRIGHT, LIBDIR };
