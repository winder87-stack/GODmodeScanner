#!/usr/bin/env python3
"""GODMODESCANNER Deployment Script - One-Command Setup.

This script handles complete deployment of GODMODESCANNER including:
- Dependency installation
- Service health checks
- Database initialization
- Configuration validation
- System startup
"""

import asyncio
import subprocess
import sys
import time
from pathlib import Path


class Colors:
    """Terminal colors for output."""
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_header(text):
    """Print section header."""
    line = Colors.BOLD + Colors.BLUE + '=' * 80 + Colors.END
    print(f"\n{line}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text:^80}{Colors.END}")
    print(f"{line}\n")


def print_success(text):
    """Print success message."""
    print(f"{Colors.GREEN}✅ {text}{Colors.END}")


def print_warning(text):
    """Print warning message."""
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.END}")


def print_error(text):
    """Print error message."""
    print(f"{Colors.RED}❌ {text}{Colors.END}")


def run_command(cmd, check=True):
    """Run shell command and return output."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            check=check,
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        return False, e.stdout, e.stderr


def check_python_version():
    """Check Python version."""
    print_header("CHECKING PYTHON VERSION")
    version = sys.version_info
    print(f"Python Version: {version.major}.{version.minor}.{version.micro}")

    if version.major >= 3 and version.minor >= 8:
        print_success("Python version is compatible (>= 3.8)")
        return True
    else:
        print_error("Python 3.8+ required")
        return False


def install_dependencies():
    """Install Python dependencies."""
    print_header("INSTALLING DEPENDENCIES")

    print("Installing Python packages from requirements.txt...")
    success, stdout, stderr = run_command("pip install -r requirements.txt")

    if success:
        print_success("All dependencies installed successfully")
        return True
    else:
        print_error(f"Dependency installation failed: {stderr}")
        return False


def check_services():
    """Check if required services are running."""
    print_header("CHECKING REQUIRED SERVICES")

    services = {
        "Redis": "redis-cli ping",
        "Docker": "docker --version",
    }

    all_ok = True

    for service, cmd in services.items():
        success, stdout, stderr = run_command(cmd, check=False)

        if success:
            print_success(f"{service} is available")
        else:
            print_warning(f"{service} is not available (optional)")

    return True  # Services are optional


def setup_environment():
    """Setup environment file."""
    print_header("SETTING UP ENVIRONMENT")

    env_template = Path(".env.template")
    env_file = Path(".env")

    if not env_file.exists():
        if env_template.exists():
            import shutil
            shutil.copy(env_template, env_file)
            print_success("Created .env file from template")
        else:
            print_warning(".env.template not found, skipping environment setup")
    else:
        print_success(".env file already exists")

    return True


def validate_configuration():
    """Validate configuration files."""
    print_header("VALIDATING CONFIGURATION")

    config_files = [
        "config/agents.json",
        "config/orchestrator.json",
        "config/detection_rules.json",
    ]

    all_ok = True

    for config_file in config_files:
        path = Path(config_file)
        if path.exists():
            print_success(f"Found: {config_file}")
        else:
            print_error(f"Missing: {config_file}")
            all_ok = False

    return all_ok


def start_services():
    """Start Docker services if available."""
    print_header("STARTING SERVICES")

    if Path("docker-compose.yml").exists():
        print("Starting Docker services...")
        success, stdout, stderr = run_command("docker-compose up -d", check=False)

        if success:
            print_success("Docker services started")
            time.sleep(3)  # Wait for services to initialize
        else:
            print_warning("Docker services not started (optional)")
    else:
        print_warning("docker-compose.yml not found, skipping service startup")

    return True


def print_next_steps():
    """Print next steps for user."""
    print_header("DEPLOYMENT COMPLETE")

    print(Colors.GREEN + Colors.BOLD)
    print("╔═══════════════════════════════════════════════════════════════╗")
    print("║                                                                 ║")
    print("║            🔥 GODMODESCANNER IS READY TO LAUNCH! 🔥            ║")
    print("║                                                                 ║")
    print("╚═══════════════════════════════════════════════════════════════╝")
    print(Colors.END + "\n")

    print(Colors.BOLD + "Next Steps:" + Colors.END + "\n")
    print("1. Review configuration (optional):")
    print(f"   {Colors.BLUE}nano .env{Colors.END}\n")

    print("2. Start GODMODESCANNER:")
    print(f"   {Colors.BLUE}python example_detector.py{Colors.END}\n")

    print("3. Monitor logs:")
    print(f"   {Colors.BLUE}tail -f logs/detector.log{Colors.END}\n")

    print("4. Check health:")
    print(f"   {Colors.BLUE}python scripts/health_check.py{Colors.END}\n")

    print(Colors.BOLD + "Documentation:" + Colors.END)
    print(f"   {Colors.BLUE}README.md{Colors.END} - Complete usage guide")
    print(f"   {Colors.BLUE}docs/godmodescanner_system_prompt.md{Colors.END} - System behavior\n")


def main():
    """Main deployment routine."""
    print("\n" + Colors.BOLD + Colors.BLUE)
    print("╔═══════════════════════════════════════════════════════════════╗")
    print("║                                                                 ║")
    print("║          🔥 GODMODESCANNER DEPLOYMENT SCRIPT 🔥                ║")
    print("║                                                                 ║")
    print("║  Automated setup for the BEST pump.fun insider detector       ║")
    print("║                                                                 ║")
    print("╚═══════════════════════════════════════════════════════════════╝")
    print(Colors.END + "\n")

    steps = [
        ("Python Version Check", check_python_version),
        ("Dependency Installation", install_dependencies),
        ("Service Check", check_services),
        ("Environment Setup", setup_environment),
        ("Configuration Validation", validate_configuration),
        ("Service Startup", start_services),
    ]

    for step_name, step_func in steps:
        try:
            if not step_func():
                print_error(f"{step_name} failed")
                print("\nDeployment incomplete. Please fix errors and try again.\n")
                sys.exit(1)
        except Exception as e:
            print_error(f"{step_name} error: {str(e)}")
            sys.exit(1)

    print_next_steps()


if __name__ == "__main__":
    main()
