# Branch Protection Guidelines

## Overview

This document outlines the branch protection rules and best practices for the GODmodeScanner repository to maintain code quality, security, and stability.

## Why Branch Protection?

Branch protection helps prevent:
- Accidental force pushes that can lose commit history
- Direct commits to main without proper review
- Deletion of critical branches
- Deployment of untested or unreviewed code
- Security vulnerabilities from being merged

## Recommended Branch Protection Rules for Main Branch

### 1. Protect Against Force Push and Deletion

**Setting**: Enable "Protect this branch" in GitHub repository settings

**Benefits**:
- Preserves commit history
- Prevents accidental branch deletion
- Maintains audit trail of all changes

### 2. Require Pull Request Reviews

**Settings**:
- Require at least 1 approval before merging
- Dismiss stale pull request approvals when new commits are pushed
- Require review from Code Owners (if CODEOWNERS file exists)

**Benefits**:
- Ensures code review before merging
- Catches bugs and security issues early
- Knowledge sharing across team
- Maintains code quality standards

### 3. Require Status Checks to Pass

**Recommended Checks**:
- ✅ CI/CD pipeline (build, test, lint)
- ✅ Security scanning (CodeQL, dependency checks)
- ✅ Code quality checks (linting, formatting)
- ✅ Test coverage requirements

**Benefits**:
- Prevents breaking changes from being merged
- Ensures all tests pass before merge
- Maintains high code quality standards
- Catches security vulnerabilities automatically

### 4. Require Signed Commits (Optional but Recommended)

**Benefits**:
- Verifies commit authenticity
- Prevents commit spoofing
- Enhanced security posture

### 5. Restrict Who Can Push to the Branch

**Settings**:
- Allow specific teams or users to bypass protections
- Restrict direct pushes (all changes through PRs)

**Benefits**:
- Enforces code review process
- Prevents accidental direct commits
- Maintains quality gate

## How to Enable Branch Protection on GitHub

### Step 1: Navigate to Repository Settings

1. Go to your repository on GitHub
2. Click on "Settings" tab
3. Click on "Branches" in the left sidebar

### Step 2: Add Branch Protection Rule

1. Click "Add rule" or "Add branch protection rule"
2. In "Branch name pattern", enter: `main` (or `master` if that's your default branch)

### Step 3: Configure Protection Settings

**Essential Settings**:

☑️ **Require a pull request before merging**
   - ☑️ Require approvals: 1 (or more for larger teams)
   - ☑️ Dismiss stale pull request approvals when new commits are pushed
   - ☑️ Require review from Code Owners (if applicable)

☑️ **Require status checks to pass before merging**
   - ☑️ Require branches to be up to date before merging
   - Select required status checks:
     - CI/CD pipeline
     - Tests
     - Linting
     - Security scans

☑️ **Require conversation resolution before merging**
   - Ensures all PR comments are addressed

☑️ **Require signed commits** (recommended)

☑️ **Require linear history** (optional, prevents merge commits)

☑️ **Include administrators**
   - Applies rules to repository administrators too

☑️ **Restrict who can push to matching branches**
   - Prevents direct pushes, forces PR workflow

☑️ **Allow force pushes** - ❌ Keep DISABLED
   - Prevents rewriting history

☑️ **Allow deletions** - ❌ Keep DISABLED
   - Prevents accidental branch deletion

### Step 4: Save Changes

1. Click "Create" or "Save changes"
2. Verify the protection rules are active

## GitHub Actions Workflows for Status Checks

This repository includes automated workflows in `.github/workflows/` that run on every pull request:

- **ci.yml**: Continuous Integration (build, test, lint)
- **security.yml**: Security scanning (CodeQL, dependency checks)
- **code-quality.yml**: Code quality checks

These workflows provide the status checks required by branch protection.

## Working with Protected Branches

### Making Changes

1. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes and commit**
   ```bash
   git add .
   git commit -m "Your commit message"
   ```

3. **Push to GitHub**
   ```bash
   git push origin feature/your-feature-name
   ```

4. **Create a Pull Request**
   - Go to GitHub repository
   - Click "Compare & pull request"
   - Fill in PR details
   - Submit for review

5. **Address Review Comments**
   - Make requested changes
   - Push additional commits
   - Request re-review if needed

6. **Wait for Status Checks**
   - All required checks must pass
   - Fix any failures before merging

7. **Merge After Approval**
   - Once approved and checks pass
   - Click "Merge pull request"
   - Delete feature branch after merge

### Emergency Hotfixes

For critical production issues:

1. Create hotfix branch: `hotfix/critical-issue`
2. Make minimal fix
3. Create PR with "HOTFIX" label
4. Request expedited review
5. Merge after approval and checks

**Note**: Even for hotfixes, branch protection rules apply to maintain quality.

## Best Practices

1. **Keep PRs Small**: Easier to review and less risky
2. **Write Descriptive Commit Messages**: Helps with code history
3. **Include Tests**: All changes should have test coverage
4. **Update Documentation**: Keep docs in sync with code
5. **Respond to Reviews Promptly**: Don't let PRs go stale
6. **Run Tests Locally**: Before pushing to save CI resources
7. **Keep Branches Updated**: Regularly sync with main

## Troubleshooting

### "Push declined due to branch protection"

This is expected behavior. You need to:
1. Create a pull request instead of pushing directly
2. Go through the code review process

### Status Checks Failing

1. Check the GitHub Actions logs for specific errors
2. Fix issues locally
3. Push fixes to your branch
4. Checks will re-run automatically

### Cannot Delete Branch

Main branch is protected from deletion. This is intentional and should not be changed.

### Need to Force Push to Feature Branch

Force pushing to feature branches (not main) is allowed:
```bash
git push -f origin feature/your-branch
```

**Warning**: Never force push to main or shared branches.

## Additional Resources

- [GitHub Branch Protection Documentation](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Pull Request Best Practices](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests)

## Questions or Issues?

If you have questions about branch protection or encounter issues:
1. Check this documentation first
2. Review GitHub's official documentation
3. Contact repository maintainers
4. Open an issue with the "question" label

---

**Last Updated**: 2026-02-02
**Maintained by**: Repository Maintainers
