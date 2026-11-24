"""图片 OCR：把页面配图里的「A賞 xxx 共 2 个」读成文本，交给验收层核对。

公众号赏品图鉴、小红书九宫格只把逐赏表印在图片里，纯文本校验必然 name_unverified / quote_mismatch。
这里只负责「把图读成字」——判断口径仍在 accept.py（原文命中 + 数字一致 + Σ 平衡），一点不放松。

本机能力：`scripts/ocrbin`（macOS Vision，随工作流分发）+ `sips` 放大；取图走 ego-browser 渲染，
因为公众号图片是懒加载，urllib 拿到的 src 是占位图。
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import urllib.request
from pathlib import Path

from . import browser
from .common import _opener

OCR_BIN = Path(__file__).resolve().parents[1] / "ocrbin"
# 一个页面最多 OCR 几张图：公众号图鉴常按赏别拆成 8–12 张；11 张的盘取前 10 张会漏掉最后一赏
MAX_IMAGES = 12

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)


def available() -> bool:
    """OCR 能不能用：ocrbin 在、可执行，而且有 sips（放大后再识别，小字才认得出来）。"""
    return OCR_BIN.exists() and os.access(OCR_BIN, os.X_OK) and bool(shutil.which("sips"))


def page_ocr(url: str, workdir: Path, timeout: int = 120) -> str:
    """一个页面所有配图的 OCR 文本。失败返回空串，不抛异常（没有 OCR 就当没有）。"""
    if not available() or not str(url or "").startswith("http"):
        return ""
    workdir.mkdir(parents=True, exist_ok=True)
    ok, images, _error = browser.page_images(url, workdir, timeout=timeout)
    if not ok or not images:
        return ""
    texts: list[str] = []
    for index, image_url in enumerate(images[:MAX_IMAGES], 1):
        text = _ocr_one(image_url, workdir, index=index, timeout=timeout)
        if text:
            texts.append(text)
    return "\n".join(texts)


def _ocr_one(image_url: str, workdir: Path, index: int = 1, timeout: int = 90, referer: str = "") -> str:
    workdir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(image_url.encode("utf-8")).hexdigest()[:10]
    raw = workdir / f"img-{index:02d}-{digest}"
    png = workdir / f"img-{index:02d}-{digest}.png"
    if not raw.exists():
        try:
            raw.write_bytes(_download(image_url, referer=referer))
        except Exception:  # noqa: BLE001 - 单张图下载失败不影响其它图
            return ""
    if not png.exists():
        try:
            subprocess.run(
                ["sips", "-s", "format", "png", str(raw), "--out", str(png), "-Z", "3240"],
                capture_output=True,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    if not png.exists() or png.stat().st_size == 0:
        # 小红书封面是 webp，sips 有时认不出（.bin 落盘、无扩展名会直接报 invalid）；
        # 有 Pillow 就用它转一道，仍然失败才放弃
        if not _png_via_pillow(raw, png):
            return ""
    try:
        result = subprocess.run(
            [str(OCR_BIN), str(png)], capture_output=True, text=True, timeout=timeout
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (result.stdout or "").strip()


def _png_via_pillow(raw: Path, png: Path) -> bool:
    try:
        from PIL import Image  # type: ignore
    except Exception:  # noqa: BLE001 - 没装 Pillow 就走 sips 的结果
        return False
    try:
        with Image.open(raw) as image:
            image = image.convert("RGB")
            image.thumbnail((3240, 3240))
            image.save(png, "PNG")
        return png.exists() and png.stat().st_size > 0
    except Exception:  # noqa: BLE001 - 解码失败按没有图处理
        return False


def _download(url: str, referer: str = "") -> bytes:
    # 小红书图床只认自己的 referer，公众号图只认 mp.weixin.qq.com；传错一律 403
    request = urllib.request.Request(
        url,
        headers={"user-agent": _UA, "referer": referer or "https://mp.weixin.qq.com/", "accept": "image/*"},
    )
    with _opener().open(request, timeout=30) as response:
        return response.read(8_000_000)
