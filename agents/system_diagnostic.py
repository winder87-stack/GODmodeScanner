#!/usr/bin/env python3
"""
System Diagnostic for GODMODESCANNER

Comprehensive diagnostic covering:
1. Subordinate agents and their status
2. Knowledge base structure and accessible files
3. Status of 6 specialized agents
4. Requirements to start running subordinate agents
"""

import os
import json
import sys
import importlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

# Add project to path
project_root = '/a0/usr/projects/godmodescanner'
sys.path.insert(0, project_root)

@dataclass
class AgentInfo:
    """Information about an agent"""
    name: str
    file_path: str
    type: str  # 'structured', 'standalone', 'utility'
    status: str  # 'ready', 'needs_config', 'missing_deps', 'not_implemented'
    description: str = ""
    dependencies: List[str] = field(default_factory=list)
    missing_deps: List[str] = field(default_factory=list)
    config_files: List[str] = field(default_factory=list)
    last_modified: str = ""

class SystemDiagnostic:
    """
    System Diagnostic for GODMODESCANNER
    
    Performs comprehensive analysis of:
    - All agents and their status
    - Knowledge base structure
    - Specialized agent readiness
    - Startup requirements
    """
    
    def __init__(self):
        self.project_root = Path(project_root)
        self.agents_dir = self.project_root / 'agents'
        self.config_dir = self.project_root / 'config'
        self.knowledge_dir = self.project_root / 'data' / 'knowledge'
        self.data_dir = self.project_root / 'data'
        
        self.all_agents: List[AgentInfo] = []
        self.specialized_agents: Dict[str, AgentInfo] = {}
        self.knowledge_files: List[Dict[str, Any]] = []
        self.config_files: List[Dict[str, Any]] = []
        
    def scan_agents(self) -> List[AgentInfo]:
        """Scan all agent files in the agents directory"""
        agents = []
        
        # Get all Python files in agents directory
        for py_file in self.agents_dir.rglob('*.py'):
            # Skip __init__.py files and test files
            if py_file.name == '__init__.py' or 'test' in py_file.name.lower():
                continue
            
            # Determine agent type
            relative_path = py_file.relative_to(self.agents_dir)
            parts = list(relative_path.parts[:-1])
            
            # Check if it's a structured agent (has agent.py and subdirectories)
            if 'agent.py' in py_file.name:
                agent_type = 'structured'
                agent_name = parts[0] if parts else py_file.stem
            elif any(x in py_file.name.lower() for x in ['monitor', 'analyzer', 'detector', 'manager', 'scoring']):
                agent_type = 'standalone'
                agent_name = py_file.stem
            elif py_file.name in ['orchestrator.py', 'planner.py', 'data_fetcher.py']:
                agent_type = 'utility'
                agent_name = py_file.stem
            else:
                agent_type = 'utility'
                agent_name = py_file.stem
            
            # Get file stats
            stat = py_file.stat()
            last_modified = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            
            # Determine status by checking if file is readable
            try:
                with open(py_file, 'r') as f:
                    content = f.read()
                status = 'ready'
                description = self._extract_description(content, agent_name)
                dependencies = self._extract_dependencies(content)
            except Exception as e:
                status = 'not_implemented'
                description = f"Error reading file: {e}"
                dependencies = []
            
            agents.append(AgentInfo(
                name=agent_name,
                file_path=str(py_file.relative_to(self.project_root)),
                type=agent_type,
                status=status,
                description=description,
                dependencies=dependencies,
                last_modified=last_modified
            ))
        
        self.all_agents = agents
        return agents
    
    def _extract_description(self, content: str, agent_name: str) -> str:
        """Extract description from agent file"""
        # Look for docstring or comments
        lines = content.split('\n')
        
        # Try to find docstring
        in_docstring = False
        docstring_lines = []
        for line in lines[:20]:  # Check first 20 lines
            if '"""' in line or "'''" in line:
                if in_docstring:
                    break
                in_docstring = True
                continue
            if in_docstring:
                if line.strip() and not line.strip().startswith('#'):
                    docstring_lines.append(line.strip())
                    if len(docstring_lines) > 3:
                        break
        
        if docstring_lines:
            return ' '.join(docstring_lines[:2])
        
        # Try to find class definition
        for line in lines:
            if 'class ' in line and 'Agent' in line:
                return line.strip()
        
        return f"{agent_name} agent"
    
    def _extract_dependencies(self, content: str) -> List[str]:
        """Extract Python dependencies from content"""
        dependencies = set()
        
        # Look for import statements
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('import '):
                parts = line[7:].split()
                for part in parts:
                    if not part.startswith('.') and part[0].isupper():
                        dependencies.add(part.split('.')[0])
            elif line.startswith('from '):
                parts = line[5:].split()
                for part in parts:
                    if not part.startswith('.') and part[0].isupper():
                        dependencies.add(part.split('.')[0])
        
        return sorted(list(dependencies))
    
    def identify_specialized_agents(self) -> Dict[str, AgentInfo]:
        """Identify the 6 specialized agents"""
        specialized_names = [
            'transaction_monitor',
            'wallet_analyzer',
            'pattern_recognition',
            'sybil_detection',
            'risk_scoring',
            'alert_manager'
        ]
        
        found = {}
        for agent in self.all_agents:
            for spec_name in specialized_names:
                if spec_name in agent.name.lower():
                    found[spec_name] = agent
                    break
        
        self.specialized_agents = found
        return found
    
    def scan_knowledge_base(self) -> List[Dict[str, Any]]:
        """Scan knowledge base directory"""
        knowledge_files = []
        
        if self.knowledge_dir.exists():
            for file_path in self.knowledge_dir.rglob('*'):
                if file_path.is_file():
                    stat = file_path.stat()
                    knowledge_files.append({
                        'name': file_path.name,
                        'path': str(file_path.relative_to(self.project_root)),
                        'size_bytes': stat.st_size,
                        'size_human': self._human_size(stat.st_size),
                        'last_modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                        'type': file_path.suffix[1:] if file_path.suffix else 'unknown'
                    })
        
        self.knowledge_files = knowledge_files
        return knowledge_files
    
    def scan_config_files(self) -> List[Dict[str, Any]]:
        """Scan configuration files"""
        config_files = []
        
        if self.config_dir.exists():
            for file_path in self.config_dir.glob('*.json'):
                stat = file_path.stat()
                config_files.append({
                    'name': file_path.name,
                    'path': str(file_path.relative_to(self.project_root)),
                    'size_bytes': stat.st_size,
                    'size_human': self._human_size(stat.st_size),
                    'last_modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                })
        
        self.config_files = config_files
        return config_files
    
    def _human_size(self, bytes_size: int) -> str:
        """Convert bytes to human readable size"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.2f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.2f} TB"
    
    def check_agent_readiness(self, agent: AgentInfo) -> Tuple[str, List[str]]:
        """Check if agent is ready to run"""
        missing = []
        status = 'ready'
        
        # Check for configuration file
        config_file = self.config_dir / f"{agent.name}_config.json"
        if not config_file.exists():
            status = 'needs_config'
            missing.append(f"Configuration file: {config_file.name}")
        
        # Check for required data directories
        data_subdirs = [
            self.data_dir / 'graph_data',
            self.data_dir / 'memory',
            self.data_dir / 'models'
        ]
        for data_dir in data_subdirs:
            if not data_dir.exists():
                status = 'needs_config'
                missing.append(f"Data directory: {data_dir.relative_to(self.project_root)}")
        
        # Check dependencies
        for dep in agent.dependencies:
            try:
                importlib.import_module(dep)
            except ImportError:
                status = 'missing_deps'
                missing.append(f"Python package: {dep}")
        
        return status, missing
    
    def check_dependencies(self) -> Dict[str, Any]:
        """Check all system dependencies"""
        deps_status = {
            'python_packages': {},
            'external_services': {},
            'data_directories': {},
            'config_files': {}
        }
        
        # Check Python packages from requirements.txt
        req_file = self.project_root / 'requirements.txt'
        if req_file.exists():
            with open(req_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        pkg_name = line.split('==')[0].split('>=')[0].split('<=')[0].strip()
                        try:
                            importlib.import_module(pkg_name.replace('-', '_'))
                            deps_status['python_packages'][pkg_name] = 'installed'
                        except ImportError:
                            deps_status['python_packages'][pkg_name] = 'missing'
        
        # Check external services (Redis, TimescaleDB)
        services = {
            'redis': 'redis.Redis',
            'timescaledb': 'psycopg2'
        }
        for service, module_path in services.items():
            try:
                importlib.import_module(module_path)
                deps_status['external_services'][service] = 'available'
            except ImportError:
                deps_status['external_services'][service] = 'not_available'
        
        # Check data directories
        data_subdirs = [
            'graph_data',
            'memory',
            'models',
            'knowledge'
        ]
        for subdir in data_subdirs:
            dir_path = self.data_dir / subdir
            if dir_path.exists():
                deps_status['data_directories'][subdir] = 'exists'
            else:
                deps_status['data_directories'][subdir] = 'missing'
        
        # Check config files
        config_files = [
            'agents.json',
            'detection_rules.json',
            'orchestrator.json'
        ]
        for config_file in config_files:
            config_path = self.config_dir / config_file
            if config_path.exists():
                deps_status['config_files'][config_file] = 'exists'
            else:
                deps_status['config_files'][config_file] = 'missing'
        
        return deps_status
    
    def generate_startup_requirements(self) -> Dict[str, Any]:
        """Generate list of requirements to start running"""
        deps_status = self.check_dependencies()
        
        missing_packages = [pkg for pkg, status in deps_status['python_packages'].items() if status == 'missing']
        missing_dirs = [dir for dir, status in deps_status['data_directories'].items() if status == 'missing']
        missing_configs = [cfg for cfg, status in deps_status['config_files'].items() if status == 'missing']
        
        return {
            'install_packages': missing_packages,
            'create_directories': missing_dirs,
            'configure_files': missing_configs,
            'setup_commands': self._generate_setup_commands(missing_packages, missing_dirs),
            'startup_sequence': self._generate_startup_sequence()
        }
    
    def _generate_setup_commands(self, packages: List[str], dirs: List[str]) -> List[str]:
        """Generate setup commands"""
        commands = []
        
        if packages:
            commands.append(f"pip install {' '.join(packages)}")
        
        for dir in dirs:
            commands.append(f"mkdir -p data/{dir}")
        
        return commands
    
    def _generate_startup_sequence(self) -> List[Dict[str, str]]:
        """Generate recommended startup sequence"""
        return [
            {
                'step': 1,
                'name': 'Start Redis Server',
                'command': 'redis-server --daemonize yes',
                'description': 'Start Redis for pub/sub messaging and caching'
            },
            {
                'step': 2,
                'name': 'Start TimescaleDB',
                'command': 'docker-compose up -d timescaledb',
                'description': 'Start TimescaleDB for time-series data storage'
            },
            {
                'step': 3,
                'name': 'Initialize Database Schema',
                'command': 'python scripts/init_timescaledb.py',
                'description': 'Create database tables and indexes'
            },
            {
                'step': 4,
                'name': 'Start Transaction Monitor',
                'command': 'python agents/transaction_monitor.py',
                'description': 'Begin monitoring pump.fun transactions'
            },
            {
                'step': 5,
                'name': 'Start Orchestrator',
                'command': 'python agents/orchestrator.py',
                'description': 'Coordinate all agents and manage workflow'
            },
            {
                'step': 6,
                'name': 'Start Alert Manager',
                'command': 'python agents/alert_manager_agent.py',
                'description': 'Handle alert generation and delivery'
            }
        ]
    
    def generate_diagnostic_report(self) -> Dict[str, Any]:
        """Generate complete diagnostic report"""
        print("="*70)
        print("GODMODESCANNER - SYSTEM DIAGNOSTIC REPORT")
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*70)
        print()
        
        # Scan everything
        self.scan_agents()
        self.identify_specialized_agents()
        self.scan_knowledge_base()
        self.scan_config_files()
        deps_status = self.check_dependencies()
        startup_reqs = self.generate_startup_requirements()
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'summary': {},
            'all_agents': [],
            'specialized_agents': {},
            'knowledge_base': self.knowledge_files,
            'configuration': self.config_files,
            'dependencies': deps_status,
            'startup_requirements': startup_reqs
        }
        
        # Summary
        print("📊 SUMMARY")
        print("-"*70)
        print(f"Total Agents Found: {len(self.all_agents)}")
        print(f"Specialized Agents Found: {len(self.specialized_agents)}/6")
        print(f"Knowledge Files: {len(self.knowledge_files)}")
        print(f"Config Files: {len(self.config_files)}")
        print(f"Missing Dependencies: {len([p for p, s in deps_status['python_packages'].items() if s == 'missing'])}")
        print(f"Missing Directories: {len([d for d, s in deps_status['data_directories'].items() if s == 'missing'])}")
        print()
        
        # All agents
        print("🤖 ALL AGENTS")
        print("-"*70)
        for agent in sorted(self.all_agents, key=lambda x: x.name):
            status_icon = "✅" if agent.status == 'ready' else "⚠️"
            print(f"{status_icon} {agent.name:30s} | {agent.type:12s} | {agent.status:18s}")
            if agent.description:
                print(f"   └─ {agent.description}")
        print()
        
        # Specialized agents
        print("🎯 SPECIALIZED AGENTS (6 Required)")
        print("-"*70)
        specialized_names = [
            'transaction_monitor',
            'wallet_analyzer',
            'pattern_recognition',
            'sybil_detection',
            'risk_scoring',
            'alert_manager'
        ]
        
        for name in specialized_names:
            if name in self.specialized_agents:
                agent = self.specialized_agents[name]
                status, missing = self.check_agent_readiness(agent)
                status_icon = "✅" if status == 'ready' else "⚠️"
                print(f"{status_icon} {agent.name:30s} | {status:18s}")
                if missing:
                    print(f"   └─ Missing: {', '.join(missing)}")
                report['specialized_agents'][name] = {
                    'status': status,
                    'file_path': agent.file_path,
                    'missing': missing
                }
            else:
                print(f"❌ {name:30s} | NOT FOUND")
                report['specialized_agents'][name] = {
                    'status': 'not_found',
                    'file_path': None,
                    'missing': ['Agent file not found']
                }
        print()
        
        # Knowledge base
        print("📚 KNOWLEDGE BASE")
        print("-"*70)
        if self.knowledge_files:
            for kb in self.knowledge_files:
                print(f"  📄 {kb['name']:40s} | {kb['type']:8s} | {kb['size_human']:10s} | {kb['last_modified']}")
        else:
            print("  ⚠️ No knowledge files found")
        print()
        
        # Configuration files
        print("⚙️  CONFIGURATION FILES")
        print("-"*70)
        if self.config_files:
            for cfg in self.config_files:
                print(f"  📄 {cfg['name']:40s} | {cfg['size_human']:10s} | {cfg['last_modified']}")
        else:
            print("  ⚠️ No configuration files found")
        print()
        
        # Dependencies
        print("📦 DEPENDENCIES")
        print("-"*70)
        print("Python Packages:")
        for pkg, status in sorted(deps_status['python_packages'].items()):
            icon = "✅" if status == 'installed' else "❌"
            print(f"  {icon} {pkg}")
        print()
        print("External Services:")
        for svc, status in deps_status['external_services'].items():
            icon = "✅" if status == 'available' else "❌"
            print(f"  {icon} {svc}")
        print()
        print("Data Directories:")
        for dir, status in deps_status['data_directories'].items():
            icon = "✅" if status == 'exists' else "❌"
            print(f"  {icon} data/{dir}")
        print()
        
        # Startup requirements
        print("🚀 STARTUP REQUIREMENTS")
        print("-"*70)
        if startup_reqs['install_packages']:
            print("Install missing packages:")
            for cmd in startup_reqs['setup_commands']:
                if 'pip install' in cmd:
                    print(f"  $ {cmd}")
            print()
        
        if startup_reqs['create_directories']:
            print("Create missing directories:")
            for cmd in startup_reqs['setup_commands']:
                if 'mkdir' in cmd:
                    print(f"  $ {cmd}")
            print()
        
        print("Recommended startup sequence:")
        for step in startup_reqs['startup_sequence']:
            print(f"  {step['step']}. {step['name']}")
            print(f"     $ {step['command']}")
            print(f"     → {step['description']}")
        print()
        
        # Add to report
        report['all_agents'] = [
            {
                'name': a.name,
                'type': a.type,
                'status': a.status,
                'file_path': a.file_path,
                'dependencies': a.dependencies,
                'last_modified': a.last_modified
            }
            for a in self.all_agents
        ]
        
        return report

def main():
    """Main entry point"""
    print("Starting System Diagnostic...")
    print()
    
    diagnostic = SystemDiagnostic()
    
    try:
        report = diagnostic.generate_diagnostic_report()
        
        print("="*70)
        print("✅ System diagnostic complete")
        print("="*70)
        
        # Save report
        report_file = '/a0/usr/projects/godmodescanner/SYSTEM_DIAGNOSTIC_REPORT.json'
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\n📄 Report saved to: {report_file}")
        
        return report
        
    except Exception as e:
        print(f"\n❌ Diagnostic failed: {e}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    main()
