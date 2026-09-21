"""Download the latest listed public files, with provenance and content checks."""

import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
RAW.mkdir(exist_ok=True)
manifest = []
for dataset in ["OA-22522", "OA-22523", "OA-22502"]:
    url = f"https://data.seoul.go.kr/dataList/{dataset}/F/1/datasetView.do"
    html = subprocess.check_output(["curl", "-fsSL", "--retry", "2", url]).decode(
        "utf8"
    )
    (RAW / f"{dataset}.html").write_text(html)
    rows = re.findall(
        r'<span title="([^"]+)" onclick="javascript:downloadFile\(\'(\d+)\'\);">', html
    )
    form = re.search(r'<form name="frmFile".*?</form>', html, re.S)[0]
    infseq = re.search(r'name="infSeq" value="([^"]+)"', form)[1]
    name, seq = rows[0]
    path = RAW / Path(name).name
    endpoint = (
        "https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?useCache=false"
    )
    subprocess.run(
        [
            "curl",
            "-fsSL",
            "--retry",
            "2",
            "--max-time",
            "180",
            "-d",
            f"infId={dataset}&seq={seq}&infSeq={infseq}",
            endpoint,
            "-o",
            str(path),
        ],
        check=True,
    )
    blob = path.read_bytes()
    assert not blob.lstrip().startswith(b"<html")
    manifest.append(
        dict(
            dataset=dataset,
            filename=name,
            seq=seq,
            infSeq=infseq,
            page=url,
            url=endpoint,
            bytes=len(blob),
            sha256=hashlib.sha256(blob).hexdigest(),
            checked_on="2026-09-21",
        )
    )
    print(name, len(blob), flush=True)
(ROOT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
