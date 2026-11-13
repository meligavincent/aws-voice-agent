"""Build a deterministic Lambda ZIP from the application and uv-locked runtime SDK.
Run through `uv run`: only these runtime distributions are included, never dev tools.
"""

import importlib.metadata
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
(root / "build").mkdir(exist_ok=True)
files = {str(p.relative_to(root / "src")): p for p in (root / "src/voice_agent").glob("*.py")}
for name in ["boto3", "botocore", "s3transfer", "jmespath", "python-dateutil", "six", "urllib3"]:
    distribution = importlib.metadata.distribution(name)
    for entry in distribution.files or []:
        if ".." in entry.parts or "__pycache__" in entry.parts or str(entry).endswith(".pyc"):
            continue
        path = Path(distribution.locate_file(entry))
        if path.is_file():
            files[str(entry)] = path
with zipfile.ZipFile(root / "build/lambda.zip", "w", zipfile.ZIP_DEFLATED) as archive:
    for name, path in sorted(files.items()):
        info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        archive.writestr(info, path.read_bytes())
print(root / "build/lambda.zip")
