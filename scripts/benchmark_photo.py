import io
import sys
import time
import statistics
from pathlib import Path
from PIL import Image, ImageOps

MAX_DIMENSION = 1280
JPEG_QUALITY = 85
RUNS = 5


def compress_image(contents: bytes) -> tuple[bytes, str]:
    img = Image.open(io.BytesIO(contents))
    img = ImageOps.exif_transpose(img)

    w, h = img.size
    if max(w, h) > MAX_DIMENSION:
        ratio = MAX_DIMENSION / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

    has_alpha = img.mode in ("RGBA", "LA") or (
        img.mode == "P" and "transparency" in img.info
    )

    out = io.BytesIO()
    if has_alpha:
        img.save(out, format="PNG", optimize=True)
        return out.getvalue(), ".png"
    else:
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        return out.getvalue(), ".jpeg"


def make_synthetic_image(width: int, height: int, mode: str = "RGB") -> bytes:
    """테스트용 합성 이미지 생성 (실제 사진보다 압축률이 낮게 측정됨)"""
    import random
    img = Image.new(mode, (width, height))
    if mode == "RGB":
        img.putdata([
            (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
            for _ in range(width * height)
        ])
    buf = io.BytesIO()
    fmt = "PNG" if mode == "RGBA" else "JPEG"
    img.save(buf, format=fmt, quality=95)
    return buf.getvalue()


def benchmark(name: str, contents: bytes) -> dict:
    times = []
    compressed = None
    for _ in range(RUNS):
        t0 = time.perf_counter()
        compressed, _ = compress_image(contents)
        times.append(time.perf_counter() - t0)

    orig_size = len(contents)
    comp_size = len(compressed)
    return {
        "name": name,
        "original_kb": orig_size / 1024,
        "compressed_kb": comp_size / 1024,
        "reduction_pct": (1 - comp_size / orig_size) * 100,
        "avg_ms": statistics.mean(times) * 1000,
        "min_ms": min(times) * 1000,
        "max_ms": max(times) * 1000,
    }


def print_results(results: list[dict], note: str = ""):
    if note:
        print(f"\n[{note}]")
    print(f"\n{'파일':<30} {'원본':>9} {'압축후':>9} {'절감':>7} {'평균':>9} {'최소':>9} {'최대':>9}")
    print("-" * 88)
    for r in results:
        print(
            f"{r['name']:<30} "
            f"{r['original_kb']:>7.1f}KB "
            f"{r['compressed_kb']:>7.1f}KB "
            f"{r['reduction_pct']:>6.1f}% "
            f"{r['avg_ms']:>7.1f}ms "
            f"{r['min_ms']:>7.1f}ms "
            f"{r['max_ms']:>7.1f}ms"
        )

    total_orig = sum(r["original_kb"] for r in results)
    total_comp = sum(r["compressed_kb"] for r in results)
    overall_pct = (1 - total_comp / total_orig) * 100 if total_orig > 0 else 0
    print("-" * 88)
    print(f"{'합계':<30} {total_orig:>7.1f}KB {total_comp:>7.1f}KB {overall_pct:>6.1f}%")


def run_synthetic():
    print("합성 이미지 벤치마크 (랜덤 픽셀 — 실제 사진보다 압축률 낮게 측정됨)")
    cases = [
        ("소형 JPEG (800x600)", make_synthetic_image(800, 600)),
        ("중형 JPEG (1920x1080, FHD)", make_synthetic_image(1920, 1080)),
        ("대형 JPEG (3024x4032, 12MP)", make_synthetic_image(3024, 4032)),
        ("대형 JPEG (4032x3024, 가로)", make_synthetic_image(4032, 3024)),
        ("소형 PNG 투명 (1000x1000)", make_synthetic_image(1000, 1000, "RGBA")),
    ]
    results = [benchmark(name, data) for name, data in cases]
    print_results(results, note="합성 이미지 결과")
    print(
        "\n* 실제 스마트폰 사진은 자연 장면을 담고 있어 압축률이 더 높게 측정됩니다.\n"
        "  실제 파일로 측정하려면: python benchmark_photo.py 파일1.jpg 파일2.jpg"
    )


def run_with_files(paths: list[str]):
    results = []
    for p in paths:
        path = Path(p)
        if not path.exists():
            print(f"파일 없음: {p}")
            continue
        contents = path.read_bytes()
        results.append(benchmark(path.name, contents))
    if results:
        print_results(results, note="실제 파일 결과")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_with_files(sys.argv[1:])
    else:
        run_synthetic()
