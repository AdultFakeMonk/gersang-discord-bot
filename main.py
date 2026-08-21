import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import urllib3
from bs4 import BeautifulSoup


urllib3.disable_warnings(
    urllib3.exceptions.InsecureRequestWarning
)


# ============================================================
# 기본 설정
# ============================================================

NOTICE_URL = (
    "https://www.gersang.co.kr/"
    "news/notice.gs?GSbid=1001"
)

EVENT_URL = (
    "https://www.gersang.co.kr/"
    "news/event.gs"
)

STATE_FILE = Path("last_seen.json")


NOTICE_WEBHOOK_URL = os.environ.get(
    "DISCORD_NOTICE_WEBHOOK_URL",
    "",
).strip()

EVENT_WEBHOOK_URL = os.environ.get(
    "DISCORD_EVENT_WEBHOOK_URL",
    "",
).strip()

MAX_SEND_PER_RUN = int(
    os.environ.get(
        "MAX_SEND_PER_RUN",
        "5",
    )
)


# ============================================================
# HTTP 헤더
# ============================================================

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
    "Referer": (
        "https://www.gersang.co.kr/"
    ),
}


# ============================================================
# 거상 홈페이지 가져오기
# ============================================================

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
                or response.encoding.lower()
                == "iso-8859-1"
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
                wait_seconds = (
                    5 * (attempt + 1)
                )

                print(
                    f"{wait_seconds}초 후 "
                    "다시 시도합니다."
                )

                time.sleep(
                    wait_seconds
                )

    raise last_error


# ============================================================
# 공지사항 파싱
# ============================================================

def parse_notices(html):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    notices = []

    for row in soup.select(
        "div.tr[data-uid]"
    ):
        uid_text = (
            row.get("data-uid")
            or ""
        ).strip()

        if not uid_text.isdigit():
            continue

        subject = row.select_one(
            ".box-subject"
        )

        date_box = row.select_one(
            ".box-date"
        )

        if subject is None:
            continue

        title = " ".join(
            subject.stripped_strings
        ).strip()

        if not title:
            continue

        date = ""

        if date_box:
            date = " ".join(
                date_box.stripped_strings
            ).strip()

        notices.append(
            {
                "kind": "공지",
                "id": int(uid_text),
                "title": title,
                "date": date,
                "url": NOTICE_URL,
            }
        )

    notices.sort(
        key=lambda item: item["id"],
        reverse=True,
    )

    return notices


# ============================================================
# 이벤트 URL 확인
# ============================================================

def normalize_event_url(href):
    full_url = urljoin(
        EVENT_URL,
        href,
    )

    parsed = urlparse(
        full_url
    )

    if parsed.scheme not in {
        "http",
        "https",
    }:
        return None

    if parsed.netloc.lower() not in {
        "gersang.co.kr",
        "www.gersang.co.kr",
    }:
        return None

    if not parsed.path.lower().startswith(
        "/event/"
    ):
        return None

    return parsed._replace(
        query="",
        fragment="",
    ).geturl()


# ============================================================
# 이미지 URL 정리
# ============================================================

def normalize_image_url(
    image_url,
    base_url,
):
    if not image_url:
        return None

    image_url = image_url.strip()

    if not image_url:
        return None

    if image_url.lower().startswith(
        "data:"
    ):
        return None

    if image_url.lower().startswith(
        "javascript:"
    ):
        return None

    if image_url.startswith("//"):
        image_url = (
            "https:"
            + image_url
        )

    full_url = urljoin(
        base_url,
        image_url,
    )

    parsed = urlparse(
        full_url
    )

    if parsed.scheme not in {
        "http",
        "https",
    }:
        return None

    return full_url


# ============================================================
# CSS background-image에서 URL 추출
# ============================================================

def extract_background_image(
    element,
):
    style = (
        element.get("style")
        or ""
    ).strip()

    if not style:
        return None

    match = re.search(
        r"""
        background-image
        \s*:\s*
        url
        \s*\(
        [\'"]?
        ([^\'")]+)
        [\'"]?
        \s*\)
        """,
        style,
        flags=(
            re.IGNORECASE
            | re.VERBOSE
        ),
    )

    if match:
        return match.group(1).strip()

    return None


# ============================================================
# 이벤트 대표 이미지 추출
# ============================================================

