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
        "httpx>=0.24.0",
    ],
    extras_require={
        "dev": [
            "pytest",
            "pytest-asyncio",
            "watchdog",  # For hot reloading in dev mode
        ],
        "http": [
            "aiohttp",
        ],
        "observability": [
            "structlog",
            "opentelemetry-api",
            "opentelemetry-sdk",
        ],
        "all": [
            "structlog",
            "opentelemetry-api",
            "opentelemetry-sdk",
            "watchdog",
        ],
    },
    entry_points={
        "console_scripts": [
            "flowforge=flowforge.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
    ],
)
