#!/usr/bin/env bash
# One-command setup. Idempotent — safe to re-run after a failure.
#
#   cd ~/Desktop/sports-dashboard && ./bootstrap.sh
#
# Two steps need you personally and cannot be scripted away:
#   1. `gh auth login` opens a browser for your GitHub password/2FA.
#   2. The Gmail App Password comes from your Google account.
# Everything else is automatic.

set -uo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

EMAIL="${1:-ljdolibois@gmail.com}"
REPO="${2:-sports-dashboard}"

bold() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\n\033[31m✗ %s\033[0m\n' "$*"; exit 1; }

# ---------------------------------------------------------------- 1. tools
bold "1/6  Checking tools"

if ! command -v brew >/dev/null; then
  die "Homebrew missing. Install it first:
  /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"
Then re-run this script."
fi
ok "homebrew"

command -v git >/dev/null || die "git missing — run: xcode-select --install"
ok "git"

if ! command -v gh >/dev/null; then
  warn "installing GitHub CLI (takes a minute)..."
  brew install gh || die "brew install gh failed"
fi
ok "gh $(gh --version | head -1 | awk '{print $3}')"

# ---------------------------------------------------------------- 2. auth
bold "2/6  GitHub login"
if ! gh auth status >/dev/null 2>&1; then
  warn "opening a browser — choose GitHub.com, HTTPS, and authenticate"
  gh auth login || die "gh auth login failed. Re-run this script when done."
fi
OWNER="$(gh api user --jq .login 2>/dev/null)" || die "gh is authenticated but the API call failed"
ok "signed in as $OWNER"

# ---------------------------------------------------------------- 3. repo
bold "3/6  Repository"
if [ ! -d .git ]; then
  git init -q
  git add -A
  git -c user.email="$EMAIL" -c user.name="$OWNER" commit -qm "Daily sports brief"
  ok "git repo initialized"
else
  git add -A
  git -c user.email="$EMAIL" -c user.name="$OWNER" commit -qm "Update" 2>/dev/null && ok "committed changes" || ok "nothing new to commit"
fi
git branch -M main

if gh repo view "$OWNER/$REPO" >/dev/null 2>&1; then
  git remote get-url origin >/dev/null 2>&1 || git remote add origin "https://github.com/$OWNER/$REPO.git"
  ok "repo $OWNER/$REPO already exists"
else
  gh repo create "$REPO" --public --source=. --remote=origin >/dev/null || die "could not create the repo"
  ok "created $OWNER/$REPO"
fi
git push -u origin main >/dev/null 2>&1 && ok "pushed" || warn "push reported nothing to do"

# ---------------------------------------------------------------- 4. email
bold "4/6  Email delivery (optional)"
echo "  Paste a Gmail App Password — 16 characters, from"
echo "    https://myaccount.google.com/apppasswords"
echo "  (needs 2-Step Verification on; your normal password will NOT work)"
echo "  Press Enter alone to skip email and just publish the web page."
printf "  App password: "
read -rs APP_PW; echo

if [ -n "${APP_PW:-}" ]; then
  gh secret set MAIL_USERNAME --repo "$OWNER/$REPO" --body "$EMAIL"  >/dev/null
  gh secret set MAIL_PASSWORD --repo "$OWNER/$REPO" --body "$APP_PW" >/dev/null
  gh secret set MAIL_TO       --repo "$OWNER/$REPO" --body "$EMAIL"  >/dev/null
  ok "email secrets set — the brief will arrive at $EMAIL"
else
  warn "skipped. The page still publishes; you just won't get the email."
  warn "Re-run this script later to add it."
fi

# ---------------------------------------------------------------- 5. pages
bold "5/6  GitHub Pages"
if gh api "repos/$OWNER/$REPO/pages" >/dev/null 2>&1; then
  gh api -X PUT "repos/$OWNER/$REPO/pages" -f build_type=workflow >/dev/null 2>&1
  ok "Pages already enabled"
elif gh api -X POST "repos/$OWNER/$REPO/pages" -f build_type=workflow >/dev/null 2>&1; then
  ok "Pages enabled"
else
  warn "couldn't enable Pages via the API."
  warn "Turn it on here, set Source = GitHub Actions:"
  warn "  https://github.com/$OWNER/$REPO/settings/pages"
fi

# ---------------------------------------------------------------- 6. run
bold "6/6  First run"
gh workflow run "Daily sports brief" --repo "$OWNER/$REPO" >/dev/null 2>&1 \
  && ok "triggered" \
  || warn "couldn't trigger automatically — use the Actions tab"

sleep 6
echo
echo "  Watching the run (Ctrl-C is safe, it keeps going):"
gh run watch --repo "$OWNER/$REPO" --exit-status 2>/dev/null || true

cat <<EOF

────────────────────────────────────────────────────────────
  Dashboard:  https://$OWNER.github.io/$REPO/
  Repo:       https://github.com/$OWNER/$REPO
  Runs:       https://github.com/$OWNER/$REPO/actions

  Rebuilds daily at 12:15 UTC (7:15am Central in summer).
  Bookmark the dashboard URL — it is always current.

  Pages can take 2-3 minutes to serve the first time.
────────────────────────────────────────────────────────────
EOF
