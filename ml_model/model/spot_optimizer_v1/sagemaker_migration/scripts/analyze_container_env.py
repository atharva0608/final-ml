#!/usr/bin/env python3
"""
SageMaker Environment Analysis Entrypoint

PURPOSE:
    Runs inside a SageMaker training job to print installed library versions.
    Used for debugging dependency conflicts and validating container state.

LAUNCHED BY:
    submit_env_check.py

DEPENDENCIES:
    None (uses only stdlib to inspect environment)

COST:
    <$0.01 (10 minute job on ml.m5.xlarge)
"""
import subprocess
import sys

import pkg_resources


def get_installed_packages():
    print("=" * 60)
    print(f"Python Version: {sys.version.split()[0]}")
    print("=" * 60)

    # Critical libraries to check explicitly
    critical_libs = [
        "scikit-learn",
        "pandas",
        "numpy",
        "scipy",
        "joblib",
        "lightgbm",
        "matplotlib",
        "seaborn",
        "boto3",
        "sagemaker",
    ]

    print("\nCritical Library Versions:")
    print("-" * 30)
    for lib in critical_libs:
        try:
            version = pkg_resources.get_distribution(lib).version
            print(f"{lib:<15} : {version}")
        except pkg_resources.DistributionNotFound:
            print(f"{lib:<15} : NOT INSTALLED")

    print("\nFull pip freeze output:")
    print("=" * 60)
    subprocess.call([sys.executable, "-m", "pip", "freeze"])
    print("=" * 60)


if __name__ == "__main__":
    get_installed_packages()
