# Contributing to GODmodeScanner

Thank you for your interest in contributing to GODmodeScanner! This document provides guidelines and best practices for contributing to this project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Branch Protection and Workflow](#branch-protection-and-workflow)
- [Development Process](#development-process)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)
- [Testing Guidelines](#testing-guidelines)
- [Documentation](#documentation)

## Code of Conduct

By participating in this project, you agree to maintain a respectful and collaborative environment. Be kind, professional, and constructive in all interactions.

## Getting Started

1. **Fork the Repository**
   ```bash
   # Click "Fork" on GitHub, then clone your fork
   git clone https://github.com/YOUR_USERNAME/GODmodeScanner.git
   cd GODmodeScanner
   ```

2. **Set Up Development Environment**
   ```bash
   # Install Python dependencies
   pip install -r requirements.txt
   
   # Install development dependencies
   pip install pytest pytest-cov flake8 black pylint
   
   # Configure environment
   cp .env.template .env
   # Edit .env with your configuration
   ```

3. **Add Upstream Remote**
   ```bash
   git remote add upstream https://github.com/winder87-stack/GODmodeScanner.git
   ```

## Branch Protection and Workflow

### Protected Branches

The `main` branch is protected with the following rules:

- ✅ No direct pushes (all changes via Pull Requests)
- ✅ Requires at least 1 approval before merging
- ✅ Requires status checks to pass (CI, tests, security scans)
- ✅ No force pushes allowed
- ✅ No deletion allowed

See [BRANCH_PROTECTION.md](BRANCH_PROTECTION.md) for detailed information.

### Working with Protected Branches

Since the main branch is protected, you must use the following workflow:

1. **Create a Feature Branch**
   ```bash
   # Always create a new branch for your work
   git checkout -b feature/your-feature-name
   
   # Or for bug fixes
   git checkout -b fix/bug-description
   ```

2. **Make Your Changes**
   - Write code following our [coding standards](#coding-standards)
   - Add tests for new functionality
   - Update documentation as needed
   - Keep commits focused and atomic

3. **Test Locally**
   ```bash
   # Run tests
   pytest tests/
   
   # Run linter
   flake8 .
   black --check .
   
   # Validate syntax
   python -m py_compile your_file.py
   ```

4. **Commit Your Changes**
   ```bash
   git add .
   git commit -m "feat: Add new feature description"
   ```
   
   Use conventional commit messages:
   - `feat:` - New feature
   - `fix:` - Bug fix
   - `docs:` - Documentation changes
   - `test:` - Adding or updating tests
   - `refactor:` - Code refactoring
   - `perf:` - Performance improvements
   - `chore:` - Maintenance tasks

5. **Keep Your Branch Updated**
   ```bash
   # Fetch latest changes from upstream
   git fetch upstream
   
   # Rebase your branch on latest main
   git rebase upstream/main
   
   # Or merge if you prefer
   git merge upstream/main
   ```

6. **Push to Your Fork**
   ```bash
   git push origin feature/your-feature-name
   ```

7. **Create Pull Request**
   - Go to GitHub and create a Pull Request from your fork
   - Fill in the PR template with details
   - Link any related issues
   - Request review from maintainers

## Development Process

### Setting Up Your Development Environment

1. **Install Required Tools**
   - Python 3.10 or higher
   - Docker and Docker Compose (for container testing)
   - Redis (for local development)
   - Git

2. **Install Dependencies**
   ```bash
   # Main dependencies
   pip install -r requirements.txt
   
   # Development dependencies
   pip install -r requirements-dev.txt  # If exists
   
   # Or install common dev tools
   pip install pytest pytest-cov pytest-asyncio
   pip install flake8 black pylint mypy
   pip install pre-commit  # For git hooks
   ```

3. **Configure Pre-commit Hooks** (Optional but Recommended)
   ```bash
   pre-commit install
   ```

### Running the Project Locally

```bash
# Option 1: Direct Python execution
python detector.py

# Option 2: Using Docker Compose
docker-compose up -d

# Option 3: Quick start script
./scripts/quick_start.sh

# Option 4: MCP server mode
./scripts/start_mcp_server.sh
```

## Pull Request Process

### Before Submitting

- ✅ Code follows project style guidelines
- ✅ All tests pass locally
- ✅ New features include tests
- ✅ Documentation is updated
- ✅ Commits are clean and well-described
- ✅ Branch is up to date with main

### PR Title and Description

**Title Format**: `type: Brief description`

Examples:
- `feat: Add support for Telegram alerts`
- `fix: Resolve race condition in wallet analyzer`
- `docs: Update installation instructions`

**Description Should Include**:
- **What**: What changes are being made
- **Why**: Why these changes are needed
- **How**: How the changes work (if complex)
- **Testing**: How you tested the changes
- **Screenshots**: For UI changes (if applicable)

### PR Checklist

When creating a PR, ensure:

- [ ] Code follows the project's coding standards
- [ ] Tests added/updated for new functionality
- [ ] All tests pass (`pytest tests/`)
- [ ] Linting passes (`flake8 .`, `black --check .`)
- [ ] Documentation updated (README, code comments, etc.)
- [ ] No merge conflicts with main branch
- [ ] PR description clearly explains changes
- [ ] Linked to related issues (if any)

### Review Process

1. **Automated Checks**
   - CI pipeline runs automatically
   - All checks must pass before merge
   - Fix any failing checks

2. **Code Review**
   - At least 1 approval required
   - Address all review comments
   - Push fixes to the same branch
   - Request re-review after changes

3. **Merging**
   - Maintainers will merge after approval
   - Squash merge may be used for cleaner history
   - Your branch will be deleted after merge

## Coding Standards

### Python Style Guide

Follow [PEP 8](https://pep8.org/) with these specifics:

- **Line Length**: 120 characters maximum
- **Indentation**: 4 spaces (no tabs)
- **Quotes**: Prefer double quotes for strings
- **Imports**: Group by standard library, third-party, local
- **Naming**:
  - `snake_case` for functions, variables, modules
  - `PascalCase` for classes
  - `UPPER_CASE` for constants

### Code Formatting

Use [Black](https://black.readthedocs.io/) for automatic formatting:

```bash
# Format all Python files
black .

# Check without modifying
black --check .
```

### Linting

Use Flake8 for code quality:

```bash
# Run linter
flake8 .

# Common issues to avoid
# - Unused imports
# - Undefined variables
# - Line too long
# - Missing docstrings
```

### Type Hints

Use type hints for function signatures:

```python
def analyze_wallet(wallet_address: str, threshold: float = 0.65) -> dict:
    """Analyze wallet for insider behavior."""
    pass
```

### Documentation

- **Docstrings**: Use for all public functions and classes
- **Format**: Google-style docstrings
- **Comments**: Explain "why", not "what"

Example:
```python
def calculate_risk_score(signals: list[dict], weights: dict) -> float:
    """
    Calculate composite risk score from multiple signals.
    
    Args:
        signals: List of detected behavior signals with confidence scores
        weights: Weight mapping for each signal type
        
    Returns:
        Risk score between 0.0 and 1.0
        
    Raises:
        ValueError: If signals or weights are invalid
    """
    pass
```

## Testing Guidelines

### Writing Tests

- **Location**: Tests in `tests/` directory
- **Framework**: pytest
- **Coverage**: Aim for >80% code coverage
- **Structure**: Mirror source code structure

### Test Structure

```python
import pytest
from your_module import function_to_test

class TestYourFeature:
    """Test suite for your feature."""
    
    def test_normal_case(self):
        """Test normal operation."""
        result = function_to_test("input")
        assert result == "expected"
    
    def test_edge_case(self):
        """Test edge cases."""
        with pytest.raises(ValueError):
            function_to_test(None)
    
    @pytest.mark.asyncio
    async def test_async_function(self):
        """Test async operations."""
        result = await async_function()
        assert result is not None
```

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_wallet_analyzer.py

# Run with coverage
pytest --cov=agents tests/

# Run with verbose output
pytest -v

# Run only failed tests
pytest --lf
```

### Test Best Practices

- ✅ Test one thing per test function
- ✅ Use descriptive test names
- ✅ Include both positive and negative test cases
- ✅ Test edge cases and error conditions
- ✅ Use fixtures for common setup
- ✅ Mock external dependencies (RPC, Redis, etc.)
- ✅ Keep tests fast and independent

## Documentation

### When to Update Documentation

Update documentation when:
- Adding new features
- Changing existing functionality
- Fixing bugs that affect documented behavior
- Adding configuration options
- Changing APIs or interfaces

### Documentation Files

- **README.md**: Project overview, quick start
- **BRANCH_PROTECTION.md**: Branch protection guidelines
- **CONTRIBUTING.md**: This file, contribution guidelines
- **API documentation**: In code docstrings
- **Technical docs**: In `docs/` or `projects/godmodescanner/docs/`

### Documentation Style

- Clear and concise
- Include code examples
- Use proper markdown formatting
- Keep it up to date with code changes

## Questions and Support

### Getting Help

If you need help:
1. Check existing documentation
2. Search existing issues
3. Ask in discussions or community channels
4. Create a new issue with "question" label

### Reporting Issues

When reporting bugs or issues:
- Use issue templates (if available)
- Include clear reproduction steps
- Provide system information (OS, Python version, etc.)
- Include error messages and logs
- Describe expected vs actual behavior

### Feature Requests

When requesting features:
- Explain the use case
- Describe the proposed solution
- Consider alternative approaches
- Discuss potential impacts

## License

By contributing, you agree that your contributions will be licensed under the same license as the project (MIT License).

## Recognition

Contributors are recognized in:
- Git commit history
- Release notes
- Project documentation
- Community acknowledgments

Thank you for contributing to GODmodeScanner! 🚀

---

**Questions?** Open an issue or contact the maintainers.

**Last Updated**: 2026-02-02
