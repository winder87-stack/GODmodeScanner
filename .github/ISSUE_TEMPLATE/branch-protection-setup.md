---
name: Enable Branch Protection
about: Quick guide to enable branch protection for the main branch
title: '[SETUP] Enable Branch Protection for Main Branch'
labels: 'setup, documentation'
assignees: ''
---

## Branch Protection Setup Checklist

This issue tracks the setup of branch protection rules for the `main` branch to prevent accidental force pushes, deletions, and ensure code quality through required reviews and automated checks.

### Quick Setup Steps

#### 1. Navigate to Branch Protection Settings

1. Go to repository on GitHub: https://github.com/winder87-stack/GODmodeScanner
2. Click **Settings** → **Branches** → **Add rule**
3. Enter branch name pattern: `main`

#### 2. Configure Required Settings

Check these essential options:

**Pull Request Requirements:**
- [ ] ✅ Require a pull request before merging
  - [ ] Require approvals: `1` (or more)
  - [ ] Dismiss stale pull request approvals when new commits are pushed
  - [ ] Require review from Code Owners (optional, if CODEOWNERS exists)

**Status Check Requirements:**
- [ ] ✅ Require status checks to pass before merging
  - [ ] Require branches to be up to date before merging
  - [ ] Add required status checks:
    - [ ] `CI - Continuous Integration / lint`
    - [ ] `CI - Continuous Integration / test`
    - [ ] `CI - Continuous Integration / build`
    - [ ] `Security Checks / codeql-analysis`

**Additional Protections:**
- [ ] ✅ Require conversation resolution before merging
- [ ] ✅ Require signed commits (recommended)
- [ ] ✅ Require linear history (optional)
- [ ] ✅ Include administrators (apply rules to admins)

**Restrictions:**
- [ ] ✅ Allow force pushes: **DISABLED** ❌
- [ ] ✅ Allow deletions: **DISABLED** ❌

#### 3. Save and Verify

- [ ] Click **Create** or **Save changes**
- [ ] Verify protection rules are active
- [ ] Test by attempting direct push (should fail)
- [ ] Test by creating a PR (should succeed)

### Documentation

The repository now includes comprehensive documentation:

- 📖 **[BRANCH_PROTECTION.md](../../BRANCH_PROTECTION.md)** - Complete branch protection guide
- 📖 **[CONTRIBUTING.md](../../CONTRIBUTING.md)** - Contribution guidelines
- 🔧 **[.github/workflows/ci.yml](../workflows/ci.yml)** - CI pipeline
- 🔒 **[.github/workflows/security.yml](../workflows/security.yml)** - Security checks

### Benefits

Once enabled, branch protection provides:

✅ **Prevents accidental damage** - No force pushes or branch deletion
✅ **Ensures code review** - All changes reviewed before merging
✅ **Maintains quality** - Automated tests and checks must pass
✅ **Increases security** - Security scans catch vulnerabilities
✅ **Preserves history** - Complete audit trail of all changes
✅ **Team collaboration** - Structured workflow for all contributors

### Verification

After setup, verify protection is working:

```bash
# Try to push directly to main (should fail)
git checkout main
git commit --allow-empty -m "test"
git push origin main
# Expected: Error about branch protection

# Create PR instead (should work)
git checkout -b test/branch-protection
git push origin test/branch-protection
# Create PR on GitHub - should work correctly
```

### Questions?

- Review [BRANCH_PROTECTION.md](../../BRANCH_PROTECTION.md) for detailed instructions
- Check [GitHub's official documentation](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
- Comment on this issue if you need help

---

**Priority**: High  
**Estimated Time**: 5-10 minutes  
**Assigned To**: Repository administrators/maintainers
