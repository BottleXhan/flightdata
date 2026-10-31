"""국기 그림 받기: flag-icons(MIT, https://github.com/lipis/flag-icons) 의 4:3 SVG 를 web/flags/<나라 코드>.svg 로.

    py -3.13 tools/flags/get_flags.py

Windows 는 국기 이모지를 그리지 못해(글자 "KR" 로 보임) 그림 파일을 쓴다. 화면은 <img src="flags/kr.svg"> 로 필요한 것만 읽는다.
"""
import io
import os
import tarfile
import urllib.request

VERSION = "7.2.3"
URL = f"https://registry.npmjs.org/flag-icons/-/flag-icons-{VERSION}.tgz"
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "web", "flags")


def main():
    with urllib.request.urlopen(URL, timeout=60) as r:
        data = r.read()
    os.makedirs(OUT, exist_ok=True)
    n = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as t:
        for m in t.getmembers():
            name = m.name.replace("\\", "/")
            if name.startswith("package/flags/4x3/") and name.endswith(".svg") and m.isfile():
                code = os.path.basename(name)
                if "/" in code or ".." in code:
                    continue
                with open(os.path.join(OUT, code), "wb") as f:
                    f.write(t.extractfile(m).read())
                n += 1
            elif name == "package/LICENSE":
                with open(os.path.join(OUT, "LICENSE.txt"), "wb") as f:
                    f.write(b"flag-icons " + VERSION.encode() + b" (https://github.com/lipis/flag-icons)\n\n" + t.extractfile(m).read())
    print(f"{OUT}: 국기 {n}개")


if __name__ == "__main__":
    main()
