"""FlowForge Package Setup"""

from setuptools import find_packages, setup

setup(
    name="flowforge",
    version="0.1.0",
    description="A DAG-based Chain Orchestration Framework",
    author="FlowForge Team",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        # Core dependencies only - minimal footprint
    ],
    extras_require={
        "dev": [
            "pytest",
            "pytest-asyncio",
        ],
        "http": [
            "aiohttp",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)
