"""Setup configuration for LXC Autoscaler."""

from pathlib import Path
from setuptools import find_packages, setup

# Read the README file
readme_path = Path(__file__).parent / "README.md"
long_description = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""

# Read requirements
requirements_path = Path(__file__).parent / "requirements.txt"
if requirements_path.exists():
    with open(requirements_path, encoding="utf-8") as f:
        requirements = [
            line.strip() 
            for line in f 
            if line.strip() and not line.startswith("#")
        ]
    
    # Filter out development dependencies
    install_requires = []
    extras_require = {
        "dev": [],
        "test": [],
        "docs": []
    }
    
    for req in requirements:
        if any(dev_keyword in req.lower() for dev_keyword in ["mypy", "types-", "pytest", "ruff", "black"]):
            if "mypy" in req or "types-" in req:
                extras_require["dev"].append(req)
            elif "pytest" in req:
                extras_require["test"].append(req)
            elif "ruff" in req or "black" in req:
                extras_require["dev"].append(req)
        elif "sphinx" in req.lower():
            extras_require["docs"].append(req)
        else:
            install_requires.append(req)
else:
    install_requires = [
        "proxmoxer>=2.0.1",
        "aiohttp>=3.8.0", 
        "PyYAML>=6.0",
        "aiofiles>=23.0.0",
    ]
    extras_require = {}

setup(
    name="lxc-autoscaler",
    version="1.0.0",
    description="Production-ready LXC container autoscaler for Proxmox VE",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="LXC Autoscaler Team",
    author_email="support@example.com",
    url="https://github.com/example/lxc-autoscaler",
    project_urls={
        "Bug Tracker": "https://github.com/example/lxc-autoscaler/issues",
        "Documentation": "https://lxc-autoscaler.readthedocs.io/",
        "Source Code": "https://github.com/example/lxc-autoscaler",
    },
    packages=find_packages(),
    include_package_data=True,
    install_requires=install_requires,
    extras_require=extras_require,
    python_requires=">=3.8",
    entry_points={
        "console_scripts": [
            "lxc-autoscaler=lxc_autoscaler.core.daemon:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9", 
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: System :: Systems Administration",
        "Topic :: System :: Monitoring",
        "Environment :: No Input/Output (Daemon)",
    ],
    keywords="proxmox lxc autoscaler containers virtualization monitoring",
    package_data={
        "lxc_autoscaler": [
            "*.yaml",
            "*.yml", 
            "*.conf",
            "config/*.yaml",
            "config/*.yml",
        ],
    },
    data_files=[
        ("etc/systemd/system", [
            "systemd/lxc-autoscaler.service",
            "systemd/lxc-autoscaler-healthcheck.service", 
            "systemd/lxc-autoscaler.timer"
        ]),
        ("etc/tmpfiles.d", [
            "systemd/tmpfiles.d/lxc-autoscaler.conf"
        ]),
        ("share/doc/lxc-autoscaler", [
            "examples/config.yaml",
        ]),
    ],
    zip_safe=False,
)