def extract_event_image(
    box,
    base_url,
):
    image_attributes = [
        "src",
        "data-src",
        "data-original",
        "data-lazy-src",
        "data-image",
        "data-original-src",
    ]

    # img 태그
    for img in box.select(
        "img"
    ):
        for attr in image_attributes:
            image_url = normalize_image_url(
                img.get(attr),
                base_url,
            )

            if image_url:
                return image_url

    # source srcset
    for source in box.select(
        "source"
    ):
        srcset = (
            source.get("srcset")
            or ""
        ).strip()

        if srcset:
            first_url = (
                srcset.split(",")[0]
                .strip()
                .split(" ")[0]
            )

            image_url = normalize_image_url(
                first_url,
                base_url,
            )

            if image_url:
                return image_url

    # background-image
    for element in box.select(
        "[style]"
    ):
        raw_url = (
            extract_background_image(
                element
            )
        )

        image_url = normalize_image_url(
            raw_url,
            base_url,
        )

        if image_url:
            return image_url

    return None


# ============================================================
# 이벤트 상세페이지에서 이미지 찾기
# ============================================================

def extract_detail_page_image(
    event_url,
):
    print(
        "목록에서 이벤트 이미지를 "
        "찾지 못했습니다."
    )

    print(
        f"상세페이지 이미지 확인: "
        f"{event_url}"
    )

    try:
        html = fetch_html(
            event_url
        )

    except Exception as e:
        print(
            f"이벤트 상세페이지 "
            f"접속 실패: {e}"
        )

        return None

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    selectors = [
        ".event-view",
        ".event-detail",
        ".view-content",
        ".contents",
        ".content",
        ".board-view",
        "article",
        "body",
    ]

    for selector in selectors:
        container = soup.select_one(
            selector
        )

        if container is None:
            continue

        image_url = extract_event_image(
            container,
            event_url,
        )

        if image_url:
            return image_url

    return None


# ============================================================
# 이벤트 파싱
# ============================================================

def parse_events(html):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    events = {}

    for box in soup.select(
        "div.list-box"
    ):
        label_box = box.select_one(
            ".txt-box .label"
        )

        subject_link = box.select_one(
            ".txt-box .subject a"
        )

        subject_box = box.select_one(
            ".txt-box .subject"
        )

        date_box = box.select_one(
            ".txt-box .date"
        )

        if label_box is None:
            continue

        if subject_link is None:
            continue

        status = " ".join(
            label_box.stripped_strings
        ).strip()

        # 진행중인 이벤트만
        if status != "진행중":
            continue

        href = (
            subject_link.get("href")
            or ""
        ).strip()

        full_url = normalize_event_url(
            href
        )

        if not full_url:
            continue

        title = " ".join(
            subject_link.stripped_strings
        ).strip()

        if (
            not title
            and subject_box
        ):
            title = " ".join(
                subject_box.stripped_strings
            ).strip()

        if not title:
            continue

        period = ""

        if date_box:
            period = " ".join(
                date_box.stripped_strings
            ).strip()

        # 이벤트 대표 이미지 추출
        image_url = extract_event_image(
            box,
            EVENT_URL,
        )

        # 목록에서 못 찾으면 상세페이지에서 검색
        if not image_url:
            image_url = (
                extract_detail_page_image(
                    full_url
                )
            )

        if image_url:
            print(
                f"이벤트 이미지 발견: "
                f"{image_url}"
            )
        else:
            print(
                f"이벤트 이미지 없음: "
                f"{title}"
            )

        events[full_url] = {
            "kind": "이벤트",
            "title": title,
            "status": status,
            "period": period,
            "url": full_url,
            "image_url": image_url,
        }

    return list(
        events.values()
    )


# ============================================================
# 상태 파일
# ============================================================

def load_state():
    default = {
        "notice_last_id": None,
        "event_seen_urls": [],
    }

    if not STATE_FILE.exists():
        return default

    try:
        data = json.loads(
            STATE_FILE.read_text(
                encoding="utf-8"
            )
        )

        return {
            "notice_last_id": data.get(
                "notice_last_id"
            ),
            "event_seen_urls": list(
                data.get(
                    "event_seen_urls",
                    [],
                )
            ),
        }

    except Exception as e:
        print(
            f"상태 파일 읽기 실패: {e}"
        )

        return default


