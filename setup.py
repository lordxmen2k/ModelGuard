"""Setup script for ModelGuard — configured for PyPI publishing."""

from setuptools import setup, find_packages
import os


def read_long_description():
    """Read the long description from README.md."""
    here = os.path.abspath(os.path.dirname(__file__))
    with open(os.path.join(here, "README.md"), encoding="utf-8") as f:
        return f.read()


setup(
    name="aimodelguard",
    version="0.2.0",
    author="Gerald Enrique Nelson Mc Kenzie",
    author_email="gerald@example.com",
    maintainer="Gerald Enrique Nelson Mc Kenzie",
    maintainer_email="gerald@example.com",
    description="A password-protected CLI for managing an allowlist of approved AI model signatures",
    long_description=read_long_description(),
    long_description_content_type="text/markdown",
    url="https://github.com/lordxmen2k/aimodelguard",
    project_urls={
        "Bug Tracker": "https://github.com/lordxmen2k/aimodelguard/issues",
        "Source": "https://github.com/lordxmen2k/aimodelguard",
        "Documentation": "https://github.com/lordxmen2k/aimodelguard#readme",
    },
    packages=find_packages(exclude=["tests", "tests.*"]),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Security",
        "Topic :: System :: Systems Administration",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Typing :: Typed",
    ],
    python_requires=">=3.11",
    install_requires=[
        "click>=8.0",
        "cryptography>=41.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-cov>=4.0",
            "build>=0.10",
            "twine>=4.0",
        ],
        "test": [
            "pytest>=7.0",
            "pytest-cov>=4.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "aimodelguard=aimodelguard.cli:cli",
        ],
    },
    include_package_data=True,
    package_data={
        "aimodelguard": ["py.typed"],
    },
    zip_safe=False,
    keywords="ai security model-governance model-registry llm access-control",
    license="Apache-2.0",
    platforms=["any"],
)
