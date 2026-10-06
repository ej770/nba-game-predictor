"""Step 0 - Download the raw data (about 300 MB) and check every file against its checksum."""
import hashlib
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import config as C


def fetch(name: str, expected: str) -> str:
    path = C.RAW / name
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == expected:
        return f"ok      {name}"
    url = C.ODDS_URL if name == "OddsData.sqlite" else C.PBP_URL.format(name=name)
    urllib.request.urlretrieve(url, path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected:
        raise RuntimeError(f"{name}: checksum {digest[:12]}... does not match the pinned file")
    return f"fetched {name}"


def main() -> None:
    C.RAW.mkdir(parents=True, exist_ok=True)
    sums = json.loads(C.CHECKSUMS.read_text())
    with ThreadPoolExecutor(max_workers=8) as pool:
        for line in pool.map(lambda kv: fetch(*kv), sums.items()):
            print(line)


if __name__ == "__main__":
    main()
