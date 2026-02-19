"""Runtime dependency checks for each pipeline invocation."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import PipelineConfig


def ensure_runtime_requirements(config: "PipelineConfig") -> None:
    """Fail fast with a clear install guide when required modules are missing."""
    del config  # requirements are global for every CLI run
    missing = _missing_requirements()
    if not missing:
        return

    _print_missing_requirements(missing)
    if _should_prompt_install():
        if _prompt_install(missing):
            _install_requirements(missing)
            missing = _missing_requirements()
            if not missing:
                return
            print("\nSome dependencies are still missing after installation:")
            _print_missing_requirements(missing)
        else:
            raise RuntimeError("Installation cancelled by user.")

    raise RuntimeError(
        "Install all required dependencies with:\n"
        "  pip install -r requirements.txt"
    )


def _mandatory_requirements() -> tuple[tuple[str, str, int], ...]:
    return (
        ("yt_dlp", "yt-dlp>=2024.1.0", 5),
        ("openai", "openai>=1.0.0", 10),
        ("gtts", "gtts>=2.5.0", 1),
        ("moviepy", "moviepy>=1.0.3,<2.0.0", 30),
        ("PIL", "Pillow>=10.0.0", 15),
        ("matplotlib", "matplotlib>=3.7.0", 60),
        ("requests", "requests>=2.28.0", 3),
        ("longport", "longport>=1.0.0", 5),
        ("yfinance", "yfinance>=0.2.0", 5),
        ("numpy", "numpy>=1.24.0", 70),
        ("gradio", "gradio>=4.0.0", 120),
    )


def _is_installed(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _missing_requirements() -> list[tuple[str, str, int]]:
    missing: list[tuple[str, str, int]] = []
    for module_name, package_spec, size_mb in _mandatory_requirements():
        if not _is_installed(module_name):
            missing.append((module_name, package_spec, size_mb))
    return missing


def _print_missing_requirements(missing: list[tuple[str, str, int]]) -> None:
    print("\nMissing Python dependencies:")
    total_size = 0
    for _module_name, package_spec, size_mb in missing:
        total_size += size_mb
        print(f"  - {package_spec} (~{size_mb} MB)")
    print(f"Estimated total download: ~{total_size} MB")


def _should_prompt_install() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _prompt_install(missing: list[tuple[str, str, int]]) -> bool:
    del missing
    answer = input("Install missing libraries now? [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def _install_requirements(missing: list[tuple[str, str, int]]) -> None:
    specs = [package_spec for _module_name, package_spec, _size_mb in missing]
    print("\nInstalling missing libraries...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", *specs])
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Dependency installation failed (exit {exc.returncode}).") from exc
