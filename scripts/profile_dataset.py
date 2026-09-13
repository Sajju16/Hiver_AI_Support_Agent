"""
profile_dataset.py — Comprehensive Dataset Profiling Entrypoint.

Runs all Phase 1 dataset analysis modules:
  1. Dataset inspection & schema verification (src/data/inspect_dataset.py)
  2. Noise & data quality analysis (scripts/noise_analysis.py)
  3. Per-brand conversation analysis (scripts/brand_analysis.py)
  4. Conversation reconstruction demo & example extraction (scripts/extract_examples.py)

Usage:
    python scripts/profile_dataset.py
"""

import sys, json, time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.inspect_dataset import inspect_dataset
from scripts.noise_analysis import analyze_noise
from scripts.brand_analysis import analyze_brands
from scripts.extract_examples import extract_examples


def profile_all():
    print("=" * 80)
    print(" H I V E R   S D E   I N T E R N — PHASE 1 DATASET PROFILING")
    print("=" * 80)

    t0 = time.time()

    print("\n--- 1. Inspecting Dataset & Verifying Schema ---")
    inspection = inspect_dataset()

    print("\n--- 2. Noise & Data Quality Analysis ---")
    noise = analyze_noise()

    print("\n--- 3. Per-Brand Breakdown ---")
    brands = analyze_brands()

    print("\n--- 4. Conversation Reconstruction Demo ---")
    extract_examples()

    elapsed = time.time() - t0

    top_brand = max(brands.items(), key=lambda item: item[1].get("usable_conversations", 0))

    print("\n" + "=" * 80)
    print(f" PROFILING COMPLETE IN {elapsed:.2f} SECONDS")
    print("=" * 80)
    print(f"  • Total Rows Processed: {inspection['total_rows']:,}")
    print(f"  • Verified Schema: {len(inspection['columns'])} columns")
    print(f"  • Total Brand Handles Identified: {inspection['authors']['unique_brand_handles']}")
    print(f"  • Top Brand by Usable Convos: {top_brand[0]} ({top_brand[1]['usable_conversations']:,} convos)")
    print(f"  • Profile outputs saved to: data/processed/")


if __name__ == "__main__":
    profile_all()
