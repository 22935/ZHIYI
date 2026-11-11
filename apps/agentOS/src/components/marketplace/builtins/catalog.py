"""将平台自有代码构建为可校验 ZIP，目录中不接收用户传入的可执行内容。"""
import hashlib
import io
import json
import zipfile
from pathlib import Path
from ..contracts import CatalogItem
from contracts.resource.resource_signing import __file__ as signing_source
from .contracts import SUPPORTED_PAIRS


def build_builtin_catalog(catalog_root, package_root):
    catalog_root, package_root = Path(catalog_root), Path(package_root)
    catalog_root.mkdir(parents=True, exist_ok=True)
    package_root.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).parent
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ["__init__.py", "contracts.py", "pdf_parser.py", "file_converter.py", "worker.py", "server.py"]:
            archive.writestr(zipfile.ZipInfo("agentos_local_tools/" + name, (2026, 1, 1, 0, 0, 0)), (source / name).read_bytes())
        archive.writestr(zipfile.ZipInfo("agentos_local_tools/signing.py", (2026, 1, 1, 0, 0, 0)), Path(signing_source).read_bytes())
    payload = buffer.getvalue()
    digest = hashlib.sha256(payload).hexdigest()
    package_name = f"local-tools-{digest[:16]}.zip"
    package = package_root / package_name
    if not package.exists() or package.read_bytes() != payload:
        package.write_bytes(payload)
    items = []
    for slug, title, capability, description in [
        ("pdf-parser", "PDF 解析", "pdf.parse", "离线提取 PDF 文字与页码信息。支持页范围选择；扫描件暂不支持 OCR。"),
        ("file-converter", "文件格式转换", "file.convert", "离线转换文本、表格和办公文档；输出独立副本，保留源文件。"),
    ]:
        formats = ["pdf → text"] if slug == "pdf-parser" else [f"{s} → {' / '.join(sorted(t))}" for s, t in SUPPORTED_PAIRS.items()]
        item = CatalogItem(catalogId="tool." + slug, kind="tool_service", version="1.0.0", displayName=title, description=description,
            packagePath=package_name, sha256=digest, sizeBytes=len(payload), category="文档工具",
            requirements={"python": ">=3.10", "dependencies": ["pypdf==7.0.0", "python-docx==1.2.0", "openpyxl==3.1.5", "Markdown==3.7"], "formats": formats, "maxFileMb": 20, "offline": True},
            runtime={"runtimeId": "runtime:platform:" + slug, "nodeId": "node:device:platform-tools", "kind": "tool_service", "placement": "device", "trust": "host_trusted", "displayName": title,
                "capabilities": [capability], "capacity": 1, "adapter": "agentos_http", "provider": "AgentOS Local Tools", "sourceType": "platform-local", "endpoint": {"protocol": "http", "address": "http://127.0.0.1:0"}},
            startup={"pythonModule": "agentos_local_tools.server", "capability": capability})
        target = catalog_root / (item.catalog_id + ".json")
        serialized = item.model_dump_json(by_alias=True, indent=2)
        if not target.exists() or target.read_text(encoding="utf-8") != serialized:
            target.write_text(serialized, encoding="utf-8")
        items.append(item)
    return items


ensure_builtin_catalog = build_builtin_catalog
