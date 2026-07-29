#!/usr/bin/env bash
# One-time setup: create the repo, set the email secrets, enable Pages.
#
# Prereqs:
#   brew install gh && gh auth login
#   A Gmail App Password (NOT your normal password):
#     https://myaccount.google.com/apppasswords
#     Requires 2-Step Verification to be on. It gives you a 16-character
#     string. Google will not let you use your account password for SMTP.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

REPO="${1:-sports-dashboard}"
EMAIL="${2:-ljdolibois@gmail.com}"

command -v gh >/dev/null || { echo "Install the GitHub CLI first: brew install gh"; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "Run: gh auth login"; exit 1; }

if [ ! -d .git ]; then
  git init -q
  git add -A
  git commit -qm "Daily sports brief"
fi
git branch -M main

if ! gh repo view "$REPO" >/dev/null 2>&1; then
  gh repo create "$REPO" --public --source=. --remote=origin --push
else
  git push -u origin main
fi

OWNER="$(gh api user --jq .login)"

echo
echo "Gmail App Password (16 chars, from https://myaccount.google.com/apppasswords):"
read -rs APP_PW
echo

gh secret set MAIL_USERNAME --repo "$OWNER/$REPO" --body "$EMAIL"
gh secret set MAIL_PASSWORD --repo "$OWNER/$REPO" --body "$APP_PW"
gh secret set MAIL_TO       --repo "$OWNER/$REPO" --body "$EMAIL"

# Enable Pages with the Actions build type.
gh api -X POST "repos/$OWNER/$REPO/pages" \
  -f "build_type=workflow" >/dev/null 2>&1 || \
gh api -X PUT "repos/$OWNER/$REPO/pages" \
  -f "build_type=workflow" >/dev/null 2>&1 || \
  echo "  (couldn't set Pages automatically — turn it on at"
  echo "   https://github.com/$OWNER/$REPO/settings/pages, source = GitHub Actions)"

echo
echo "Done. Repo: https://github.com/$OWNER/$REPO"
echo "Dashboard will publish to: https://$OWNER.github.io/$REPO/"
echo
echo "Kick off the first run now:"
echo "  gh workflow run 'Daily sports brief' --repo $OWNER/$REPO"
echo "  gh run watch --repo $OWNER/$REPO"
