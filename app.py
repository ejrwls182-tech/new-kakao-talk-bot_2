"""
제71기 신임관리자과정 - 카카오톡 챗봇 스킬 서버
카카오 i 오픈빌더의 스킬(웹훅) 서버로 사용합니다.

지원 발화 예시:
    - "오늘 강의"        -> 오늘 일정
    - "내일 강의"        -> 내일 일정
    - "6/22 강의" / "6월 22일 강의" / "2026-06-22 강의" -> 해당 날짜 일정
    - "이번주 해야할일" / "이번주 할일" -> 이번 주(월~일) 안에 마감인 제출/마감 항목들
    - "다음주 해야할일" / "다음주 할일" -> 다음 주(월~일) 안에 마감인 제출/마감 항목들

실행:
    pip install -r requirements.txt
    python app.py

오픈빌더 설정:
    - 스킬 URL 에 "https://<배포주소>/skill" 등록
    - 시나리오 발화에 위 예시들을 등록하고 모두 같은 스킬에 연결
    - 발화 패턴(블록 발화)에 정규식/패턴 매칭을 쓰면 날짜 입력형 발화도 한 블록으로 받을 수 있습니다.
      (예: 패턴 "{날짜} 강의")
"""

import json
import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import Flask, request, jsonify

app = Flask(__name__)

SCHEDULE_PATH = os.path.join(os.path.dirname(__file__), "schedule.json")
KST = ZoneInfo("Asia/Seoul")
WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]


def load_schedule():
    with open(SCHEDULE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def today_kst():
    return datetime.now(KST).date()


# ---------------------------------------------------------------------------
# 날짜 파싱
# ---------------------------------------------------------------------------

# "6/22", "6.22", "6-22", "6월 22일", "2026-06-22", "2026.6.22" 등을 인식
DATE_PATTERNS = [
    re.compile(r"(\d{4})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})"),  # YYYY-MM-DD
    re.compile(r"(\d{1,2})[.\-/월]\s*(\d{1,2})"),                    # MM-DD (올해 기준)
]

WEEKDAY_NAME_TO_INDEX = {
    "월요일": 0, "화요일": 1, "수요일": 2, "목요일": 3,
    "금요일": 4, "토요일": 5, "일요일": 6,
    "월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6,
}


def parse_date_from_text(text, base_date):
    """발화 텍스트에서 날짜를 추출. 못 찾으면 None."""
    if "내일" in text:
        return base_date + timedelta(days=1)
    if "어제" in text:
        return base_date - timedelta(days=1)
    if "모레" in text:
        return base_date + timedelta(days=2)
    if "오늘" in text:
        return base_date

    # "이번주 금요일", "다음주 월요일" 등
    week_offset = None
    if "다음주" in text or "다음 주" in text:
        week_offset = 1
    elif "이번주" in text or "이번 주" in text:
        week_offset = 0

    if week_offset is not None:
        for name, idx in WEEKDAY_NAME_TO_INDEX.items():
            if name in text:
                monday = base_date - timedelta(days=base_date.weekday())
                return monday + timedelta(days=idx + 7 * week_offset)

    for pattern in DATE_PATTERNS:
        m = pattern.search(text)
        if m:
            groups = m.groups()
            if len(groups) == 3:
                year, month, day = (int(g) for g in groups)
            else:
                year = base_date.year
                month, day = (int(g) for g in groups)
            try:
                return datetime(year, month, day).date()
            except ValueError:
                return None
    return None


# ---------------------------------------------------------------------------
# 응답 생성
# ---------------------------------------------------------------------------

def get_day_text(target_date):
    schedule = load_schedule()
    date_key = target_date.strftime("%Y-%m-%d")
    weekday_kr = WEEKDAY_KR[target_date.weekday()]
    header = f"📅 {target_date.strftime('%Y.%m.%d')}({weekday_kr}) 강의/일정"

    sessions = schedule.get(date_key)

    if sessions is None:
        body = "교육 기간에 포함되지 않은 날짜입니다."
    elif len(sessions) == 0:
        body = "해당 날짜는 별도의 강의가 없는 날입니다."
    else:
        body = "\n".join(f"• {s}" for s in sessions)

    return f"{header}\n\n{body}"


def get_week_deadlines_text(base_date, label="이번 주"):
    """base_date가 속한 주(월~일)에 마감되는 [제출] 항목 정리"""
    schedule = load_schedule()

    monday = base_date - timedelta(days=base_date.weekday())
    sunday = monday + timedelta(days=6)
    header = f"🗒 {label}({monday.strftime('%m.%d')}~{sunday.strftime('%m.%d')}) 제출/마감 일정"

    lines = []
    seen = set()
    for i in range(7):
        d = monday + timedelta(days=i)
        date_key = d.strftime("%Y-%m-%d")
        sessions = schedule.get(date_key, [])
        for s in sessions:
            if "제출" in s or "마감" in s:
                if s in seen:
                    continue
                seen.add(s)
                weekday_kr = WEEKDAY_KR[d.weekday()]
                lines.append(f"• {d.strftime('%m.%d')}({weekday_kr}) {s}")

    if not lines:
        body = f"{label}에는 별도의 제출/마감 일정이 없습니다."
    else:
        body = "\n".join(lines)

    return f"{header}\n\n{body}"


# ---------------------------------------------------------------------------
# 라우트
# ---------------------------------------------------------------------------

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/skill", methods=["POST"])
def skill():
    """카카오 i 오픈빌더 스킬(웹훅) 엔드포인트"""
    payload = request.get_json(silent=True) or {}
    utterance = (
        payload.get("userRequest", {}).get("utterance", "")
        or payload.get("action", {}).get("params", {}).get("utterance", "")
        or ""
    ).strip()

    base_date = today_kst()

    if "할일" in utterance.replace(" ", "") or "할 일" in utterance:
        if "다음주" in utterance or "다음 주" in utterance:
            target_week_date = base_date + timedelta(days=7)
            label = "다음 주"
        else:
            target_week_date = base_date
            label = "이번 주"
        text = get_week_deadlines_text(target_week_date, label=label)
    else:
        target_date = parse_date_from_text(utterance, base_date)
        if target_date is None:
            target_date = base_date  # 발화에서 날짜를 못 찾으면 오늘로 처리
        text = get_day_text(target_date)

    response = {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "simpleText": {
                        "text": text
                    }
                }
            ]
        }
    }
    return jsonify(response)


if __name__ == "__main__":
    # 로컬 테스트용. 배포 시에는 gunicorn 등 WSGI 서버 사용 권장.
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
