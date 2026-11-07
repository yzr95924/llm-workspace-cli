#!/usr/bin/env python3
"""pdf_import — PDF → Markdown 的 raw/ 受控写路径（`llmw wiki import-pdf`）。

产物契约：`raw/articles/<slug>.md` 带 provenance frontmatter 的纯文本 Markdown；
图片只留占位符，原 PDF 不入 wiki。转换器是外部 `docling` 命令（uv tool 独立安装），
未安装时报环境错误；转换失败不落半成品。
退出码：0 = 成功；1 = 用户输入错误；2 = 下载 / 转换 / 写入失败。
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from urllib.parse import unquote, urlsplit

from llmw.errors import PdfDependencyMissing, PdfImportFailed
from llmw.fsutil import atomic_write, sha256_file

CONVERTER_NAME = "docling"
DOCLING_INSTALL_HINT = "uv tool install --python 3.12 docling"
PDF_MAGIC = b"%PDF-"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
VERSION_RE = re.compile(r"\d+\.\d+\.\d+(?:\.\d+)?")


def _is_url(source: str) -> bool:
    return urlsplit(source).scheme in {"http", "https"}


def _default_slug(source: str) -> str:
    path = urlsplit(source).path if _is_url(source) else source
    stem = Path(unquote(path)).stem
    return re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")


def _download_pdf(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "llmw"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response, destination.open("wb") as fp:
            shutil.copyfileobj(response, fp)
    except (urllib.error.URLError, OSError) as e:
        raise PdfImportFailed(
            f"PDF 下载失败: {url} ({e})",
            hint="检查 URL 与网络；也可先手动下载，再用本地路径导入",
        ) from e


def _validate_pdf(path: Path) -> None:
    try:
        with path.open("rb") as fp:
            header = fp.read(5)
    except OSError as e:
        raise PdfImportFailed(f"PDF 读取失败: {path} ({e})") from e
    if header != PDF_MAGIC:
        raise PdfImportFailed(
            f"文件不是 PDF（magic header 缺失）: {path}",
            hint="Docling 只接收 PDF；其他格式先转换或另行处理",
        )


def _docling_version() -> str:
    try:
        proc = subprocess.run(
            [CONVERTER_NAME, "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
    except FileNotFoundError as e:
        raise PdfDependencyMissing(
            "PDF 导入需要外部 docling 命令（不在 PATH）",
            hint=f"一次性安装: {DOCLING_INSTALL_HINT}",
        ) from e
    if proc.returncode != 0:
        raise PdfImportFailed(
            f"docling --version 失败（exit {proc.returncode}）",
            hint=f"检查安装: {DOCLING_INSTALL_HINT}",
        )
    match = VERSION_RE.search(proc.stdout + proc.stderr)
    if match is None:
        raise PdfImportFailed("无法从 docling --version 输出解析版本号")
    return match.group(0)


def _convert_pdf(pdf_path: Path, markdown_path: Path) -> str:
    command = [
        CONVERTER_NAME,
        "convert",
        str(pdf_path),
        "--from=pdf",
        "--to=md",
        "--image-export-mode=placeholder",
        "--fail-on=partial",
        f"--output-file={markdown_path}",
    ]
    proc = subprocess.run(command, stdout=sys.stderr, stderr=sys.stderr)
    if proc.returncode != 0:
        raise PdfImportFailed(
            f"Docling 转换失败（exit {proc.returncode}）",
            hint="检查 PDF 是否损坏 / 扫描件是否需要更强 OCR；完整日志见上方 docling 输出",
        )
    try:
        body = markdown_path.read_text(encoding="utf-8")
    except OSError as e:
        raise PdfImportFailed(f"Docling 未产出 Markdown: {markdown_path} ({e})") from e
    if not body.strip():
        raise PdfImportFailed(
            f"Docling 输出为空: {markdown_path}",
            hint="空正文不落 raw；检查 PDF 是否无文本层且 OCR 失败",
        )
    return body


def _render_markdown(
    body: str,
    *,
    source: str,
    is_url: bool,
    imported_at: str,
    original_sha256: str,
) -> str:
    source_key = "source_url" if is_url else "source_path"
    lines = [
        "---",
        "original_format: pdf",
        f"{source_key}: {json.dumps(source, ensure_ascii=False)}",
        f"imported_at: {imported_at}",
        f"original_sha256: {original_sha256}",
        "---",
    ]
    content = "\n".join(lines) + "\n\n" + body
    return content if content.endswith("\n") else content + "\n"


def _source_pdf(source: str, tmp: Path) -> Path | None:
    if _is_url(source):
        pdf_path = tmp / "source.pdf"
        _download_pdf(source, pdf_path)
        return pdf_path
    pdf_path = Path(source).expanduser()
    if not pdf_path.is_file():
        print(f"本地 PDF 不存在: {pdf_path}", file=sys.stderr)
        return None
    return pdf_path


def _report_result(report: dict, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"已导入 PDF → {report['path']}", file=sys.stderr)


def _slug_error(slug: str) -> str | None:
    if not slug:
        return "无法从 source 推导 slug，请显式传 --slug=SLUG"
    if not SLUG_RE.match(slug):
        return f"slug 必须匹配 ^[a-z0-9][a-z0-9-]*$（kebab-case）: {slug}"
    return None


def _article_path(wiki_root: Path, slug: str) -> Path | None:
    path = wiki_root / "raw" / "articles" / f"{slug}.md"
    if path.exists():
        print(f"目标 Markdown 已存在（导入不覆盖）: {path}", file=sys.stderr)
        return None
    return path


def _convert_and_write_article(
    article_path: Path,
    pdf_path: Path,
    work_dir: Path,
    *,
    source: str,
    is_url: bool,
    original_sha256: str,
) -> str:
    converter_version = _docling_version()
    body = _convert_pdf(pdf_path, work_dir / "body.md")
    atomic_write(
        article_path,
        _render_markdown(
            body,
            source=source,
            is_url=is_url,
            imported_at=date.today().isoformat(),
            original_sha256=original_sha256,
        ),
    )
    return converter_version


def run(
    wiki_root: Path,
    *,
    source: str,
    slug: str | None = None,
    as_json: bool = False,
) -> int:
    """import-pdf 业务入口（cli.py dispatch 直调；flag SSOT 在 llmw.cli argparse 树）。"""
    resolved_slug = slug or _default_slug(source)
    error = _slug_error(resolved_slug)
    if error:
        print(error, file=sys.stderr)
        return 1

    article_path = _article_path(wiki_root, resolved_slug)
    if article_path is None:
        return 1

    is_url = _is_url(source)
    with tempfile.TemporaryDirectory(prefix="llmw-import-pdf-") as tmp:
        work_dir = Path(tmp)
        pdf_path = _source_pdf(source, work_dir)
        if pdf_path is None:
            return 1
        _validate_pdf(pdf_path)
        original_sha256 = sha256_file(pdf_path)
        if original_sha256 is None:
            raise PdfImportFailed(f"无法计算 PDF SHA-256: {pdf_path}")

        provenance_source = source if is_url else str(Path(source).expanduser().absolute())
        converter_version = _convert_and_write_article(
            article_path,
            pdf_path,
            work_dir,
            source=provenance_source,
            is_url=is_url,
            original_sha256=original_sha256,
        )

    _report_result(
        {
            "path": article_path.relative_to(wiki_root).as_posix(),
            "source_url": source if is_url else None,
            "original_sha256": original_sha256,
            "converter": CONVERTER_NAME,
            "converter_version": converter_version,
        },
        as_json=as_json,
    )
    return 0
