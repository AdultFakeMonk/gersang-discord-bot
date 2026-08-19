import sys
import time

import requests
import urllib3
from bs4 import BeautifulSoup


urllib3.disable_warnings(
    urllib3.exceptions.InsecureRequestWarning
)

EVENT_URL = "https://www.gersang.co.kr/news/event.gs"

TARGET_TITLE = "천하제일 낚시 대회!"


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": (
        "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
    ),
    "Referer": "https://www.gersang.co.kr/",
}


def fetch_html(url):
    last_error = None

    for attempt in range(5):
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=30,
                verify=False,
            )

            response.raise_for_status()

            if (
                not response.encoding
                or response.encoding.lower() == "iso-8859-1"
            ):
                response.encoding = (
                    response.apparent_encoding
                    or "utf-8"
                )

            print(
                f"페이지 접속 성공: {url} "
                f"(HTTP {response.status_code}, "
                f"{len(response.text)} bytes)"
            )

            return response.text

        except requests.RequestException as e:
            last_error = e

            print(
                f"접속 실패 "
                f"({attempt + 1}/5): {e}"
            )

            if attempt < 4:
                wait_seconds = 5 * (attempt + 1)

                print(
                    f"{wait_seconds}초 후 "
                    "다시 시도합니다."
                )

                time.sleep(wait_seconds)

    raise last_error


def main():
    print(
        "거상 이벤트 목록 HTML 진단을 시작합니다."
    )

    html = fetch_html(
        EVENT_URL
    )

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    print("")
    print("===== 기본 구조 =====")
    print(
        "a 개수:",
        len(
            soup.find_all(
                "a"
            )
        ),
    )

    print(
        "div 개수:",
        len(
            soup.find_all(
                "div"
            )
        ),
    )

    print(
        "li 개수:",
        len(
            soup.find_all(
                "li"
            )
        ),
    )

    print("")
    print(
        "===== 대상 이벤트 검색 ====="
    )

    found = False

    # 먼저 제목 문자열이 들어있는 태그를 직접 찾음
    for tag in soup.find_all(
        string=lambda text: (
            text
            and TARGET_TITLE in text
        )
    ):
        found = True

        print("")
        print(
            "대상 이벤트 제목 발견:"
        )

        print(
            tag.strip()
        )

        parent = tag.parent

        for level in range(6):
            if parent is None:
                break

            print("")
            print(
                f"----- 부모 단계 {level} -----"
            )

            print(
                "태그:",
                parent.name,
            )

            print(
                "class:",
                parent.get("class"),
            )

            print(
                "id:",
                parent.get("id"),
            )

            print(
                "href:",
                parent.get("href"),
            )

            print(
                "data-*:",
                {
                    key: value
                    for key, value
                    in parent.attrs.items()
                    if key.startswith("data-")
                },
            )

            snippet = str(
                parent
            )

            if len(snippet) > 5000:
                snippet = (
                    snippet[:5000]
                    + "...(생략)"
                )

            print(
                snippet
            )

            parent = (
                parent.parent
            )

        break

    print("")
    print(
        "===== 링크 기준 검색 ====="
    )

    link_count = 0

    for a in soup.find_all(
        "a",
        href=True,
    ):
        text = " ".join(
            a.stripped_strings
        ).strip()

        href = (
            a.get("href")
            or ""
        ).strip()

        combined = (
            f"{text} {href}"
        )

        if (
            TARGET_TITLE not in combined
            and "/event/" not in href.lower()
        ):
            continue

        link_count += 1

        print("")
        print(
            f"----- 링크 후보 {link_count} -----"
        )

        print(
            "TEXT:",
            text,
        )

        print(
            "HREF:",
            href,
        )

        print(
            "CLASS:",
            a.get("class"),
        )

        parent = (
            a.parent
        )

        for level in range(4):
            if parent is None:
                break

            print("")
            print(
                f"[링크 부모 단계 {level}]"
            )

            print(
                "태그:",
                parent.name,
            )

            print(
                "class:",
                parent.get("class"),
            )

            snippet = str(
                parent
            )

            if len(snippet) > 4000:
                snippet = (
                    snippet[:4000]
                    + "...(생략)"
                )

            print(
                snippet
            )

            parent = (
                parent.parent
            )

        if link_count >= 10:
            break

    print("")
    print(
        "===== 진단 결과 ====="
    )

    if found:
        print(
            f"'{TARGET_TITLE}' 이벤트를 "
            "HTML에서 찾았습니다."
        )
    else:
        print(
            f"'{TARGET_TITLE}' 이벤트 제목을 "
            "HTML 텍스트에서 찾지 못했습니다."
        )

    print(
        "이벤트 목록 HTML 진단 완료"
    )

    return 0


if __name__ == "__main__":
    sys.exit(
        main()
    )
