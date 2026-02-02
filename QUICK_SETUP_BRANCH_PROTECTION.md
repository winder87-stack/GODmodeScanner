# Quick Setup: Branch Protection

This is a condensed guide for repository administrators to quickly enable branch protection.

## ⚡ 5-Minute Setup

### Step 1: Go to Settings (30 seconds)

1. Navigate to: https://github.com/winder87-stack/GODmodeScanner/settings/branches
2. Click **"Add rule"** or **"Add branch protection rule"**
3. Enter branch name: `main`

### Step 2: Configure Protection (3 minutes)

Copy these settings:

**✅ Essential Settings:**

```
☑ Require a pull request before merging
  ☑ Require approvals: 1
  ☑ Dismiss stale pull request approvals when new commits are pushed

☑ Require status checks to pass before merging
  ☑ Require branches to be up to date before merging
  Add these checks (after first workflow runs):
    - CI - Continuous Integration / lint
    - CI - Continuous Integration / test
    - CI - Continuous Integration / build
    - Security Checks / codeql-analysis

☑ Require conversation resolution before merging

☑ Include administrators

☐ Allow force pushes (KEEP UNCHECKED)
☐ Allow deletions (KEEP UNCHECKED)
```

### Step 3: Save (30 seconds)

1. Click **"Create"** at the bottom
2. Verify the protection rule appears in the list

### Step 4: Verify (1 minute)

Test that it's working:

```bash
# This should FAIL with "protected branch" error
git checkout main
git commit --allow-empty -m "test protection"
git push origin main
# ✅ Expected: Error about branch protection

# This should WORK
git checkout -b test/protection-check
git push origin test/protection-check
# ✅ Expected: Push succeeds
```

## ✨ What This Protects Against

- ❌ Direct pushes to main (forces PR workflow)
- ❌ Force pushes (prevents history rewriting)
- ❌ Branch deletion (preserves main branch)
- ❌ Merging untested code (requires CI to pass)
- ❌ Unreviewed code (requires approval)

## 📝 After Setup

Your contributors will need to:

1. **Create feature branches** instead of pushing to main
2. **Open Pull Requests** for all changes
3. **Wait for CI checks** to pass
4. **Get at least 1 approval** before merging

All of this is documented in:
- 📖 [BRANCH_PROTECTION.md](BRANCH_PROTECTION.md) - Detailed guide
- 📖 [CONTRIBUTING.md](CONTRIBUTING.md) - Contributor guidelines
- 📖 [README.md](README.md) - Updated with branch protection info

## 🔧 Automated Workflows

The repository now includes:

- **`.github/workflows/ci.yml`** - Runs on every PR:
  - Lints code with flake8 and black
  - Runs tests with pytest
  - Validates build
  - Checks Docker configuration

- **`.github/workflows/security.yml`** - Security scans:
  - Dependency vulnerability scanning
  - Secret detection
  - CodeQL security analysis

These provide the status checks required by branch protection.

## ⚠️ Important Notes

1. **Status Checks**: The workflow names will appear as available status checks after the first time they run. You may need to edit the protection rule to add them.

2. **First PR**: The first PR to this repository will trigger the workflows and create the status checks.

3. **Administrators**: Even repository administrators are subject to these rules if you check "Include administrators" (recommended).

## 🆘 Troubleshooting

**Can't find status checks to add?**
- Status checks only appear after workflows have run at least once
- Create a test PR to trigger the workflows
- Then edit the protection rule to add the checks

**Need to bypass temporarily?**
- This is discouraged, but administrators can temporarily:
  - Disable the rule
  - Make the change
  - Re-enable the rule
- Better: Create a PR even as an admin

**Workflows failing?**
- Check the Actions tab for detailed logs
- Fix issues in your PR branch
- Push fixes to re-trigger checks

## 📚 Full Documentation

For complete details, see:
- [BRANCH_PROTECTION.md](BRANCH_PROTECTION.md) - Comprehensive guide with all options and best practices

## ✅ Setup Checklist

Copy this to track your setup:

- [ ] Navigated to Settings > Branches
- [ ] Created protection rule for `main` branch
- [ ] Enabled "Require pull request before merging" with 1 approval
- [ ] Enabled "Require status checks to pass"
- [ ] Disabled "Allow force pushes"
- [ ] Disabled "Allow deletions"
- [ ] Clicked "Create" to save
- [ ] Tested by trying to push directly (should fail)
- [ ] Tested by creating a PR (should work)
- [ ] Informed team about new workflow

---

**Time Required**: ~5 minutes  
**Difficulty**: Easy  
**Impact**: High (prevents accidental damage, ensures code quality)

**Questions?** See [BRANCH_PROTECTION.md](BRANCH_PROTECTION.md) or the issue template in `.github/ISSUE_TEMPLATE/branch-protection-setup.md`
