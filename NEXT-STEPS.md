# Start here

## 1. Look at what's already built (30 seconds)

Open `out/dashboard.html`. It's a real build of Tue Jul 28, 2026 — 20 finals,
9 standout performances, 12 stories. If you don't like it, say so before
automating; automating a page you don't want is scheduled disappointment.

## 2. Run one command

```bash
cd ~/Desktop/sports-dashboard
./bootstrap.sh
```

That installs the GitHub CLI if needed, logs you in, creates the repo, sets the
email secrets, enables Pages, and triggers the first build. It's idempotent —
if it dies halfway, just run it again.

Two prompts need you personally and can't be scripted:

- **GitHub login** — opens a browser. Choose GitHub.com → HTTPS → authenticate.
- **Gmail App Password** — 16 characters from
  https://myaccount.google.com/apppasswords. Requires 2-Step Verification.
  Press Enter to skip; the web page still publishes, you just don't get email.

When it finishes you'll have `https://<your-username>.github.io/sports-dashboard/`,
rebuilt every morning whether your laptop is open or not. Bookmark it.

## 3. If anything breaks

```bash
cd ~/Desktop/sports-dashboard && claude
```

Paste the prompt from the chat. `CLAUDE.md` already contains the design rules,
the endpoint reference, and the known gaps.

## You do NOT need a local Python setup

Earlier advice said to make a venv first. Ignore that — it makes you fight
macOS's Python 3.9 to solve a problem you don't have. GitHub's runner brings
its own Python 3.12. `bootstrap.sh` needs only `git` and `gh`.

The local path (`scripts/install-schedule.sh`, launchd) still works if you ever
want an offline copy. It is not required.

## The two things worth fixing first

1. **Soccer standouts don't work.** ESPN's soccer summary has no per-player box
   score, so soccer falls through to a flat score of 35 and never surfaces.
   Needs a `_soccer()` rule reading `summary['keyEvents']`.
2. **The thresholds are my opinion, not yours.** After a week you'll disagree
   with some. They're all in `src/standouts.py`, one function per sport.
