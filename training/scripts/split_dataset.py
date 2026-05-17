"""
Reproducible YOLO train/valid/test split for a single dataset root.

Moves image/label pairs together; preserves YOLO .txt labels.

Example (from repo root):
  python training/scripts/split_dataset.py --dataset dataset/cucumber
  python training/scripts/split_dataset.py --dataset dataset/cucumber --seed 42 --train 0.8 --valid 0.1 --test 0.1
"""

from __future__ import annotations

import argparse
import random
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
SPLITS = ("train", "valid", "test")


def _is_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXT


def collect_pairs(dataset_root: Path) -> list[tuple[Path, Path]]:
    """Collect (image, label) pairs from train/valid/test; verify 1:1 stems."""
    pairs: list[tuple[Path, Path]] = []
    issues: list[str] = []

    for split in SPLITS:
        img_dir = dataset_root / split / "images"
        lbl_dir = dataset_root / split / "labels"
        if not img_dir.is_dir():
            continue
        if not lbl_dir.is_dir():
            issues.append(f"Missing labels dir for split {split}: {lbl_dir}")
            continue

        images = {p.stem: p for p in img_dir.iterdir() if _is_image(p)}
        labels = {p.stem: p for p in lbl_dir.iterdir() if p.suffix.lower() == ".txt"}

        for stem, img_path in images.items():
            if stem not in labels:
                issues.append(f"Image without label: {img_path}")
                continue
            pairs.append((img_path, labels[stem]))

        for stem, lbl_path in labels.items():
            if stem not in images:
                issues.append(f"Label without image: {lbl_path}")

    if issues:
        print("Pair integrity errors:", file=sys.stderr)
        for msg in issues[:20]:
            print(f"  - {msg}", file=sys.stderr)
        if len(issues) > 20:
            print(f"  ... and {len(issues) - 20} more", file=sys.stderr)
        raise SystemExit(1)

    if not pairs:
        raise SystemExit(f"No image/label pairs found under {dataset_root}")

    return pairs


def assign_splits(
    n: int,
    *,
    train_ratio: float,
    valid_ratio: float,
    test_ratio: float,
    seed: int,
) -> dict[str, list[int]]:
    total = train_ratio + valid_ratio + test_ratio
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"Ratios must sum to 1.0, got {total}")

    indices = list(range(n))
    rng = random.Random(seed)
    rng.shuffle(indices)

    n_train = int(n * train_ratio)
    n_valid = int(n * valid_ratio)
    # Remainder goes to test so all samples are assigned
    n_test = n - n_train - n_valid

    return {
        "train": indices[:n_train],
        "valid": indices[n_train : n_train + n_valid],
        "test": indices[n_train + n_valid :],
    }


def move_pair(img: Path, lbl: Path, dataset_root: Path, split: str) -> None:
    dest_img_dir = dataset_root / split / "images"
    dest_lbl_dir = dataset_root / split / "labels"
    dest_img_dir.mkdir(parents=True, exist_ok=True)
    dest_lbl_dir.mkdir(parents=True, exist_ok=True)

    dest_img = dest_img_dir / img.name
    dest_lbl = dest_lbl_dir / lbl.name

    if img.resolve() != dest_img.resolve():
        if dest_img.exists():
            dest_img.unlink()
        shutil.move(str(img), str(dest_img))
    if lbl.resolve() != dest_lbl.resolve():
        if dest_lbl.exists():
            dest_lbl.unlink()
        shutil.move(str(lbl), str(dest_lbl))


def count_split(dataset_root: Path, split: str) -> tuple[int, int]:
    img_dir = dataset_root / split / "images"
    lbl_dir = dataset_root / split / "labels"
    n_img = sum(1 for p in img_dir.iterdir() if _is_image(p)) if img_dir.is_dir() else 0
    n_lbl = sum(1 for p in lbl_dir.iterdir() if p.suffix.lower() == ".txt") if lbl_dir.is_dir() else 0
    return n_img, n_lbl


def verify_counts(dataset_root: Path) -> None:
    print("\nFinal counts:")
    for split in SPLITS:
        n_img, n_lbl = count_split(dataset_root, split)
        status = "OK" if n_img == n_lbl else "MISMATCH"
        print(f"  {split:5s}  images={n_img:4d}  labels={n_lbl:4d}  [{status}]")


def write_data_yaml(dataset_root: Path) -> None:
    content = """train: train/images
val: valid/images
test: test/images

nc: 1
names: ['diseased']
"""
    path = dataset_root / "data.yaml"
    path.write_text(content, encoding="utf-8")
    print(f"\nWrote {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Split YOLO dataset into train/valid/test")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=REPO_ROOT / "dataset" / "cucumber",
        help="Dataset root (contains train/valid/test)",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--train", type=float, default=0.8, help="Train ratio")
    parser.add_argument("--valid", type=float, default=0.1, help="Valid ratio")
    parser.add_argument("--test", type=float, default=0.1, help="Test ratio")
    parser.add_argument("--no-write-yaml", action="store_true", help="Skip data.yaml rewrite")
    args = parser.parse_args()

    dataset_root = args.dataset.resolve()
    if not dataset_root.is_dir():
        raise SystemExit(f"Dataset root not found: {dataset_root}")

    pairs = collect_pairs(dataset_root)
    n = len(pairs)
    print(f"Collected {n} image/label pairs from {dataset_root}")
    print(f"Split ratios: train={args.train} valid={args.valid} test={args.test} seed={args.seed}")

    buckets = assign_splits(
        n,
        train_ratio=args.train,
        valid_ratio=args.valid,
        test_ratio=args.test,
        seed=args.seed,
    )

    for split, idxs in buckets.items():
        print(f"  -> {split}: {len(idxs)} pairs")

    # Move pairs to assigned splits (order does not matter)
    for split, idxs in buckets.items():
        for i in idxs:
            img, lbl = pairs[i]
            move_pair(img, lbl, dataset_root, split)

    if not args.no_write_yaml:
        write_data_yaml(dataset_root)

    verify_counts(dataset_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
