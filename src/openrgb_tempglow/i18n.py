"""Tiny translation table. English strings are the keys; add a language by adding a dict."""
import locale
import os

KO = {
    "Lighting": "조명",
    "Devices": "장치",
    "Alerts": "경고",
    "All parts": "전체",
    "Changes here apply to every part at once": "여기서 바꾸면 모든 부품에 한꺼번에 적용돼요",
    "Case / Motherboard": "케이스 / 메인보드",
    "Fans": "팬",
    "Graphics card": "그래픽카드",
    "RAM": "램",
    "Not assigned (off)": "사용 안 함 (끄기)",
    "Effect": "효과",
    "Color": "색상",
    "Brightness": "밝기",
    "Speed": "속도",
    "Static": "고정",
    "Breathing": "숨쉬기",
    "Rainbow": "무지개",
    "Off": "끄기",
    "No lights assigned to this part yet (see Devices)": "이 부품에 연결된 조명이 아직 없어요 (장치 탭에서 지정)",
    "Overheat alert": "과열 경고",
    "When the CPU or graphics card passes its limit, the selected parts switch to the alert color":
        "CPU나 그래픽카드가 기준 온도를 넘으면 선택한 부품을 경고색으로 바꿔요",
    "Enabled": "사용",
    "Alert color": "경고 색상",
    "CPU limit (°C)": "CPU 기준 온도 (°C)",
    "Graphics card limit (°C)": "그래픽카드 기준 온도 (°C)",
    "Return to normal after cooling by (°C)": "복귀 온도 차이 (°C)",
    "Parts that change color": "경고색으로 바꿀 부품",
    "Current temperatures": "현재 온도",
    "not available": "읽을 수 없음",
    "Choose which part each lighting zone belongs to": "조명 구역마다 어느 부품에 속하는지 정해 주세요",
    "LED count": "LED 개수",
    "Set this to the number of LEDs connected to the header": "이 헤더에 연결된 LED 개수로 맞춰 주세요",
    "Built-in driver": "내장 드라이버",
    "Restart service": "서비스 다시 시작",
    "Reset to defaults": "기본값으로 되돌리기",
    "Reset to defaults?": "기본값으로 되돌릴까요?",
    "Lighting, schedule, alert and device settings will all be reset.":
        "조명, 예약, 경고, 장치 설정이 모두 초기화돼요.",
    "Cancel": "취소",
    "Reset": "되돌리기",
    "Settings reset": "기본값으로 되돌렸어요",
    "The lighting service is not running": "조명 서비스가 실행 중이 아니에요",
    "Start": "시작",
    "OpenRGB was not found. Install OpenRGB 1.0 or newer.": "OpenRGB를 찾지 못했어요. OpenRGB 1.0 이상을 설치해 주세요.",
    "Connecting to OpenRGB…": "OpenRGB에 연결하는 중…",
    "No devices found yet": "아직 찾은 장치가 없어요",
    "Lighting zones appear here once the service connects to OpenRGB.":
        "서비스가 OpenRGB에 연결되면 조명 구역이 여기에 나타나요.",
    "About": "정보",
    "Schedule": "예약",
    "Schedules": "예약",
    "During each time window the selected parts change. Where schedules overlap, the lower one wins. "
    "Overheat alerts still show.":
        "정해 둔 시간 동안 선택한 부품의 조명이 바뀌어요. 예약 시간이 겹치면 아래쪽 예약이 우선이고, "
        "과열 경고는 그대로 표시돼요.",
    "Add schedule": "예약 추가",
    "No schedules yet": "아직 예약이 없어요",
    "Press + to turn lights off, dim them or change their color at set times":
        "+를 눌러 정한 시간에 조명을 끄거나, 어둡게 하거나, 색을 바꿀 수 있어요",
    "Name": "이름",
    "End": "끝",
    "Days": "요일",
    "Mo": "월", "Tu": "화", "We": "수", "Th": "목", "Fr": "금", "Sa": "토", "Su": "일",
    "Action": "동작",
    "Turn off": "끄기",
    "Dim": "어둡게",
    "Custom lighting": "다른 조명으로",
    "% of usual": "평소 대비 %",
    "Delete schedule": "예약 삭제",
    "Schedule {n}": "예약 {n}",
    "Every day": "매일",
    "Weekdays": "평일",
    "Weekends": "주말",
    "No days": "요일 없음",
    "No parts": "부품 없음",
    "Active now": "지금 적용 중",
}

_TABLES = {"ko": KO}


def _lang():
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(var)
        if val:
            return val.split(":")[0][:2].lower()
    try:
        return (locale.getlocale()[0] or "en")[:2].lower()
    except ValueError:
        return "en"


_table = _TABLES.get(_lang(), {})


def _(text):
    return _table.get(text, text)
