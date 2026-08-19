import os
import sys

import requests


NOTICE_WEBHOOK_URL = os.environ.get(
    "DISCORD_NOTICE_WEBHOOK_URL",
    "",
).strip()

EVENT_WEBHOOK_URL = os.environ.get(
    "DISCORD_EVENT_WEBHOOK_URL",
    "",
).strip()


def send_discord(item):
    kind = item["kind"]

    if kind == "공지":
        webhook_url = NOTICE_WEBHOOK_URL

    elif kind == "이벤트":
        webhook_url = EVENT_WEBHOOK_URL

    else:
        raise RuntimeError(
            f"알 수 없는 알림 종류입니다: {kind}"
        )

    if not webhook_url:
        raise RuntimeError(
            f"{kind}용 Discord Webhook 환경변수가 없습니다."
        )

    fields = []

    # 공지 등록일
    if item.get("date"):
        fields.append(
            {
                "name": "등록일",
                "value": item["date"],
                "inline": True,
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

    payload = {
        "username": "거상 소식 알림",
        "embeds": [
            {
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
        ],
    }

    response = requests.post(
        webhook_url,
        json=payload,
        timeout=20,
    )

    response.raise_for_status()


def main():
    print(
        "Discord 공지/이벤트 "
        "표시 형식 테스트를 시작합니다."
    )

    print("")
    print(
        "===== 공지 알림 테스트 ====="
    )

    send_discord(
        {
            "kind": "공지",
            "title": "8월 19일 본서버 임시점검 안내",
            "date": "2026-08-19",
            "url": (
                "https://www.gersang.co.kr/"
                "news/notice.gs?GSbid=1001"
            ),
        }
    )

    print(
        "공지 테스트 메시지 전송 완료"
    )

    print("")
    print(
        "===== 이벤트 알림 테스트 ====="
    )

    send_discord(
        {
            "kind": "이벤트",
            "title": "이벤트 기간 표시 테스트",
            "date": "",
            "period": (
                "2026-08-20 ~ "
                "2026-09-10"
            ),
            "url": (
                "https://www.gersang.co.kr/"
                "news/event.gs"
            ),
        }
    )

    print(
        "이벤트 테스트 메시지 전송 완료"
    )

    print("")
    print(
        "공지/이벤트 표시 형식 테스트 완료"
    )

    return 0


if __name__ == "__main__":
    sys.exit(
        main()
    )
