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


def send_test(webhook_url, kind, title, url):
    if not webhook_url:
        raise RuntimeError(
            f"{kind}용 Discord Webhook 환경변수가 없습니다."
        )

    payload = {
        "username": "거상 소식 알림",
        "embeds": [
            {
                "title": f"[{kind}] {title}",
                "url": url,
                "description": (
                    f"{kind} 전용 Discord Webhook "
                    "분리 테스트입니다."
                ),
                "footer": {
                    "text": "천하제일상 거상 알림 테스트"
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
    print("Discord Webhook 분리 테스트를 시작합니다.")

    print("")
    print("===== 공지 채널 테스트 =====")

    send_test(
        NOTICE_WEBHOOK_URL,
        "공지",
        "공지 채널 분리 테스트",
        "https://www.gersang.co.kr/news/notice.gs?GSbid=1001",
    )

    print("공지 채널 테스트 메시지 전송 완료")

    print("")
    print("===== 이벤트 채널 테스트 =====")

    send_test(
        EVENT_WEBHOOK_URL,
        "이벤트",
        "이벤트 채널 분리 테스트",
        "https://www.gersang.co.kr/news/event.gs",
    )

    print("이벤트 채널 테스트 메시지 전송 완료")

    print("")
    print("두 Webhook 분리 테스트 완료")

    return 0


if __name__ == "__main__":
    sys.exit(main())