def save_state(state):
    STATE_FILE.write_text(
        json.dumps(
            state,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


# ============================================================
# 이벤트 이미지 다운로드
# ============================================================

def download_event_image(
    image_url,
    event_url,
):
    """
    Discord가 거상 서버에서 직접 이미지를
    가져가도록 하지 않고,
    GitHub Actions가 먼저 원본 이미지를
    다운로드한 뒤 Discord에 파일로 첨부합니다.

    이미지 크기는 변경하지 않습니다.
    """

    print("")
    print(
        "이벤트 이미지 다운로드 시작"
    )

    print(
        f"이미지 URL: {image_url}"
    )

    image_headers = dict(
        HEADERS
    )

    image_headers["Referer"] = (
        event_url
    )

    try:
        response = requests.get(
            image_url,
            headers=image_headers,
            timeout=30,
            verify=False,
        )

        response.raise_for_status()

        if not response.content:
            raise RuntimeError(
                "이미지 응답 내용이 비어 있습니다."
            )

        content_type = (
            response.headers.get(
                "Content-Type",
                "",
            )
            .split(";")[0]
            .strip()
            .lower()
        )

        print(
            f"이미지 다운로드 성공 "
            f"(HTTP {response.status_code})"
        )

        print(
            f"Content-Type: "
            f"{content_type}"
        )

        print(
            f"이미지 크기: "
            f"{len(response.content)} bytes"
        )

        # 확장자 결정
        extension = ".jpg"

        if content_type == "image/png":
            extension = ".png"

        elif content_type == "image/webp":
            extension = ".webp"

        elif content_type == "image/gif":
            extension = ".gif"

        elif content_type in {
            "image/jpeg",
            "image/jpg",
        }:
            extension = ".jpg"

        filename = (
            "gersang_event_image"
            + extension
        )

        return (
            filename,
            response.content,
            content_type or "image/jpeg",
        )

    except requests.RequestException as e:
        print(
            f"이벤트 이미지 다운로드 실패: "
            f"{e}"
        )

        return None


# ============================================================
# Discord 전송
# ============================================================

def send_discord(item):
    kind = item["kind"]

    if kind == "공지":
        webhook_url = (
            NOTICE_WEBHOOK_URL
        )

    elif kind == "이벤트":
        webhook_url = (
            EVENT_WEBHOOK_URL
        )

    else:
        raise RuntimeError(
            f"알 수 없는 알림 종류입니다: "
            f"{kind}"
        )

    if not webhook_url:
        raise RuntimeError(
            f"{kind}용 Discord Webhook "
            "환경변수가 없습니다."
        )

    fields = []

    # 공지 등록일
    if (
        kind == "공지"
        and item.get("date")
    ):
        fields.append(
            {
                "name": "등록일",
                "value": item["date"],
                "inline": False,
            }
        )

    # 이벤트 기간
    if (
        kind == "이벤트"
        and item.get("period")
    ):
        fields.append(
            {
                "name": "이벤트 기간",
                "value": item["period"],
                "inline": False,
            }
        )

    embed = {
        "title": (
            f"[{kind}] "
            f"{item['title']}"
        )[:256],

        "url": item["url"],

        "description": (
            f"거상 홈페이지에 새 "
            f"{kind}이(가) 등록되었습니다."
        ),

        "fields": fields,

        "footer": {
            "text": (
                "천하제일상 거상 "
                "공식 홈페이지"
            )
        },
    }

    image_file = None

    # --------------------------------------------------------
    # 이벤트는 원본 대표 이미지를 첨부
    # --------------------------------------------------------

    if (
        kind == "이벤트"
        and item.get("image_url")
    ):
        image_file = (
            download_event_image(
                item["image_url"],
                item["url"],
            )
        )

        if image_file:
            filename = (
                image_file[0]
            )

            embed["image"] = {
                "url": (
                    "attachment://"
                    f"{filename}"
                )
            }

            print(
                "Discord Embed 이미지 연결: "
                f"attachment://{filename}"
            )

        else:
            print(
                "이미지 다운로드 실패. "
                "이미지 없이 Discord 전송"
            )

    payload = {
        "username": "거상 소식 알림",
        "embeds": [
            embed
        ],
    }

    # 이미지가 있으면 파일 첨부
    if image_file:
        (
            filename,
            image_bytes,
            content_type,
        ) = image_file

        files = {
            "file": (
                filename,
                image_bytes,
                content_type,
            )
        }

        data = {
            "payload_json": json.dumps(
                payload,
                ensure_ascii=False,
            )
        }

        response = requests.post(
            webhook_url,
            data=data,
            files=files,
            timeout=30,
        )

    else:
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=30,
        )

    response.raise_for_status()

    print(
        "Discord 전송 성공"
    )


# ============================================================
# 공지 처리
# ============================================================

def process_notices(state):
    print("")
    print(
        "===== 공지사항 확인 ====="
    )

    try:
        html = fetch_html(
            NOTICE_URL
        )

    except Exception as e:
        print(
            f"공지사항 페이지 "
            f"접속 실패: {e}"
        )

        return False

    notices = parse_notices(
        html
    )

    print(
        f"공지사항 감지 개수: "
        f"{len(notices)}"
    )

    for item in notices[:5]:
        print(
            f"감지: ID={item['id']} / "
            f"{item['date']} / "
            f"{item['title']}"
        )

    if not notices:
        print(
            "경고: 공지사항 게시물을 "
            "찾지 못했습니다."
        )

        return False

    newest_id = notices[0]["id"]

    last_id = state.get(
        "notice_last_id"
    )

    if last_id is None:
        state[
            "notice_last_id"
        ] = newest_id

        print(
            f"공지 초기화: 최신 ID "
            f"{newest_id}을 "
            "기준점으로 저장"
        )

        return True

    try:
        last_id = int(
            last_id
        )

    except Exception:
        last_id = 0

    new_notices = [
        item
        for item in notices
        if item["id"] > last_id
    ]

    if not new_notices:
        print(
            f"새 공지 없음. "
            f"last={last_id}, "
            f"newest={newest_id}"
        )

        return False

    print(
        f"새 공지 "
        f"{len(new_notices)}개 발견"
    )

    new_notices.sort(
        key=lambda item: item["id"]
    )

    selected = new_notices[
        -MAX_SEND_PER_RUN:
    ]

    for item in selected:
        send_discord(
            item
        )

        print(
            f"공지 Discord 전송: "
            f"{item['id']} / "
            f"{item['title']}"
        )

    state[
        "notice_last_id"
    ] = max(
        item["id"]
        for item in selected
    )

    return True


# ============================================================
# 이벤트 처리
# ============================================================

def process_events(state):
    print("")
    print(
        "===== 이벤트 확인 ====="
    )

    try:
        html = fetch_html(
            EVENT_URL
        )

    except Exception as e:
        print(
            f"이벤트 페이지 "
            f"접속 실패: {e}"
        )

        return False

    events = parse_events(
        html
    )

    print(
        f"진행중 이벤트 감지 개수: "
        f"{len(events)}"
    )

    for item in events[:10]:
        print(
            f"감지: "
            f"{item['title']} / "
            f"{item['period']} / "
            f"{item['url']}"
        )

        print(
            f"  이미지: "
            f"{item.get('image_url')}"
        )

    if not events:
        print(
            "경고: 진행중인 이벤트를 "
            "찾지 못했습니다."
        )

        return False

    old_seen = set(
        state.get(
            "event_seen_urls",
            [],
        )
    )

    current_urls = [
        item["url"]
        for item in events
    ]

    # --------------------------------------------------------
    # 첫 실행
    # --------------------------------------------------------

    if not old_seen:
        state[
            "event_seen_urls"
        ] = current_urls[:100]

        print(
            f"이벤트 초기화: "
            f"현재 진행중 이벤트 "
            f"{len(current_urls)}개를 "
            "기준점으로 저장"
        )

        return True

    # --------------------------------------------------------
    # 새 이벤트 확인
    # --------------------------------------------------------

    new_events = [
        item
        for item in events
        if item["url"] not in old_seen
    ]

    if new_events:
        print(
            f"새 이벤트 "
            f"{len(new_events)}개 발견"
        )

        for item in new_events[
            :MAX_SEND_PER_RUN
        ]:
            send_discord(
                item
            )

            print(
                f"이벤트 Discord 전송: "
                f"{item['title']} / "
                f"{item['period']}"
            )

    else:
        print(
            "새 이벤트 없음"
        )

    # --------------------------------------------------------
    # 상태 저장
    # --------------------------------------------------------

    merged = []

    for url in (
        current_urls
        + list(old_seen)
    ):
        if url not in merged:
            merged.append(
                url
            )

    new_state = merged[:100]

    changed = (
        new_state
        != state.get(
            "event_seen_urls",
            [],
        )
    )

    state[
        "event_seen_urls"
    ] = new_state

    return (
        changed
        or bool(new_events)
    )


# ============================================================
# 메인
# ============================================================

def main():
    print(
        "거상 공지/이벤트 "
        "확인을 시작합니다."
    )

    state = load_state()

    changed = False

    # 공지 확인
    if process_notices(
        state
    ):
        changed = True

    # 이벤트 확인
    if process_events(
        state
    ):
        changed = True

    # 상태 저장
    if changed:
        save_state(
            state
        )

        print("")
        print(
            "상태 파일 저장 완료"
        )

    else:
        print("")
        print(
            "상태 변경 없음"
        )

    print("")
    print(
        "확인 작업 완료"
    )

    return 0


if __name__ == "__main__":
    sys.exit(
        main()
    )
