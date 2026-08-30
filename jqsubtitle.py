#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# JQSubtitle — Just Quality AI Subtitle Maker
# Copyright (c) 2026 JQ Park. Licensed under the MIT License (see LICENSE).
"""
JQSubtitle 1.1 — Just Quality AI Subtitle Maker
(구 SRT 자막 생성기 / JQSub 후속)

- 음성/영상 파일 -> SRT 자막 생성 (whisper large-v3, 문장 단위 분할, 단어 실측 타이밍)
- Claude API 키가 있으면 교정·문장 분할·번역까지 자동 (없으면 받아쓰기만)
- UI 표시 언어 7종 (English/한국어/日本語/中文/Français/Português/Español)
  * 첫 실행은 English, 선택하면 config.json에 저장되어 기억됨
- 메뉴바: Settings(_words.srt 저장 여부) / Language / Help(빠른 시작·문제 해결·정보)
- 각 기능 옆 ? 버튼으로 상세 설명
- v4.5: 음성 인식 결과가 0개면 빈 자막을 만들지 않고 경고 표시
- v4.6: 파일별 에러 격리(하나 실패해도 끝까지) + 마지막 에러 요약,
  디코딩 실패/무음 시 ffmpeg 오디오 추출 폴백, 캐릭터 이름 -> AI 추가 지시 자유 입력칸,
  빠른 시작(엔진은 실제 생성 시점에 로딩)
- v4.7: 상단 소개문 제거, 음성 언어 목록 맨 위 '자동 감지'(기본값),
  AI 추가 지시 칸 확대(5줄 시작, +/- 크기 조절, 전체 폭)

- v4.8: 음성 언어 선택 저장·복원, AI 추가 지시 칸은 회색 설명문으로 시작
  (사용자가 직접 입력한 내용만 기억 — 자동으로 문구를 채워넣지 않음)

- v4.9: 출력 자막 언어를 Claude AI 섹션 안으로 통합 (③ 번호는 Claude 섹션으로)

- v4.10: Claude 체크박스를 끄면 섹션 내용(API 키·출력 언어·추가 지시)이 통째로 접힘

- v4.11: Claude 기본값 꺼짐 (켜면 그 상태를 기억)

- v4.12: 이미 자막 있는 파일 건너뛰기(Settings, 기본 꺼짐), 진행률에 현재 파일 표시,
  완료 알림음+창 깜빡임, 파일 목록 펼치기(추가/제거/비우기), 드래그 앤 드롭

- 1.0: 이름 JQSubtitle 확정, MIT License, 메뉴에 문의·후원 링크
- 1.2: AI 엔진 3종 중 반드시 하나 선택 (Gemini 무료·권장 / Claude 유료 / 로컬 AI 오프라인) — SDK 없이 REST 직접 호출,
  엔진별 API 키 저장, 기존 Claude 키 사용자는 자동으로 Claude 엔진 유지,
  자동 업데이트 확인(시작 시 GitHub의 version.json 조회 -> 새 버전이면 팝업 -> 교체 후 재시작),
  제작자 유튜브 채널 배너

실행: python jqsubtitle_v1.1.py
"""

import os
import re
import sys
import json
import time
import threading
import subprocess
import shutil
import tempfile
import wave
import difflib
import random
import webbrowser
import tkinter as tk
from tkinter import filedialog, ttk, messagebox


def _register_nvidia_dll_dirs():
    """pip로 설치된 nvidia-cublas-cu12 / nvidia-cudnn-cu12 등의 DLL 검색 경로 등록."""
    if not sys.platform.startswith("win"):
        return
    try:
        import site
        roots = set(site.getsitepackages())
        try:
            roots.add(site.getusersitepackages())
        except Exception:
            pass
        for root in roots:
            nvidia_dir = os.path.join(root, "nvidia")
            if not os.path.isdir(nvidia_dir):
                continue
            for pkg in os.listdir(nvidia_dir):
                bin_dir = os.path.join(nvidia_dir, pkg, "bin")
                if os.path.isdir(bin_dir):
                    try:
                        os.add_dll_directory(bin_dir)
                    except Exception:
                        pass
                    os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass

_register_nvidia_dll_dirs()

APP_NAME = "JQSubtitle"
APP_FULL = "Just Quality AI Subtitle Maker"
VERSION = "1.8"
COPYRIGHT = "© 2026 JQ Park · MIT License"
GITHUB_URL = "https://github.com/i3luegirl/jqsubtitle"
ISSUES_URL = GITHUB_URL + "/issues"
DONATE_URL = "https://paypal.me/jqpark"
MODEL_NAME = "large-v3"

# ---- 자동 업데이트 확인 (1.1) ----
# version.json 예시:
#   {"version": "1.3", "file": "jqsubtitle.py",
#    "requires_reinstall": false,
#    "notes": {"en": "...", "ko": "..."}}
#
# ★ v1.2부터 배포 파일명은 버전 없는 "jqsubtitle.py" 로 고정한다.
#   설치본도 원래 %LOCALAPPDATA%\JQSubtitle\jqsubtitle.py 라서 이름이 일치하고,
#   apply_update() 는 실행 중인 파일을 그 자리에서 덮어쓰므로
#   버전이 올라가도 파일명이 어긋나는 일이 없다.
#   version.json 의 "file" 값도 항상 "jqsubtitle.py" 로 둘 것.
UPDATE_RAW_BASE = "https://raw.githubusercontent.com/i3luegirl/jqsubtitle/main"
UPDATE_INFO_URL = UPDATE_RAW_BASE + "/version.json"
ICON_URL = UPDATE_RAW_BASE + "/jqsubtitle.ico"
ICON_NAME = "jqsubtitle.ico"

# =============================================================================
#  채널 배너 (v1.4.0)
# =============================================================================
#
#  ★ 이 프로그램의 목적 중 하나가 채널 홍보다. 배너를 줄이거나 빼지 말 것.
#
#  ★ 그림을 파일로 내려받지 말고 여기 박아 둔다.
#    첫 실행에 인터넷이 막혀 있으면 배너만 빈 칸이 되는데, 정작 첫인상이
#    제일 중요한 순간이다. base64 로 들고 있으면 항상 뜬다.
#
#  ★ 3장을 돌려 쓴다. 켤 때 무작위로 시작하고, 파일 하나 끝날 때마다 다음 장.
#    같은 그림이 계속 뜨면 사흘이면 눈에 안 들어온다.
#
#  각 항목:
#    img  — 680x116 배너 (PNG)
#    edge — 배너 왼쪽 끝 2x116 세로 띠. 창을 넓혔을 때 이걸 가로로 늘려
#           왼쪽을 메운다. 배너 왼쪽 110px 을 이 띠로 균일화해 두었으므로
#           아무리 늘려도 이음매가 안 보인다.
#    bg   — 캔버스 바탕색 (띠의 평균색). 만일을 위한 보험.
BANNER_W = 680
BANNER_H = 116
BANNERS = [
  {"bg": "#A09339",
   "img":
    "iVBORw0KGgoAAAANSUhEUgAAAqgAAAB0CAMAAAB+BTATAAAABGdBTUEAALGPC/xhBQAAACBjSFJNAAB6JgAAgIQAAPoAAACA"
    "6AAAdTAAAOpgAAA6mAAAF3CculE8AAADAFBMVEWag0GXeUaohTyUgj6mhkiXeDyndkeXiTyTfD2JdkaHdjqGaTl6dTeGZ0d3"
    "Zkh4aDeXaEaneFaXZzmIZyx1UDFyaStqYjVrZShnWTZlWytaVShSTi9aRjdiWiiHWjZ2WUaXeFaGalWValaHdlllSzelakaW"
    "hUaYhlenhVedkkWpllWMilV8g1FyhDy3hldSThx7gnOeol+WkmuJg2iYhmiWeHateW3HlojVqobls4nlsnKzp3Spk2pbZHNb"
    "YktRVmlnWVZ2aGaGaWZ3aFaminRpV0eGWE2iWz3Ee1ZmOiSAfSl4eCZ1dElQTU8+RCY8Q1BmaHZzWGu2iGbHmHbFqZW4ppiw"
    "q5OPiDCLgjVpaEhVWEaualOnemXVl2fjm3DOkVOncDtpZWZdb4FyeIeSd4qHdIWnmZa4pIeml4iplkeTizGCdi60eki0o0S4"
    "hUqjlTackTOckjummDusm0O0oUm1e1XGi2XFiFjXp3fNrHK0pFW5pkrLrFnHlljUuGXcwmzWp2bIlWbpyIXuzZDs0Yf02Zf2"
    "4J/r0Kf55LL45cn78dq2lGm1mVRsck+WeWTOiW/UmXaniGeolXZxUE+APiCkXEEyMjQuNkN0a3SEWGi4mYaHeXawnz+1inV5"
    "d2W3l3YfLkCPaXOtk46WlZinpKnnnIVnWWaLWDCYjjKmo4rZxajItpe1lUnx0neGeWWZlIirmz6YlHeUiofXuJbOw5T/4IJI"
    "NTOJlaeMmq53d3aJhoijk0KOj5a1r7DNxraym0qqkz53dlhqZliIi5ajlTmYiHbHurewnUR+jqJ3dSp5hJPHp4ici0LX0NDQ"
    "tYqne4SbpJGYoay3qKiRiS6JhnbizLeWm6apnKTXxrihjEPJsqu5s7bnyXjHtaiKhC3Uu6fWyshYO0WlqrevwdLn1sjq49To"
    "2dLx7OL36Nbv2se2usnz2rcrGBnJw8nEvcNIQRujssaktMicrMKZprdHRRqPobVEPBiesMf69eWFgSvp1Lp1dSZ8eyj4+PP+"
    "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"
    "r89evIg89+LZz0+edDmqPcz/w4fdi/+F8B8ewJpHRbgaDxJUxPxeVfX5Dub9+kXAxU4RM1BnhYcv2SXSwH1q7FlV5VhfX15u"
    "I9I3MzMLtbHx80uj1lgTI/RkcnkY7lB4qBfHLs7Myh578TtqHBB0EaZ/HzmpK/etGLNi5cpV3y1dujycWqYuz8oUNHX3uHFU"
    "UrUMH5UFDJ9FC5YsWJCxgD4KZFm7l0VLCA1mJQXIMmnLbjbDlsknJLePyOy5zO0w4cnyL1uihJnSAkXur5dy7rH/EoXl3r1E"
    "oGcZ8y93f7eADrNkN19iuQYfVSwjF+179mTWElrU6HyqSa5ob+zy8sBTQ8rQ+fTpUw7q4E6af6opXMdSxqlw2vcsmGATqYug"
    "ogxOSzZdC1oJ0wzyCKiaHrf9JKlexr5eFOqzetR5Jr4meRUg1QmSum5dih6Z/pTUj/2o9bxfHJX6y/RMWFsWbR1NzZF2donq"
    "OoOMtL3Y7+yYV1zs4JhHbaE9wXtgUGpQ0PpKE/JPx29wvFQEUGetz7bJnREw2c1txgxjejDFC/2/CFWSCt80Cphefw4f9fnz"
    "Zz//+uuvL14cOviiHaQSpm0Y/uKpMkYxvXdPEf0/YLp6wzuvyssLrJ728Kxy8JZKdPvF+aXZEKjUCupU2sleon5GvtpUYdWz"
    "ql7uLVbTB6ni0Li4tLRwBqoEf7MeaWpONgjNzslO/24soqmgxos0XLw4dt9YTC9SndSlS7MyQepyjLOYA0CK+t13u5ftZqD+"
    "96R0+kgk2S9dt0iYObqgu2UlTe2KXPgyzc5D9iUckbMLFHmInbOKzJafMDmzWLDkO6Xl3g2N73F0HGXR7u5rcB3Ka/s6Ex7A"
    "EjgCTJqfDh5MtfeHwF0xNBwwndZ1UpMpdsBBgw0pTVf4rxYKA0HbjiocjwwqyCVAida1bCBv1ZJpqp2lq9SePFR7RTDFfFQJ"
    "lU4x058HOulxP0gNDYXtSwuHoM6alRZnRsWoYhMtbS1tdW1/zdyR1lYW/jozasuuVsfm11TvrefJ0TEvz7PCsdTZGQrqbEI9"
    "Q1Q4OnmvKw1al50jE+W6UYm/2wwjH9+Cgs8LWEGqkxNx2tr67NnzQwcjzx988YJENfLMwRcA9dkzkHqw6dnjH7j5b/tLRPVQ"
    "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"
    "d6V3yyWlojrDYY1uubTOef16eqI6JihoHUClH5HI4VQKKUnxJZACBsEfcCPiEut47jfbB9BXMoGSgIVEthZ0JSqPk8gPYJGY"
    "wBQP6NQl7AHKTCETH5zoJLb3uLx68Ob1vRgurInJCWTQcT5kxw4WCxmIlB8HBkx08Ncd/qOYcCZkjPozMTFhYRLLTWAeZbNJ"
    "Fm+2/0FfiSwlJLIZSDC9hKXObshIYpbJaOI2NssElRzYRKWgUjRFz6XovQtMUQO53Z+VNQuSmh3oaiMnnQSqV23Bapkt81NN"
    "q1j7EmMTwGpsTI8KpA72hKmpqX2Vtak9BtPcXO1axP20TVLrPpM4nellKpHLJJ7Gp90PHyFOmaIeGAFSEfX7hq77mBVP6ev3"
    "N2T1+0cNHdJ0+dC5800Atenc+V9/+eHxDz9fn+3uLujpv/41h1yBCRMIVKG8v9vTfl7Hn1n+1tYGhinrjeLePdajz/0TIdHR"
    "za0dDFRo6us1D4MhqQpSH+ZrafnqDNfpJxKJHB2joi45hoURquvWb3Yuqgyj+l+BNnokqOx1vSmyONYpBTX9m8X66FveK0JV"
    "VaZKrzPIyrKx0UshRSVSnVsAKVgNqXR2puf+GJzXg9QgwfQjHa3rmfhywqvXCEpc3mTUJVy89/r1tUWJTEgTMXmDBFohTqRe"
    "b6adeP26I6OuLuMV/6Z08cGbB/sB5zLaNRmZX917vcYl48Hr3y4Conlv4KJCAV+9OTHa3/YEHckFGfH1ZkcC0N/B8j/Yn5Ag"
    "fHe8hga6vHFhp56eiLXXEt/sT6Qz3rNLpOU3Dy4Cuv0PXt/b/+ayocu9N3Q03Bdsjm1589t+C1x0ol0HXSZ2ukeHBqf7f8Om"
    "RL7ezrzL9INTUyaoMP3ZNrD82VmzIKupiKtsXOUODoKk2sJFtS+DaFKZKpWVUnfnWiaYSEwlRCfyQW9NwSzsvra/v4Q1vZab"
    "1BoBVGiqj5dE4iDPM/aYbWtLijpnyvjxPjMP+BSw9ld6TtSBFZWV99/6xygS1VHW1+GhnmOFqJGHfmaCOneLu/vkfwlpDngE"
    "qFFdj6b4synB+LcJoN7Z2XCClalSYT+9LY1AfXC/Db5q8+2ONb8pbP+JbqCu2Wms1c/XSEsDd7Cjd01NVBSBGmezbn2rc3BR"
    "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",
   "edge":
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAB0CAMAAACYExPKAAAABGdBTUEAALGPC/xhBQAAACBjSFJNAAB6JgAAgIQAAPoAAACA"
    "6AAAdTAAAOpgAAA6mAAAF3CculE8AAAA4VBMVEWbgEGaf0CXf0GVfT+TfT6Ufj+UgT+VgkCWgz+YhUGbiUCdi0KfjkKgj0Oj"
    "kkKllESplkSsmUetm0SvnUawnkWyoEezoUa0oke0o0W1pEa2pUe2pUW2pkO1pUK0o0OzokKyoUGwnz+vnkCunT+tnD6smz2p"
    "mj6nmDymlzulljqjljuilTqhlDmilTijljmkljejlTailjahlTWfkzOekjKekTSdkDObkTOakDKZjzOYjjKWjjKUjDCTizGR"
    "iS+PiDCMhS2IhC2HgyyFgCyCfSmAfSp+eyh7eyl5eSd4eCb///9WIjtRAAAAAWJLR0RKHgy1xgAAAAd0SU1FB+oIFwceG93e"
    "VhUAAADFSURBVBjTdcnXEsFQAADRVaNG7yQheu9E7+H/f4jLnfHCzHnZWQCHA6cTlwu3W/J48HpRFHw+/H4CAYJBQiHCYVSV"
    "SIRolFiMeJxEgmSSVIp0mkyGbJZcTsjnKRS+ikWpVJI0TdB1DEMol6lUME2qVWo16nUaDZpNWi3abaHTodv9odeT+n0Gg7+G"
    "Q0YjxmNhMhGmU2Yz5nMWC5ZLybJYrViv2WzYbtnt2O85HDgeOZ04n7lcuF653bBt7nfh8ZA++fJab09MBiQfCLvbsAAAACV0"
    "RVh0ZGF0ZTpjcmVhdGUAMjAyNi0wOC0yM1QwNzozMDoyNyswMDowMOkrXGgAAAAldEVYdGRhdGU6bW9kaWZ5ADIwMjYtMDgt"
    "MjNUMDc6MzA6MjcrMDA6MDCYduTUAAAAAElFTkSuQmCC"},
  {"bg": "#C5A874",
   "img":
    "iVBORw0KGgoAAAANSUhEUgAAAqgAAAB0CAMAAAB+BTATAAAABGdBTUEAALGPC/xhBQAAACBjSFJNAAB6JgAAgIQAAPoAAACA"
    "6AAAdTAAAOpgAAA6mAAAF3CculE8AAADAFBMVEXb3djb3tTe4uO3xNHe4NLMycjf4dzd3M7Nyrvi3cvb09Ta1cTo2sfc1cLT"
    "zMHY0rzIxLfiuKjNtam0vsjFuaawsrOit8iarsGXqLenp6WTnaWWoamboJ+OmaOXmZqWqLadscKdtMmlu9LRuKjw1bH116X0"
    "zJrquIfVuIfUq4XVqnXMqmzUq2rZtGjkuWvlxHn42FnmuHbzzHb21Jn414f0ypTzxon54Zn35Kj57bf98srz68zt6NHm2tX3"
    "6+bx5dvy3sj26NP47tz689b68tz8+OP8+uv7+vL+/v3UyLXUuJXJqIjIqHfFm3XFmGfUsmvs0IrmyIb48uTj29S5l2bKpmbn"
    "q1flyZXvuoz25LXs3bPr5dL15sjj3MTKxLPTzLuknJfBnom3iWW3hVi3k1rrrm7z6tySkYjd0Ku1jlK8mVzJsm3NqWPSq2PS"
    "qF3lq4PbvHvlqHnlyqXi4dLKq5vVxqnapUvUtXbr05jg3+Dm2be4sqe3mXariVmshmbEomT1yJT+4IL74Izt4bnz69LDo2zD"
    "mla3hUvy47zk4M3GppXKwaqphVCphUy9oWrLo1y5kk7EpHLXmXXs6d3r5NvMq5OoelXGoVuxik2uh0yukW3j3dmoo5eii1fH"
    "iGbimFL67fC1nYrHhlnbunLWlmjTkFHn6N7Ks4jMs6K0gzPs5Mfr5MypdWamgU2odEiYYzm2eFbRq5e0eWahfEqeeUm4kVS1"
    "d0jjmnHi5OHGe2TJtZeTblHq5uHk492mZziceEfGeFHRjzKmZ1emZ0aYZ0SOh3NcW1PdwXttaV2ZdkmUZDGTbFnGcza5o3hz"
    "a1Xx5cLTimp5VS+KWDWsbDHMsXa+so22aDnp1qa7sprNwJpdVkWsooqtnX23qZWKUyyjaB6QVUWypIuVWjWzqZSlWy/YxJbc"
    "wYe1a1OonYmXVimza0dXSS2TTCa2p4eYWUaHSCR0TCyQSzeFQx1tMx2lbGJ5NhdtKxKEOheFPSK2kFOmUBmrnoOYRhWMNw6a"
    "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"
    "2jioRlq0Voxt1G+PH/ggN0mlqyCotPl9FbWmud7t8WMdc6vxrL0HnyTW+LeRlPaBOsPH22TvgQMP+6RcqCk0dY78ZAyOwXZM"
    "3x07kgJ2oMVgGyAeAH3U2NxYqir81Nh6FlJVXcqQ2t216W/YZEiTJpDTyc1xKpAq/7RxowLJSkFJCwpg/gHqwYMLGVKJ7R9J"
    "Rf0zzb8m9TWjIuU1nZiyBfUvNPz4MDNV07G587AZcWs/Yby/5+Senfmndq4Gp6t3LhaBnfUPbOIzSvP3IJqKj88ryYsvjAej"
    "8z/OgpsKVrf137jts6z9I9gr5eHV29O7pefsEduY/W/pA03t2jXIGkht2lTkF3Jg3bpX1nWeNs2w/es6KxGN8ceR2UijQk1T"
    "ExhDBSksg2S4lKUS1Wr8g6uG/i8NTOnWTdWs2MXGziVKeqvb3KoX5r5839rSbL9d9RmH//CVt4HI6ePHLXkA8FzuUX7ieLWX"
    "klLaLzXkVMf6SfYmAfVMbQHTXhPKeApnPh/o5g39TPrA0uZ4fJBmPfXwMakTb+EyLW2BnH2etCNtR0DSjiSQGVAnJiBmRwyI"
    "hbKiwfTnktV6cFSJKiN/DvNTff7KRa2tBBWKOoQ+KvRUcdq8+fbm2xuLrS9QYVRygTQ5HjZMnFRu/jwUpv/N15oNff3PQ9/4"
    "s8pRvWbt5pew/y3h9C0oao23IKh/a95g0krq6Sdr187YnVGSl5d/6tTHy9YsG71n1qy4WbMyZpLTmRl78svi4+Lj55fkl8yn"
    "h5pVOH8bRHXjtiyYfZxu7N/O3YOsenZsidbB5e/bNjLw90ZAFeRfTzqkNqFVDynadIBwTqN3Os0SR+kwykhM+QcyK0W77wdA"
    "E6ioxpIQFPSbgMroCLBYflWiqhcRWrvY/9zm/ufrllu5L93zfek89ze/NXcO5Ov4cRtFrVbt2PETx48pUGupKF/7qIJpjMY0"
    "W+X5s7MNUBlbpdEjTdKeqo+HBca5pqQYQ0E/oKIetwF16esmdeCYlAQWTR3l7Mw7kNSAmKSAGNC7A8Y/pg4hJbc7cnPr0fjX"
    "k/8J9evWFU11rC+p1FFSkArTL6A2BKpQ08nQUyxDmi9atJ2o0jVlNCWYKlBxdLZg4cJhw4zYH5y+1ux1OgC0/a9JX/9rr2lN"
    "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"
    "f73z5a8//8z139hUoZSgCqVPvnkiZanSQfWZzNnfH5iS1//y8HKDnA7u1GlwIAMpMf3EVLpQpx2oxbzpDt9OA7WNtzbLKdS0"
    "Q6vZkyclmSUxUMtCaTY1tUjE0mhm8/TtYT26DxZntEimAsDHxPSUGpbin+rPN6eplwdaQD15MvN3GQO//xN7/29bng6moKer"
    "BVO6qKukMAWgSg0VSIWgVrp+KBlUmv2ozExQOlyklZq6SgKq8YnjmKPa0la+dA+U4kM1vXAvp/y0DAYMm+KCX3p3Svk9Vq9C"
    "U+mptpSgSvRSC+klZrDu3p0KT5Y+7V2mCu5aZdXoNoBTIKBKYgoeKiHtuZSZCWX+lypZfczIn4X+Mrj/8VcM9q9eAKen16t3"
    "pK2/fv1QgUT9yQAzOYVL45RkwoqAiomqHmFh4aBzd5yoaPyu+F1x8TT9eVI4zS6qOyKpuj1l5+qdB4D015+1kv7bltWLP9NF"
    "vf+MpML6E9OLEkRtHNFfC2p/d4b7PuDUN7gL9DQkpKjI0s0PNYUkJnQJ7jQ4wMJpC+t2qiRPAWr0gOgWARzkJ92rqhQgOztJ"
    "BBWy6Wd0l8K0Bzr2mLTDlG4J+WUYKydYs0xIoV6HxjdPW0DdeSoz84hyU19uO/8XQvm/bwzY2NXPvv5l8yTkX0XLr8J+eKmM"
    "qMrdtkzplZgomf4oELqWZj9zbSZQVaI6Zsz7S99f9X6idKS23SIzAkmJ4L3e9G/h4ebkVFpaL44HePfde5ZCaxV1XeJ2qigp"
    "86yEk5BTkO+C6XtTZTy2ekgEVyYVunePhr9Sqg8B6nIsIPXa0qVKT6VzCoSe5ihUPVcKSYXRvyrA3hY39Toif4RT23U2FYgm"
    "X09OaZpMHzUFQVVjtIKFw84ePAiLzzdPxski/mn+Hc7sf+qWZvQOXdVfxTulvN4BrHfu/FzV7n92kW/05Qw/UFXp7L/4mXpb"
    "z/4R/f9OUGH4vdp7DwxmT2iXboykIjdtUvNKmpPMMSZTanAn5k19BqrRpAB0Uivj1WmzIaSw+Ij2B/RwrFdUrCHNzq5FSTWr"
    "khURVgT1kUGRnF+lCMa9b0yRDLEWoWUHKrOn8j601GB5JWqqemkwQM3XCO7MP3kKh/lVDLjEUflV4f2/QvakRFN7di7ZucYo"
    "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"
    "AAAASUVORK5CYII=",
   "edge":
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAB0CAMAAACYExPKAAAABGdBTUEAALGPC/xhBQAAACBjSFJNAAB6JgAAgIQAAPoAAACA"
    "6AAAdTAAAOpgAAA6mAAAF3CculE8AAAA+VBMVEXb3djb3tbb3tLc39Pe4NHf38/h38vj3cTl3L3j2rvm17Hl1rDo1KTl0aHm"
    "zpfiypPjyIfgxYTgwn3dv3rcunLauHDWtGrTsWfTrmXPqmHQp1/OpV3Mo1vLolrKoVvLolzJpF3Lpl/Mp2LOqWTPqWfRq2nS"
    "r27TsG/Tr3HTr3PRrXHOqm7Lp2vHo2fDn2O/m1+8mFy6k1i4kVa3kFW2j1S0jVK2j1K3kFO4kVS5klWzjFGxik+viE2rh02p"
    "hUungk2mgUyjfUuifEqhe0mgekifeUmceEebd0aeekmfe0qgfEuhfUqifkujf0ymgk+nhE6ohU+phlD///9NoHHeAAAAAWJL"
    "R0RSDWAtkAAAAAd0SU1FB+oIFwceG93eVhUAAADYSURBVBjTbcrVDsJQFETRjUtx9+Lu7lLc4f9/ht6kCTxwsh5mJgd+Tqf7"
    "T6/HYNAYjYLJJJjNgsUiWK3YbNjtSBIOB04nLhduNx4PXi8+H34/gQDBIKEQ4TCRCNEosRjxOIkEySSplEaWSafJZMhmyeXI"
    "5ykUKBYplSiXhUqFapVajXqdRoNmk1aLdptOh26XXo9+n8FAGA4ZjYTxmMnkS63qqL5Np8xmzOcsFiyXrFas12w2KArbLbsd"
    "+71wOGiOx28+nTifuVy4XrnduN95PHg+eb14v1UfNTgiXVvThZMAAAAldEVYdGRhdGU6Y3JlYXRlADIwMjYtMDgtMjNUMDc6"
    "MzA6MjcrMDA6MDDpK1xoAAAAJXRFWHRkYXRlOm1vZGlmeQAyMDI2LTA4LTIzVDA3OjMwOjI3KzAwOjAwmHbk1AAAAABJRU5E"
    "rkJggg=="},
  {"bg": "#CD9A72",
   "img":
    "iVBORw0KGgoAAAANSUhEUgAAAqgAAAB0CAMAAAB+BTATAAAABGdBTUEAALGPC/xhBQAAACBjSFJNAAB6JgAAgIQAAPoAAACA"
    "6AAAdTAAAOpgAAA6mAAAF3CculE8AAADAFBMVEXozcP1ycjjzMXm0MXmxcTn1MnYx8flxLnducLbtrjju8HkvLvmuMPVqbXk"
    "ubbYxLjYwq7WuKjItKjJo7PGm7K5lqq4p7ezj7DGmaq2kcezrszIubfHucTZytKzqbGomqW3iZescLCnl5exd4uViZSwiI/M"
    "dI/JiIXJhXjFeXbThnzXiYXZlorklorHp4fYmJTJl4bbppfHlZnGqpfZp6i2mJe2mYfHiZVza5Nvg59vh7WRjbN8os1dZ591"
    "kcaOpdFtfsBtcayPcKykdcTUbsTSqM7NksXktuLpeMbsjLPUjavWiJXqk47jqZj1qZTzsq72yKbrxLPzx7f0tcvzjcjPcK7N"
    "Vq/x1bn657L218X27dH07Ob55tb4yNf31tbHqajodWyRdIyuVqnjcpLjqqXluKjxyrLoc6/myta4l3eHeYaYhoZvVY/z0avy"
    "zq2Wg3mnlImJV5PMcHDnt5f69fS3qKaJeXV4aW7Rm3nWmHWmiIaQmMj2t5Xry7vRVY7rxLuUe3bl1OCJdWj41Ka4pJiSdWmu"
    "XGOwdW6minauiXDLlXLXqYXbtobIsZLatJjntInoxJjpxarXpHjlq4bVtnfapmjlq1jkqGnSs1jkw2zxzHX62oX3xZnryLTy"
    "r23mtHfvy5BFPENwUHL66JzriXjkp3jTq1XewITo19T+4ILNmXXQsW7UUnD+4IrDmljUlFtcUEzEkmzIlWnYlmbtyqO8oG14"
    "ZVPMiVnQi0nDpkz2p4dZSUq7lGXFmXbUijnHpnfHp2eZg2q5o4u/oki9gzH1p3mSbE/GhVpeRDPFiGZrVk3VimbEpFa4iVe7"
    "i2PKq1n1l3j2todwTTS1iFq3glC7g129nFq5iGa5elmod1jGXC27nVS9oVa6eWfjclXDfFa5k1fEgVTkmWjJhlalakawaji5"
    "eVTLbjbRdE3pklbXiFe1clHRjVy5dVKtcEjvj25RNyjJq1O2dUqZYTrDo1qtVC6NWUT+/v6LUzSWWjc2KimeSxdgKxeONBEp"
    "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"
    "QhttqoZNt9FUpasI3c04qZqFdJMUT5WaygnWO1h07GhsZpCspxcKPQ01DA2jY4UNPGV8NTiTtUUHNrya0VE1oe23sDAHnmA1"
    "ArpqTU7DrWX8FCdPCQ/QZqYgp54ejKWkBcDTfZC7u4CKWNrVtb9m/CGpFwYk5EJQS8t2lqYfqK/ffY6kNhxrqGw4J56p4vTo"
    "0R+uXfvy8rVrlxlP7du2rWQd9LO2sHbzmqQ1sVlZiU0PHlx+sC8vf9u+bfmb8vM3rd+wrCDz3e7io74KSR3xysgRw0a+s7gv"
    "fNSi3NrawuZb3+o81a1O/Z1c1Hi7T9977/1P309Le+89FyrqOE8/f79xnhDUCIZPPXt2cnBwdo5ydnZ2cOjalY85FFCN6AMY"
    "GRlZcg4xS0sgamlk1A4OarteRpY2qY5D4uLs2m3n5BFTfdwGgFR4qLfuNVcR1f3k9Mw9mv/99FGTgjRUleWXiJ9CSlc1JCwk"
    "LJQMI9jS2yvc7VVQ7lX1vc8OuN3756yW/s9A82wJ05SV9+t0Oi2CDE0tyiGoSRsjghHyAdTIFPqnnJZDKsEapcFgVMx9sAiq"
    "BdWUeppCOkVXQxS2gqjFM1TNOlJQKakdBVVt5asjFRWkAlJDmn/R01BOUUBOTckm32puAjmlqhJREwvzcAsfE6Aqvf2xMuEf"
    "IKIaTlENb3VSdZbf3c2d+an+zE65wEuloNL2z5+fmJuTfrmudGcJ9FQrdFHPnbvQALOP5e7do3evQVDJ6oPL3++TUlKyjoKK"
    "31rsxtjY2Nz0prsP6q7tW5dfAlo3bcvb9PGGZCtl+FU8xWekzRiZ5nvjRk0zQ6j99279IKDeuNLs4vSek4sTJ+R/7/3330t7"
    "Dy+nNBeXmVRUdqj1DDfQN+hgYhcHSjkJpqzOzjH2XRWqPXpxaycFSmppCWQNhVwjjnoDq0DV0lCCqkD3rTVwUG/evAfLv3lT"
    "LQWVpG5l3D++lkNQQWpgSGsuVdNSHCqhBaVcAepeFGz27VWFx/tUZd/enbrjH3/cu7fNDc/Y3funhGqc5jMBe/9syc5burtL"
    "aP3Z8CXGPyk7mE/RDA6OLAgJIafBBQXAlIvacb6+YKWb1FO1TVHHilFCm2Khk9SOOlEVd5Ut0OzXQ1WVKQHgGuCcsbGBQYrM"
    "6cbHxIW1h93XDzUAqB1NzJicQtwFSTWXjoLskkXDb+JjIv38fRSmoFWNTBFpDVdpKk9tZfF158Mk+sFF5XP9GE9J2A8P1aMo"
    "sfo6AqTS9NPMSp1m1E9Ozx2jf1qHiP4urD7tPjb7EPsf3bftSxHUwqxaGv6NGzfGZmXsvXP3xgOQum3fPg5TWffhhqA1PboK"
    "qa+qaGrkyHcA6oMbNTX3cmuzCqtyym410fZnuJNSp/dksIiL06dkNY2KOtHXb9xYz7Genqawvh3s4hydZ8wZJiV+WHz8sOjh"
    "wyGtjo4ODnEOMPCOqUeOpDqujrO05GzM8FXbxTk6DhkSN81olmEvOqw2Rts5IU9Ibr+arRLzg1Jyun//GZ2kVon5D1JPmwqT"
    "Z0uK2Q/RQRoyN2QuBBerHqm7ckUIvNKm/mflSutGgaq2Sn/b8LpXXtBoVu6fOHH/KjS6RF3BWxhWSTg1PjY2CMbfIjg4JJKD"
    "/kMKgkPgpxakhKi5uYJ19p9DosGnUEtMLQRTLCkppm2K6Cp3OGumK3wIAGS1o0irnAC7ZgYp4BJeafv2FFP9UD09+BvGVGXm"
    "Y2ntuQGwgcoB4BwsHJBiYRJBsx8BL5U9/gMiqKcRMP1MBviHewa0GUnt5eYroLr0V6WRGaomCGpR6fnrCJBKd5+uFxcVkVTl"
    "uZU0/NfuPrz64NrROuGUm6ZriP1FUdfl5xex32UWTT9LUdPtn6G6JevYpXrTzZL8TZs39rCVwdPvvvqXd0eMYDj1jhNAbarB"
    "77u2tgjeYXNzc35VoBcMv9N7Lsr0f+oCTD91SiO8E33HwfCHm+rrdbSLswWmC+fA5sP6j3CWJwrExy+cEz08OkqV4Xtijtjb"
    "ycBhOKrb2/V0jnJESY2bBrvfziY1Nc5G7H9oQDPD/ZvN95SDClTpo57BPje3VjP+IWFsPaXdx5qicRokbkGQ7PX+hMYrbai8"
    "0kqv1Pft1bZty4//Ee29VyVh1fZOsf3wUiXwT0rKzg6yCIqMDAkMCi6AF8ClIFiJKVYWToPKqqmpCGyKmhWVehpiwclSnkVV"
    "Kc88VTNj7DrKtHVi/zsy5O/YkbQadDQ2NkPkT1HVD9VXT8A0SDGGoOKNJjD7HdgaK6iqeYICzTmzRQQBtfCxiLBWQ/1AZ4Rm"
    "9ZWqhjP299Sm+hVBdeNDU5WHSh/1feb8c3JzSuuu1+wsrq4/B0U93QCTT0GF3T9691jdQ2b7GUdBLh8wohJOS8rA6Vooau2a"
    "jWvKZUxbVkLTg59v4PK6L/fdLFlXsm5T7YaecWoqCvqo8FBnzBg5w+nGDZCaWJWVVZhbVFUI1JNM+zrB9P/dRWYvc3r/vflp"
    "sPyQ1okuE/3G+Q0K19dvZ9K1i4PjjDnOI2y72svTje3t7emtEtY58QujWWLi7GH5QSnntzViXBXnuChqcfQix7hpCPy3W8Y5"
    "UlSnTnnjjXJvELrpjMRSZ0RPt6oGKkhskkhqkL4YtxB9UzN9/UB9uAKBnEFlI65sFJKD9K5ohQTKnuveK88VOafbqat7/7fl"
    "8+ewPk6V1YGaFBsbkQRRDYpA8B8cKS8KJ1BNKRBYcYRasEauTDAjdMocKRaiqyHitfKKqRk8VgPoqgGQhRdAN8BAk1HFqPJR"
    "AW+KqYAKVJOT9RHECadMeVnQ9uM2+qlmnMdSUA2E2Q9nNiACrPqoeW65su0mFi/NSQ3XBFU9o8+XnLqBU7AqpLJtqmlAUW7x"
    "+QunSmpKz9dfoO1HrM8kKqw/4qijiKQePIDV3yfW/xrk9ehRxWlhkbioWXRRN5bHxo7PrblB3T26ruTolzfXbVu3rnBzu7ge"
    "3V96tzWTCifVqXPNg9s3boHUWmhqLsDICgrv+54TUH1v5t8FVRfaf2KKddzEiRb6E0wRQ8HsOzsQUQd7Ps2wh7w497WDfVyc"
    "vb0NpNSyp6gpnFPafWb+OQuz3bQhUYscp9lYtjeycUxNtaT5DwsqBKEqMdWsslNbCWyVuKm0/iGhk/jIPlh9U9h9YAoVDUwK"
    "StIoTUraqNeGx8v/oa6V423OXt73v4H0x71/BPoK3QXmUmHI4DhBU4FqUjBpDbKIDCyIZGYVRPKlNtRSC1ZNLQo4jY/gS20l"
    "nIAW0IWoNECKCrSU8YeSYmOgNiwp9AAMDCiuBqZQVFMYGA4G0kvhBODEXOkxUbWQZ1gzGuMzQhBPydjBCIDKkcTW4ZztlrSO"
    "58jiWMAqogpXpnUWFXdfT3f13DSX/v00088s6oUBOUWlx6/vLSvbXX/+/Ln68w0N1+/WHSOmx+5KKCWe6b4mMCoB1bUHR8Fp"
    "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"
    "WrqpOYm7T5+Hgjbcbni/IY15qdsNVy+wS241+/83Njax+zhRTa/58fIF6a5W7VqaXqYseZE26XQJQqZ9JPVWcw1YLbqXf2bT"
    "mebmSwylLs0nplsTm5We5m/kZBRT9d/UnxAIUNMa59/49NtLn3566VuSCk7nJwZuzPHa7brSabHzR4sXL1qxePFicDqDAdWM"
    "qDlzouYoWFdELyWoSyuZlhpOiLCuiF5RuUJarlAqTvz++/05iIGiIKmDOfO0Sv/rirWjDdyAuVahBYimAKqafIqzTUpCavby"
    "5ctXrBgK4289eNFi/JTKxYvwg1FbWlk5NJM+av3u3afrq0/z0fH1p6t5dPo0qsDvNC6crpfru3GdV+T6gdO4sru6/jTuOs0N"
    "d6cVsKflBF64q/rAbj4+GW+px91ywI8UYkvTmcSRRM7BgyKvKj+OuD9TGvqFVNmWb16jUbqmXNsta1MXMNdwy82a8i1Wa9b8"
    "CZprnt+Ut6mtIYDasdRVwTlUrfizua6xkoX/KKWjq1Z5D8wQXCGnENOBQHXgqkMD167NOHgAxh8uUvGh4hxppAKquTmrcoqr"
    "z5+vZ5tpY2MaFiJ7fjfH7/dn7/VGye0T1Jqay00XLtRXu3JwDqedvgkqb/KB91Xg78a1ayq1WnOTmirzNNykoF6St7bmUJvz"
    "N8sYf32EUxPC01z4DHY4B8CUnFJY508fAB/VbfdKgDosfqHT4jSnxVhIKiRVo5SKGhNdceLEiV2cWqoC6lmBteKYmhOtkrBW"
    "7Prl9//+PZ4z+Ec5ttp+cGqtcYqYXzyAuZYMpuZmj2+dflKpqtfy5UtXxAy2trOZZmPvELWYc4JCWWOi8e1omJ0VC1AJowBZ"
    "fZqlXh7NLTXiVl+vznBXr85qVwVPYa9eO6PuELb5FvV5wuYBfAUUp4rcA0pY4d2WppcWl6bjD3pIUF21KndVbOzHygHQdPUP"
    "ZaNG7mYlsmt0BK95Rp/VM6jbAKmDXfcutSeE2W0+PluoVEha6QC1WiPH2Zlr1ohzuko8UwZP3ChIuTuUs3bgoYFwUw/WA9XZ"
    "8HMOlrLlX30LczJy0k8D1HMk9UIjXpwNld2jm+oZTV1obDzev2kv2PzxStMDXGQ3y6amphsPbkhpQkgP/kpu/PzzD4iuLl26"
    "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"
    "YII=",
   "edge":
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAB0CAMAAACYExPKAAAABGdBTUEAALGPC/xhBQAAACBjSFJNAAB6JgAAgIQAAPoAAACA"
    "6AAAdTAAAOpgAAA6mAAAF3CculE8AAABIFBMVEXpzcTozsTmz8Tn0MXpz8PozsDpzr7nzLzpyrfoybbpx7Hnxa/qw6fowaXp"
    "vp3lupnot5Hks43kr4birYThqHzepXneonDbn23bnGnYmWbYlmTWlGLUkmDSkF7Sj13QjVvOi1nMiVfLiFjKh1fJhlbHhFTG"
    "g1PFgVbEgFXDf1TCfVXAe1O/elK+eVG9eFK8d1G6dlK4dFC3c0+2cVC1c1G2dFK4dlS4eVi6e1q9gF7Ag2HCiGXFi2jJj2zM"
    "km/OlnTQmHbPmXfQmnjLmHPIlXDGk27DkGu/jmi8i2W5iGC4h1+1iFy1iFi2iVm2j1a3kFe6lFS9l1fAm1bCnVjEo1bGpVjH"
    "p1XKqljKqlTIq1HGqU/FqE7DpkzBpEq/okj///96q/I0AAAAAWJLR0Rfc9FRLQAAAAd0SU1FB+oIFwceG93eVhUAAADuSURB"
    "VBjTVcTVUgJQAADRpUFCukNSaemQRrq7hP//DL1P6s6ZhT9JJL+kUmSyf+RyQaEQlEpUKtRqNBqentBq0enQ6zEYeH7GaMRk"
    "wmzGYsFqxWbDbsfhwOnE5cLtxuPB68Xnw+8nEODlhWCQUIhwmEhEiEaJxXh95e1NiMdJJEgmSaVIp8lkyGZ5fyeXI58XCgWh"
    "WBRKJcplKhWqVWo16nU+Pmg0aDZptWi36XTodun1xH/0+3x+MhgwHDIaMR4zmTCdMpsJ8zmLBcslqxXrNZsN2y27Hfs9hwPH"
    "I6cT57NwuXC9crvx9cX9zuPxDVOlJycqi7S+AAAAJXRFWHRkYXRlOmNyZWF0ZQAyMDI2LTA4LTIzVDA3OjMwOjI3KzAwOjAw"
    "6StcaAAAACV0RVh0ZGF0ZTptb2RpZnkAMjAyNi0wOC0yM1QwNzozMDoyNyswMDowMJh25NQAAAAASUVORK5CYII="},
]


# =============================================================================
#  AI 엔진 정의 (v1.3.2)
# =============================================================================
#
#  ★ 새 엔진을 추가할 때 손댈 곳은 두 군데뿐이다.
#      ① 아래 ENGINES 표에 항목 하나 추가
#      ② @engine_call("이름") 을 붙인 호출 함수 하나 작성
#    나머지 코드는 엔진 이름을 모른다. 묶음 크기·대기 시간·재시도 정책이
#    필요하면 EOPT(provider, "키") 로 표에 물어본다.
#
#  ★ 엔진별 값을 코드 여기저기에 if 문으로 흩지 말 것.
#    v1.3.1 까지는 `LOCAL_CHUNK_WORDS if provider == "local" else ...` 같은
#    삼항 분기가 5군데에 흩어져 있었다. 엔진을 하나 더 넣으려면 그 5군데를
#    모두 찾아 고쳐야 했고, 하나라도 놓치면 새 엔진이 로컬용 값으로 돌았다.
#    값은 전부 이 표에 모으고, 바깥은 EOPT() 만 부른다.
#
#  ---- 항목 설명 -------------------------------------------------------------
#   [표시]  name          UI에 보이는 이름
#           key_url       API 키 발급 페이지
#           needs_key     False면 키 입력칸을 숨기고 키 없이도 실행 허용
#   [모델]  model         기본 모델
#           models        대체 후보 목록 (앞에서부터 시도). 없으면 model 하나만
#   [요청]  min_interval  요청 사이 최소 간격(초). 무료 티어 분당 한도 대비용
#           http_retries  HTTP 오류 시 _post_json 내부 재시도 횟수
#           http_timeout  한 요청의 제한 시간(초)
#           retry_codes   이 상태코드는 대기 후 재시도
#           fallback_codes 이 상태코드는 '다음 모델 후보'로 넘어감
#   [묶음]  rebuild_chunk_words  재조립 때 한 번에 보내는 단어 수
#           lines_chunk          교정·번역 때 한 번에 보내는 줄 수
#           gap_fill_batch       빠진 줄 보충 때 한 번에 보내는 줄 수
#           max_tokens_cap       출력 토큰 상한
#   [한도]  quota_guard   True면 한도 오류 연속 감지 시 그 단계를 중단
#           quota_streak  몇 번 연속이면 중단할지
# =============================================================================

ENGINE_DEFAULTS = {
    "needs_key": True,
    "models": None,
    "min_interval": 0.0,
    "http_retries": 3,
    "http_timeout": 180,
    "retry_codes": (429, 500, 502, 503, 529),
    "fallback_codes": (404,),
    "rebuild_chunk_words": 150,
    "lines_chunk": 200,
    "gap_fill_batch": 12,
    "max_tokens_cap": 8000,
    #  context_window — 이 엔진이 한 번에 읽고 쓸 수 있는 총량.
    #    ★ ⑤ 추가 요청이 '통째로 보낼지 나눠 보낼지' 를 이 값으로 정한다.
    #    ★ v1.7.15 전에는 이 값이 없어서 `max_tokens_cap * 2` 로 얼버무렸다.
    #      제미나이는 실제로 1,000,000 인데 64,000 으로 보고 있었고,
    #      50분짜리부터 필요 없이 나눠 보냈다. 무료 티어는 요청 수가 전부라
    #      (모델당 하루 20회) 그냥 손해였다.
    "context_window": 16000,
    "quota_guard": False,
    "quota_streak": 3,
}

ENGINES = {
    # ---------------------------------------------------------------- Claude
    "claude": {
        "name": "Claude",
        "model": "claude-sonnet-4-6",
        "key_url": "https://console.anthropic.com/settings/keys",
        "context_window": 200000,
        # 유료라 분당 한도가 넉넉하다. 간격도 차단기도 필요 없다.
        "min_interval": 0.0,
        "quota_guard": False,
        "fallback_codes": (),          # 대체 모델 목록이 없다
        "rebuild_chunk_words": 150,
        "lines_chunk": 200,
    },

    # ---------------------------------------------------------------- Gemini
    "gemini": {
        "name": "Gemini",
        # ---- 모델 후보 (2026-08-20 갱신) --------------------------------
        #  ★ 구글이 모델을 자주 은퇴시킨다. 목록 전체가 죽는 사고가 실제로 났다.
        #
        #    2026-08-20 사고: 목록 4개 중 3개가 404 였다.
        #      gemini-3-flash   404
        #      gemini-2.5-flash 404
        #      gemini-2.0-flash 404 — 구글이 응답으로 직접 알려 줬다:
        #        "no longer available. Please update your code to use
        #         models/gemini-3.6-flash"
        #    살아 있는 건 gemini-flash-latest 하나뿐이었고 그마저 한도에 걸려,
        #    재조립이 통째로 무음 폴백으로 떨어졌다.
        #
        #  ★ 1순위는 반드시 gemini-flash-latest.
        #    구글이 "항상 최신 Flash"를 가리키도록 유지하는 별칭이다. 이걸 앞에 두면
        #    모델명이 또 바뀌어도 목록을 고칠 필요가 없다 — 이번 사고의 근본 대책이다.
        #
        #  ★ 그런데 latest 하나만 두면 안 된다. 이유는 두 가지다.
        #    ① 분당 한도는 모델별로 따로 센다. 2026-08-20 로그에서 실제로
        #       gemini-flash-latest 만 429 였다. 대안이 없으면 거기서 작업이 끝난다.
        #    ② 503(과부하)은 새 모델일수록 잦다. 다들 최신으로 몰리기 때문이다.
        #       한 세대 낮은 모델은 대체로 한산하다.
        #    그래서 latest 를 앞세우되, 뒤에 실명 모델을 후보로 남겨 둔다.
        #    (일일 한도는 프로젝트 단위라 모델을 바꿔도 안 풀린다 — 그건 _call_gemini 가
        #     daily=True 를 보고 전환하지 않고 바로 포기한다)
        #
        #  ★ 404 가 나면 그 모델은 은퇴한 것이다. 응답에 대체 모델명이 적혀 오고
        #    _retired_model_hint() 가 그걸 로그에 찍는다. 그 이름으로 갱신하면 된다.
        #  ★ v1.7.2: gemini-3.5-flash-lite 를 뺐다.
        #    v1.7.1 에서 429/503 에 걸리면 기다리지 않고 바로 다음 모델로
        #    넘어가게 했더니, 앞 둘이 막힌 날 lite 까지 내려가 거기서 작업했다.
        #    lite 는 가벼운 만큼 문장을 덜 쪼갠다 — 재조립이 249줄 나오던 것이
        #    183줄로 줄고, 자막 한 줄에 세 문장이 들어갔다.
        #    **빠른 실패보다 나쁜 결과가 더 비싸다.** 둘 다 막히면 차라리
        #    마지막 모델에서 기다렸다 다시 하는 편이 낫다.
        #    다시 넣으려면 "그 모델이 만든 자막이 읽을 만한가"를 먼저 볼 것.
        #
        #  ★ v1.7.4: 구세대 두 개를 뒤에 더 붙였다. 이유가 두 가지다.
        #
        #    ① 2026-08-27 사고: 후보 둘이 **둘 다 최신 세대**였다.
        #       gemini-flash-latest 는 3.7 을 가리키고 3.6 은 바로 그 전이다.
        #       사람이 몰리는 쪽이 나란히 둘이라, 하나가 503 이면 다른 하나도 503 이었다.
        #       재조립 2블록이 전부 폴백으로 떨어져 문장 조립을 통째로 못 받았다.
        #       "다음 모델로 전환"이 전환한 티가 안 났던 이유가 이것이다.
        #       구세대는 한산하다 — 후보 목록에 **세대 차이**가 있어야 의미가 있다.
        #
        #    ② 일일 한도(RPD 20)는 모델별로 따로 센다.
        #       후보 2개 = 하루 40회, 4개 = 하루 80회. 즉 모델을 늘리면
        #       처리 가능한 편수가 늘어난다. 묶음을 줄이는 것과 정반대로 공짜다.
        #
        #    ★ 순서를 바꾸지 말 것. 앞이 살아 있으면 뒤는 아예 호출되지 않는다.
        #      품질 좋은 순서 = 최신 순서이므로, 품질 손해 없이 대비만 두꺼워진다.
        #    ★ lite 계열은 넣지 말 것 (위 v1.7.2 항목 참고 — 문장을 덜 쪼갠다).
        #    ★ 2026-08-27 확인: 아래 4개 모두 살아 있다(models 목록 조회).
        #      목록 확인은 `python 모델확인.py` — 일일 한도를 쓰지 않는다.
        "models": ["gemini-flash-latest",   # 항상 최신 = 절대 낡지 않는다
                   "gemini-3.6-flash",      # latest 가 붐빌 때 (2026-07-21 출시)
                   "gemini-3.5-flash",      # 한 세대 아래 — 여기부터 한산해진다
                   "gemini-2.5-flash"],     # 두 세대 아래 — 가장 한산한 최후 보루
        "model": "gemini-flash-latest",
        "key_url": "https://aistudio.google.com/apikey",

        # ---- 무료 티어 실측값 (2026-08-21, 콘솔 확인) --------------------
        #  ★ 웹 검색으로 나오는 "분당 15회 / 일당 1500회"는 틀린 정보다.
        #    사용자 콘솔(ai.dev/rate-limit) 실측:
        #        RPM 5  ·  RPD 20  ·  TPM 250,000        (모델별로 각각)
        #
        #  ★ 이 한도의 모양이 전략을 정한다.
        #      토큰은 남아돈다 — 한 편 처리에 TPM의 3%만 쓴다
        #      요청 횟수가 전부다 — 하루 20회면 한 편도 빠듯하다
        #    따라서 **묶음을 키워서 요청 수를 줄이는 것**이 유일하게 옳은 방향이다.
        #    로컬과 정반대다. 로컬은 컨텍스트가 좁아 잘게 쪼개야 하고,
        #    Gemini 무료는 컨텍스트가 남아돌고 요청 횟수가 모자란다.
        #
        #  분당 5회 = 요청당 12초. 여유를 둬서 13초.
        # 실측: gemini-flash 계열은 입력 1,048,576 (2026-08-27 모델 목록 조회).
        # 답도 같이 앉으므로 넉넉히 잡되 그대로 다 쓰진 않는다.
        "context_window": 1000000,

        "min_interval": 13.0,

        # ★ 요청 수를 줄이는 것이 전부다. 한 편(3,200단어 / 730줄) 기준:
        #      400단어·200줄 -> 재조립 8 + 교정 4 + 번역 4 = 16회  (하루 한도 초과)
        #      800단어·400줄 -> 재조립 4 + 교정 2 + 번역 2 =  8회  (하루 2편 가능)
        #    TPM 25만 중 8천만 쓰던 상황이라 키워도 토큰은 전혀 문제되지 않는다.
        "rebuild_chunk_words": 800,
        "lines_chunk": 400,
        "gap_fill_batch": 60,          # 보충도 크게 — 12줄씩 나누면 요청만 낭비한다

        # 묶음이 커진 만큼 출력 한도도 올린다 (400줄 영어 ≈ 5,000토큰).
        # TPM 25만이라 여유가 많다.
        "max_tokens_cap": 32000,

        # ★ v1.7.4: 제한 시간을 기본 180초에서 300초로 늘렸다. Gemini 만.
        #
        #   2026-08-27 실측: 교정 한 묶음(184줄)에서
        #     [English] block 1/1 failed — kept as-is: The read operation timed out
        #   503 과는 다른 고장이다. 503 은 구글이 요청을 **안 받은** 것이고,
        #   시간 초과는 **받아 놓고** 180초 안에 다 못 만든 것이다.
        #
        #   위에서 봤듯 묶음을 크게 잡는 것이 무료 티어의 유일한 전략인데,
        #   400줄짜리 답을 만드는 데 붐빌 때는 3분이 모자란다.
        #   묶음을 줄이면 요청 수가 늘어 하루 한도를 깎아 먹는다.
        #   **기다리는 것은 공짜고, 쪼개는 것은 한도를 쓴다.** 그래서 기다린다.
        #
        #   ★ 더 늘릴 때는 주의. 실패한 요청도 한도를 한 번 쓴 것이라
        #     오래 기다린 끝에 실패하면 시간과 한도를 둘 다 잃는다.
        "http_timeout": 300,

        # ★ 503(과부하)·429(한도)에서도 다음 모델 후보로 넘어간다.
        #   v1.3.1까지는 404에서만 넘어갔다. gemini-3-flash가 붐빈다고
        #   2.5-flash까지 붐비는 건 아닌데, 그대로 죽어버렸다.
        "fallback_codes": (404, 429, 500, 502, 503, 529),

        # ★ 한도가 소진되면 더 두드려도 소용없다. 3연속이면 그 단계를 접는다.
        "quota_guard": True,
        "quota_streak": 3,
    },

    # ------------------------------------------------------------- 로컬(Ollama)
    "local": {
        "name": "Local AI",
        "model": "",                   # 실제 모델명은 LOCAL_MODEL 참조
        "key_url": "https://ollama.com",
        "needs_key": False,            # 내 컴퓨터에서 도니 키가 없다

        # 내 GPU라 한도도 요금도 없다. 간격·차단기 모두 끈다.
        "min_interval": 0.0,
        "quota_guard": False,

        # ★ 아래는 **가장 작은 카드 기준 기본값**이다 (num_ctx 8192).
        #   40줄 ≒ 시스템 700 + 입력 700 + 출력 900 ≈ 2,300 토큰.
        #
        #   ★ v1.7.6: 실행할 때 pick_local_tuning() 이 카드 크기를 보고
        #     이 두 값을 덮어쓴다 (LOCAL_CTX_STEPS 표 참고).
        #     16GB 이상이면 150줄·240단어로 커진다.
        #     여기 값을 직접 올리지 말 것 — 작은 카드에서 컨텍스트가 넘친다.
        "rebuild_chunk_words": 60,
        "lines_chunk": 40,
    },
}

PROVIDER_ORDER = ["claude", "gemini", "local"]
DEFAULT_PROVIDER = "gemini"

# 기존 코드 호환용 별칭 (UI가 PROVIDERS[code]["name"] 등을 그대로 쓴다)
PROVIDERS = ENGINES


def EOPT(provider, key):
    """엔진 설정값을 읽는다. 해당 엔진에 없으면 기본값으로 떨어진다.

    ★ 바깥 코드는 이 함수만 쓴다. `if provider == "local"` 을 새로 만들지 말 것."""
    eng = ENGINES.get(provider)
    if eng is not None and key in eng:
        return eng[key]
    return ENGINE_DEFAULTS[key]


# 엔진별 실제 호출 함수 등록소. @engine_call("이름") 데코레이터로 채워진다.
ENGINE_CALLS = {}


def engine_call(code):
    """엔진 호출 함수를 등록한다.

    함수 시그니처: fn(api_key, system, user_text, max_tokens, log) -> str
    """
    def deco(fn):
        ENGINE_CALLS[code] = fn
        return fn
    return deco
LOCAL_MODEL = {"name": "gemma4:12b", "chosen": False}   # Settings에서 변경 가능
#  chosen — 사용자가 설정 창에서 직접 고른 적이 있는가 (config: local_model_chosen).
#           False 면 pick_local_tuning() 이 카드를 보고 더 큰 모델로 올려 줄 수 있다.
# v1.2: gemma4:12b -> gemma4:12b 로 교체.
#   qwen3 는 추론형이라 <think> 에서 수천 토큰을 소모해 매우 느렸고, 형식 준수도 불안정했다.
#   gemma4:12b 는 7.6GB / 256K 컨텍스트 / 사고 모드 기본 꺼짐 / 140개 언어.
#
# v1.3: 26b 를 '선택지로만' 추가한다. 기본값은 그대로 12b 다.
#   ★ 기본값을 바꾸지 말 것.
#     기본값은 "아무 카드에서나 GPU 안에 다 들어가는 것"이어야 한다.
#     GPU 밖으로 밀려나면 Ollama 는 에러를 내지 않고 조용히 본체 메모리로 넘겨
#     3~5배 느려진다. "되긴 하는데 이유 없이 느린" 상태가 가장 나쁜 경험이다.
#     쓰고 싶은 사람만 설정에서 고르게 하고, 밀려나면 경고를 띄운다(check_local_vram).
#
# ---- v1.7.4: 목록을 실측으로 다시 짰다 (2026-08-27, ollama.com/library/gemma4/tags)
#
#   ★ `gemma4:26b` 를 뺐다. 16GB 카드(5070 Ti)에서 **매번 죽었다.**
#       llama-server process has terminated: exit status 1
#     크기가 19GB 다. 처음에 14.4GB 로 알고 넣었는데 그 뒤로 계속 커졌다.
#     26b 계열 중 제일 작은 것도 16GB(qat)라, 화면 표시분 1~1.5GB 를 빼면
#     **어떤 26b 도 16GB 카드에 다 들어가지 않는다.** 압축판을 찾아도 답이 없다.
#
#   ★ 그래서 26b 자리에 `26b-a4b-it-qat`(16GB)를 넣었다. 19GB 보다 3GB 작다.
#     - qat = 압축을 전제로 학습시킨 판. 같은 크기에서 품질이 제일 낫다.
#     - a4b = 26B 를 다 갖고 있되 토큰 하나에 4B 만 깨우는 구조(MoE).
#       **밀려나도 손해가 작다** — 넘어간 부분을 매번 다 읽지 않기 때문이다.
#       보통 모델이 3~5배 느려질 자리에서 이건 훨씬 덜 느려진다.
#     여전히 GPU 밖으로 조금 넘친다. 본체 메모리가 넉넉해야 하고(16GB 이상 여유),
#     느린 대신 죽지는 않는다. check_local_vram 이 경고를 띄운다.
#
#   ★ v1.7.8: `12b-it-q8_0`(13GB)을 뺐다. "12b 와 26b 의 중간"으로 넣었는데
#     **16GB 카드에서 오히려 나빴다.** 모델이 커진 만큼 문맥 쓸 자리를 뺏는다.
#         16GB + 12b    -> 남는 자리 6.8GB -> 한 번에 300줄
#         16GB + q8_0   -> 남는 자리 1.4GB -> 한 번에  40줄
#     모델은 조금 좋아지고 문맥은 7배 나빠진다. 24GB 카드에서나 쓸 만한데
#     24GB 면 26b 를 쓰면 된다. 설 자리가 없다.
#
#   ★★ 교훈: 모델 크기만 보고 목록에 넣지 말 것.
#      **카드 − 모델 − 화면 = 문맥에 남는 자리** 까지 계산해야 한다.
#      큰 모델은 자기 무게만큼 문맥을 먹는다. 그 둘의 합이 품질이다.
#
#   ★ 크기는 추측하지 말 것. ollama.com/library/gemma4/tags 에 실제 크기가 있다.
#     이름을 지어내면 다운로드가 그냥 실패한다.
#   ★ v1.7.11: 작은 판 둘을 넣었다 (e2b / e4b).
#     VRAM 이 작은 카드에서는 **모델을 줄이고 문맥을 넓히는 쪽**이 나을 수 있다.
#     12GB 카드에서 12b 는 문맥이 16,384(100줄)까지밖에 안 되는데,
#     e2b(4.3GB)면 같은 카드에서 65,536(300줄)이 나온다.
#     어느 쪽이 이기는지는 아직 안 재봤다 — 그래서 자동 선택은 하지 않고
#     **고를 수 있게만** 해 둔다. 재보고 나서 정할 것.
LOCAL_MODELS = [
    "gemma4:12b",              #  7.6GB — 기본. 목록 첫 줄은 기본값이니 옮기지 말 것
    "gemma4:26b-a4b-it-qat",   # 16GB   — 24GB 카드용
]
#   ★ v1.7.12: e2b-it-qat / e4b-it-qat 를 뺐다. **실제로 돌려보고 뺀 것이다.**
#     "작은 모델 + 넓은 문맥" 이 나을까 싶어 넣었는데, 같은 300줄 조건에서
#     e2b(4.3GB) 가 12b 에 전부 밀렸다 (2026-08-28 실측):
#         재조립  12b 227줄  /  e2b 171줄 (3블록 중 2블록이 검증 실패 -> 폴백)
#         교정    12b 77줄 수정  /  e2b 10줄
#         번역    12b 성공  /  e2b 번호를 세 번 다시 매겨 통째로 실패
#         노래구간 e2b 는 0:00~15:48(영상 전체)이라고 답했다
#     문맥을 아무리 줘도 **모델이 형식을 못 지키면 소용없다.**
#     그리고 위 실측대로 12GB 카드도 12b 를 65,536 으로 돌릴 수 있으므로,
#     작은 모델을 둘 이유 자체가 없어졌다.

# v1.7.4: 모델마다 내려받는 크기가 다르다.
#   그전에는 안내 문구에 "~7.6GB" 가 박혀 있어서, 26b 를 골라도 7.6GB 라고 나왔다.
#   실제로는 두 배가 넘는다. 사람이 그 숫자를 보고 받을지 말지 정한다.
#   ★ 모르는 모델이면 숫자를 지어내지 말고 아예 빼 버린다.
#     받는 동안 실제 크기가 진행률 줄에 나오므로 그쪽이 정확하다.
LOCAL_MODEL_SIZE = {
    "gemma4:12b": "7.6GB",
    "gemma4:26b-a4b-it-qat": "16GB",
}


def local_model_size(name):
    """안내 문구에 끼워 넣을 크기 조각. 모르면 빈 문자열."""
    s = LOCAL_MODEL_SIZE.get((name or "").strip())
    return (" (~%s)" % s) if s else ""


OLLAMA_URL = "http://127.0.0.1:11434"

# ---- 로컬 AI 튜닝값 (v1.2) — 값의 근거는 _local_chat_stream() 주석 참고 ----
# ---- 컨텍스트(책상 크기)와 묶음 크기 — 카드를 보고 정한다 (v1.7.6) --------
#
#  Ollama 기본 4096 으로는 시스템 프롬프트가 잘린다. 그래서 v1.2 에서 8192 로
#  올렸고, 묶음 크기(40줄·60단어)는 **그 8192 안에 들어가도록** 정한 값이다.
#
#  ★ 문제: gemma4 는 256K 를 지원하는데 우리는 8192(3%)만 쓰고 있었다.
#    책상이 좁으니 40줄씩 잘라야 하고, 자른 경계마다 두 가지 사고가 난다.
#      ① 문맥이 끊긴다 — 2026-08-27 실측:
#         #208 'you're a material.' / #209 'Fine.'  ->  'material' / 'mastermind'
#         두 줄을 같이 봐야 고칠 수 있다. 경계가 그 사이에 떨어지면 영영 못 고친다.
#      ② 형식 사고 기회가 묶음 수만큼 늘어난다 (번호 재부여 등).
#    218줄이면 40줄씩 6묶음 = 경계 5개. 150줄씩이면 2묶음 = 경계 1개다.
#
#  ★ 그런데 책상을 넓히면 **그 책상이 VRAM 을 먹는다.**
#    8192 를 그냥 32768 로 올리면 10~12GB 카드에서 모델이 GPU 밖으로 밀려난다.
#    이 프로그램은 남에게 배포하는 것이라 내 카드만 보고 정할 수 없다.
#      "8GB~24GB 어느 카드에서든 같은 결과가 나오도록" — 원래 주석의 원칙이다.
#
#  ★ 그래서 **카드 크기를 보고 자동으로 고른다.** 설정을 새로 만들지 않는다.
#    작은 카드를 쓰는 사람에게는 예전과 완전히 같은 값이 간다.
#
#    ┌ VRAM ────┬ num_ctx ┬ 교정/번역 ┬ 재조립 ┬ 비고 ────────────────┐
#    │  24GB 이상│  65536  │  300줄   │ 500단어│ 여유가 많다           │
#    │  16GB 이상│  24576  │  150줄   │ 240단어│ whisper 3GB 감안       │
#    │  그 이하  │   8192  │   40줄   │  60단어│ v1.2~v1.7.5 와 동일    │
#    └──────────┴─────────┴──────────┴───────┴─────────────────────┘
#
#  ★ 32768 이 아니라 24576 인 이유: whisper large-v3(약 3GB)가 AI 단계 내내
#    GPU 에 올라가 있다. 16GB 카드 실제 예산은 16 - 3(whisper) - 1.5(화면) ≈ 11.5GB
#    이고 여기에 모델 7.6GB 가 들어간다. 남는 자리가 크지 않다.
#    whisper 를 먼저 놓아주도록 고치면 그때 다시 올릴 것.
#
#  ★ 묶음은 num_ctx 의 절반도 안 쓰게 잡는다. 출력이 예상보다 길어질 때
#    잘리면 그 묶음이 통째로 버려지기 때문이다. 여유가 안전이다.
#      150줄 ≒ 시스템 700 + 입출력 6,000 ≈ 6,700 토큰 (24576 의 27%)
#
#  ★ 기준을 16.0 / 24.0 으로 잡지 말 것. **카드는 이름보다 조금 작게 보고한다.**
#    16GB 짜리 5070 Ti 의 실제 값은 15.92GB 다. 16.0 으로 잡으면 정작
#    이 카드가 탈락해 8192 칸으로 떨어진다. 그래서 15.0 / 23.0 이다.
#
#  ★ v1.7.8: 카드 크기가 아니라 **문맥에 쓸 수 있는 남는 자리**로 고른다.
#
#    v1.7.6~7 은 카드 크기만 봤다. 그런데 같은 카드라도 어떤 모델을 고르느냐에
#    따라 남는 자리가 완전히 달라진다.
#
#        16GB 카드 + gemma4:12b(7.6GB)      -> 남는 자리 6.8GB   (넉넉)
#        16GB 카드 + 12b-it-q8_0(13GB)      -> 남는 자리 1.4GB   (거의 없다)
#
#    카드만 보면 둘 다 "16GB 니까 32768" 이 된다. 뒤쪽은 그대로 밀려난다.
#
#      남는 자리 = 카드 전체 − 모델 크기 − 화면 표시분
#
#  ★ 문맥은 자리를 얼마나 먹나 — 대략 16K 당 1GB 로 잡는다(12B급 GQA 기준).
#    정확한 값은 모델 구조에 따라 다르므로 **넉넉히 잡아 둔다.**
#    모자라면 Ollama 가 조용히 본체 메모리로 넘겨 3~5배 느려지는데,
#    그건 에러보다 나쁘다(원인이 안 보인다). 여유가 안전이다.
DISPLAY_RESERVE_GB = 1.5      # 윈도우가 화면 표시에 쓰는 몫

#  ★ v1.7.10: max_tokens(출력 상한)도 같이 정한다. 이걸 빼먹으면 안 된다.
#
#    num_ctx 는 '읽을 것 + 쓸 것' 을 합친 책상 크기이고,
#    max_tokens 는 그중 **AI 가 답으로 쓸 수 있는 몫**이다. 따로 있는 게 아니다.
#
#    2026-08-28 사고: 문맥만 8,192 -> 65,536 으로 8배 올리고 출력은 8,000 에
#    그대로 뒀다. ④ 추가 요청이 235줄을 쓰다가 정확히 거기서 칸이 떨어져
#    14:42 에서 끊겼다. 책상만 넓히고 종이는 안 넓힌 셈이다.
#
#    ★ 출력을 num_ctx 와 같게 잡지 말 것. 읽을 것이 들어갈 자리가 없어진다.
#      절반이면 넉넉하다 — ④ 는 읽을 것 약 12,000 / 쓸 것 약 7,000 이 실측이다.
#  ★★ v1.7.12: 기준을 **실측값**으로 낮췄다. 그전 값은 6배 넘게 보수적이었다.
#
#    2026-08-28 실측 (ollama ps, gemma4:12b, num_ctx 65536):
#        NAME        SIZE      PROCESSOR   CONTEXT
#        gemma4:12b  8.5 GB    100% GPU    65536
#      모델 자체가 7.6GB 이므로 **문맥 65,536 이 먹는 양은 0.9GB 뿐**이다.
#      "16K 당 1GB" 로 어림했던 것이 네 배쯤 틀렸다.
#
#    그래서 계산이 뒤집혔다. 12GB 카드도 65,536 을 쓸 수 있다:
#        모델 7.6 + 문맥 0.9 + 화면 1.5 = 10.0GB  <  12GB
#      예전 기준(6.0GB 필요)으로는 16,384(100줄)까지밖에 못 갔다.
#
#    ★ 문맥은 싸고 모델은 비싸다. 문맥을 아끼려고 묶음을 줄이지 말 것.
#      65,536 을 절반으로 줄여도 0.45GB 밖에 안 남아 아무 데도 못 쓴다.
#
#    ★ 그래도 여유는 3배 가까이 둔다. 모델마다 문맥 비용이 다르고
#      (계산해서 쓰는 게 아니라 실측 하나에 기대고 있다), 밀려나면
#      Ollama 가 조용히 느려져서 원인이 안 보인다.
#  ★★ v1.7.13: 맨 위 칸을 131,072 로 올렸다. 문맥이 싸다는 걸 실측했기 때문이다.
#
#    2026-08-28 사고: ⑤ 추가 요청이 50분짜리에서 잘렸다. 원인이 출력 한도인 줄
#    알고 32,000 -> 48,000 으로 올렸는데 결과가 **글자 수까지 똑같았다.**
#    다시 계산해 보니 한도가 아니라 **자리가 없었던 것**이다:
#        읽을 것  자막 540줄 19,980 + 단어 2,600개 15,600 + 지시문 400 = 35,980
#        책상     65,536
#        답이 쓸 자리 = 29,556      <- 한도 32,000 보다 작다
#      한도를 올려도 앉을 자리가 없으니 아무 소용이 없었다.
#
#    문맥을 두 배로 하면 그 자리가 29,556 -> 95,092 가 된다.
#    비용은 실측 기준 0.9GB -> 1.8GB 뿐이고, 12GB 카드도 들어간다:
#        모델 7.6 + 문맥 1.8 + 화면 1.5 = 10.9GB  <  12GB
#
#    ★ "출력 한도가 모자란가?" 를 먼저 의심하지 말 것.
#      num_ctx 는 읽을 것과 쓸 것이 **같이 앉는 자리**다. 읽을 것이 크면
#      쓸 자리가 그만큼 없어진다. 한도는 그다음 문제다.
#  ★ 문맥 비용은 실측이다: 65,536 = 0.9GB (2026-08-28, ollama ps).
#    262,144 는 gemma4 의 **최대치**다. 그 위는 없다.
LOCAL_CTX_STEPS = [
    # (필요한 '남는 자리' GB, num_ctx, lines_chunk, rebuild_chunk_words, max_tokens)
    (2.7, 131072,  500,  700, 48000),  # 실측 1.8GB — 12GB·16GB 카드 + 12b 가 여기
    (1.4,  65536,  500,  700, 32000),  # 실측 0.9GB
    (0.7,  32768,  300,  450, 16000),
    (0.0,  16384,  150,  220,  8000),  # 바닥 — 여기까지 오면 이미 빠듯하다
]
#  ★★ 262,144 / 1,000줄 칸을 만들었다가 **뺐다.** 재보니 손해였다.
#    2026-08-29, 같은 파일(5,213단어)을 같은 모델로 돌린 실측:
#        문맥 65,536 · 500줄   재조립 3:59  교정 2:37
#        문맥 262,144 · 1000줄 재조립 7:11  교정 5:40   <- 두 배 느리다
#      한 번에 보는 양이 늘면 계산량은 그보다 빠르게 는다.
#      게다가 16GB 카드가 꽉 차서(작업 관리자로 확인) 조금만 넘쳐도
#      Ollama 가 본체 메모리로 넘기며 3~5배 더 느려진다.
#      결정적으로 ⑤ 가 죽었다 — 자막 824줄 + 단어 5,213개(약 62,000칸)를
#      **읽기만 하는 데** 5분이 넘어 제한 시간(300초)에 걸렸다:
#          Local AI sent nothing for 300s
#
#    ★ "문맥이 싸니까 최대로 쓰자" 는 틀렸다. VRAM 값은 싸지만 **시간이 비싸다.**
#      확인된 좋은 자리는 131,072 / 500줄이다. 올리려면 시간부터 재고 올릴 것.

#  ★ v1.7.13: 모델이 아예 안 들어가면 시작하지 않는다.
#    8GB 카드 + gemma4:12b = 모델 7.6 + 화면 1.5 = 9.1GB 로, **문맥을 0 으로
#    해도 안 들어간다.** 그래도 Ollama 는 에러 없이 본체 메모리로 넘겨 3~5배
#    느리게 돈다 — 50분짜리가 두 시간이 되고, 사용자는 이유를 모른다.
#    "되긴 하는데 이유 없이 느린" 것이 그냥 안 되는 것보다 나쁘다.
#    ★ §6-1 의 "미리 막지 말 것" 과 충돌하지 않는다. 그건 '될 수도 있는 것을
#      막지 말라' 는 뜻이고, 이건 **산술적으로 불가능한 조합**이다.
LOCAL_MIN_FREE_GB = 0.3   # 모델과 화면을 빼고 이만큼도 안 남으면 거부
#  ★ 묶음을 500 으로 올렸다 (300 -> 500). 45분 영상이 3묶음 -> 2묶음이 된다.
#    책상의 46% 만 쓴다(입력 15,700 + 출력 15,000 / 65,536).
#    ★ 900 으로 더 올리지 말 것 — **아직 안 재봤다.**
#      오늘 형식이 확인된 최대치는 227줄이다. 500 은 그 2배로 한 걸음 안이지만,
#      900 은 4배다. 묶음이 크면 한 번 튕길 때 다시 물어보는 양도 그만큼 크다.
#      긴 영상으로 500 이 멀쩡한 것을 확인한 뒤에 올릴 것.


def _model_size_gb(name):
    """이 모델이 GPU 에서 차지할 크기(GB). 못 알아내면 None.

    ★ v1.7.11: **먼저 Ollama 에게 물어본다.** 표는 예비다.

      2026-08-28 사고: gemma4:e2b-it-qat(4.3GB)를 시험하려고 골랐더니
      LOCAL_MODEL_SIZE 표에 없어서 크기를 '모름' 으로 판정했고,
      그 결과 **가장 안전한 칸(8,192 / 40줄)** 으로 떨어졌다.
      12b(7.6GB)보다 작은 모델인데 정반대 대접을 받은 것이다.
        Graphics card 16GB, ? free for context — using 8,192 tokens (40 lines)
      시험 자체가 무효가 됐다.

      표를 계속 늘려서 따라잡을 수 없다 — 사용자가 아무 모델이나 적을 수 있고,
      태그는 조용히 커진다(26b 가 14.4GB 로 알려졌다가 19GB 가 됐다).
      Ollama 는 설치된 모델의 실제 바이트 수를 알고 있다. 그걸 쓰면 항상 맞다.

    ★ 순서를 바꾸지 말 것. 표를 먼저 보면 위 사고가 그대로 재현된다.
    """
    name = (name or "").strip()
    if not name:
        return None

    # ① Ollama 에게 물어본다 — 설치돼 있으면 이게 진짜 값이다
    try:
        for m in (local_server_models(detail=True) or []):
            nm = (m.get("name") or m.get("model") or "").strip()
            # "gemma4:12b" 와 "gemma4:12b:latest" 를 같은 것으로 본다
            if nm == name or nm.split(":latest")[0] == name:
                n = int(m.get("size") or 0)
                if n > 0:
                    return n / (1000.0 ** 3)   # Ollama 표시와 같은 1000 기준
    except Exception:
        pass

    # ② 아직 안 받은 모델이면 표를 본다 (다운로드 전 안내용)
    s = LOCAL_MODEL_SIZE.get(name)
    if not s:
        return None
    try:
        return float(re.sub(r"[^0-9.]", "", s))
    except Exception:
        return None
LOCAL_CTX = {"n": 8192, "picked": False}


def local_num_ctx():
    """지금 쓰기로 정한 컨텍스트 크기."""
    return LOCAL_CTX["n"]


def gpu_total_vram_gb():
    """그래픽카드 전체 VRAM(GB). 못 알아내면 None.

    ★ '남은 양'이 아니라 '전체'를 본다. 남은 양은 그때그때 달라서
      같은 컴퓨터에서 실행할 때마다 다른 묶음 크기가 나온다 —
      결과가 재현되지 않으면 무엇이 좋아졌는지 비교할 수 없다."""
    try:
        import torch
        if torch.cuda.is_available():
            n = torch.cuda.get_device_properties(0).total_memory
            if n > 0:
                return n / (1024.0 ** 3)
    except Exception:
        pass
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=8,
            creationflags=(0x08000000 if sys.platform.startswith("win") else 0))
        if out.returncode == 0:
            mb = max(int(x) for x in out.stdout.split() if x.strip().isdigit())
            return mb / 1024.0
    except Exception:
        pass
    return None


def pick_local_tuning(log=None):
    """카드와 모델을 보고 num_ctx·묶음 크기를 정한다. 실행당 한 번만.

    ★ 모델을 바꾸면 다시 골라야 한다 — picked 를 False 로 되돌릴 것."""
    if LOCAL_CTX["picked"]:
        return
    LOCAL_CTX["picked"] = True
    gb = gpu_total_vram_gb()

    # ★ v1.7.13: 카드가 크면 더 좋은 모델로 알아서 올린다.
    #   24GB 급이면 26b(16GB)가 문맥 최대치(262,144)까지 얹고도 들어간다:
    #       모델 16 + 문맥 3.6 + 화면 1.5 = 21.1GB  <  23.69GB
    #   12b 를 쓰면 그 카드는 14.6GB 를 놀린다.
    #   ★ 사용자가 설정 창에서 직접 고른 적이 있으면(chosen) 손대지 않는다.
    #     고른 것을 프로그램이 되돌리면 고를 이유가 없어진다.
    #   ★ 목록 순서대로 보되 '들어가는 것 중 제일 큰 것' 을 고른다.
    if gb is not None and not LOCAL_MODEL.get("chosen"):
        best, best_sz = LOCAL_MODEL["name"], -1.0
        for cand in LOCAL_MODELS:
            cz = _model_size_gb(cand)
            if cz is None:
                continue
            if gb - cz - DISPLAY_RESERVE_GB >= LOCAL_CTX_STEPS[0][0] and cz > best_sz:
                best, best_sz = cand, cz
        if best != LOCAL_MODEL["name"]:
            if log:
                log(T("log_local_upgrade", m=best, v=f"{gb:.0f}GB") + "\n")
            LOCAL_MODEL["name"] = best

    msz = _model_size_gb(LOCAL_MODEL["name"])

    # 카드나 모델 크기를 모르면 제일 안전한 칸으로 간다 (예전과 같은 값)
    need, ctx, lines, words, maxtok = LOCAL_CTX_STEPS[-1]
    free = None
    if gb is not None and msz is not None:
        free = gb - msz - DISPLAY_RESERVE_GB
        for need, ctx, lines, words, maxtok in LOCAL_CTX_STEPS:
            if free >= need:
                break
    # ★ v1.7.13: 산술적으로 불가능하면 여기서 멈춘다.
    #   free 는 '모델과 화면을 뺀 나머지' 다. 이게 음수면 모델조차 안 들어간다.
    if free is not None and free < LOCAL_MIN_FREE_GB:
        raise RuntimeError(T("err_vram_small",
                             v=f"{gb:.0f}GB", m=LOCAL_MODEL["name"],
                             s=f"{msz:.1f}GB", n=f"{msz + DISPLAY_RESERVE_GB:.1f}GB"))

    LOCAL_CTX["n"] = ctx
    ENGINES["local"]["lines_chunk"] = lines
    ENGINES["local"]["rebuild_chunk_words"] = words
    ENGINES["local"]["max_tokens_cap"] = maxtok      # v1.7.10: 출력 몫도 같이
    if log:
        log(T("log_local_tune",
              v=(f"{gb:.0f}GB" if gb is not None else "?"),
              f=(f"{free:.1f}GB" if free is not None else "?"),
              c=f"{ctx:,}", l=lines) + "\n")
        # 자리가 없어 제일 작은 칸으로 떨어졌으면 왜 그런지 알려 준다
        if free is not None and free < LOCAL_CTX_STEPS[-2][0]:
            log(T("log_local_tight", m=LOCAL_MODEL["name"]) + "\n")
#  (묶음 크기는 v1.3.2부터 ENGINES 표로 옮겼다 — "rebuild_chunk_words")
LOCAL_READ_TIMEOUT = 300   # 줄과 줄 사이 제한 (전체 시간 제한이 아님)

# ---- 교정·번역 묶음 크기 (v1.3) ----------------------------------------
#  ★ 이 값들을 없애고 "한 번에 전부 보내기"로 되돌리지 말 것.
#
#  v1.2 까지 correct_with_claude / translate_with_claude 는 자막 전체를 한 번에
#  보냈다. 800줄짜리 영상이면 입력만 1만 토큰이 넘는데 컨텍스트가 그보다 작아
#  Ollama 가 프롬프트 앞부분을 잘라냈다. 잘려 나가는 게 하필 맨 앞에 있는
#  '시스템 프롬프트'(=출력 형식 지시)여서, 모델은 아무 지시도 못 본 채
#  한국어 덩어리만 받고 엉뚱한 짧은 답을 뱉었다.
#
#  그 결과가 실제 로그다:
#      done — 1497 chars in 101s
#      Warning: correction returned 0 of 722 lines
#      Translation done: 0 lines
#  722줄을 보냈는데 1,497자만 돌아왔고 형식 매칭은 0건이었다.
#  번역이 통째로 실패했는데도 _en.srt 는 한국어인 채로 저장됐다.
#
#  재조립(rebuild_from_words)만 멀쩡했던 이유가 이거다 — 거기만 쪼개서 보냈다.
#  아래 값은 그 방식을 교정·번역에도 똑같이 적용한 것이다.
#  ★ v1.3.2: 엔진별 묶음 크기는 이 자리가 아니라 ENGINES 표에 있다.
#    여기에 상수를 다시 만들지 말 것 — 표와 어긋나면 "고쳤는데 안 먹는" 상태가 된다.
#      로컬   lines_chunk 40   (num_ctx 8192 안에 들어가야 한다)
#      클라우드 lines_chunk 200 (컨텍스트가 넉넉하다)
NUMBERED_MIN_MATCH = 0.6       # 한 묶음에서 이 비율 미만이 돌아오면 그 묶음은 다시 시도
NUMBERED_RETRIES = 2           # 묶음당 재시도 횟수 (첫 시도 포함하면 최대 3번)
GAP_FILL_ROUNDS = 2            # 빠진 줄 보충을 몇 바퀴 돌 것인가

# ---- ④ 추가 요청의 '하다 만 답' 검사 (v1.7.9) ----------------------------
#  자세한 근거는 apply_extra_request() 주석 참고.
EXTRA_RETRIES = 2              # 형식을 못 읽는 답을 몇 번까지 다시 물어볼 것인가
#  ★ v1.7.16 에서 EXTRA_EDGE_TOL / EXTRA_MAX_TOKENS 를 지웠다.
#    '전체를 다시 쓰게' 하던 시절의 장치였다. 이제는 바뀐 것만 받으므로
#    답이 짧은 게 정상이고, 출력 몫이 모자랄 일도 없다.
                               # (한 번에 보내는 줄 수는 엔진별: EOPT "gap_fill_batch")


# ---- 사용량 한도 처리 (v1.3.2) -------------------------------------------
#
#  실제 사고 기록. Gemini 무료 티어로 한 편을 돌렸더니 4시간 반을 헛돌았다.
#
#  원인은 재시도가 세 겹으로 곱해진 것이다:
#      _post_json 3회(20+40+60초) × 묶음 재시도 3회 × 보충 배치 32개
#      = 한 단계에 140분. 교정과 번역을 합쳐 280분.
#
#  재시도 자체는 옳다 — 로컬에서 무작위로 깨지는 묶음을 되살려 줬다.
#  문제는 "가끔 실패"와 "계속 실패"를 구분하지 못한 것이다.
#  429가 30번 연속으로 났으면 31번째도 실패한다. 그때는 멈춰야 한다.
#
#  ★ 이 장치는 quota_guard=True 인 엔진에서만 동작한다(현재 Gemini뿐).
#    로컬은 429를 낼 일이 없어 코드가 있어도 절대 걸리지 않고,
#    Claude는 표에서 꺼 두었다.

class QuotaError(RuntimeError):
    """API 사용량 한도 오류(429). 일반 실패와 구분해서 다룬다.

    daily=True  일일 한도 — 오늘은 기다려도 안 풀린다. 즉시 포기한다.
    daily=False 분당 한도 — 잠시 기다리면 회복된다."""
    def __init__(self, msg, daily=False):
        super().__init__(msg)
        self.daily = daily


def _is_daily_quota(body):
    """429 본문이 '일일 한도'를 가리키는지 본다.

    구글은 quota metric 이름에 per_day / PerDay / 'per day' 를 넣어 준다.
    표기가 판마다 조금씩 달라 아래를 모두 본다.

    ★ 이 함수가 제대로 일하려면 body 가 충분히 길어야 한다.
      _post_json 에서 2000자까지 읽는 이유가 이것이다 (300자로 자르면
      metric 이름이 날아가 항상 False 가 나온다)."""
    b = (body or "").lower()
    return any(k in b for k in ("per_day", "perday", "per day",
                                "requests per day", "daily limit",
                                "/day", "per-day"))


def _retired_model_hint(body):
    """404 본문에서 구글이 알려 주는 '대체 모델명'을 뽑는다.

    구글은 은퇴한 모델을 부르면 이렇게 답한다:
      "This model models/gemini-2.0-flash is no longer available.
       Please update your code to use models/gemini-3.6-flash ..."
    그 이름을 로그에 남겨 두면 ENGINES 목록을 뭘로 고쳐야 할지 바로 알 수 있다."""
    m = re.search(r"use\s+models/([A-Za-z0-9.\-_]+)", body or "")
    return m.group(1) if m else ""


_QUOTA = {"streak": 0, "dead": False}


def reset_quota_state():
    """작업을 새로 시작할 때 호출. 지난 실행의 한도 상태를 지운다."""
    _QUOTA["streak"] = 0
    _QUOTA["dead"] = False


def quota_dead():
    return _QUOTA["dead"]


def note_quota_fail(provider, daily=False):
    """한도 오류 1건 기록. 차단 상태가 되면 True."""
    if not EOPT(provider, "quota_guard"):
        return False                    # 이 엔진은 차단기를 쓰지 않는다
    _QUOTA["streak"] += 1
    if daily or _QUOTA["streak"] >= EOPT(provider, "quota_streak"):
        _QUOTA["dead"] = True
    return _QUOTA["dead"]


def note_quota_ok():
    _QUOTA["streak"] = 0


# ---- 요청 간격 (v1.3.2) ---------------------------------------------------
_LAST_CALL = {}


def pace_engine(provider, log=None):
    """엔진별 최소 요청 간격을 지킨다. min_interval=0 이면 아무 일도 안 한다.

    ★ 취소가 즉시 먹도록 잘게 쪼개서 잔다.
      한 번에 6.5초를 자면 그동안 멈춤 버튼이 안 통한다."""
    gap = EOPT(provider, "min_interval")
    if gap <= 0:
        return
    last = _LAST_CALL.get(provider, 0.0)
    remain = gap - (time.time() - last)
    if last > 0 and remain > 0:
        if log and remain >= 1.0:
            log("\r" + T("log_pace", p=EOPT(provider, "name"), s=f"{remain:.0f}"))
        end = time.time() + remain
        while time.time() < end:
            raise_if_cancelled()
            time.sleep(min(0.25, max(0.0, end - time.time())))
    _LAST_CALL[provider] = time.time()
#
# ---- v1.3.1: 왜 재시도·보충이 필요한가 -----------------------------------
#  v1.3 첫 실행 결과: 828줄 중 684줄 번역, 144줄(17%)이 한국어로 남았다.
#      · 120줄 = 묶음 4·7·10 이 통째로 거부됨
#      ·  24줄 = 성공한 묶음 안에서 개별로 빠짐
#
#  실패한 묶음의 원문을 성공한 묶음과 비교해 봤지만 줄 길이·미완결 문장 비율·
#  짧은 줄 수 어느 지표로도 구분되지 않았다. 즉 내용 탓이 아니라 무작위 실패다.
#  (로컬 모델이 40줄쯤에서 번호를 놓치는 일이 확률적으로 일어난다.)
#
#  ★ 무작위 실패이므로 '다시 시도하면 대체로 성공한다'. 그런데 v1.3 은 재시도가
#    없었고, 더 나쁘게는 부분 성공까지 통째로 버렸다 — 묶음 10 은 40줄 중 21줄이
#    제대로 왔는데도 기준(60%) 미달이라 21줄을 다 버렸다.
#    고칠 원칙 두 가지:
#      ① 돌아온 줄은 버리지 않는다.
#      ② 못 받은 줄만 다시 묻는다 (묶음 단위 재시도 -> 빠진 줄만 보충).


# ---- 취소 처리 (v1.3) ---------------------------------------------------
#
#  v1.2 까지 cancel_flag 는 네 군데에서만 확인됐다: 파일 사이, Whisper 세그먼트,
#  번역 언어 사이, 그리고 전체 종료 시점. 정작 오래 걸리는 안쪽 루프에는 없었다.
#      · 재조립 블록 루프   60블록 × 10~20초  -> 취소까지 최대 15분
#      · 교정/번역 묶음 루프 21묶음 × 30~60초 -> 취소까지 최대 20분
#      · AI 응답 스트리밍   한 번에 100초까지
#  그래서 "멈춤을 눌렀는데 한참 안 멈추는" 증상이 났다.
#
#  ★ 해결은 '가장 안쪽'에서 확인하는 것이다. AI가 글자를 하나씩 받아오는
#    스트리밍 루프에 확인을 넣으면 1초 안에 멈춘다. 바깥 루프에만 넣으면
#    현재 호출이 끝날 때까지는 여전히 기다려야 한다.
#
#  함수 인자로 콜백을 6단계 내려보내는 대신 모듈 전역 훅을 쓴다. 작업 스레드는
#  한 번에 하나뿐이라 이걸로 충분하고, 기존 함수 시그니처를 건드리지 않아 안전하다.
_CANCEL = {"fn": None}


class CancelledError(RuntimeError):
    """사용자가 멈춤을 눌렀을 때. 일반 실패와 구분하려고 따로 둔다.
    (일반 실패로 처리하면 '번역 실패' 같은 엉뚱한 메시지가 로그에 남는다.)"""
    pass


def set_cancel_check(fn):
    """작업 시작 시 App 이 자기 cancel_flag 를 읽는 함수를 등록한다.
    작업이 끝나면 None 으로 되돌린다."""
    _CANCEL["fn"] = fn


def is_cancelled():
    fn = _CANCEL.get("fn")
    if not fn:
        return False
    try:
        return bool(fn())
    except Exception:
        return False


def raise_if_cancelled():
    if is_cancelled():
        raise CancelledError("cancelled by user")

# 모델 계열별 샘플링/사고모드 설정.
#  ★ 샘플링 값은 각 모델 제조사가 공식 문서에서 권장하는 값이다. 임의로 바꾸지 말 것.
#    (Gemma 4 는 temperature 1.0 을 권장한다. "형식을 지키게 하려고" 0.2 처럼 낮추면
#     오히려 반복·붕괴가 생긴다 — Gemma 계열의 알려진 특성이다.)
LOCAL_TUNING = {
    "gemma4": {  # https://ollama.com/library/gemma4  Best Practices
        "temperature": 1.0, "top_p": 0.95, "top_k": 64,
        "prompt_suffix": "",   # <|think|> 토큰을 안 넣으면 사고 모드가 꺼진 상태다
    },
    "qwen3": {
        "temperature": 0.2, "top_p": 0.9, "top_k": 40,
        "prompt_suffix": "\n/no_think",   # think 파라미터를 무시하는 빌드 대비
    },
}
LOCAL_TUNING_DEFAULT = {"temperature": 0.3, "top_p": 0.9, "top_k": 40, "prompt_suffix": ""}


def local_tuning(model_name=None):
    """모델 이름 앞부분으로 계열을 찾아 튜닝값을 돌려준다 (없으면 무난한 기본값)."""
    name = (model_name or LOCAL_MODEL["name"] or "").lower()
    for family, cfg in LOCAL_TUNING.items():
        if name.startswith(family):
            return cfg
    return LOCAL_TUNING_DEFAULT


def strip_thinking(text):
    """모델이 남긴 '사고 과정' 블록을 제거한다.

    계열마다 형식이 달라 전부 처리한다:
      qwen3   <think> ... </think>
      gemma4  <|channel>thought ... <channel|>
              (사고를 꺼도 빈 블록을 그대로 뱉는다 — 공식 문서에 명시된 동작이라
               반드시 걷어내야 한다. 안 그러면 응답 첫 줄이 태그로 시작해 파싱이 깨진다.)
    """
    out = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    out = re.sub(r"<\|?channel\|?>\s*thought\b.*?<\/?\|?channel\|?>", "", out, flags=re.S)
    out = re.sub(r"<\|?channel\|?>\s*thought\b.*", "", out, flags=re.S)  # 닫는 태그가 없는 경우
    out = re.sub(r"</?\|?(?:channel|think)\|?>", "", out)                # 남은 조각 태그
    return out.strip()

# ---- 제작자 채널 배너 (v1.1) ----
YT_CHANNEL_NAME = "sunny friends STEM"
YT_VIDEO_URL = "https://www.youtube.com/watch?v=R8Rf05Ca5u0&list=PLKtXVVR0NNN0"
YT_CHANNEL_URL = "https://www.youtube.com/@sunnyfriends.science"
# v1.7.6: 성공 모델 캐시는 없앴다 — 항상 표 순서대로 간다. _call_gemini 주석 참고.
_GEMINI_DEAD = set()                 # 오늘 일일 한도가 소진된 모델 (실행마다 초기화)

# ---- 사고(thinking) 설정 자동 탐색 (v1.3.6) -------------------------------
#
#  ★ 구글이 세대마다 '사고 끄는 방법'의 이름을 바꾼다. 하나로 고정하면 반드시 깨진다.
#      Gemini 2.5  : thinkingBudget: 0
#      Gemini 3.x  : thinkingLevel: "low"   (옛 이름을 주면 400 INVALID_ARGUMENT)
#    게다가 일부 Gemini 3 모델은 사고를 아예 끌 수 없다
#    ("Budget 0 is invalid. This model only works in thinking mode").
#
#  ★ 2026-08-21 사고: v1.3.4 에서 thinkingBudget: 0 을 넣었더니
#    gemini-3.6-flash / gemini-3.5-flash-lite 가 전부 400 을 뱉었다.
#    모델을 바꾼 직후부터 재조립·교정·번역이 통째로 실패했다.
#
#  ★ 그래서 이름을 추측하지 않는다. 모델명으로 세대를 알 수도 없다
#    (gemini-flash-latest 가 몇 세대인지 이름만 봐선 모른다).
#    아래 순서로 시도해 보고, 통한 방식을 그 모델용으로 기억한다.
#  ★ 반드시 thinkingConfig 로 한 번 감싸야 한다.
#    v1.3.6 은 껍데기를 빼먹고 알맹이만 generationConfig 바로 아래에 넣었다.
#    그 결과 모델 3개가 전부 'level'·'budget' 을 거부하고 'none' 으로 떨어져,
#    사고 모드가 꺼지지 않은 채 돌면서 탐색에만 9회(모델3 × 방식3)를 낭비했다.
#    (그래도 결과가 나온 건 출력 한도를 32,000 으로 올려둔 덕이다 — v1.3.4)
THINK_MODES = [
    ("level",  {"thinkingConfig": {"thinkingLevel": "low"}}),   # Gemini 3.x
    ("budget", {"thinkingConfig": {"thinkingBudget": 0}}),      # Gemini 2.5
    ("none",   {}),                          # 최후 — 사고 설정을 아예 안 보냄
]
_GEMINI_THINK = {}                   # {모델명: THINK_MODES 인덱스} — 통한 방식 기억
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

# ============================================================================
# ★★★  _words.srt 는 언제나 만든다. 이 값을 False 로 바꾸지 말 것.  ★★★
#
#  이건 사용자 옵션이 아니라 프로그램의 동작 규격이다.
#  config.json 에도 저장하지 않고, 메뉴에도 끄는 스위치를 두지 않는다.
#
#  [왜 필수인가]
#   - 이 프로그램의 자막 정확도는 전적으로 Whisper 의 '단어별 실측 타임스탬프'
#     에서 나온다. _words.srt 는 그 원본 데이터를 그대로 담은 파일이다.
#   - AI 2차 검수는 문장을 다시 자르고 붙이는데, 그때 각 자막의 시작/끝 시간을
#     이 단어 타임스탬프에서 되찾는다. 이 근거가 없으면 타이밍이 '비율 추정'
#     으로 떨어져 자막이 눈에 띄게 어긋난다.
#   - 결과가 이상할 때 원인을 추적할 수 있는 유일한 파일이기도 하다.
#
#  [주의]
#   과거 v4.5 에서 "잘 안 쓰는 것 같다"는 이유로 기본값을 끈 적이 있고,
#   그 값이 config.json 에 남아 이후 버전에서도 파일이 아예 생성되지 않는
#   문제가 오래 지속됐다. 같은 실수를 반복하지 말 것.
#   코드 정리·옵션 축소·리팩터링 중에도 이 상수와 아래 저장 블록은 건드리지 않는다.
# ============================================================================
ALWAYS_SAVE_WORDS = True

# 출력/음성 언어 목록 (기능 변경 없음) — 표시는 각 언어의 원어 이름
NATIVE = {
    "en": "English", "ko": "한국어", "ja": "日本語", "zh": "中文",
    "es": "Español", "fr": "Français", "de": "Deutsch", "it": "Italiano",
    "pt": "Português", "ru": "Русский", "vi": "Tiếng Việt", "th": "ไทย",
    "id": "Bahasa Indonesia", "hi": "हिन्दी", "ar": "العربية",
}
LANG_CODES = ["en", "ko", "ja", "zh", "es", "fr", "de", "it",
              "pt", "ru", "vi", "th", "id", "hi", "ar"]
LANG_FULLNAME = {
    "en": "English", "ko": "Korean", "ja": "Japanese", "zh": "Chinese",
    "es": "Spanish", "fr": "French", "de": "German", "it": "Italian",
    "pt": "Portuguese", "ru": "Russian", "vi": "Vietnamese", "th": "Thai",
    "id": "Indonesian", "hi": "Hindi", "ar": "Arabic",
}
SENT_END = set(".?!。？！…")

# ---------------- UI 표시 언어 (i18n) ----------------
UI_LANGS = [("en", "English"), ("ko", "한국어"), ("ja", "日本語"),
            ("zh", "中文(简体)"), ("fr", "Français"), ("pt", "Português"),
            ("es", "Español")]
UI = {"lang": "en"}  # 첫 실행 기본값: English (config에 저장되면 기억)

I18N = {
"tagline": {
 "en": "Creates SRT subtitles from video/audio — Whisper transcription + AI correction & translation",
 "ko": "영상/음성에서 SRT 자막 자동 생성 — Whisper 받아쓰기 + AI 교정·번역",
 "ja": "動画/音声からSRT字幕を自動生成 — Whisper書き起こし + AI校正・翻訳",
 "zh": "从视频/音频自动生成 SRT 字幕 — Whisper 转写 + AI 校对·翻译",
 "fr": "Crée des sous-titres SRT depuis vidéo/audio — transcription Whisper + correction/traduction AI",
 "pt": "Cria legendas SRT de vídeo/áudio — transcrição Whisper + correção/tradução AI",
 "es": "Crea subtítulos SRT desde vídeo/audio — transcripción Whisper + corrección/traducción AI"},
"menu_settings": {"en": "Settings", "ko": "설정", "ja": "設定", "zh": "设置",
 "fr": "Paramètres", "pt": "Configurações", "es": "Configuración"},
"menu_language": {"en": "Language", "ko": "Language (언어)", "ja": "Language (言語)",
 "zh": "Language (语言)", "fr": "Langue", "pt": "Idioma", "es": "Idioma"},
"menu_help": {"en": "Help", "ko": "도움말", "ja": "ヘルプ", "zh": "帮助",
 "fr": "Aide", "pt": "Ajuda", "es": "Ayuda"},
"mi_save_words": {
 "en": "Save word-timestamp file (_words.srt)",
 "ko": "단어 타임스탬프 파일 저장 (_words.srt)",
 "ja": "単語タイムスタンプファイルを保存 (_words.srt)",
 "zh": "保存单词时间戳文件 (_words.srt)",
 "fr": "Enregistrer le fichier d'horodatage des mots (_words.srt)",
 "pt": "Salvar arquivo de marcação de palavras (_words.srt)",
 "es": "Guardar archivo de marcas de palabras (_words.srt)"},
"mi_quickstart": {"en": "Quick start", "ko": "빠른 시작", "ja": "クイックスタート",
 "zh": "快速入门", "fr": "Démarrage rapide", "pt": "Início rápido", "es": "Inicio rápido"},
"mi_trouble": {"en": "Troubleshooting", "ko": "문제 해결", "ja": "トラブルシューティング",
 "zh": "疑难解答", "fr": "Dépannage", "pt": "Solução de problemas", "es": "Solución de problemas"},
"mi_about": {"en": "About JQSub", "ko": "JQSub 정보", "ja": "JQSubについて",
 "zh": "关于 JQSub", "fr": "À propos de JQSub", "pt": "Sobre o JQSub", "es": "Acerca de JQSub"},
"frm_claude": {
 "en": "③ AI (correction · sentence split · translation)",
 "ko": "③ AI (교정 · 문장 분할 · 번역)",
 "ja": "③ AI（校正・文分割・翻訳）",
 "zh": "③ AI（校对 · 分句 · 翻译）",
 "fr": "③ IA (correction · découpage · traduction)",
 "pt": "③ IA (correção · divisão · tradução)",
 "es": "③ IA (corrección · división · traducción)"},
"api_placeholder": {
 "en": "Enter your {p} API key — enables AI correction & translation (empty = transcription only)",
 "ko": "{p} API 키 입력 — 자막 교정·번역에 사용 (비워두면 받아쓰기만)",
 "ja": "{p} APIキーを入力 — AI校正・翻訳に使用（空欄なら書き起こしのみ）",
 "zh": "输入 {p} API 密钥 — 用于 AI 校对·翻译（留空则仅转写）",
 "fr": "Saisir la clé API {p} — active correction et traduction IA (vide = transcription seule)",
 "pt": "Digite a chave de API {p} — ativa correção e tradução por IA (vazio = só transcrição)",
 "es": "Introduce la clave API de {p} — activa corrección y traducción IA (vacío = solo transcripción)"},
"show_key": {"en": "Show", "ko": "표시", "ja": "表示", "zh": "显示",
 "fr": "Afficher", "pt": "Mostrar", "es": "Mostrar"},
"hint_on": {
 "en": "✓ AI correction · translation ON — {p}",
 "ko": "✓ AI 교정·번역 사용 중 — {p}",
 "ja": "✓ AI校正・翻訳 有効 — {p}",
 "zh": "✓ AI 校对·翻译 已启用 — {p}",
 "fr": "✓ Correction · traduction IA activées — {p}",
 "pt": "✓ Correção · tradução por IA ativadas — {p}",
 "es": "✓ Corrección · traducción IA activadas — {p}"},
"hint_need_key": {
 "en": "Enter your API key above to enable AI correction · sentence split · translation",
 "ko": "위에 API 키를 입력하면 AI 교정·문장 분할·번역이 켜집니다",
 "ja": "上にAPIキーを入力するとAI校正・文分割・翻訳が有効になります",
 "zh": "在上方输入 API 密钥即可启用 AI 校对·分句·翻译",
 "fr": "Saisissez votre clé API ci-dessus pour activer la correction · le découpage · la traduction IA",
 "pt": "Digite sua chave de API acima para ativar correção · divisão · tradução por IA",
 "es": "Introduce tu clave API arriba para activar corrección · división · traducción IA"},
"hint_off": {
 "en": "AI OFF — plain transcription only (no correction / translation)",
 "ko": "AI 끔 — whisper 받아쓰기만 저장 (교정·번역 없음)",
 "ja": "AIオフ — 書き起こしのみ保存（校正・翻訳なし）",
 "zh": "AI 已关闭 — 仅保存转写（无校对/翻译）",
 "fr": "AI désactivé — transcription seule (sans correction / traduction)",
 "pt": "AI desligado — apenas transcrição (sem correção / tradução)",
 "es": "AI desactivado — solo transcripción (sin corrección / traducción)"},
"lbl_names": {"en": "Character names:", "ko": "캐릭터 이름:", "ja": "キャラクター名:",
 "zh": "角色名称:", "fr": "Noms des personnages :", "pt": "Nomes dos personagens:",
 "es": "Nombres de personajes:"},
"hint_names": {
 "en": "Comma-separated (e.g. Titi, Sunny) — fixes mis-heard character names",
 "ko": "쉼표로 구분 (예: Titi, Sunny) — 비슷하게 잘못 들린 이름을 바로잡습니다",
 "ja": "カンマ区切り（例: Titi, Sunny）— 聞き間違えた名前を修正します",
 "zh": "用逗号分隔（如 Titi, Sunny）— 修正听错的角色名",
 "fr": "Séparés par des virgules (ex. Titi, Sunny) — corrige les noms mal entendus",
 "pt": "Separados por vírgula (ex.: Titi, Sunny) — corrige nomes mal ouvidos",
 "es": "Separados por comas (ej.: Titi, Sunny) — corrige nombres mal oídos"},
"frm_src": {
 "en": "② Audio language (what is spoken in the file)",
 "ko": "② 음성 언어 (파일에서 말하는 언어)",
 "ja": "② 音声言語（ファイル内で話されている言語）",
 "zh": "② 音频语言（文件中所讲的语言）",
 "fr": "② Langue audio (parlée dans le fichier)",
 "pt": "② Idioma do áudio (falado no arquivo)",
 "es": "② Idioma del audio (hablado en el archivo)"},
"lbl_src": {"en": "Audio language:", "ko": "이 파일의 음성 언어:", "ja": "音声言語:",
 "zh": "音频语言:", "fr": "Langue audio :", "pt": "Idioma do áudio:", "es": "Idioma del audio:"},
"hint_src": {
 "en": "Auto-checked & locked as the base output below · 'Auto detect' lets Whisper decide (see log)",
 "ko": "아래 출력 언어에 자동 선택·고정됩니다 · 자동 감지 시 whisper가 판별 (로그 표시)",
 "ja": "下の出力言語に自動選択・固定されます · 自動検出はWhisperが判別（ログ表示）",
 "zh": "会在下方输出语言中自动勾选并锁定 · 自动检测时由 Whisper 判断（见日志）",
 "fr": "Coché et verrouillé comme base dans la sortie ci-dessous · « Détection auto » : Whisper décide (voir journal)",
 "pt": "Marcado e fixado como base na saída abaixo · 'Detecção automática': o Whisper decide (ver log)",
 "es": "Se marca y fija como base en la salida de abajo · 'Detección automática': Whisper decide (ver registro)"},
"frm_out": {
 "en": "Output subtitle languages:",
 "ko": "출력 자막 언어:",
 "ja": "出力字幕の言語:",
 "zh": "输出字幕语言:",
 "fr": "Langues des sous-titres produits :",
 "pt": "Idiomas das legendas geradas:",
 "es": "Idiomas de los subtítulos generados:"},
"chk_all": {
 "en": "Select all (except audio language)",
 "ko": "전체 선택 (음성 언어 외)",
 "ja": "すべて選択（音声言語以外）",
 "zh": "全选（音频语言除外）",
 "fr": "Tout sélectionner (sauf langue audio)",
 "pt": "Selecionar tudo (exceto idioma do áudio)",
 "es": "Seleccionar todo (excepto idioma del audio)"},
"hint_out": {
 "en": "Each checked language is saved as SRT · base language: no suffix, translations: _ko style suffix",
 "ko": "체크된 언어는 모두 SRT 저장 · 음성 언어는 접미사 없음(영상과 동일), 번역은 _ko 식 접미사",
 "ja": "チェックした言語はSRTで保存 · 基準言語は接尾辞なし、翻訳は _ko 形式の接尾辞",
 "zh": "勾选的语言都会保存为 SRT · 基准语言无后缀，翻译带 _ko 式后缀",
 "fr": "Chaque langue cochée est enregistrée en SRT · langue de base : sans suffixe, traductions : suffixe _ko",
 "pt": "Cada idioma marcado é salvo como SRT · idioma base: sem sufixo, traduções: sufixo _ko",
 "es": "Cada idioma marcado se guarda como SRT · idioma base: sin sufijo, traducciones: sufijo _ko"},
"lock_base": {"en": "(base)", "ko": "(기준·고정)", "ja": "（基準・固定）", "zh": "（基准·锁定）",
 "fr": "(base)", "pt": "(base)", "es": "(base)"},
"frm_file": {
 "en": "① Select video/audio files (multiple allowed)",
 "ko": "① 파일 선택 (여러 개 선택 가능)",
 "ja": "① ファイル選択（複数選択可）",
 "zh": "① 选择文件（可多选）",
 "fr": "① Sélection des fichiers (plusieurs possibles)",
 "pt": "① Selecionar arquivos (vários permitidos)",
 "es": "① Seleccionar archivos (se permiten varios)"},
"btn_browse": {"en": "Browse...", "ko": "찾아보기...", "ja": "参照...", "zh": "浏览...",
 "fr": "Parcourir...", "pt": "Procurar...", "es": "Examinar..."},
"btn_go": {"en": "Create subtitles", "ko": "자막 만들기", "ja": "字幕を作成", "zh": "生成字幕",
 "fr": "Créer les sous-titres", "pt": "Criar legendas", "es": "Crear subtítulos"},
"btn_busy": {"en": "Working...", "ko": "생성 중...", "ja": "作成中...", "zh": "生成中...",
 "fr": "En cours...", "pt": "Processando...", "es": "Procesando..."},
"btn_cancel": {"en": "Cancel", "ko": "취소", "ja": "キャンセル", "zh": "取消",
 "fr": "Annuler", "pt": "Cancelar", "es": "Cancelar"},
"frm_extra": {
 "en": "④ Targeted fixes (optional)",
 "ko": "④ 콕 집어 고치기 (선택)",
 "ja": "④ 狙って直す（任意）",
 "zh": "④ 精准修正（可选）",
 "fr": "④ Corrections ciblées (facultatif)",
 "pt": "④ Correções pontuais (opcional)",
 "es": "④ Correcciones puntuales (opcional)"},
"frm_song": {
 "en": "⑤ Song lyrics (optional) — for the musical / theme song part",
 "ko": "⑤ 노래 가사 (선택) — 뮤지컬·주제가 구간용",
 "ja": "⑤ 歌の歌詞（任意）— ミュージカル・主題歌の区間用",
 "zh": "⑤ 歌词（可选）— 用于音乐剧·主题曲片段",
 "fr": "⑤ Paroles de la chanson (facultatif) — pour la partie chantée",
 "pt": "⑤ Letra da música (opcional) — para a parte cantada",
 "es": "⑤ Letra de la canción (opcional) — para la parte cantada"},
"ph_song": {
 "en": "Speech recognition drops singing, so the musical or theme song usually gets no\n"
       "subtitles at all. Paste the lyrics here and that part is found and filled in.\n"
       "One line = one subtitle line. Markers such as [Chorus] are ignored.",
 "ko": "\uc74c\uc131 \uc778\uc2dd\uc740 \ub178\ub798\ub97c \ubc84\ub9bd\ub2c8\ub2e4. \uadf8\ub798\uc11c \ubba4\uc9c0\uceec\u00b7\uc8fc\uc81c\uac00 \uad6c\uac04\uc5d0\ub294 \uc790\ub9c9\uc774 \uc544\uc608\n"
       "\uc548 \ub9cc\ub4e4\uc5b4\uc9d1\ub2c8\ub2e4. \uc5ec\uae30\uc5d0 \uac00\uc0ac\ub97c \ub123\uc73c\uba74 \uadf8 \uad6c\uac04\uc744 \ucc3e\uc544\uc11c \ucc44\uc6cc \uc90d\ub2c8\ub2e4.\n"
       "\ud55c \uc904\uc774 \uc790\ub9c9 \ud55c \uc904\uc785\ub2c8\ub2e4. [Chorus] \uac19\uc740 \uad6c\uac04 \ud45c\uc2dc\ub294 \uc54c\uc544\uc11c \ubb34\uc2dc\ud569\ub2c8\ub2e4.",
 "ja": "\u97f3\u58f0\u8a8d\u8b58\u306f\u6b4c\u3092\u6368\u3066\u308b\u305f\u3081\u3001\u30df\u30e5\u30fc\u30b8\u30ab\u30eb\u30fb\u4e3b\u984c\u6b4c\u306e\u533a\u9593\u306f\u5b57\u5e55\u304c\n"
       "\u307e\u3063\u305f\u304f\u4f5c\u3089\u308c\u307e\u305b\u3093\u3002\u3053\u3053\u306b\u6b4c\u8a5e\u3092\u5165\u308c\u308b\u3068\u305d\u306e\u533a\u9593\u3092\u63a2\u3057\u3066\u88dc\u5b8c\u3057\u307e\u3059\u3002\n"
       "1\u884c\u304c\u5b57\u5e55 1\u884c\u3067\u3059\u3002[Chorus] \u306a\u3069\u306e\u8868\u793a\u306f\u7121\u8996\u3055\u308c\u307e\u3059\u3002",
 "zh": "\u8bed\u97f3\u8bc6\u522b\u4f1a\u4e22\u6389\u6b4c\u58f0\uff0c\u56e0\u6b64\u97f3\u4e50\u5267\u00b7\u4e3b\u9898\u66f2\u7247\u6bb5\u901a\u5e38\u5b8c\u5168\u6ca1\u6709\u5b57\u5e55\u3002\n"
       "\u5728\u6b64\u7c98\u8d34\u6b4c\u8bcd\uff0c\u7a0b\u5e8f\u4f1a\u627e\u5230\u8be5\u7247\u6bb5\u5e76\u8865\u5168\u3002\n"
       "\u4e00\u884c\u5373\u4e00\u6761\u5b57\u5e55\u3002[Chorus] \u7b49\u6807\u8bb0\u4f1a\u81ea\u52a8\u5ffd\u7565\u3002",
 "fr": "La reconnaissance vocale ignore le chant : la partie chant\u00e9e n'a donc souvent\n"
       "aucun sous-titre. Collez les paroles ici et cette partie sera retrouv\u00e9e et compl\u00e9t\u00e9e.\n"
       "Une ligne = un sous-titre. Les marqueurs comme [Chorus] sont ignor\u00e9s.",
 "pt": "O reconhecimento de fala descarta o canto, ent\u00e3o a parte cantada costuma ficar\n"
       "sem legendas. Cole a letra aqui e esse trecho \u00e9 encontrado e preenchido.\n"
       "Uma linha = uma legenda. Marcadores como [Chorus] s\u00e3o ignorados.",
 "es": "El reconocimiento de voz descarta el canto, as\u00ed que la parte cantada suele\n"
       "quedarse sin subt\u00edtulos. Pegue aqu\u00ed la letra y esa parte se localiza y se rellena.\n"
       "Una l\u00ednea = un subt\u00edtulo. Los marcadores como [Chorus] se ignoran."},
"hq_song_t": {
 "en": "Song lyrics", "ko": "노래 가사", "ja": "歌の歌詞", "zh": "歌词",
 "fr": "Paroles", "pt": "Letra", "es": "Letra"},
"hq_song_b": {
 "en": ("Speech recognition drops singing: music is not treated as speech, so the "
        "musical number at the start of an episode usually gets no subtitles at all.\n\n"
        "Paste the lyrics here and that part can be filled in from real measured "
        "timings instead of guesswork.\n\n"
        "The song section is found automatically and only that part is redone. "
        "The subtitles from before the change are saved as _nosong.srt, so you can "
        "fall back to them. The first run downloads the vocal separator (a few minutes)."),
 "ko": ("음성 인식은 노래를 버립니다. 음악을 '말'로 보지 않기 때문에, 화면 앞부분의 "
        "뮤지컬 구간에는 보통 자막이 하나도 안 만들어집니다.\n\n"
        "여기에 가사를 붙여넣으면 그 구간을 짐작이 아니라 실측 시각으로 채울 수 "
        "있습니다.\n\n"
        "가사를 넣으면 노래 구간을 알아서 찾아 그 부분만 다시 처리합니다. "
        "바꾸기 전 자막은 _nosong.srt 로 따로 저장하니 마음에 안 들면 그걸 쓰시면 됩니다. "
        "처음 한 번은 보컬 분리기(Demucs)를 내려받느라 몇 분 걸립니다."),
 "ja": ("音声認識は歌を捨てます。音楽を「話し声」と見なさないため、冒頭のミュージカル"
        "区間には字幕がまったく作られないことが多いです。\n\n"
        "ここに歌詞を貼ると、その区間を推測ではなく実測の時刻で埋められます。\n\n"
        "歌詞を入れると歌区間を自動で見つけ、その部分だけやり直します。変更前の字幕は _nosong.srt に保存されます。初回はボーカル分離器のダウンロードに数分かかります。"),
 "zh": ("语音识别会丢掉歌声：音乐不被视为语音，所以开头的音乐剧片段通常完全没有字幕。\n\n"
        "在此粘贴歌词，即可用实测时间而非猜测来填补该片段。\n\n"
        "填入歌词后会自动找到歌曲片段并只重做该部分。修改前的字幕会另存为 _nosong.srt。首次运行需下载人声分离器，约几分钟。"),
 "fr": ("La reconnaissance vocale ignore le chant : la musique n'est pas traitée comme "
        "de la parole, donc la partie chantée du début n'a souvent aucun sous-titre.\n\n"
        "Collez les paroles ici pour combler cette partie avec des temps mesurés.\n\n"
        "La partie chantée est trouvée automatiquement et seule cette portion est refaite. "
        "Les sous-titres d'avant sont enregistrés en _nosong.srt."),
 "pt": ("O reconhecimento de fala descarta o canto: música não é tratada como fala, "
        "então a parte cantada do início costuma ficar sem legendas.\n\n"
        "Cole a letra aqui para preencher essa parte com tempos medidos.\n\n"
        "A parte cantada é encontrada automaticamente e só ela é refeita. "
        "As legendas anteriores ficam em _nosong.srt."),
 "es": ("El reconocimiento de voz descarta el canto: la música no se trata como habla, "
        "así que la parte cantada del inicio suele quedarse sin subtítulos.\n\n"
        "Pegue aquí la letra para rellenar esa parte con tiempos medidos.\n\n"
        "La parte cantada se encuentra automáticamente y solo esa parte se rehace. "
        "Los subtítulos previos quedan en _nosong.srt.")},
"log_song_stage": {
 "en": "=== Filling in the song section ===", "ko": "=== 노래 구간 채우기 ===",
 "ja": "=== 歌区間の補完 ===", "zh": "=== 填补歌曲片段 ===",
 "fr": "=== Remplissage de la partie chantée ===",
 "pt": "=== Preenchendo a parte cantada ===", "es": "=== Rellenando la parte cantada ==="},
"log_song_found_words": {
 "en": "Lyric words cluster at {s} - {e} ({n} words matched)",
 "ko": "가사 단어가 {s} ~ {e} 에 몰려 있습니다 ({n}개 일치)",
 "ja": "歌詞の単語が {s} ~ {e} に集中しています（{n}語一致）",
 "zh": "歌词词语集中在 {s} ~ {e}（匹配 {n} 个）",
 "fr": "Mots des paroles regroupés entre {s} et {e} ({n} correspondances)",
 "pt": "Palavras da letra concentradas entre {s} e {e} ({n} correspondências)",
 "es": "Palabras de la letra agrupadas entre {s} y {e} ({n} coincidencias)"},
"song_src_words": {
 "en": "word matching", "ko": "단어 대조", "ja": "単語照合", "zh": "词语比对",
 "fr": "correspondance de mots", "pt": "correspondência de palavras",
 "es": "coincidencia de palabras"},
"song_bad_wide": {
 "en": "the AI range is far too wide", "ko": "AI 구간이 너무 넓음",
 "ja": "AIの区間が広すぎる", "zh": "AI 给出的区间过宽",
 "fr": "plage IA beaucoup trop large", "pt": "faixa da IA larga demais",
 "es": "rango de la IA demasiado amplio"},
"song_bad_off": {
 "en": "the AI range does not line up", "ko": "AI 구간이 어긋남",
 "ja": "AIの区間がずれている", "zh": "AI 给出的区间不吻合",
 "fr": "la plage IA ne correspond pas", "pt": "a faixa da IA não bate",
 "es": "el rango de la IA no cuadra"},
"log_song_range": {
 "en": "Song section: {s} - {e} (source: {how})",
 "ko": "노래 구간: {s} ~ {e} (판단: {how})",
 "ja": "歌区間: {s} ~ {e}（判定: {how}）",
 "zh": "歌曲片段：{s} ~ {e}（判定：{how}）",
 "fr": "Partie chantée : {s} - {e} (source : {how})",
 "pt": "Parte cantada: {s} - {e} (origem: {how})",
 "es": "Parte cantada: {s} - {e} (origen: {how})"},
"log_song_none": {
 "en": "No song section found - the subtitles were left as they are.",
 "ko": "노래 구간을 찾지 못했습니다 — 자막은 그대로 둡니다.",
 "ja": "歌区間が見つかりませんでした — 字幕はそのままです。",
 "zh": "未找到歌曲片段 — 字幕保持原样。",
 "fr": "Aucune partie chantée trouvée - les sous-titres sont inchangés.",
 "pt": "Nenhuma parte cantada encontrada - as legendas ficaram como estão.",
 "es": "No se encontró parte cantada - los subtítulos quedan igual."},
"log_song_install": {
 "en": "Installing the vocal separator (Demucs). First time only, a few minutes.",
 "ko": "보컬 분리기(Demucs)를 설치합니다. 처음 한 번만, 몇 분 걸립니다.",
 "ja": "ボーカル分離(Demucs)をインストールします。初回のみ、数分かかります。",
 "zh": "正在安装人声分离器（Demucs）。仅首次，需几分钟。",
 "fr": "Installation du séparateur de voix (Demucs). Une seule fois, quelques minutes.",
 "pt": "Instalando o separador de voz (Demucs). Apenas na primeira vez, alguns minutos.",
 "es": "Instalando el separador de voz (Demucs). Solo la primera vez, unos minutos."},
"log_song_install_fail": {
 "en": "Could not install Demucs ({e}) - the song section was left as it is.",
 "ko": "Demucs 설치에 실패했습니다 ({e}) — 노래 구간은 그대로 둡니다.",
 "ja": "Demucs のインストールに失敗しました（{e}）— 歌区間はそのままです。",
 "zh": "Demucs 安装失败（{e}）— 歌曲片段保持原样。",
 "fr": "Échec de l'installation de Demucs ({e}) - partie chantée inchangée.",
 "pt": "Falha ao instalar o Demucs ({e}) - parte cantada inalterada.",
 "es": "No se pudo instalar Demucs ({e}) - parte cantada sin cambios."},
"log_song_separate": {
 "en": "Separating the vocals...", "ko": "보컬을 분리하는 중...",
 "ja": "ボーカルを分離中...", "zh": "正在分离人声...",
 "fr": "Séparation de la voix...", "pt": "Separando os vocais...",
 "es": "Separando la voz..."},
"log_song_separate_fail": {
 "en": "Vocal separation failed ({e}) - the song section was left as it is.",
 "ko": "보컬 분리에 실패했습니다 ({e}) — 노래 구간은 그대로 둡니다.",
 "ja": "ボーカル分離に失敗しました（{e}）— 歌区間はそのままです。",
 "zh": "人声分离失败（{e}）— 歌曲片段保持原样。",
 "fr": "Échec de la séparation ({e}) - partie chantée inchangée.",
 "pt": "Falha na separação ({e}) - parte cantada inalterada.",
 "es": "Fallo la separación ({e}) - parte cantada sin cambios."},
"log_song_clip_fail": {
 "en": "Could not cut out the song section ({e}).",
 "ko": "노래 구간을 잘라내지 못했습니다 ({e}).",
 "ja": "歌区間を切り出せませんでした（{e}）。",
 "zh": "无法截取歌曲片段（{e}）。",
 "fr": "Impossible d'extraire la partie chantée ({e}).",
 "pt": "Não foi possível recortar a parte cantada ({e}).",
 "es": "No se pudo recortar la parte cantada ({e})."},
"log_song_ai_fail": {
 "en": "The AI could not name the song section ({e}) - falling back to word matching.",
 "ko": "AI가 노래 구간을 짚지 못했습니다 ({e}) — 단어 대조로 찾습니다.",
 "ja": "AIが歌区間を特定できませんでした（{e}）— 単語照合で探します。",
 "zh": "AI 未能指出歌曲片段（{e}）— 改用词语比对查找。",
 "fr": "L'IA n'a pas identifié la partie chantée ({e}) - recherche par mots.",
 "pt": "A IA não identificou a parte cantada ({e}) - buscando por palavras.",
 "es": "La IA no identificó la parte cantada ({e}) - búsqueda por palabras."},
"log_song_ai_reject": {
 "en": "AI said {s} - {e}, but that does not hold up ({why}) - using word matching instead.",
 "ko": "AI는 {s} ~ {e} 라고 했는데 검산에서 걸렀습니다 ({why}) — 단어 대조 결과를 씁니다.",
 "ja": "AIは {s} ~ {e} と答えましたが検算で除外しました（{why}）— 単語照合を使います。",
 "zh": "AI 给出 {s} ~ {e}，但未通过校验（{why}）— 改用词语比对结果。",
 "fr": "L'IA a proposé {s} - {e}, rejeté à la vérification ({why}) - on garde la correspondance par mots.",
 "pt": "A IA indicou {s} - {e}, rejeitado na verificação ({why}) - usando a correspondência por palavras.",
 "es": "La IA propuso {s} - {e}, rechazado en la comprobación ({why}) - se usa la coincidencia por palabras."},
"log_song_asr": {
 "en": "Transcribing the vocals ({n} words)...",
 "ko": "보컬을 받아쓰는 중 ({n}단어 인식)...",
 "ja": "ボーカルを文字起こし中（{n}語認識）...",
 "zh": "正在转写人声（识别 {n} 词）...",
 "fr": "Transcription de la voix ({n} mots)...",
 "pt": "Transcrevendo os vocais ({n} palavras)...",
 "es": "Transcribiendo la voz ({n} palabras)..."},
"log_song_done": {
 "en": "Song section filled: {n} lyric lines in, {d} old lines removed. "
       "{hit} lines came from measured timing, {est} were estimated.",
 "ko": "노래 구간을 채웠습니다: 가사 {n}줄 넣고 기존 {d}줄 제거. "
       "{hit}줄은 실측 시각, {est}줄은 추정입니다.",
 "ja": "歌区間を補完しました: 歌詞 {n} 行を挿入、既存 {d} 行を削除。"
       "{hit} 行は実測、{est} 行は推定です。",
 "zh": "已填补歌曲片段：插入歌词 {n} 行，移除原有 {d} 行。"
       "{hit} 行为实测时间，{est} 行为推测。",
 "fr": "Partie chantée remplie : {n} lignes de paroles ajoutées, {d} anciennes retirées. "
       "{hit} lignes mesurées, {est} estimées.",
 "pt": "Parte cantada preenchida: {n} linhas de letra inseridas, {d} antigas removidas. "
       "{hit} linhas medidas, {est} estimadas.",
 "es": "Parte cantada rellenada: {n} líneas de letra insertadas, {d} antiguas eliminadas. "
       "{hit} líneas medidas, {est} estimadas."},
"log_song_backup": {
 "en": "Subtitles before the song step were saved separately: {p}",
 "ko": "노래 구간을 채우기 전 자막을 따로 저장했습니다: {p}",
 "ja": "歌区間の補完前の字幕を別途保存しました: {p}",
 "zh": "已另存填补前的字幕：{p}",
 "fr": "Les sous-titres d'avant l'étape chantée ont été enregistrés : {p}",
 "pt": "As legendas antes da etapa da música foram salvas: {p}",
 "es": "Los subtítulos previos al paso de la canción se guardaron: {p}"},
"log_song_fail": {
 "en": "The song step failed ({e}) - the subtitles were left as they are.",
 "ko": "노래 구간 채우기에 실패했습니다 ({e}) — 자막은 그대로 둡니다.",
 "ja": "歌区間の補完に失敗しました（{e}）— 字幕はそのままです。",
 "zh": "填补歌曲片段失败（{e}）— 字幕保持原样。",
 "fr": "Échec de l'étape chantée ({e}) - sous-titres inchangés.",
 "pt": "A etapa da música falhou ({e}) - legendas inalteradas.",
 "es": "El paso de la canción falló ({e}) - subtítulos sin cambios."},
"frm_prog": {"en": "Progress", "ko": "진행률", "ja": "進行状況", "zh": "进度",
 "fr": "Progression", "pt": "Progresso", "es": "Progreso"},
"st_idle": {"en": "Ready", "ko": "대기 중", "ja": "待機中", "zh": "就绪",
 "fr": "Prêt", "pt": "Pronto", "es": "Listo"},
"frm_log": {"en": "Log", "ko": "진행 상황", "ja": "ログ", "zh": "日志",
 "fr": "Journal", "pt": "Registro", "es": "Registro"},
"log_ready": {
 "en": "Ready. Select files and press 'Create subtitles'.",
 "ko": "준비 완료. 파일을 선택하고 '자막 만들기'를 누르세요.",
 "ja": "準備完了。ファイルを選択して「字幕を作成」を押してください。",
 "zh": "已就绪。请选择文件并点击“生成字幕”。",
 "fr": "Prêt. Sélectionnez des fichiers puis cliquez sur « Créer les sous-titres ».",
 "pt": "Pronto. Selecione arquivos e clique em 'Criar legendas'.",
 "es": "Listo. Selecciona archivos y pulsa 'Crear subtítulos'."},
"auto_detect": {"en": "Auto detect", "ko": "자동 감지", "ja": "自動検出", "zh": "自动检测",
 "fr": "Détection auto", "pt": "Detecção automática", "es": "Detección automática"},
"t_notice": {"en": "Notice", "ko": "알림", "ja": "お知らせ", "zh": "提示",
 "fr": "Information", "pt": "Aviso", "es": "Aviso"},
"t_error": {"en": "Error", "ko": "오류", "ja": "エラー", "zh": "错误",
 "fr": "Erreur", "pt": "Erro", "es": "Error"},
"w_no_file": {
 "en": "Please select a valid audio/video file.",
 "ko": "유효한 음성/영상 파일을 선택하세요.",
 "ja": "有効な音声/動画ファイルを選択してください。",
 "zh": "请选择有效的音频/视频文件。",
 "fr": "Veuillez sélectionner un fichier audio/vidéo valide.",
 "pt": "Selecione um arquivo de áudio/vídeo válido.",
 "es": "Selecciona un archivo de audio/vídeo válido."},
"w_no_lang": {
 "en": "Select at least one output language.",
 "ko": "출력 언어를 최소 1개 이상 선택하세요.",
 "ja": "出力言語を1つ以上選択してください。",
 "zh": "请至少选择一种输出语言。",
 "fr": "Sélectionnez au moins une langue de sortie.",
 "pt": "Selecione pelo menos um idioma de saída.",
 "es": "Selecciona al menos un idioma de salida."},
"fd_title": {
 "en": "Select audio/video files (multiple allowed)",
 "ko": "음성/영상 파일 선택 (여러 개 선택 가능)",
 "ja": "音声/動画ファイルを選択（複数可）",
 "zh": "选择音频/视频文件（可多选）",
 "fr": "Sélectionner des fichiers audio/vidéo (plusieurs possibles)",
 "pt": "Selecionar arquivos de áudio/vídeo (vários permitidos)",
 "es": "Seleccionar archivos de audio/vídeo (varios permitidos)"},
"fd_media": {"en": "Audio/Video", "ko": "음성/영상", "ja": "音声/動画", "zh": "音频/视频",
 "fr": "Audio/Vidéo", "pt": "Áudio/Vídeo", "es": "Audio/Vídeo"},
"fd_all": {"en": "All files", "ko": "모든 파일", "ja": "すべてのファイル", "zh": "所有文件",
 "fr": "Tous les fichiers", "pt": "Todos os arquivos", "es": "Todos los archivos"},
"lbl_nfiles": {"en": "{n} files selected", "ko": "{n}개 파일 선택됨", "ja": "{n}個のファイルを選択",
 "zh": "已选择 {n} 个文件", "fr": "{n} fichiers sélectionnés", "pt": "{n} arquivos selecionados",
 "es": "{n} archivos seleccionados"},
"log_sel": {"en": "Selected: {p}", "ko": "선택됨: {p}", "ja": "選択: {p}", "zh": "已选择: {p}",
 "fr": "Sélectionné : {p}", "pt": "Selecionado: {p}", "es": "Seleccionado: {p}"},
"st_prog": {
 "en": "{p}%   ·   {t}", "ko": "{p}%   ·   {t}", "ja": "{p}%   ·   {t}",
 "zh": "{p}%   ·   {t}", "fr": "{p} %   ·   {t}", "pt": "{p}%   ·   {t}",
 "es": "{p} %   ·   {t}"},
"stg_asr": {"en": "Transcribing", "ko": "받아쓰는 중", "ja": "文字起こし中", "zh": "转写中",
 "fr": "Transcription", "pt": "Transcrevendo", "es": "Transcribiendo"},
"stg_rebuild": {"en": "Rebuilding sentences", "ko": "문장 재조립 중", "ja": "文の再構成中",
 "zh": "重组句子中", "fr": "Reconstruction", "pt": "Remontando frases", "es": "Reconstruyendo"},
"stg_correct": {"en": "Correcting", "ko": "교정 중", "ja": "校正中", "zh": "校对中",
 "fr": "Correction", "pt": "Corrigindo", "es": "Corrigiendo"},
"stg_song": {"en": "Filling in the song", "ko": "노래 구간 채우는 중", "ja": "歌区間の補完中",
 "zh": "填补歌曲片段中", "fr": "Partie chantée", "pt": "Parte cantada", "es": "Parte cantada"},
"stg_extra": {"en": "Targeted fixes", "ko": "콕 집어 고치는 중", "ja": "狙って直しています",
 "zh": "精准修正中", "fr": "Corrections ciblées", "pt": "Correções pontuais",
 "es": "Correcciones puntuales"},
"stg_translate": {"en": "Translating", "ko": "번역 중", "ja": "翻訳中", "zh": "翻译中",
 "fr": "Traduction", "pt": "Traduzindo", "es": "Traduciendo"},
"st_remaining": {
 "en": "{p}%   ·   time left {t}", "ko": "{p}%   ·   남은 시간 {t}",
 "ja": "{p}%   ·   残り {t}", "zh": "{p}%   ·   剩余 {t}",
 "fr": "{p} %   ·   temps restant {t}", "pt": "{p}%   ·   tempo restante {t}",
 "es": "{p} %   ·   tiempo restante {t}"},
"st_cancelled": {"en": "Cancelled", "ko": "취소됨", "ja": "キャンセル済み", "zh": "已取消",
 "fr": "Annulé", "pt": "Cancelado", "es": "Cancelado"},
"st_preparing": {"en": "0%   ·   preparing", "ko": "0%   ·   준비 중", "ja": "0%   ·   準備中",
 "zh": "0%   ·   准备中", "fr": "0 %   ·   préparation", "pt": "0%   ·   preparando",
 "es": "0 %   ·   preparando"},
"calc": {"en": "estimating", "ko": "계산 중", "ja": "計算中", "zh": "估算中",
 "fr": "estimation", "pt": "estimando", "es": "estimando"},
"dur_s": {"en": "~{s}s", "ko": "약 {s}초", "ja": "約{s}秒", "zh": "约{s}秒",
 "fr": "~{s} s", "pt": "~{s}s", "es": "~{s} s"},
"dur_m": {"en": "~{m}m {s}s", "ko": "약 {m}분 {s}초", "ja": "約{m}分{s}秒", "zh": "约{m}分{s}秒",
 "fr": "~{m} min {s} s", "pt": "~{m}min {s}s", "es": "~{m} min {s} s"},
"dur_h": {"en": "~{h}h {m}m", "ko": "약 {h}시간 {m}분", "ja": "約{h}時間{m}分", "zh": "约{h}小时{m}分",
 "fr": "~{h} h {m} min", "pt": "~{h}h {m}min", "es": "~{h} h {m} min"},
}
I18N.update({
"log_no_key_note": {
 "en": "Note: no API key — AI steps (correction · split · translation) will be skipped.",
 "ko": "참고: API 키가 없어 AI 단계(교정·분할·번역)는 건너뜁니다.",
 "ja": "注意: APIキーがないため、AIの工程（校正・分割・翻訳）はスキップされます。",
 "zh": "注意：未填 API 密钥 — 将跳过 AI 步骤（校对·分句·翻译）。",
 "fr": "Remarque : pas de clé API — les étapes AI (correction · découpage · traduction) seront ignorées.",
 "pt": "Nota: sem chave de API — as etapas do AI (correção · divisão · tradução) serão puladas.",
 "es": "Nota: sin clave API — se omitirán los pasos de AI (corrección · división · traducción)."},

# ---- v1.2: 첫 실행 Gemini 권장 안내 ----
"intro_t": {
 "en": "Welcome — set up a free AI key first",
 "ko": "환영합니다 — 무료 AI 키부터 준비하세요",
 "ja": "ようこそ — まず無料のAIキーを用意してください",
 "zh": "欢迎 — 请先准备免费的 AI 密钥",
 "fr": "Bienvenue — commencez par une clé IA gratuite",
 "pt": "Bem-vindo — comece com uma chave de IA gratuita",
 "es": "Bienvenido — empieza con una clave de IA gratuita"},
"intro_b": {
 "en": ("Gemini is strongly recommended. It is free, needs no credit card, and takes about\n"
        "a minute to set up with a Google account.\n"
        "\n"
        "Why it matters\n"
        "  Speech recognition returns a stream of words with no sentence boundaries.\n"
        "  The AI is what turns them into real subtitles — one sentence per line, split\n"
        "  where the speaker actually changes, with punctuation. It also handles\n"
        "  translation into other languages.\n"
        "\n"
        "  Without a key the program still works, but it can only cut the text at\n"
        "  silences. Separate sentences get glued together, lines get cut in the middle,\n"
        "  and nothing is translated. The difference is large.\n"
        "\n"
        "The three engines\n"
        "  Gemini    free, recommended — best balance of quality and cost\n"
        "  Claude    paid — slightly better on difficult audio, billed per use\n"
        "  Local AI  free and offline — good quality now, but needs a decent GPU\n"
        "\n"
        "Click the button below to get a Gemini key, then paste it into the API key box\n"
        "on the main screen. You can also reach this from the ? button any time."),
 "ko": ("Gemini를 강력히 권장합니다. 무료이고 카드 등록도 필요 없으며, 구글 계정만\n"
        "있으면 1분이면 발급됩니다.\n"
        "\n"
        "왜 필요한가\n"
        "  음성 인식은 문장 구분이 없는 단어 나열만 돌려줍니다.\n"
        "  이걸 진짜 자막으로 만드는 게 AI입니다 — 한 줄에 한 문장씩, 말하는 사람이\n"
        "  바뀌는 자리에서 끊고, 문장부호를 붙입니다. 다른 언어 번역도 AI가 합니다.\n"
        "\n"
        "  키가 없어도 프로그램은 돌아가지만, 소리가 끊기는 지점에서 자르는 것밖에\n"
        "  못 합니다. 서로 다른 문장이 한 줄에 붙고, 문장이 중간에 잘리고, 번역은\n"
        "  아예 되지 않습니다. 차이가 큽니다.\n"
        "\n"
        "엔진 3종\n"
        "  Gemini     무료 · 권장 — 품질과 비용의 균형이 가장 좋습니다\n"
        "  Claude     유료 — 어려운 음성에서 조금 더 낫고, 쓴 만큼 과금됩니다\n"
        "  로컬 AI    무료 · 오프라인 — 품질은 좋아졌지만 GPU 성능을 탑니다\n"
        "\n"
        "아래 버튼으로 Gemini 키를 발급받아 메인 화면의 API 키 칸에 붙여넣으세요.\n"
        "이 안내는 ? 버튼에서 언제든 다시 볼 수 있습니다."),
 "ja": ("Gemini を強くおすすめします。無料でカード登録も不要、Googleアカウントがあれば\n"
        "1分ほどで取得できます。\n"
        "\n"
        "なぜ必要か\n"
        "  音声認識は文の区切りがない単語の羅列しか返しません。\n"
        "  それを本物の字幕にするのがAIです — 1行1文にまとめ、話者が変わる位置で\n"
        "  区切り、句読点を付けます。他言語への翻訳もAIが行います。\n"
        "\n"
        "  キーがなくても動作しますが、無音位置で切ることしかできません。別々の文が\n"
        "  1行にくっつき、文が途中で切れ、翻訳は行われません。差は大きいです。\n"
        "\n"
        "エンジン3種\n"
        "  Gemini     無料・推奨 — 品質とコストのバランスが最良\n"
        "  Claude     有料 — 難しい音声でやや優秀、従量課金\n"
        "  ローカルAI 無料・オフライン — 品質は向上しましたがGPU性能に依存します\n"
        "\n"
        "下のボタンから Gemini キーを取得し、メイン画面のAPIキー欄に貼り付けてください。\n"
        "この案内は ? ボタンからいつでも再表示できます。"),
 "zh": ("强烈推荐 Gemini。免费、无需绑卡，有 Google 账号约一分钟即可申请。\n"
        "\n"
        "为什么需要\n"
        "  语音识别只会返回没有句子边界的单词流。\n"
        "  把它变成真正字幕的正是 AI — 一行一句，在说话人切换处断句，并加上标点。\n"
        "  翻译成其他语言也由 AI 完成。\n"
        "\n"
        "  没有密钥程序仍可运行，但只能在静音处切分。不同的句子会挤在一行，句子会\n"
        "  从中间断开，而且不会翻译。差别很大。\n"
        "\n"
        "三种引擎\n"
        "  Gemini    免费 · 推荐 — 质量与成本平衡最佳\n"
        "  Claude    付费 — 在困难音频上略好，按用量计费\n"
        "  本地 AI   免费 · 离线 — 质量已不错，但依赖显卡性能\n"
        "\n"
        "点击下方按钮获取 Gemini 密钥，然后粘贴到主界面的 API 密钥框。\n"
        "此说明可随时通过 ? 按钮再次查看。"),
 "fr": ("Gemini est fortement recommandé. C'est gratuit, sans carte bancaire, et il faut\n"
        "environ une minute avec un compte Google.\n"
        "\n"
        "Pourquoi c'est important\n"
        "  La reconnaissance vocale ne renvoie qu'un flux de mots sans frontières de phrase.\n"
        "  C'est l'IA qui en fait de vrais sous-titres — une phrase par ligne, coupée là où\n"
        "  le locuteur change, avec la ponctuation. Elle gère aussi la traduction.\n"
        "\n"
        "  Sans clé le programme fonctionne, mais il ne peut couper qu'aux silences.\n"
        "  Des phrases distinctes se retrouvent collées, des lignes sont coupées au milieu,\n"
        "  et rien n'est traduit. La différence est importante.\n"
        "\n"
        "Les trois moteurs\n"
        "  Gemini    gratuit, recommandé — meilleur rapport qualité/coût\n"
        "  Claude    payant — un peu meilleur sur l'audio difficile, facturé à l'usage\n"
        "  IA locale gratuite, hors ligne — bonne qualité, mais exige un vrai GPU\n"
        "\n"
        "Cliquez ci-dessous pour obtenir une clé Gemini, puis collez-la dans le champ\n"
        "de clé API. Ce message reste accessible via le bouton ?."),
 "pt": ("O Gemini é fortemente recomendado. É grátis, não pede cartão e leva cerca de\n"
        "um minuto com uma conta Google.\n"
        "\n"
        "Por que importa\n"
        "  O reconhecimento de fala devolve apenas palavras, sem limites de frase.\n"
        "  É a IA que as transforma em legendas de verdade — uma frase por linha, cortada\n"
        "  onde o falante muda, com pontuação. Ela também faz a tradução.\n"
        "\n"
        "  Sem chave o programa funciona, mas só consegue cortar nos silêncios. Frases\n"
        "  diferentes ficam grudadas, linhas são cortadas no meio e nada é traduzido.\n"
        "  A diferença é grande.\n"
        "\n"
        "Os três motores\n"
        "  Gemini    grátis, recomendado — melhor equilíbrio entre qualidade e custo\n"
        "  Claude    pago — um pouco melhor em áudio difícil, cobrado por uso\n"
        "  IA local  grátis, offline — boa qualidade, mas exige uma GPU decente\n"
        "\n"
        "Clique no botão abaixo para obter uma chave Gemini e cole-a no campo de chave\n"
        "de API. Este aviso continua disponível no botão ?."),
 "es": ("Se recomienda encarecidamente Gemini. Es gratis, no pide tarjeta y se consigue\n"
        "en un minuto con una cuenta de Google.\n"
        "\n"
        "Por qué importa\n"
        "  El reconocimiento de voz solo devuelve palabras, sin límites de frase.\n"
        "  Es la IA la que las convierte en subtítulos reales — una frase por línea, cortada\n"
        "  donde cambia quien habla, con puntuación. También hace la traducción.\n"
        "\n"
        "  Sin clave el programa funciona, pero solo puede cortar en los silencios. Frases\n"
        "  distintas quedan pegadas, las líneas se cortan por la mitad y no se traduce nada.\n"
        "  La diferencia es grande.\n"
        "\n"
        "Los tres motores\n"
        "  Gemini    gratis, recomendado — mejor equilibrio entre calidad y coste\n"
        "  Claude    de pago — algo mejor con audio difícil, se cobra por uso\n"
        "  IA local  gratis, sin conexión — buena calidad, pero exige una GPU decente\n"
        "\n"
        "Pulsa el botón de abajo para obtener una clave Gemini y pégala en el campo de\n"
        "clave API. Este aviso sigue disponible en el botón ?."),},
"intro_btn": {
 "en": "Get a free Gemini key (opens browser)",
 "ko": "무료 Gemini 키 발급받기 (브라우저 열림)",
 "ja": "無料の Gemini キーを取得（ブラウザが開きます）",
 "zh": "获取免费 Gemini 密钥（将打开浏览器）",
 "fr": "Obtenir une clé Gemini gratuite (ouvre le navigateur)",
 "pt": "Obter chave Gemini grátis (abre o navegador)",
 "es": "Obtener clave Gemini gratis (abre el navegador)"},

# ---- v1.2: 키 없이 변환 시작할 때 확인 ----
"nokey_t": {
 "en": "No API key — AI steps will be skipped",
 "ko": "API 키가 없습니다 — AI 단계를 건너뜁니다",
 "ja": "APIキーがありません — AI工程をスキップします",
 "zh": "没有 API 密钥 — 将跳过 AI 步骤",
 "fr": "Pas de clé API — les étapes IA seront ignorées",
 "pt": "Sem chave de API — as etapas de IA serão puladas",
 "es": "Sin clave API — se omitirán los pasos de IA"},
"nokey_b": {
 "en": ("AI is turned on, but the {p} API key box is empty, so every AI step will be\n"
        "skipped: sentence rebuilding, proofreading and translation.\n"
        "\n"
        "The subtitles will still be created, but they can only be cut at silences —\n"
        "separate sentences end up glued together and lines get cut mid-sentence.\n"
        "No translated files will be produced.\n"
        "\n"
        "Continue anyway?"),
 "ko": ("AI가 켜져 있지만 {p} API 키 칸이 비어 있어, AI 단계가 전부 생략됩니다:\n"
        "문장 재조립, 교정, 번역 모두 건너뜁니다.\n"
        "\n"
        "자막은 만들어지지만 소리가 끊기는 지점에서 자르는 것밖에 못 합니다 —\n"
        "서로 다른 문장이 한 줄에 붙고, 문장이 중간에서 잘립니다.\n"
        "번역 파일은 만들어지지 않습니다.\n"
        "\n"
        "그래도 진행할까요?"),
 "ja": ("AIはオンですが {p} APIキー欄が空のため、AI工程がすべてスキップされます:\n"
        "文の再構成・校正・翻訳のすべてです。\n"
        "\n"
        "字幕は作成されますが、無音位置で切ることしかできません — 別々の文が\n"
        "1行にくっつき、文が途中で切れます。翻訳ファイルは作成されません。\n"
        "\n"
        "このまま続行しますか？"),
 "zh": ("AI 已开启，但 {p} API 密钥框为空，因此所有 AI 步骤都会被跳过：\n"
        "句子重组、校对和翻译。\n"
        "\n"
        "字幕仍会生成，但只能在静音处切分 — 不同的句子会挤在一行，句子会从\n"
        "中间断开。不会生成翻译文件。\n"
        "\n"
        "仍要继续吗？"),
 "fr": ("L'IA est activée, mais le champ de clé API {p} est vide : toutes les étapes IA\n"
        "seront ignorées (reconstruction des phrases, relecture et traduction).\n"
        "\n"
        "Les sous-titres seront créés, mais ne pourront être coupés qu'aux silences —\n"
        "des phrases distinctes seront collées et des lignes coupées en plein milieu.\n"
        "Aucun fichier traduit ne sera produit.\n"
        "\n"
        "Continuer quand même ?"),
 "pt": ("A IA está ligada, mas o campo da chave de API {p} está vazio, então todas as\n"
        "etapas de IA serão puladas: remontagem de frases, revisão e tradução.\n"
        "\n"
        "As legendas ainda serão criadas, mas só podem ser cortadas nos silêncios —\n"
        "frases diferentes ficam grudadas e linhas são cortadas no meio.\n"
        "Nenhum arquivo traduzido será gerado.\n"
        "\n"
        "Continuar mesmo assim?"),
 "es": ("La IA está activada, pero el campo de clave API de {p} está vacío, así que se\n"
        "omitirán todos los pasos de IA: reconstrucción, corrección y traducción.\n"
        "\n"
        "Los subtítulos se crearán, pero solo se pueden cortar en los silencios —\n"
        "frases distintas quedan pegadas y las líneas se cortan por la mitad.\n"
        "No se generará ningún archivo traducido.\n"
        "\n"
        "¿Continuar de todos modos?"),},


# ---- v1.2: 로컬 AI 진행 상황 (다운로드 % / 응답 생성 중) ----
"log_pull_pct": {
 "en": "  downloading {m} ... {p}%  ({d} / {t}){e}",
 "ko": "  {m} 다운로드 중 ... {p}%  ({d} / {t}){e}",
 "ja": "  {m} をダウンロード中 ... {p}%  ({d} / {t}){e}",
 "zh": "  正在下载 {m} ... {p}%  ({d} / {t}){e}",
 "fr": "  téléchargement de {m} ... {p} %  ({d} / {t}){e}",
 "pt": "  baixando {m} ... {p}%  ({d} / {t}){e}",
 "es": "  descargando {m} ... {p}%  ({d} / {t}){e}"},
"log_pull_step": {
 "en": "  {s}", "ko": "  {s}", "ja": "  {s}", "zh": "  {s}",
 "fr": "  {s}", "pt": "  {s}", "es": "  {s}"},
"log_pull_done": {
 "en": "Download complete ({t})", "ko": "다운로드 완료 ({t})",
 "ja": "ダウンロード完了 ({t})", "zh": "下载完成 ({t})",
 "fr": "Téléchargement terminé ({t})", "pt": "Download concluído ({t})",
 "es": "Descarga completada ({t})"},
"log_local_gen": {
 "en": "  local AI is writing ... {n} chars ({s}s)",
 "ko": "  로컬 AI 응답 생성 중 ... {n}자 ({s}초)",
 "ja": "  ローカルAIが生成中 ... {n}文字 ({s}秒)",
 "zh": "  本地 AI 生成中 ... {n} 字 ({s} 秒)",
 "fr": "  l'IA locale rédige ... {n} caractères ({s} s)",
 "pt": "  a IA local está escrevendo ... {n} caracteres ({s}s)",
 "es": "  la IA local está escribiendo ... {n} caracteres ({s}s)"},
"log_local_think": {
 "en": "  local AI is thinking ... ({s}s)",
 "ko": "  로컬 AI가 생각 중 ... ({s}초)",
 "ja": "  ローカルAIが思考中 ... ({s}秒)",
 "zh": "  本地 AI 思考中 ... ({s} 秒)",
 "fr": "  l'IA locale réfléchit ... ({s} s)",
 "pt": "  a IA local está pensando ... ({s}s)",
 "es": "  la IA local está pensando ... ({s}s)"},
"log_local_gen_done": {
 "en": "  done — {n} chars in {s}s",
 "ko": "  완료 — {n}자 / {s}초",
 "ja": "  完了 — {n}文字 / {s}秒",
 "zh": "  完成 — {n} 字 / {s} 秒",
 "fr": "  terminé — {n} caractères en {s} s",
 "pt": "  concluído — {n} caracteres em {s}s",
 "es": "  listo — {n} caracteres en {s}s"},
"log_local_stall": {
 "en": ("Local AI sent nothing for {s}s. The model may be too large for this PC's GPU "
        "memory, or Ollama may still be loading it into memory."),
 "ko": ("로컬 AI가 {s}초 동안 아무 응답도 보내지 않았습니다. 모델이 이 PC의 GPU 메모리에 비해 "
        "너무 크거나, Ollama가 아직 모델을 메모리에 올리는 중일 수 있습니다."),
 "ja": ("ローカルAIから{s}秒間応答がありません。モデルがこのPCのGPUメモリに対して大きすぎるか、"
        "Ollamaがまだモデルを読み込み中の可能性があります。"),
 "zh": ("本地 AI 已 {s} 秒没有任何响应。模型可能超出本机 GPU 显存，或 Ollama 仍在加载模型。"),
 "fr": ("L'IA locale n'a rien envoyé pendant {s} s. Le modèle est peut-être trop gros pour la "
        "mémoire GPU de ce PC, ou Ollama est encore en train de le charger."),
 "pt": ("A IA local não enviou nada por {s}s. O modelo pode ser grande demais para a memória "
        "da GPU deste PC, ou o Ollama ainda está carregando-o."),
 "es": ("La IA local no ha enviado nada durante {s}s. El modelo puede ser demasiado grande para "
        "la memoria de la GPU de este PC, o Ollama aún lo está cargando.")},

"log_loading": {"en": "Loading model: {m}", "ko": "모델 로딩 중: {m}", "ja": "モデル読み込み中: {m}",
 "zh": "正在加载模型: {m}", "fr": "Chargement du modèle : {m}", "pt": "Carregando modelo: {m}",
 "es": "Cargando modelo: {m}"},
"log_first": {
 "en": "(first run downloads the model — this can take a while)",
 "ko": "(처음 실행 시 모델을 내려받느라 시간이 걸립니다)",
 "ja": "（初回実行時はモデルのダウンロードに時間がかかります）",
 "zh": "（首次运行需要下载模型，可能较慢）",
 "fr": "(le premier lancement télécharge le modèle — cela peut prendre du temps)",
 "pt": "(a primeira execução baixa o modelo — pode demorar)",
 "es": "(la primera ejecución descarga el modelo — puede tardar)"},
"log_gpu": {"en": "Using GPU (CUDA)", "ko": "GPU(CUDA) 사용 중", "ja": "GPU（CUDA）使用中",
 "zh": "正在使用 GPU（CUDA）", "fr": "GPU (CUDA) utilisé", "pt": "Usando GPU (CUDA)",
 "es": "Usando GPU (CUDA)"},
"log_gpu_check": {
 "en": "Testing the GPU...", "ko": "GPU가 실제로 되는지 확인 중...",
 "ja": "GPUが実際に使えるか確認中...", "zh": "正在测试 GPU 是否可用...",
 "fr": "Test du GPU en cours...", "pt": "Testando a GPU...",
 "es": "Probando la GPU..."},
"log_gpu_runtime_fail": {
 "en": "GPU failed during transcription -> switching to CPU and restarting this file ({e})",
 "ko": "받아쓰는 중 GPU에서 실패 -> CPU로 바꿔 이 파일을 다시 시작합니다 ({e})",
 "ja": "文字起こし中にGPUで失敗 -> CPUに切替えてこのファイルをやり直します ({e})",
 "zh": "转写过程中 GPU 失败 -> 改用 CPU 并重新处理该文件（{e}）",
 "fr": "Échec du GPU pendant la transcription -> passage au CPU, fichier relancé ({e})",
 "pt": "Falha da GPU durante a transcrição -> mudando para CPU e reiniciando este arquivo ({e})",
 "es": "Fallo de GPU durante la transcripción -> cambiando a CPU y reiniciando este archivo ({e})"},
"log_cuda_hint": {
 "en": "To use the GPU, install the CUDA runtime:\n"
       "    pip install nvidia-cublas-cu12 nvidia-cudnn-cu12",
 "ko": "GPU를 쓰려면 CUDA 런타임을 설치하세요:\n"
       "    pip install nvidia-cublas-cu12 nvidia-cudnn-cu12",
 "ja": "GPUを使うにはCUDAランタイムを入れてください:\n"
       "    pip install nvidia-cublas-cu12 nvidia-cudnn-cu12",
 "zh": "要使用 GPU，请安装 CUDA 运行库：\n"
       "    pip install nvidia-cublas-cu12 nvidia-cudnn-cu12",
 "fr": "Pour utiliser le GPU, installez le runtime CUDA :\n"
       "    pip install nvidia-cublas-cu12 nvidia-cudnn-cu12",
 "pt": "Para usar a GPU, instale o runtime CUDA:\n"
       "    pip install nvidia-cublas-cu12 nvidia-cudnn-cu12",
 "es": "Para usar la GPU, instale el runtime CUDA:\n"
       "    pip install nvidia-cublas-cu12 nvidia-cudnn-cu12"},
"log_gpu_fail": {
 "en": "GPU unavailable -> falling back to CPU ({e})", "ko": "GPU 사용 실패 -> CPU로 전환 ({e})",
 "ja": "GPU使用不可 -> CPUに切替 ({e})", "zh": "GPU 不可用 -> 改用 CPU（{e}）",
 "fr": "GPU indisponible -> bascule sur CPU ({e})", "pt": "GPU indisponível -> usando CPU ({e})",
 "es": "GPU no disponible -> usando CPU ({e})"},
"log_recog": {"en": "=== Transcribing ({l}) ===", "ko": "=== 음성 인식 ({l}) ===",
 "ja": "=== 音声認識中 ({l}) ===", "zh": "=== 语音识别中（{l}）===",
 "fr": "=== Transcription ({l}) ===", "pt": "=== Transcrevendo ({l}) ===",
 "es": "=== Transcribiendo ({l}) ==="},
"log_detected": {"en": "Detected language: {l}{p}", "ko": "감지된 언어: {l}{p}",
 "ja": "検出された言語: {l}{p}", "zh": "检测到的语言: {l}{p}",
 "fr": "Langue détectée : {l}{p}", "pt": "Idioma detectado: {l}{p}",
 "es": "Idioma detectado: {l}{p}"},
"log_organize": {"en": "Organizing into sentences...", "ko": "문장 단위로 정리 중...",
 "ja": "文単位に整理中...", "zh": "正在按句整理...", "fr": "Organisation en phrases...",
 "pt": "Organizando em frases...", "es": "Organizando en frases..."},
"log_saved": {"en": "Saved -> {p}", "ko": "완료 -> {p}", "ja": "保存 -> {p}", "zh": "已保存 -> {p}",
 "fr": "Enregistré -> {p}", "pt": "Salvo -> {p}", "es": "Guardado -> {p}"},
"log_no_speech": {
 "en": "⚠ WARNING: no speech was recognized in this file. It may be corrupted, truncated, or silent. No subtitle file was written.",
 "ko": "⚠ 경고: 이 파일에서 음성을 인식하지 못했습니다. 파일이 손상됐거나 잘렸거나 무음일 수 있습니다. 자막 파일을 만들지 않았습니다.",
 "ja": "⚠ 警告: このファイルから音声を認識できませんでした。破損・途中切断・無音の可能性があります。字幕ファイルは作成されませんでした。",
 "zh": "⚠ 警告：未能在此文件中识别到语音。文件可能已损坏、被截断或为无声。未生成字幕文件。",
 "fr": "⚠ ATTENTION : aucune parole reconnue dans ce fichier. Il est peut-être corrompu, tronqué ou muet. Aucun sous-titre n'a été créé.",
 "pt": "⚠ AVISO: nenhuma fala foi reconhecida neste arquivo. Ele pode estar corrompido, truncado ou mudo. Nenhuma legenda foi criada.",
 "es": "⚠ AVISO: no se reconoció voz en este archivo. Puede estar dañado, truncado o en silencio. No se creó ningún subtítulo."},
"log_correct": {"en": "Correcting {l} with AI...", "ko": "AI로 {l} 교정 중...",
 "ja": "AIで{l}を校正中...", "zh": "正在用 AI 校对 {l}...",
 "fr": "Correction {l} avec AI...", "pt": "Corrigindo {l} com AI...",
 "es": "Corrigiendo {l} con AI..."},
"log_correct_fail": {"en": "Correction failed (keeping original): {e}",
 "ko": "교정 실패(원본 유지): {e}", "ja": "校正失敗（原文維持）: {e}",
 "zh": "校对失败（保留原文）: {e}", "fr": "Échec de la correction (original conservé) : {e}",
 "pt": "Falha na correção (original mantido): {e}", "es": "Fallo de corrección (se mantiene original): {e}"},
"log_split_check": {"en": "Checking for run-on subtitles...", "ko": "긴 자막 문장 분할 확인 중...",
 "ja": "長い字幕の分割を確認中...", "zh": "正在检查过长字幕...",
 "fr": "Vérification des sous-titres trop longs...", "pt": "Verificando legendas longas...",
 "es": "Comprobando subtítulos demasiado largos..."},
"log_split_fail": {"en": "Sentence split failed (keeping original): {e}",
 "ko": "문장 분할 실패(원본 유지): {e}", "ja": "文分割失敗（原文維持）: {e}",
 "zh": "分句失败（保留原文）: {e}", "fr": "Échec du découpage (original conservé) : {e}",
 "pt": "Falha na divisão (original mantido): {e}", "es": "Fallo de división (se mantiene original): {e}"},
"log_off_split": {
 "en": "(AI OFF — no correction; run-on subtitles are split at silences)",
 "ko": "(AI 꺼짐 — 교정 없이, 뭉친 자막은 침묵 기준으로 분할합니다)",
 "ja": "（AIオフ — 校正なし、長い字幕は無音位置で分割します）",
 "zh": "（AI 关闭 — 不校对；过长字幕按静音位置切分）",
 "fr": "(AI désactivé — pas de correction ; découpage aux silences)",
 "pt": "(AI desligado — sem correção; divisão nos silêncios)",
 "es": "(AI desactivado — sin corrección; división en los silencios)"},
"log_nokey_split": {
 "en": "(No API key — no correction; run-on subtitles are split at silences)",
 "ko": "(API 키 없음 — 교정 없이, 뭉친 자막은 침묵 기준으로 분할합니다)",
 "ja": "（APIキーなし — 校正なし、長い字幕は無音位置で分割します）",
 "zh": "（无 API 密钥 — 不校对；过长字幕按静音位置切分）",
 "fr": "(Pas de clé API — pas de correction ; découpage aux silences)",
 "pt": "(Sem chave de API — sem correção; divisão nos silêncios)",
 "es": "(Sin clave API — sin corrección; división en los silencios)"},
"log_pause_fail": {"en": "Silence-based split failed (keeping original): {e}",
 "ko": "침묵 기준 분할 실패(원본 유지): {e}", "ja": "無音分割失敗（原文維持）: {e}",
 "zh": "按静音切分失败（保留原文）: {e}", "fr": "Échec du découpage aux silences (original conservé) : {e}",
 "pt": "Falha na divisão por silêncio (original mantido): {e}",
 "es": "Fallo de división por silencios (se mantiene original): {e}"},
"log_translate": {"en": "=== {l} (translation) ===", "ko": "=== {l} (번역) ===",
 "ja": "=== {l}（翻訳）===", "zh": "=== {l}（翻译）===", "fr": "=== {l} (traduction) ===",
 "pt": "=== {l} (tradução) ===", "es": "=== {l} (traducción) ==="},
"log_skip_tr_off": {"en": "(AI OFF — skipping translation)", "ko": "(AI 꺼짐 — 번역을 건너뜁니다)",
 "ja": "（AIオフ — 翻訳をスキップ）", "zh": "（AI 关闭 — 跳过翻译）",
 "fr": "(AI désactivé — traduction ignorée)", "pt": "(AI desligado — pulando tradução)",
 "es": "(AI desactivado — se omite la traducción)"},
"log_skip_tr_nokey": {
 "en": "(No API key — skipping translation; a key is required to translate)",
 "ko": "(API 키가 없어 번역을 건너뜁니다 — 번역엔 키 필요)",
 "ja": "（APIキーがないため翻訳をスキップ — 翻訳にはキーが必要）",
 "zh": "（无 API 密钥，跳过翻译 — 翻译需要密钥）",
 "fr": "(Pas de clé API — traduction ignorée ; une clé est requise)",
 "pt": "(Sem chave de API — pulando tradução; é preciso uma chave)",
 "es": "(Sin clave API — se omite la traducción; se requiere una clave)"},
"log_tr_fail": {"en": "Translation failed ({l}) — skipped: {e}", "ko": "번역 실패({l}) — 건너뜀: {e}",
 "ja": "翻訳失敗（{l}）— スキップ: {e}", "zh": "翻译失败（{l}）— 已跳过: {e}",
 "fr": "Échec de traduction ({l}) — ignoré : {e}", "pt": "Falha na tradução ({l}) — pulado: {e}",
 "es": "Fallo de traducción ({l}) — omitido: {e}"},
"log_all_done_t": {
 "en": "All done ({n} files) - {t}{p}", "ko": "전체 완료 ({n}개 파일) — {t}{p}",
 "ja": "すべて完了（{n}ファイル）— {t}{p}", "zh": "全部完成（{n} 个文件）— {t}{p}",
 "fr": "Terminé ({n} fichiers) - {t}{p}", "pt": "Tudo pronto ({n} arquivos) - {t}{p}",
 "es": "Todo listo ({n} archivos) - {t}{p}"},
"st_asr": {"en": "transcribe", "ko": "받아쓰기", "ja": "文字起こし", "zh": "转写",
 "fr": "transcription", "pt": "transcrição", "es": "transcripción"},
"st_rebuild": {"en": "rebuild", "ko": "재조립", "ja": "再構成", "zh": "重组",
 "fr": "reconstruction", "pt": "remontagem", "es": "reconstrucción"},
"st_correct": {"en": "correct", "ko": "교정", "ja": "校正", "zh": "校对",
 "fr": "correction", "pt": "correção", "es": "corrección"},
"st_song": {"en": "song", "ko": "노래", "ja": "歌", "zh": "歌曲",
 "fr": "chanson", "pt": "música", "es": "canción"},
"st_extra": {"en": "targeted fixes", "ko": "콕 집어 고치기", "ja": "狙って直す", "zh": "精准修正",
 "fr": "corrections ciblées", "pt": "correções pontuais", "es": "correcciones puntuales"},
"st_translate": {"en": "translate", "ko": "번역", "ja": "翻訳", "zh": "翻译",
 "fr": "traduction", "pt": "tradução", "es": "traducción"},
"log_all_done": {"en": "All done ({n} files)", "ko": "전체 완료 ({n}개 파일)",
 "ja": "すべて完了（{n}ファイル）", "zh": "全部完成（{n} 个文件）",
 "fr": "Terminé ({n} fichiers)", "pt": "Tudo pronto ({n} arquivos)",
 "es": "Todo listo ({n} archivos)"},
"log_cancelled": {"en": "Cancelled.", "ko": "취소되었습니다.", "ja": "キャンセルされました。",
 "zh": "已取消。", "fr": "Annulé.", "pt": "Cancelado.", "es": "Cancelado."},
"log_cancel_req": {"en": "Cancel requested... stopping soon.", "ko": "취소 요청됨... 곧 멈춥니다.",
 "ja": "キャンセル要求... まもなく停止します。", "zh": "已请求取消... 即将停止。",
 "fr": "Annulation demandée... arrêt imminent.", "pt": "Cancelamento solicitado... parando em breve.",
 "es": "Cancelación solicitada... se detendrá pronto."},
"log_cancel_recog": {"en": "Cancelled during transcription.", "ko": "음성 인식 중 취소되었습니다.",
 "ja": "音声認識中にキャンセルされました。", "zh": "在识别过程中被取消。",
 "fr": "Annulé pendant la transcription.", "pt": "Cancelado durante a transcrição.",
 "es": "Cancelado durante la transcripción."},
"log_no_runon": {"en": "No run-on subtitles (split skipped)", "ko": "뭉친 자막 없음 (분할 생략)",
 "ja": "長い字幕なし（分割スキップ）", "zh": "无过长字幕（跳过切分）",
 "fr": "Aucun sous-titre trop long (découpage ignoré)", "pt": "Nenhuma legenda longa (divisão pulada)",
 "es": "Sin subtítulos largos (división omitida)"},
"log_runon_found_c": {"en": "{n} run-on subtitles found -> splitting with AI",
 "ko": "뭉친 자막 {n}개 발견 -> AI로 문장 분할",
 "ja": "長い字幕を{n}件検出 -> AIで分割", "zh": "发现 {n} 条过长字幕 -> 用 AI 分句",
 "fr": "{n} sous-titres trop longs -> découpage avec l'IA",
 "pt": "{n} legendas longas encontradas -> dividindo com a IA",
 "es": "{n} subtítulos largos encontrados -> dividiendo con la IA"},
"log_runon_found_p": {"en": "{n} run-on subtitles found -> splitting at silences",
 "ko": "뭉친 자막 {n}개 발견 -> 침묵 기준 분할",
 "ja": "長い字幕を{n}件検出 -> 無音位置で分割", "zh": "发现 {n} 条过长字幕 -> 按静音切分",
 "fr": "{n} sous-titres trop longs -> découpage aux silences",
 "pt": "{n} legendas longas encontradas -> dividindo nos silêncios",
 "es": "{n} subtítulos largos encontrados -> dividiendo en los silencios"},
"log_piece": {"en": "  #{i} -> split into {n}", "ko": "  #{i} -> {n}개로 분할",
 "ja": "  #{i} -> {n}件に分割", "zh": "  #{i} -> 分为 {n} 条",
 "fr": "  #{i} -> découpé en {n}", "pt": "  #{i} -> dividido em {n}",
 "es": "  #{i} -> dividido en {n}"},
"log_piece_fail": {"en": "  #{i} split failed (keeping original): {e}",
 "ko": "  #{i} 분할 실패(원본 유지): {e}", "ja": "  #{i} 分割失敗（原文維持）: {e}",
 "zh": "  #{i} 切分失败（保留原文）: {e}", "fr": "  #{i} échec du découpage (original conservé) : {e}",
 "pt": "  #{i} falha na divisão (original mantido): {e}",
 "es": "  #{i} fallo de división (se mantiene original): {e}"},
"log_api_call": {"en": "Calling {p} API...", "ko": "{p} API 호출 중...",
 "ja": "{p} APIを呼び出し中...", "zh": "正在调用 {p} API...",
 "fr": "Appel de l'API {p}...", "pt": "Chamando a API {p}...",
 "es": "Llamando a la API de {p}..."},

# ---- v1.2: 단어 타임스탬프 기반 문장 재조립 ----
"log_rebuild": {
 "en": "=== Rebuilding sentences from word timings ({n} words) ===",
 "ko": "=== 단어 타임스탬프로 문장 재조립 중 ({n}개 단어) ===",
 "ja": "=== 単語タイムスタンプから文を再構成中（{n}語） ===",
 "zh": "=== 依据单词时间戳重组句子（{n} 个词） ===",
 "fr": "=== Reconstruction des phrases d'après les mots ({n} mots) ===",
 "pt": "=== Reconstruindo frases a partir das palavras ({n} palavras) ===",
 "es": "=== Reconstruyendo frases a partir de las palabras ({n} palabras) ==="},
"log_rebuild_done": {
 "en": "Rebuild done: {a} -> {b} subtitles",
 "ko": "재조립 완료: 자막 {a}개 -> {b}개",
 "ja": "再構成完了: 字幕 {a}件 -> {b}件",
 "zh": "重组完成：字幕 {a} 条 -> {b} 条",
 "fr": "Reconstruction terminée : {a} -> {b} sous-titres",
 "pt": "Reconstrução concluída: {a} -> {b} legendas",
 "es": "Reconstrucción terminada: {a} -> {b} subtítulos"},
"log_rebuild_fail": {
 "en": "Rebuild failed (keeping original): {e}",
 "ko": "재조립 실패 (원본 유지): {e}",
 "ja": "再構成に失敗（原文維持）: {e}",
 "zh": "重组失败（保留原文）: {e}",
 "fr": "Échec de la reconstruction (original conservé) : {e}",
 "pt": "Falha na reconstrução (original mantido): {e}",
 "es": "Fallo en la reconstrucción (se mantiene el original): {e}"},
"log_rebuild_reject": {
 "en": "  Block {c}: AI reply failed validation ({r}) — original kept",
 "ko": "  {c}번째 묶음: AI 응답 검증 실패 ({r}) — 원본 유지",
 "ja": "  ブロック {c}: AI応答の検証に失敗（{r}）— 原文維持",
 "zh": "  第 {c} 块：AI 回复未通过校验（{r}）— 保留原文",
 "fr": "  Bloc {c} : réponse IA non valide ({r}) — original conservé",
 "pt": "  Bloco {c}: resposta da IA inválida ({r}) — original mantido",
 "es": "  Bloque {c}: respuesta de IA no válida ({r}) — se mantiene el original"},
"log_rebuild_fix": {
 "en": "  text fixed: '{a}' -> '{b}'",
 "ko": "  텍스트 보정: '{a}' -> '{b}'",
 "ja": "  テキスト補正: '{a}' -> '{b}'",
 "zh": "  文本修正：'{a}' -> '{b}'",
 "fr": "  texte corrigé : '{a}' -> '{b}'",
 "pt": "  texto corrigido: '{a}' -> '{b}'",
 "es": "  texto corregido: '{a}' -> '{b}'"},
"log_rebuild_reject_fix": {
 "en": "  text edit rejected (too far from audio): '{a}' -/-> '{b}'",
 "ko": "  텍스트 보정 거부 (원음과 차이가 큼): '{a}' -/-> '{b}'",
 "ja": "  テキスト補正を却下（音声との差が大きい）: '{a}' -/-> '{b}'",
 "zh": "  拒绝文本修改（与原音差异过大）：'{a}' -/-> '{b}'",
 "fr": "  modification refusée (trop éloignée de l'audio) : '{a}' -/-> '{b}'",
 "pt": "  edição recusada (muito distante do áudio): '{a}' -/-> '{b}'",
 "es": "  edición rechazada (muy lejos del audio): '{a}' -/-> '{b}'"},
"log_rebuild_nowords": {
 "en": "No word timings available — falling back to silence-based split",
 "ko": "단어 타임스탬프가 없어 침묵 기준 분할로 대체합니다",
 "ja": "単語タイムスタンプがないため、無音基準の分割に切り替えます",
 "zh": "没有单词时间戳，改用静音切分",
 "fr": "Pas d'horodatage par mot — découpage aux silences",
 "pt": "Sem marcações por palavra — dividindo pelos silêncios",
 "es": "Sin marcas por palabra — se divide por silencios"},
"log_correct_lines_bad": {
 "en": "Warning: correction returned {n} of {t} lines — missing lines kept as-is",
 "ko": "경고: 교정 응답이 {t}줄 중 {n}줄만 왔습니다 — 나머지는 원본 유지",
 "ja": "警告: 校正応答が {t}行中 {n}行のみ — 残りは原文維持",
 "zh": "警告：校对仅返回 {t} 行中的 {n} 行 — 其余保留原文",
 "fr": "Attention : correction reçue pour {n} lignes sur {t} — le reste est conservé",
 "pt": "Aviso: correção retornou {n} de {t} linhas — o restante foi mantido",
 "es": "Aviso: la corrección devolvió {n} de {t} líneas — el resto se mantiene"},
"log_correct_reject": {
 "en": "  #{i} correction rejected (changed too much): '{a}' -/-> '{b}'",
 "ko": "  #{i} 교정 거부 (변경 폭이 너무 큼): '{a}' -/-> '{b}'",
 "ja": "  #{i} 校正を却下（変更が大きすぎる）: '{a}' -/-> '{b}'",
 "zh": "  #{i} 拒绝校对（改动过大）：'{a}' -/-> '{b}'",
 "fr": "  #{i} correction refusée (trop de changements) : '{a}' -/-> '{b}'",
 "pt": "  #{i} correção recusada (mudou demais): '{a}' -/-> '{b}'",
 "es": "  #{i} corrección rechazada (cambió demasiado): '{a}' -/-> '{b}'"},
"log_correct_done": {"en": "Correction done: {n} lines changed (review above)",
 "ko": "교정 완료: {n}개 줄 수정됨 (위 내용 확인하세요)", "ja": "校正完了: {n}行修正（上記を確認してください）",
 "zh": "校对完成：修改了 {n} 行（请检查上方内容）",
 "fr": "Correction terminée : {n} lignes modifiées (vérifiez ci-dessus)",
 "pt": "Correção concluída: {n} linhas alteradas (confira acima)",
 "es": "Corrección terminada: {n} líneas cambiadas (revisa arriba)"},
"log_tr_call": {"en": "AI translating ({l})...", "ko": "AI 번역 중 ({l})...",
 "ja": "AI翻訳中（{l}）...", "zh": "AI 翻译中（{l}）...",
 "fr": "Traduction IA ({l})...", "pt": "IA traduzindo ({l})...",
 "es": "IA traduciendo ({l})..."},
"log_tr_missing": {"en": "Warning: {n} lines missing from translation — original kept",
 "ko": "경고: {n}개 줄이 번역 결과에 없어 원문 유지됨", "ja": "警告: {n}行が翻訳結果になく原文を維持",
 "zh": "警告：{n} 行未包含在翻译结果中 — 保留原文",
 "fr": "Attention : {n} lignes absentes de la traduction — original conservé",
 "pt": "Aviso: {n} linhas ausentes na tradução — original mantido",
 "es": "Aviso: {n} líneas ausentes en la traducción — se mantiene el original"},
"log_tr_done": {"en": "Translation done: {n} lines", "ko": "번역 완료: {n}개 줄",
 "ja": "翻訳完了: {n}行", "zh": "翻译完成：{n} 行", "fr": "Traduction terminée : {n} lignes",
 "pt": "Tradução concluída: {n} linhas", "es": "Traducción terminada: {n} líneas"},
"inst_title": {"en": "Installing", "ko": "설치 중", "ja": "インストール中", "zh": "安装中",
 "fr": "Installation", "pt": "Instalando", "es": "Instalando"},
"inst_msg": {
 "en": "Installing the required engine (faster-whisper)...\nPlease wait a moment.",
 "ko": "필요한 엔진(faster-whisper)을 설치하는 중입니다...\n잠시만 기다려 주세요.",
 "ja": "必要なエンジン（faster-whisper）をインストール中...\nしばらくお待ちください。",
 "zh": "正在安装所需引擎（faster-whisper）...\n请稍候。",
 "fr": "Installation du moteur requis (faster-whisper)...\nVeuillez patienter.",
 "pt": "Instalando o mecanismo necessário (faster-whisper)...\nAguarde um momento.",
 "es": "Instalando el motor necesario (faster-whisper)...\nEspera un momento."},
"inst_done_t": {"en": "Installed", "ko": "설치 완료", "ja": "インストール完了", "zh": "安装完成",
 "fr": "Installé", "pt": "Instalado", "es": "Instalado"},
"inst_done_b": {
 "en": "Engine installed.\nPlease close and restart the program once.",
 "ko": "엔진 설치가 끝났습니다.\n프로그램을 한 번 닫았다가 다시 실행해 주세요.",
 "ja": "エンジンのインストールが完了しました。\n一度閉じて再起動してください。",
 "zh": "引擎安装完成。\n请关闭程序后重新启动一次。",
 "fr": "Moteur installé.\nFermez puis relancez le programme.",
 "pt": "Mecanismo instalado.\nFeche e reabra o programa uma vez.",
 "es": "Motor instalado.\nCierra y vuelve a abrir el programa."},
"inst_fail_t": {"en": "Engine install failed", "ko": "엔진 설치 실패", "ja": "エンジンのインストール失敗",
 "zh": "引擎安装失败", "fr": "Échec d'installation du moteur", "pt": "Falha ao instalar o mecanismo",
 "es": "Fallo al instalar el motor"},
"inst_fail_b": {
 "en": "Automatic install of faster-whisper failed.\n\nInstall it manually in PowerShell:\n\n      python -m pip install faster-whisper\n\n(Error: {e})",
 "ko": "필요한 엔진(faster-whisper) 자동 설치에 실패했습니다.\n\nPowerShell에서 직접 설치하세요:\n\n      python -m pip install faster-whisper\n\n(오류: {e})",
 "ja": "faster-whisperの自動インストールに失敗しました。\n\nPowerShellで手動インストールしてください:\n\n      python -m pip install faster-whisper\n\n（エラー: {e}）",
 "zh": "faster-whisper 自动安装失败。\n\n请在 PowerShell 中手动安装：\n\n      python -m pip install faster-whisper\n\n（错误：{e}）",
 "fr": "L'installation automatique de faster-whisper a échoué.\n\nInstallez-le manuellement dans PowerShell :\n\n      python -m pip install faster-whisper\n\n(Erreur : {e})",
 "pt": "A instalação automática do faster-whisper falhou.\n\nInstale manualmente no PowerShell:\n\n      python -m pip install faster-whisper\n\n(Erro: {e})",
 "es": "La instalación automática de faster-whisper falló.\n\nInstálalo manualmente en PowerShell:\n\n      python -m pip install faster-whisper\n\n(Error: {e})"},
})
I18N.update({
"claude_off_row": {
 "en": "AI OFF — transcription only. Turn on to show engine · key · output language settings.",
 "ko": "AI 끔 — 받아쓰기만 저장. 켜면 엔진·키·출력 언어 설정이 나타납니다.",
 "ja": "AIオフ — 書き起こしのみ保存。オンにするとエンジン・キー・出力言語の設定が表示されます。",
 "zh": "AI 已关闭 — 仅保存转写。打开后会显示引擎·密钥·输出语言设置。",
 "fr": "IA désactivée — transcription seule. Activez pour afficher moteur · clé · langues de sortie.",
 "pt": "IA desligada — só transcrição. Ligue para mostrar motor · chave · idiomas de saída.",
 "es": "IA desactivada — solo transcripción. Actívala para mostrar motor · clave · idiomas de salida."},
"hq_api_t": {
 "en": "AI API keys — what & how to get one", "ko": "AI API 키란? (발급 방법)",
 "ja": "AI APIキーとは（取得方法）", "zh": "AI API 密钥说明（如何获取）",
 "fr": "Clés API IA — quoi et comment", "pt": "Chaves de API de IA — o quê e como obter",
 "es": "Claves API de IA — qué son y cómo obtenerlas"},
"hq_api_b": {
 "en": ("WHAT IT DOES\nWhisper transcribes the audio. With an AI engine set up, the AI then:\n"
        "  • fixes obvious transcription errors and mis-heard names\n"
        "  • splits run-on subtitles into natural sentences\n"
        "  • translates into every other checked language\nWithout it you still get plain transcription (SRT).\n\n"
        "ENGINES\n"
        "• Claude (PAID — best quality):\n"
        "   1. Sign up at console.anthropic.com and add billing\n"
        "   2. 'API Keys' -> 'Create Key' -> paste it here. ~25 min episode = a few cents.\n"
        "• Gemini (FREE key):\n"
        "   1. Open aistudio.google.com/apikey (button below) and sign in with Google\n"
        "   2. 'Create API key' -> paste it here. No credit card.\n"
        "   Free tier has per-minute limits — the app waits and retries automatically.\n"
        "• Local AI (FREE — runs on YOUR computer, no key, offline):\n"
        "   Select it and click Install — sets up Ollama + a ~7.6 GB model.\n"
        "   NVIDIA GPU with 10 GB VRAM recommended. Change the model in Settings.\n\n"
        "Each engine remembers its own key.\n\n"
        "PRIVACY\nKeys are stored only in config.json on this PC. With Local AI, nothing leaves\n"
        "your computer at all."),
 "ko": ("무엇을 하나요?\nWhisper가 받아쓰기를 하고, AI 엔진을 설정하면 AI가 추가로:\n"
        "  • 명백한 받아쓰기 오류와 잘못 들린 이름 교정\n"
        "  • 뭉친 자막을 자연스러운 문장으로 분할\n"
        "  • 체크한 다른 언어로 번역\n설정 안 해도 받아쓰기 자막(SRT)은 만들어집니다.\n\n"
        "엔진 종류\n"
        "• Claude (유료 — 품질 최고):\n"
        "   1. console.anthropic.com 가입 + 결제 등록\n"
        "   2. 'API Keys' -> 'Create Key' -> 여기에 붙여넣기. 25분 에피소드 1편 = 수십 원 수준.\n"
        "• Gemini (무료 키):\n"
        "   1. aistudio.google.com/apikey 열고(아래 버튼) Google 계정으로 로그인\n"
        "   2. 'Create API key' -> 여기에 붙여넣기. 카드 등록 불필요.\n"
        "   무료 티어는 분당 요청 제한이 있어요 — 걸리면 알아서 기다렸다 재시도합니다.\n"
        "• 로컬 AI (무료 — 내 컴퓨터에서 직접 실행, 키 없음, 오프라인):\n"
        "   엔진에서 선택하고 설치 버튼만 누르면 Ollama + 모델(~7.6GB)이 설치됩니다.\n"
        "   NVIDIA GPU VRAM 10GB 이상 권장. 모델 변경은 설정 메뉴에서.\n\n"
        "엔진마다 키를 따로 기억합니다.\n\n"
        "개인정보\n키는 이 PC의 config.json에만 저장됩니다. 로컬 AI를 쓰면 자막 텍스트가\n"
        "컴퓨터 밖으로 아예 나가지 않습니다."),
 "ja": ("何をする？\nWhisperが書き起こし、AIエンジンを設定すると、AIがさらに:\n"
        "  • 明らかな誤認識や聞き間違えた名前を修正\n  • 長すぎる字幕を自然な文に分割\n"
        "  • チェックした他の言語へ翻訳\n未設定でも書き起こし字幕（SRT）は作成されます。\n\n"
        "エンジン\n"
        "• Claude（有料 — 品質最高）: console.anthropic.com で登録+支払い設定 ->\n"
        "   'API Keys' -> 'Create Key' -> ここに貼り付け。\n"
        "• Gemini（無料キー）: aistudio.google.com/apikey（下のボタン）-> Googleでログイン ->\n"
        "   'Create API key' -> 貼り付け。カード不要。無料枠は毎分制限あり（自動再試行）。\n"
        "• ローカルAI（無料 — 自分のPCで実行、キー不要、オフライン）:\n"
        "   選択してインストールを押すだけ。Ollama + モデル（約7.6GB）を設置。\n"
        "   NVIDIA GPU VRAM 10GB以上推奨。モデル変更は設定メニュー。\n\n"
        "エンジンごとにキーを記憶します。\n\n"
        "プライバシー\nキーはこのPCのconfig.jsonにのみ保存。ローカルAIなら字幕テキストは\n一切外部に送信されません。"),
 "zh": ("它做什么？\nWhisper 负责转写。设置好 AI 引擎后，AI 还会：\n"
        "  • 修正明显的转写错误和听错的名字\n  • 把过长字幕分成自然句子\n  • 翻译成勾选的其他语言\n"
        "不设置也能生成转写字幕（SRT）。\n\n"
        "引擎\n"
        "• Claude（付费 — 质量最佳）：console.anthropic.com 注册并绑定付款 ->\n"
        "   'API Keys' -> 'Create Key' -> 粘贴到这里。\n"
        "• Gemini（免费密钥）：aistudio.google.com/apikey（下方按钮）-> Google 登录 ->\n"
        "   'Create API key' -> 粘贴。无需信用卡。免费额度有每分钟限制（自动重试）。\n"
        "• 本地 AI（免费 — 在你电脑上运行，无密钥，离线）：\n"
        "   选择后点安装即可 — 自动安装 Ollama + 模型（约 7.6GB）。\n"
        "   建议 NVIDIA GPU 显存 10GB 以上。可在设置中更换模型。\n\n"
        "每个引擎的密钥分别保存。\n\n"
        "隐私\n密钥仅保存在本机 config.json。使用本地 AI 时，字幕文本完全不会离开你的电脑。"),
 "fr": ("À QUOI ÇA SERT\nWhisper transcrit l'audio. Avec un moteur IA configuré, l'IA :\n"
        "  • corrige les erreurs évidentes et les noms mal entendus\n  • découpe les sous-titres trop longs\n"
        "  • traduit vers les autres langues cochées\nSans cela, vous obtenez quand même la transcription (SRT).\n\n"
        "MOTEURS\n"
        "• Claude (PAYANT — meilleure qualité) : console.anthropic.com + facturation ->\n"
        "   'API Keys' -> 'Create Key' -> collez-la ici.\n"
        "• Gemini (clé GRATUITE) : aistudio.google.com/apikey (bouton) -> connexion Google ->\n"
        "   'Create API key' -> collez. Sans carte. Limites par minute (réessai auto).\n"
        "• IA locale (GRATUITE — tourne sur VOTRE PC, sans clé, hors ligne) :\n"
        "   Sélectionnez-la et cliquez Installer — Ollama + modèle (~9 Go).\n"
        "   GPU NVIDIA 10 Go VRAM recommandé. Modèle modifiable dans Paramètres.\n\n"
        "Chaque moteur mémorise sa propre clé.\n\n"
        "CONFIDENTIALITÉ\nLes clés restent dans config.json. Avec l'IA locale, rien ne quitte votre PC."),
 "pt": ("O QUE FAZ\nO Whisper transcreve o áudio. Com um motor de IA configurado, a IA também:\n"
        "  • corrige erros óbvios e nomes mal ouvidos\n  • divide legendas longas em frases naturais\n"
        "  • traduz para os outros idiomas marcados\nSem isso, você ainda recebe a transcrição (SRT).\n\n"
        "MOTORES\n"
        "• Claude (PAGO — melhor qualidade): console.anthropic.com + cobrança ->\n"
        "   'API Keys' -> 'Create Key' -> cole aqui.\n"
        "• Gemini (chave GRÁTIS): aistudio.google.com/apikey (botão) -> login Google ->\n"
        "   'Create API key' -> cole. Sem cartão. Limites por minuto (repete sozinho).\n"
        "• IA local (GRÁTIS — roda no SEU PC, sem chave, offline):\n"
        "   Selecione e clique Instalar — Ollama + modelo (~7.6GB).\n"
        "   GPU NVIDIA com 10 GB VRAM recomendada. Troque o modelo em Configurações.\n\n"
        "Cada motor guarda sua própria chave.\n\n"
        "PRIVACIDADE\nAs chaves ficam só no config.json. Com a IA local, nada sai do seu PC."),
 "es": ("QUÉ HACE\nWhisper transcribe el audio. Con un motor de IA configurado, la IA además:\n"
        "  • corrige errores evidentes y nombres mal oídos\n  • divide subtítulos largos en frases naturales\n"
        "  • traduce a los demás idiomas marcados\nSin ello, igualmente obtienes la transcripción (SRT).\n\n"
        "MOTORES\n"
        "• Claude (DE PAGO — mejor calidad): console.anthropic.com + facturación ->\n"
        "   'API Keys' -> 'Create Key' -> pégala aquí.\n"
        "• Gemini (clave GRATIS): aistudio.google.com/apikey (botón) -> inicia sesión con Google ->\n"
        "   'Create API key' -> pégala. Sin tarjeta. Límites por minuto (reintenta solo).\n"
        "• IA local (GRATIS — corre en TU PC, sin clave, sin conexión):\n"
        "   Selecciónala y pulsa Instalar — Ollama + modelo (~7.6GB).\n"
        "   GPU NVIDIA con 10 GB de VRAM recomendada. Cambia el modelo en Configuración.\n\n"
        "Cada motor recuerda su propia clave.\n\n"
        "PRIVACIDAD\nLas claves se quedan en config.json. Con la IA local, nada sale de tu PC."),},
"hq_open_console": {"en": "Open console.anthropic.com", "ko": "console.anthropic.com 열기",
 "ja": "console.anthropic.com を開く", "zh": "打开 console.anthropic.com",
 "fr": "Ouvrir console.anthropic.com", "pt": "Abrir console.anthropic.com",
 "es": "Abrir console.anthropic.com"},
"hq_names_t": {"en": "Character names", "ko": "캐릭터 이름", "ja": "キャラクター名", "zh": "角色名称",
 "fr": "Noms des personnages", "pt": "Nomes dos personagens", "es": "Nombres de personajes"},
"hq_names_b": {
 "en": ("Speech-to-text often mis-hears character names as similar-sounding words.\n"
        "List the correct names here (comma-separated) and the AI will fix only clear mistakes,\n"
        "keep the exact spelling you wrote, and never translate the names.\n\nExample: Titi, Sunny"),
 "ko": ("음성 인식은 캐릭터 이름을 비슷한 발음의 단어로 잘못 적는 경우가 많습니다.\n"
        "정확한 이름을 쉼표로 구분해 적어두면, AI가 명백히 잘못 들린 경우만 바로잡고\n"
        "적어준 표기 그대로 유지하며, 번역할 때도 이름은 번역하지 않습니다.\n\n예: Titi, Sunny"),
 "ja": ("音声認識はキャラクター名を似た発音の単語に間違えがちです。\n"
        "正しい名前をカンマ区切りで書いておくと、AIは明らかな間違いだけを修正し、\n"
        "書いた通りの表記を維持し、翻訳時も名前は翻訳しません。\n\n例: Titi, Sunny"),
 "zh": ("语音识别常把角色名听成发音相近的词。\n在此用逗号列出正确名字，AI 只会纠正明显听错的情况，\n"
        "保持你写的拼写，翻译时也不会翻译名字。\n\n例：Titi, Sunny"),
 "fr": ("La reconnaissance vocale confond souvent les noms avec des mots similaires.\n"
        "Listez ici les noms corrects (séparés par des virgules) : l'IA ne corrige que les erreurs\n"
        "évidentes, garde votre orthographe exacte et ne traduit jamais les noms.\n\nExemple : Titi, Sunny"),
 "pt": ("O reconhecimento de voz costuma confundir nomes com palavras parecidas.\n"
        "Liste aqui os nomes corretos (separados por vírgula): a IA corrige só erros claros,\n"
        "mantém a grafia exata e nunca traduz os nomes.\n\nExemplo: Titi, Sunny"),
 "es": ("El reconocimiento de voz suele confundir los nombres con palabras parecidas.\n"
        "Escribe aquí los nombres correctos (separados por comas): la IA solo corrige errores claros,\n"
        "mantiene tu ortografía exacta y nunca traduce los nombres.\n\nEjemplo: Titi, Sunny")},
"hq_src_t": {"en": "Audio language", "ko": "음성 언어", "ja": "音声言語", "zh": "音频语言",
 "fr": "Langue audio", "pt": "Idioma do áudio", "es": "Idioma del audio"},
"hq_src_b": {
 "en": ("Choose the language actually spoken in the file — transcription quality depends on it.\n"
        "The chosen language becomes the 'base' subtitle: saved without a filename suffix\n"
        "(so video players auto-detect it), and used as the source for all translations.\n\n"
        "'Auto detect' lets Whisper guess the language (result shown in the log)."),
 "ko": ("파일에서 실제로 말하는 언어를 고르세요 — 받아쓰기 품질이 여기에 달려 있습니다.\n"
        "선택한 언어가 '기준' 자막이 됩니다: 파일명 접미사 없이 저장되어 플레이어가\n"
        "자동 인식하고, 모든 번역의 원본이 됩니다.\n\n"
        "'자동 감지'를 고르면 whisper가 언어를 판별합니다 (결과는 로그에 표시)."),
 "ja": ("ファイルで実際に話されている言語を選んでください — 認識品質を左右します。\n"
        "選んだ言語が「基準」字幕になります: 接尾辞なしで保存されプレイヤーが自動認識し、\n"
        "すべての翻訳の元になります。\n\n「自動検出」ではWhisperが言語を判別します（ログに表示）。"),
 "zh": ("请选择文件中实际所讲的语言 — 它决定转写质量。\n所选语言将成为“基准”字幕：保存时不带文件名后缀\n"
        "（播放器可自动识别），并作为所有翻译的源文本。\n\n选“自动检测”则由 Whisper 判断语言（结果见日志）。"),
 "fr": ("Choisissez la langue réellement parlée dans le fichier — la qualité en dépend.\n"
        "Cette langue devient le sous-titre « de base » : enregistré sans suffixe (détection\n"
        "automatique par les lecteurs) et source de toutes les traductions.\n\n"
        "« Détection auto » : Whisper devine la langue (voir le journal)."),
 "pt": ("Escolha o idioma realmente falado no arquivo — a qualidade depende disso.\n"
        "Esse idioma vira a legenda 'base': salva sem sufixo no nome (os players detectam\n"
        "automaticamente) e é a fonte de todas as traduções.\n\n"
        "'Detecção automática': o Whisper adivinha o idioma (veja o log)."),
 "es": ("Elige el idioma que realmente se habla en el archivo — de ello depende la calidad.\n"
        "Ese idioma será el subtítulo 'base': se guarda sin sufijo (los reproductores lo\n"
        "detectan solos) y es la fuente de todas las traducciones.\n\n"
        "'Detección automática': Whisper adivina el idioma (ver registro).")},
"hq_out_t": {"en": "Output languages", "ko": "출력 언어", "ja": "出力言語", "zh": "输出语言",
 "fr": "Langues de sortie", "pt": "Idiomas de saída", "es": "Idiomas de salida"},
"hq_out_b": {
 "en": ("Every checked language is saved as a .srt file.\n\n"
        "\u2022 Base (audio) language: same filename as the video -> players load it automatically\n"
        "\u2022 Translations: filename gets a language suffix like _ko, _es, _ja\n"
        "\u2022 Translations need a AI API key and always translate from the corrected base subtitle"),
 "ko": ("\uccb4\ud06c\ud55c \uc5b8\uc5b4\ub294 \uac01각 .srt \ud30c\uc77c\ub85c \uc800\uc7a5\ub429\ub2c8\ub2e4.\n\n"
        "\u2022 \uae30\uc900(\uc74c\uc131) \uc5b8\uc5b4: \uc601\uc0c1\uacfc \uac19\uc740 \ud30c\uc77c\uba85 -> \ud50c\ub808\uc774\uc5b4\uac00 \uc790\ub3d9\uc73c\ub85c \ubd88\ub7ec\uc634\n"
        "\u2022 \ubc88\uc5ed: \ud30c\uc77c\uba85 \ub4a4\uc5d0 _ko, _es, _ja \uac19\uc740 \uc5b8\uc5b4 \uc811\ubbf8\uc0ac\n"
        "\u2022 \ubc88\uc5ed\uc5d0\ub294 AI API \ud0a4\uac00 \ud544\uc694\ud558\uace0, \ud56d\uc0c1 \uad50\uc815\ub41c \uae30\uc900 \uc790\ub9c9\uc744 \uc6d0\ubcf8\uc73c\ub85c \ubc88\uc5ed\ud569\ub2c8\ub2e4"),
 "ja": ("\u30c1\u30a7\u30c3\u30af\u3057\u305f\u8a00\u8a9e\u306f\u305d\u308c\u305e\u308c .srt \u3067\u4fdd\u5b58\u3055\u308c\u307e\u3059\u3002\n\n"
        "\u2022 \u57fa\u6e96\uff08\u97f3\u58f0\uff09\u8a00\u8a9e: \u52d5\u753b\u3068\u540c\u540d -> \u30d7\u30ec\u30a4\u30e4\u30fc\u304c\u81ea\u52d5\u3067\u8aad\u307f\u8fbc\u307f\n"
        "\u2022 \u7ffb\u8a33: \u30d5\u30a1\u30a4\u30eb\u540d\u306b _ko, _es, _ja \u306e\u3088\u3046\u306a\u63a5\u5c3e\u8f9e\n"
        "\u2022 \u7ffb\u8a33\u306b\u306fAI API\u30ad\u30fc\u304c\u5fc5\u8981\u3067\u3059"),
 "zh": ("\u52fe\u9009\u7684\u8bed\u8a00\u5747\u4fdd\u5b58\u4e3a .srt \u6587\u4ef6\u3002\n\n"
        "\u2022 \u57fa\u51c6\uff08\u97f3\u9891\uff09\u8bed\u8a00\uff1a\u4e0e\u89c6\u9891\u540c\u540d -> \u64ad\u653e\u5668\u81ea\u52a8\u52a0\u8f7d\n"
        "\u2022 \u7ffb\u8bd1\uff1a\u6587\u4ef6\u540d\u5e26 _ko\u3001_es\u3001_ja \u7b49\u540e\u7f00\n"
        "\u2022 \u7ffb\u8bd1\u9700\u8981 AI API \u5bc6\u94a5"),
 "fr": ("Chaque langue coch\u00e9e est enregistr\u00e9e dans un fichier .srt.\n\n"
        "\u2022 Langue de base : m\u00eame nom que la vid\u00e9o -> charg\u00e9e automatiquement\n"
        "\u2022 Traductions : suffixe de langue (_ko, _es, _ja)\n"
        "\u2022 Les traductions n\u00e9cessitent une cl\u00e9 API AI"),
 "pt": ("Cada idioma marcado \u00e9 salvo em um arquivo .srt.\n\n"
        "\u2022 Idioma base: mesmo nome do v\u00eddeo -> carregado automaticamente\n"
        "\u2022 Tradu\u00e7\u00f5es: sufixo de idioma (_ko, _es, _ja)\n"
        "\u2022 Tradu\u00e7\u00f5es exigem chave de API AI"),
 "es": ("Cada idioma marcado se guarda en un archivo .srt.\n\n"
        "\u2022 Idioma base: mismo nombre que el v\u00eddeo -> se carga autom\u00e1ticamente\n"
        "\u2022 Traducciones: sufijo de idioma (_ko, _es, _ja)\n"
        "\u2022 Las traducciones requieren una clave de API AI")},
"qs_b": {
 "en": ("HOW TO USE (3 steps)\n\n"
        "  1. Select video/audio files ('Browse...' — multiple files OK)\n"
        "  2. Pick the audio language, then check the subtitle languages you want\n"
        "  3. Press 'Create subtitles'\n\n"
        "Subtitle files are saved next to each video with matching names,\n"
        "so most players load them automatically.\n\n"
        "OPTIONAL — AI\n"
        "Enter a AI API key to enable automatic correction, sentence splitting and\n"
        "translation. Press the ? button next to the key box for details.\n\n"
        "FIRST RUN\n"
        "The Whisper model (~3 GB) is downloaded once on first use. With an NVIDIA GPU\n"
        "transcription is many times faster; otherwise the CPU is used automatically."),
 "ko": ("사용 방법 (3단계)\n\n"
        "  1. 영상/음성 파일 선택 ('찾아보기...' — 여러 개 가능)\n"
        "  2. 음성 언어를 고르고, 원하는 출력 자막 언어를 체크\n"
        "  3. '자막 만들기' 누르기\n\n"
        "자막 파일은 영상과 같은 폴더에 같은 이름으로 저장되어\n"
        "대부분의 플레이어가 자동으로 불러옵니다.\n\n"
        "선택 사항 — AI\n"
        "AI API 키를 입력하면 자동 교정·문장 분할·번역이 켜집니다.\n"
        "자세한 내용은 키 입력칸 옆 ? 버튼을 누르세요.\n\n"
        "첫 실행\n"
        "첫 사용 시 Whisper 모델(~3GB)을 한 번 내려받습니다. NVIDIA GPU가 있으면\n"
        "훨씬 빠르고, 없으면 자동으로 CPU를 사용합니다."),
 "ja": ("使い方（3ステップ）\n\n  1. 動画/音声ファイルを選択（「参照...」— 複数可）\n"
        "  2. 音声言語を選び、欲しい字幕言語をチェック\n  3. 「字幕を作成」を押す\n\n"
        "字幕ファイルは動画と同じフォルダに同名で保存され、\n多くのプレイヤーが自動で読み込みます。\n\n"
        "オプション — AI\nAPIキーを入力すると自動校正・文分割・翻訳が有効になります。\n詳細はキー入力欄横の?ボタンで。\n\n"
        "初回実行\n初回はWhisperモデル（約3GB）をダウンロードします。NVIDIA GPUがあれば\n高速、なければ自動的にCPUを使用します。"),
 "zh": ("使用方法（3 步）\n\n  1. 选择视频/音频文件（“浏览...”— 可多选）\n"
        "  2. 选择音频语言，勾选想要的字幕语言\n  3. 点击“生成字幕”\n\n"
        "字幕文件会以相同文件名保存在视频旁边，\n大多数播放器会自动加载。\n\n"
        "可选 — AI\n填入 AI API 密钥即可启用自动校对、分句和翻译。\n详情请点密钥框旁的 ? 按钮。\n\n"
        "首次运行\n首次使用会下载 Whisper 模型（约 3GB）。有 NVIDIA GPU 会快很多，\n没有则自动使用 CPU。"),
 "fr": ("UTILISATION (3 étapes)\n\n  1. Sélectionnez les fichiers (« Parcourir... » — plusieurs possibles)\n"
        "  2. Choisissez la langue audio puis cochez les langues de sous-titres voulues\n"
        "  3. Cliquez sur « Créer les sous-titres »\n\n"
        "Les fichiers de sous-titres sont enregistrés à côté de chaque vidéo avec le même nom :\nla plupart des lecteurs les chargent automatiquement.\n\n"
        "OPTIONNEL — AI\nSaisissez une clé API AI pour activer correction, découpage et traduction.\nDétails via le bouton ? à côté du champ.\n\n"
        "PREMIER LANCEMENT\nLe modèle Whisper (~3 Go) est téléchargé une fois. Avec un GPU NVIDIA c'est\nbien plus rapide ; sinon le CPU est utilisé automatiquement."),
 "pt": ("COMO USAR (3 passos)\n\n  1. Selecione os arquivos ('Procurar...' — vários permitidos)\n"
        "  2. Escolha o idioma do áudio e marque os idiomas de legenda desejados\n  3. Clique em 'Criar legendas'\n\n"
        "As legendas são salvas ao lado de cada vídeo com o mesmo nome:\na maioria dos players carrega automaticamente.\n\n"
        "OPCIONAL — AI\nDigite uma chave de API AI para ativar correção, divisão e tradução.\nDetalhes no botão ? ao lado do campo.\n\n"
        "PRIMEIRA EXECUÇÃO\nO modelo Whisper (~3 GB) é baixado uma vez. Com GPU NVIDIA é muito mais\nrápido; sem ela, o CPU é usado automaticamente."),
 "es": ("CÓMO USAR (3 pasos)\n\n  1. Selecciona los archivos ('Examinar...' — varios permitidos)\n"
        "  2. Elige el idioma del audio y marca los idiomas de subtítulos deseados\n  3. Pulsa 'Crear subtítulos'\n\n"
        "Los subtítulos .srt se guardan junto a cada vídeo con el mismo nombre:\nla mayoría de reproductores los cargan solos.\n\n"
        "OPCIONAL — AI\nIntroduce una clave API de AI para activar corrección, división y traducción.\nDetalles en el botón ? junto al campo.\n\n"
        "PRIMERA EJECUCIÓN\nEl modelo Whisper (~3 GB) se descarga una vez. Con GPU NVIDIA es mucho más\nrápido; si no, se usa la CPU automáticamente.")},
"tr_b": {
 "en": ("SUBTITLE CAME OUT EMPTY / 'no speech recognized'\n"
        "The file may be corrupted or truncated (e.g. a single 1GB piece of a split DVD VOB).\n"
        "Join split pieces into one file first, or re-rip the source, then try again.\n\n"
        "GPU NOT USED ('falling back to CPU')\n"
        "An NVIDIA GPU with CUDA is required. Install: pip install nvidia-cublas-cu12 nvidia-cudnn-cu12\n"
        "It still works on CPU — just slower.\n\n"
        "MODEL DOWNLOAD IS SLOW\nOnly the first run downloads ~3 GB. Later runs start immediately.\n\n"
                "CORRECTION/TRANSLATION SKIPPED\nA AI API key is required — see the ? next to the key box."),
 "ko": ("자막이 비어 나옴 / '음성을 인식하지 못했습니다'\n"
        "파일이 손상됐거나 잘린 파일일 수 있습니다 (예: DVD VOB가 1GB 단위로 쪼개진 조각).\n"
        "쪼개진 조각을 하나로 합치거나 원본을 다시 추출한 뒤 시도하세요.\n\n"
        "GPU가 안 잡힘 ('CPU로 전환')\n"
        "CUDA 지원 NVIDIA GPU가 필요합니다. 설치: pip install nvidia-cublas-cu12 nvidia-cudnn-cu12\n"
        "CPU로도 동작합니다 — 속도만 느려집니다.\n\n"
        "모델 다운로드가 느림\n첫 실행만 ~3GB를 받습니다. 이후에는 바로 시작합니다.\n\n"
        "교정/번역이 건너뛰어짐\nAI API 키가 필요합니다 — 키 입력칸 옆 ?를 참고하세요."),
 "ja": ("字幕が空になる / 「音声を認識できませんでした」\n"
        "ファイルが破損しているか途中で切れている可能性があります（例: 1GB単位に分割されたDVD VOB）。\n分割ファイルを結合するか、ソースを再抽出してから再試行してください。\n\n"
        "GPUが使われない（「CPUに切替」）\nCUDA対応NVIDIA GPUが必要です。pip install nvidia-cublas-cu12 nvidia-cudnn-cu12\nCPUでも動作します（遅くなるだけ）。\n\n"
        "モデルのダウンロードが遅い\n初回のみ約3GBをダウンロードします。\n\n"
        "校正/翻訳がスキップされる\nAI APIキーが必要です — キー欄横の?を参照。"),
 "zh": ("字幕是空的 /「未能识别到语音」\n文件可能损坏或被截断（例如按 1GB 切分的 DVD VOB 片段）。\n请先把分段文件合并成一个，或重新提取源文件后再试。\n\n"
        "没有使用 GPU（「改用 CPU」）\n需要支持 CUDA 的 NVIDIA GPU。安装：pip install nvidia-cublas-cu12 nvidia-cudnn-cu12\n用 CPU 也能运行，只是更慢。\n\n"
        "模型下载慢\n只有首次运行下载约 3GB。\n\n"
        "校对/翻译被跳过\n需要 AI API 密钥 — 见密钥框旁的 ?。"),
 "fr": ("SOUS-TITRE VIDE / « aucune parole reconnue »\nLe fichier est peut-être corrompu ou tronqué (ex. morceau de VOB DVD découpé en 1 Go).\nFusionnez d'abord les morceaux ou ré-extrayez la source.\n\n"
        "GPU NON UTILISÉ (« bascule sur CPU »)\nUn GPU NVIDIA avec CUDA est requis. pip install nvidia-cublas-cu12 nvidia-cudnn-cu12\nÇa fonctionne aussi sur CPU, juste plus lentement.\n\n"
        "TÉLÉCHARGEMENT DU MODÈLE LENT\nSeul le premier lancement télécharge ~3 Go.\n\n"
        "CORRECTION/TRADUCTION IGNORÉES\nUne clé API AI est requise — voir le ? à côté du champ."),
 "pt": ("LEGENDA SAIU VAZIA / 'nenhuma fala reconhecida'\nO arquivo pode estar corrompido ou truncado (ex.: pedaço de VOB de DVD dividido em 1GB).\nJunte os pedaços em um arquivo ou extraia a fonte de novo.\n\n"
        "GPU NÃO USADA ('usando CPU')\nÉ preciso GPU NVIDIA com CUDA. pip install nvidia-cublas-cu12 nvidia-cudnn-cu12\nFunciona na CPU também, só mais devagar.\n\n"
        "DOWNLOAD DO MODELO LENTO\nSó a primeira execução baixa ~3 GB.\n\n"
        "CORREÇÃO/TRADUÇÃO PULADAS\nÉ necessária uma chave de API AI — veja o ? ao lado do campo."),
 "es": ("SUBTÍTULO VACÍO / 'no se reconoció voz'\nEl archivo puede estar dañado o truncado (p. ej., trozo de VOB de DVD partido en 1GB).\nUne primero los trozos en un archivo o vuelve a extraer la fuente.\n\n"
        "GPU NO USADA ('usando CPU')\nSe requiere GPU NVIDIA con CUDA. pip install nvidia-cublas-cu12 nvidia-cudnn-cu12\nTambién funciona con CPU, solo más lento.\n\n"
        "DESCARGA DEL MODELO LENTA\nSolo la primera ejecución descarga ~3 GB.\n\n"
        "CORRECCIÓN/TRADUCCIÓN OMITIDAS\nSe requiere una clave API de AI — mira el ? junto al campo.")},
"ab_b": {
 "en": "{app} {v}\n{full}\n\n{c}\n\nWhisper ({m}) transcription with word-level timing\nAI correction · sentence split · translation\nOutputs SRT for every selected language",
 "ko": "{app} {v}\n{full}\n\n{c}\n\nWhisper({m}) 받아쓰기 + 단어 실측 타이밍\nAI 교정 · 문장 분할 · 번역\n선택한 모든 언어를 SRT로 출력",
 "ja": "{app} {v}\n{full}\n\n{c}\n\nWhisper（{m}）書き起こし + 単語タイミング\nAI 校正・文分割・翻訳\n選択した全言語をSRTで出力",
 "zh": "{app} {v}\n{full}\n\n{c}\n\nWhisper（{m}）转写 + 单词级时间轴\nAI 校对 · 分句 · 翻译\n所有勾选语言均输出 SRT",
 "fr": "{app} {v}\n{full}\n\n{c}\n\nTranscription Whisper ({m}) avec timing par mot\nCorrection · découpage · traduction AI\nSortie SRT pour chaque langue choisie",
 "pt": "{app} {v}\n{full}\n\n{c}\n\nTranscrição Whisper ({m}) com timing por palavra\nCorreção · divisão · tradução AI\nSaída SRT para cada idioma escolhido",
 "es": "{app} {v}\n{full}\n\n{c}\n\nTranscripción Whisper ({m}) con timing por palabra\nCorrección · división · traducción AI\nSalida SRT para cada idioma elegido"},
"log_donate_line": {
 "en": "\u2615 If this saved you time, you can support the developer: {u}",
 "ko": "\u2615 도움이 됐다면 개발자를 응원해 주세요: {u}",
 "ja": "\u2615 役に立ったら開発者を応援してください: {u}",
 "zh": "\u2615 如果对你有帮助，欢迎支持开发者：{u}",
 "fr": "\u2615 Si cela vous a aidé, soutenez le développeur : {u}",
 "pt": "\u2615 Se isto ajudou, apoie o desenvolvedor: {u}",
 "es": "\u2615 Si esto te ayudó, apoya al desarrollador: {u}"},
"donate_msg": {
 "en": "You've already made {n} subtitles with {app}!\nIf it's been useful, a coffee's worth of support\nwould mean a lot. \u2615",
 "ko": "{app}로 벌써 {n}개의 자막을 만드셨네요!\n도움이 됐다면 커피 한 잔으로\n개발자를 응원해 주세요. \u2615",
 "ja": "{app}でもう{n}個の字幕を作りました！\n役に立ったなら、コーヒー1杯分の\n応援をいただけると嬉しいです。\u2615",
 "zh": "你已经用 {app} 制作了 {n} 个字幕！\n如果觉得好用，欢迎请开发者\n喝杯咖啡以示支持。\u2615",
 "fr": "Vous avez déjà créé {n} sous-titres avec {app} !\nSi c'est utile, un café en soutien\nferait très plaisir. \u2615",
 "pt": "Você já fez {n} legendas com o {app}!\nSe está sendo útil, um cafezinho\nde apoio seria muito bem-vindo. \u2615",
 "es": "¡Ya has creado {n} subtítulos con {app}!\nSi te resulta útil, un café de apoyo\nsería muy bienvenido. \u2615"},
"popup_yt": {
 "en": "The developer also makes a kids STEM animation series —\ncome take a look! \U0001F3AC",
 "ko": "개발자가 만드는 어린이 STEM 애니메이션 채널도\n한번 구경해 주세요! \U0001F3AC",
 "ja": "開発者が作る子ども向けSTEMアニメの\nチャンネルもぜひご覧ください！\U0001F3AC",
 "zh": "开发者还制作儿童 STEM 动画系列 —\n欢迎来看看！\U0001F3AC",
 "fr": "Le développeur crée aussi une série d'animation STEM\npour enfants — venez jeter un œil ! \U0001F3AC",
 "pt": "O desenvolvedor também faz uma série de animação STEM\npara crianças — dê uma olhada! \U0001F3AC",
 "es": "El desarrollador también crea una serie de animación STEM\npara niños — ¡échale un vistazo! \U0001F3AC"},
"btn_yt_go": {
 "en": "▶ Watch {ch} on YouTube", "ko": "▶ YouTube에서 {ch} 보기",
 "ja": "▶ YouTubeで {ch} を見る", "zh": "▶ 在 YouTube 观看 {ch}",
 "fr": "▶ Voir {ch} sur YouTube", "pt": "▶ Ver {ch} no YouTube",
 "es": "▶ Ver {ch} en YouTube"},
"btn_later": {"en": "Later", "ko": "나중에", "ja": "また今度", "zh": "以后再说",
 "fr": "Plus tard", "pt": "Depois", "es": "Más tarde"},
"btn_never": {"en": "Don't show again", "ko": "다시 보지 않기", "ja": "今後表示しない",
 "zh": "不再显示", "fr": "Ne plus afficher", "pt": "Não mostrar de novo", "es": "No mostrar más"},
"btn_issues": {
 "en": "Report bugs · Feedback (GitHub)", "ko": "문의 · 버그 제보 (GitHub)",
 "ja": "お問い合わせ・バグ報告 (GitHub)", "zh": "反馈 · 报告问题 (GitHub)",
 "fr": "Signaler un bug · Avis (GitHub)", "pt": "Relatar bugs · Feedback (GitHub)",
 "es": "Reportar errores · Comentarios (GitHub)"},
"btn_donate": {
 "en": "Support this project (PayPal)", "ko": "개발자 후원하기 (PayPal)",
 "ja": "開発者を支援する (PayPal)", "zh": "支持开发者 (PayPal)",
 "fr": "Soutenir le projet (PayPal)", "pt": "Apoiar o projeto (PayPal)",
 "es": "Apoyar el proyecto (PayPal)"},
})


I18N.update({
"lbl_extra": {
 "en": "Targeted fixes (optional) — tell the AI what to fix, where:",
 "ko": "콕 집어 고치기 (선택) — 어디를 어떻게 고칠지 적으세요:",
 "ja": "狙って直す（任意）— どこを どう直すか書いてください:",
 "zh": "精准修正（可选）— 写下要改哪里、怎么改:",
 "fr": "Corrections ciblées (facultatif) — dites à l'IA quoi corriger, et où :",
 "pt": "Correções pontuais (opcional) — diga à IA o que corrigir e onde:",
 "es": "Correcciones puntuales (opcional) — dile a la IA qué corregir y dónde:"},
"ph_extra": {
 "en": ("Optional. What you type is remembered for next time.\n"
        "e.g. Character names are Sunny and Titi — never write Titi as TT or TD.\n"
        "e.g. Around 12:30 the line \"Look out!\" is missing. Add it.\n"
        "e.g. Translate in a polite tone."),
 "ko": ("선택 사항. 적은 내용은 다음 실행 때도 기억됩니다.\n"
        "예: 등장인물 이름은 Sunny 와 Titi 야. Titi 를 TT 나 TD 로 쓰지 마.\n"
        "예: 12분 30초쯤에 \"조심해!\" 가 빠졌어. 넣어줘.\n"
        "예: 번역은 존댓말로 해줘."),
 "ja": ("任意。入力した内容は次回も記憶されます。\n"
        "例: 登場人物の名前は Sunny と Titi。Titi を TT や TD と書かないで。\n"
        "例: 12分30秒あたりの「危ない!」が抜けている。追加して。\n"
        "例: 翻訳は丁寧語で。"),
 "zh": ("可选。输入的内容下次会被记住。\n"
        "例：角色名字是 Sunny 和 Titi，不要把 Titi 写成 TT 或 TD。\n"
        "例：12分30秒左右漏了一句\"小心!\"，请补上。\n"
        "例：翻译用礼貌语气。"),
 "fr": ("Facultatif. Ce que vous saisissez est mémorisé.\n"
        "ex. Les personnages s'appellent Sunny et Titi — n'écrivez jamais Titi TT ou TD.\n"
        "ex. Vers 12:30 il manque « Attention ! ». Ajoute-la.\n"
        "ex. Traduis sur un ton poli."),
 "pt": ("Opcional. O que você digitar fica salvo para a próxima vez.\n"
        "ex.: Os personagens são Sunny e Titi — nunca escreva Titi como TT ou TD.\n"
        "ex.: Por volta de 12:30 falta a fala \"Cuidado!\". Acrescente.\n"
        "ex.: Traduza em tom educado."),
 "es": ("Opcional. Lo que escribas se recuerda la próxima vez.\n"
        "ej.: Los personajes son Sunny y Titi — nunca escribas Titi como TT o TD.\n"
        "ej.: Sobre las 12:30 falta la línea \"¡Cuidado!\". Añádela.\n"
        "ej.: Traduce en tono cortés."),},
"hint_extra": {
 "en": "Fix a name, add a line the recogniser missed, move a line in time — the AI changes only what you point at",
 "ko": "이름 바로잡기 · 못 들은 대사 넣기 · 자막 시각 옮기기 — 짚어준 곳만 고칩니다",
 "ja": "名前の修正 · 聞き逃した台詞の追加 · 字幕の時刻移動 — 指定した箇所だけ直します",
 "zh": "更正名字 · 补上漏听的台词 · 移动字幕时间 — 只改你指出的地方",
 "fr": "Corriger un nom, ajouter une réplique manquée, décaler une ligne — l'IA ne touche qu'à ce que vous désignez",
 "pt": "Corrigir um nome, acrescentar uma fala perdida, mover uma linha no tempo — a IA muda só o que você apontar",
 "es": "Corregir un nombre, añadir una línea perdida, mover una línea en el tiempo — la IA cambia solo lo que señales"},
"hq_extra_t": {"en": "Targeted fixes", "ko": "콕 집어 고치기", "ja": "狙って直す",
 "zh": "精准修正", "fr": "Corrections ciblées", "pt": "Correções pontuais",
 "es": "Correcciones puntuales"},
"hq_extra_b": {
 "en": ("Point at what is wrong and the AI fixes just that. It sees the whole subtitle\n"
        "file plus every word speech recognition heard, with timings, so it can find\n"
        "the spot you mean.\n\n"
        "  \u2022 Names:  \"Character names are Sunny and Titi. Never write Titi as TT or TD.\"\n"
        "  \u2022 Missing lines:  \"Around 12:30 the line 'Look out!' is missing. Add it.\"\n"
        "  \u2022 Timing:  \"The subtitle at 3:20 comes too early. Move it 5 seconds later.\"\n"
        "  \u2022 Style:  \"Translate in a polite tone.\" / \"Use Arabic numerals.\"\n\n"
        "The first three run once at the end, after the subtitles are finished — lines\n"
        "can be changed, moved, added or removed. Style notes are also passed along\n"
        "during correction and translation.\n\n"
        "Saying roughly when something happens (\"around 12:30\") makes it far more\n"
        "accurate than \"somewhere in the middle\".\n\n"
        "Saved automatically in config.json and restored next time."),
 "ko": ("무엇이 잘못됐는지 짚어 주면 그 부분만 고칩니다. AI 는 자막 전체와\n"
        "받아쓴 단어 전부를 시각과 함께 보고 있어서, 말씀하신 자리를 찾아냅니다.\n\n"
        "  \u2022 이름:  \"등장인물은 Sunny 와 Titi 야. Titi 를 TT 나 TD 로 쓰지 마\"\n"
        "  \u2022 빠진 대사:  \"12분 30초쯤에 '조심해!' 가 빠졌어. 넣어줘\"\n"
        "  \u2022 시각:  \"3분 20초 자막이 너무 일찍 나와. 5초 뒤로 옮겨\"\n"
        "  \u2022 말투:  \"번역은 존댓말로 해줘\" / \"숫자는 아라비아 숫자로\"\n\n"
        "앞의 셋은 자막이 완성된 뒤 한 번 돌면서 처리합니다 — 줄을 고치고 옮기고\n"
        "넣고 지울 수 있습니다. 말투·표기는 교정·번역할 때도 함께 전달됩니다.\n\n"
        "**시각을 대충이라도 알려 주시면**(\"12분 30초쯤\") 훨씬 정확합니다.\n"
        "\"중간 어디쯤\" 보다 훨씬 잘 찾습니다.\n\n"
        "내용은 config.json 에 저장되어 다음 실행 때 복원됩니다."),
 "ja": ("どこが違うか指すと、その部分だけ直します。AI は字幕全体と、聞き取った\n"
        "全単語を時刻付きで見ているので、指定の箇所を見つけられます。\n\n"
        "  \u2022 名前:  「登場人物は Sunny と Titi。Titi を TT や TD と書かないで」\n"
        "  \u2022 抜けた台詞:  「12分30秒あたりの『危ない!』が抜けている。追加して」\n"
        "  \u2022 時刻:  「3分20秒の字幕が早すぎる。5秒後ろへ」\n"
        "  \u2022 文体:  「翻訳は丁寧語で」/「数字は算用数字で」\n\n"
        "前の三つは字幕完成後に一度だけ処理します。文体は校正・翻訳にも渡されます。\n"
        "時刻をおおよそでも伝えると精度が大きく上がります。"),
 "zh": ("指出哪里不对，AI 只改那里。它能看到完整字幕和识别到的全部词语及时间，\n"
        "所以能找到你说的位置。\n\n"
        "  \u2022 名字:  \"角色是 Sunny 和 Titi，不要把 Titi 写成 TT 或 TD\"\n"
        "  \u2022 漏掉的台词:  \"12分30秒左右漏了'小心!'，请补上\"\n"
        "  \u2022 时间:  \"3分20秒的字幕太早了，往后挪5秒\"\n"
        "  \u2022 文体:  \"翻译用礼貌语气\" / \"数字用阿拉伯数字\"\n\n"
        "前三项在字幕完成后处理一次；文体也会传给校对和翻译。\n"
        "大致说出时间会准确得多。"),
 "fr": ("Désignez ce qui ne va pas, l'IA ne corrige que cela. Elle voit tout le fichier\n"
        "et tous les mots reconnus avec leurs temps, donc elle trouve l'endroit visé.\n\n"
        "  \u2022 Noms :  « Les personnages sont Sunny et Titi. N'écris jamais Titi TT ou TD. »\n"
        "  \u2022 Répliques manquantes :  « Vers 12:30 il manque 'Attention !'. Ajoute-la. »\n"
        "  \u2022 Timing :  « Le sous-titre à 3:20 arrive trop tôt. Décale-le de 5 s. »\n"
        "  \u2022 Style :  « Traduis sur un ton poli. » / « Chiffres arabes. »\n\n"
        "Les trois premiers tournent une fois à la fin ; le style est aussi transmis\n"
        "à la correction et à la traduction. Indiquer l'heure approximative aide beaucoup."),
 "pt": ("Aponte o que está errado e a IA corrige só aquilo. Ela vê todo o arquivo e\n"
        "todas as palavras reconhecidas com seus tempos, então acha o ponto indicado.\n\n"
        "  \u2022 Nomes:  \"Os personagens são Sunny e Titi. Nunca escreva Titi como TT ou TD.\"\n"
        "  \u2022 Falas perdidas:  \"Por volta de 12:30 falta 'Cuidado!'. Acrescente.\"\n"
        "  \u2022 Tempo:  \"A legenda em 3:20 aparece cedo demais. Mova 5 s para frente.\"\n"
        "  \u2022 Estilo:  \"Traduza em tom educado.\" / \"Use algarismos arábicos.\"\n\n"
        "Os três primeiros rodam uma vez no fim; o estilo também vai para a correção\n"
        "e a tradução. Dizer a hora aproximada ajuda muito."),
 "es": ("Señala qué está mal y la IA corrige solo eso. Ve todo el archivo y todas las\n"
        "palabras reconocidas con sus tiempos, así que encuentra el punto indicado.\n\n"
        "  \u2022 Nombres:  \"Los personajes son Sunny y Titi. Nunca escribas Titi como TT o TD.\"\n"
        "  \u2022 Líneas perdidas:  \"Sobre las 12:30 falta '¡Cuidado!'. Añádela.\"\n"
        "  \u2022 Tiempo:  \"El subtítulo de 3:20 sale muy pronto. Muévelo 5 s.\"\n"
        "  \u2022 Estilo:  \"Traduce en tono cortés.\" / \"Usa números arábigos.\"\n\n"
        "Los tres primeros se ejecutan una vez al final; el estilo también pasa a la\n"
        "corrección y la traducción. Decir la hora aproximada ayuda mucho."),},
"names_migrate": {
 "en": "If character names like {names} are mis-heard as similar-sounding words, correct them to these exact spellings.",
 "ko": "{names} 같은 캐릭터 이름이 비슷한 단어로 잘못 적혀 있으면 이 표기로 바로잡아줘.",
 "ja": "{names} のようなキャラクター名が似た単語に間違っていたらこの表記に直して。",
 "zh": "如果 {names} 等角色名被听错成相近的词，请改成这个拼写。",
 "fr": "Si des noms comme {names} sont mal transcrits, corrige-les avec cette orthographe exacte.",
 "pt": "Se nomes como {names} forem mal ouvidos, corrija para esta grafia exata.",
 "es": "Si nombres como {names} se transcriben mal, corrígelos con esta ortografía exacta."},
"words_info": {
 "en": ("_words.srt is an extra debug file containing EVERY recognized word with its own\n"
        "start/end timestamp (word-level timing), before sentences are assembled.\n\n"
        "Useful for: fixing subtitle timing by hand, re-splitting sentences later,\n"
        "or feeding other tools. Most users don't need it — it just adds one more\n"
        "file per video. Your choice is saved."),
 "ko": ("_words.srt는 문장으로 합치기 전, 인식된 '모든 단어'를 단어별 시작/끝\n"
        "타임스탬프와 함께 담은 보조 파일입니다.\n\n"
        "용도: 자막 타이밍을 손으로 수정할 때, 나중에 문장을 다시 나눌 때,\n"
        "다른 도구에 넣을 때 유용합니다. 일반 사용자는 필요 없는 경우가 대부분이고\n"
        "영상마다 파일이 하나 더 생길 뿐입니다. 선택은 저장됩니다."),
 "ja": ("_words.srt は文にまとめる前の「認識された全単語」を単語ごとの開始/終了\n"
        "タイムスタンプ付きで収めた補助ファイルです。\n\n"
        "用途: 字幕タイミングの手動修正、後で文を分け直す、他ツールへの入力など。\n"
        "通常は不要で、動画ごとにファイルが1つ増えるだけです。選択は保存されます。"),
 "zh": ("_words.srt 是辅助文件：在拼成句子之前，包含识别出的每个单词及其\n"
        "开始/结束时间戳（单词级时间轴）。\n\n"
        "用途：手动修正字幕时间、以后重新分句、或供其他工具使用。\n"
        "普通用户一般不需要 — 只会让每个视频多一个文件。你的选择会被保存。"),
 "fr": ("_words.srt est un fichier annexe contenant CHAQUE mot reconnu avec son propre\n"
        "horodatage début/fin (timing par mot), avant l'assemblage en phrases.\n\n"
        "Utile pour : corriger le timing à la main, redécouper les phrases plus tard,\n"
        "ou alimenter d'autres outils. La plupart des utilisateurs n'en ont pas besoin.\n"
        "Votre choix est enregistré."),
 "pt": ("_words.srt é um arquivo auxiliar com CADA palavra reconhecida e seus próprios\n"
        "tempos de início/fim (timing por palavra), antes da montagem em frases.\n\n"
        "Útil para: ajustar timing manualmente, redividir frases depois, ou usar em\n"
        "outras ferramentas. A maioria dos usuários não precisa. Sua escolha fica salva."),
 "es": ("_words.srt es un archivo auxiliar con CADA palabra reconocida y sus propios\n"
        "tiempos de inicio/fin (timing por palabra), antes de montar las frases.\n\n"
        "Útil para: ajustar tiempos a mano, redividir frases después, o usarlo en otras\n"
        "herramientas. La mayoría no lo necesita. Tu elección queda guardada."),},
"log_fallback": {
 "en": "Decoding failed mid-file — extracting audio with ffmpeg and retrying...",
 "ko": "파일 중간에서 디코딩 실패 — ffmpeg로 오디오만 추출해서 재시도합니다...",
 "ja": "ファイル途中でデコード失敗 — ffmpegで音声のみ抽出して再試行します...",
 "zh": "文件中途解码失败 — 用 ffmpeg 仅提取音频后重试...",
 "fr": "Échec du décodage en cours de fichier — extraction audio via ffmpeg puis nouvel essai...",
 "pt": "Falha de decodificação no meio do arquivo — extraindo áudio com ffmpeg e tentando de novo...",
 "es": "Fallo de decodificación a mitad de archivo — extrayendo audio con ffmpeg y reintentando..."},
"log_fallback2": {
 "en": "No speech found — extracting audio with ffmpeg and retrying once...",
 "ko": "음성이 인식되지 않음 — ffmpeg로 오디오를 추출해 한 번 더 시도합니다...",
 "ja": "音声が認識されず — ffmpegで音声を抽出してもう一度試します...",
 "zh": "未识别到语音 — 用 ffmpeg 提取音频后再试一次...",
 "fr": "Aucune parole détectée — extraction audio via ffmpeg puis nouvel essai...",
 "pt": "Nenhuma fala encontrada — extraindo áudio com ffmpeg e tentando mais uma vez...",
 "es": "No se detectó voz — extrayendo audio con ffmpeg y reintentando una vez..."},
"log_ffmpeg_missing": {
 "en": "ffmpeg not found — installing helper (imageio-ffmpeg)...",
 "ko": "ffmpeg이 없음 — 보조 패키지(imageio-ffmpeg)를 설치합니다...",
 "ja": "ffmpegが見つからず — 補助パッケージ(imageio-ffmpeg)をインストールします...",
 "zh": "未找到 ffmpeg — 正在安装辅助包（imageio-ffmpeg）...",
 "fr": "ffmpeg introuvable — installation du paquet d'aide (imageio-ffmpeg)...",
 "pt": "ffmpeg não encontrado — instalando pacote auxiliar (imageio-ffmpeg)...",
 "es": "ffmpeg no encontrado — instalando paquete auxiliar (imageio-ffmpeg)..."},
"log_ffmpeg_fail": {
 "en": "Audio extraction failed: {e}", "ko": "오디오 추출 실패: {e}",
 "ja": "音声抽出失敗: {e}", "zh": "音频提取失败：{e}",
 "fr": "Échec de l'extraction audio : {e}", "pt": "Falha na extração de áudio: {e}",
 "es": "Fallo en la extracción de audio: {e}"},
"log_extracted": {
 "en": "Audio extracted — transcribing again...", "ko": "오디오 추출 완료 — 다시 인식합니다...",
 "ja": "音声抽出完了 — 再認識します...", "zh": "音频提取完成 — 重新识别...",
 "fr": "Audio extrait — nouvelle transcription...", "pt": "Áudio extraído — transcrevendo de novo...",
 "es": "Audio extraído — transcribiendo de nuevo..."},
"sum_skipped": {
 "en": "!! Some steps did not run — the subtitles are usable but not finished:",
 "ko": "!! 일부 단계가 실행되지 않았습니다 — 자막은 쓸 수 있지만 완성본은 아닙니다:",
 "ja": "!! 一部の工程が実行されませんでした — 字幕は使えますが完成版ではありません:",
 "zh": "!! 部分步骤未执行 — 字幕可用但并非成品：",
 "fr": "!! Certaines étapes n'ont pas tourné — sous-titres utilisables mais incomplets :",
 "pt": "!! Algumas etapas não rodaram — legendas utilizáveis, mas não finalizadas:",
 "es": "!! Algunos pasos no se ejecutaron — subtítulos usables pero sin terminar:"},
"skip_rebuild": {
 "en": "Sentences were NOT rebuilt by AI (server busy or limit) — lines are split "
       "on pauses only, so many have no capital letters or full stops",
 "ko": "문장 재조립을 AI가 못 했습니다 (서버 혼잡 또는 한도) — 무음 위치로만 잘려 "
       "있어서 대문자·마침표가 없는 줄이 많습니다",
 "ja": "文の再構成をAIができませんでした（混雑または制限）— 無音位置だけで区切られ、"
       "大文字や句点のない行が多くあります",
 "zh": "AI 未能重组句子（服务器繁忙或额度）— 仅按静音处切分，许多行没有大写和句号",
 "fr": "Les phrases n'ont PAS été reconstruites par l'IA (serveurs saturés ou limite) — "
       "découpage sur les silences seulement, sans majuscules ni points",
 "pt": "As frases NÃO foram reconstruídas pela IA (servidor ocupado ou limite) — "
       "cortes apenas nas pausas, muitas linhas sem maiúsculas nem pontos",
 "es": "La IA NO reconstruyó las frases (servidor ocupado o límite) — solo se cortó "
       "en los silencios, muchas líneas sin mayúsculas ni puntos"},
"skip_rebuild_part": {
 "en": "Sentence rebuilding fell back for {n} of {t} block(s) — those parts are split "
       "on pauses only",
 "ko": "문장 재조립이 {t}개 묶음 중 {n}개에서 실패했습니다 — 그 부분은 무음 위치로만 잘려 있습니다",
 "ja": "文の再構成が{t}ブロック中{n}ブロックで失敗しました — その部分は無音位置だけで区切られています",
 "zh": "句子重组在 {t} 个块中有 {n} 个失败 — 这些部分仅按静音处切分",
 "fr": "La reconstruction des phrases a échoué sur {n} bloc(s) sur {t} — ces parties sont "
       "découpées sur les silences seulement",
 "pt": "A reconstrução das frases falhou em {n} de {t} bloco(s) — essas partes foram "
       "cortadas apenas nas pausas",
 "es": "La reconstrucción de frases falló en {n} de {t} bloque(s) — esas partes se "
       "cortaron solo en los silencios"},
"skip_correct": {
 "en": "Correction did not run (AI limit) — mis-heard words were left as they are",
 "ko": "교정을 못 했습니다 (AI 한도) — 잘못 들은 단어가 그대로 남아 있습니다",
 "ja": "校正できませんでした（AI制限）— 聞き間違いがそのまま残っています",
 "zh": "未能校对（AI 额度）— 听错的词原样保留",
 "fr": "Correction non effectuée (limite IA) — les mots mal entendus restent tels quels",
 "pt": "Correção não executada (limite de IA) — palavras mal ouvidas ficaram como estão",
 "es": "No se corrigió (límite de IA) — las palabras mal oídas quedan tal cual"},
"skip_translate": {
 "en": "{l} was not translated (AI limit) — no file was written",
 "ko": "{l} 번역을 못 했습니다 (AI 한도) — 파일이 만들어지지 않았습니다",
 "ja": "{l} の翻訳ができませんでした（AI制限）— ファイルは作られていません",
 "zh": "未能翻译{l}（AI 额度）— 未生成文件",
 "fr": "{l} non traduit (limite IA) — aucun fichier créé",
 "pt": "{l} não foi traduzido (limite de IA) — nenhum arquivo criado",
 "es": "{l} no se tradujo (límite de IA) — no se creó ningún archivo"},
"sum_header": {
 "en": "===== Finished: {ok} succeeded, {fail} FAILED =====",
 "ko": "===== 작업 정리: 성공 {ok}개, 실패 {fail}개 =====",
 "ja": "===== 結果: 成功{ok}件、失敗{fail}件 =====",
 "zh": "===== 结果：成功 {ok} 个，失败 {fail} 个 =====",
 "fr": "===== Terminé : {ok} réussis, {fail} ÉCHECS =====",
 "pt": "===== Concluído: {ok} com sucesso, {fail} FALHARAM =====",
 "es": "===== Terminado: {ok} correctos, {fail} FALLARON ====="},
"sum_ok_all": {
 "en": "===== All {ok} files succeeded =====",
 "ko": "===== 전체 {ok}개 파일 모두 성공 =====",
 "ja": "===== 全{ok}ファイル成功 =====",
 "zh": "===== 全部 {ok} 个文件成功 =====",
 "fr": "===== Les {ok} fichiers ont réussi =====",
 "pt": "===== Todos os {ok} arquivos com sucesso =====",
 "es": "===== Los {ok} archivos se procesaron correctamente ====="},
"sum_item": {"en": "✗ {f}\n   {e}", "ko": "✗ {f}\n   {e}", "ja": "✗ {f}\n   {e}",
 "zh": "✗ {f}\n   {e}", "fr": "✗ {f}\n   {e}", "pt": "✗ {f}\n   {e}", "es": "✗ {f}\n   {e}"},
"err_nospeech_short": {
 "en": "No speech recognized", "ko": "음성 인식 결과 없음", "ja": "音声認識結果なし",
 "zh": "未识别到语音", "fr": "Aucune parole reconnue", "pt": "Nenhuma fala reconhecida",
 "es": "No se reconoció voz"},
"hint_decode": {
 "en": "   → The stream is broken or changes format mid-file (e.g. joined pieces of different formats, or a truncated file). Try re-making the file, or split off the differing part.",
 "ko": "   → 파일 중간에 스트림이 깨졌거나 형식이 바뀝니다 (예: 형식이 다른 조각을 이어붙였거나 잘린 파일). 파일을 다시 만들거나, 형식이 다른 부분을 분리해 보세요.",
 "ja": "   → ファイル途中でストリームが壊れているか形式が変わっています（例: 形式の違う断片の結合、途中で切れたファイル）。作り直すか、異なる部分を分離してください。",
 "zh": "   → 文件中途流损坏或格式发生变化（例如拼接了不同格式的片段，或文件被截断）。请重新生成文件，或把格式不同的部分分开。",
 "fr": "   → Le flux est endommagé ou change de format en cours de fichier (morceaux de formats différents joints, ou fichier tronqué). Refaites le fichier ou séparez la partie différente.",
 "pt": "   → O stream está quebrado ou muda de formato no meio (pedaços de formatos diferentes unidos, ou arquivo truncado). Refaça o arquivo ou separe a parte diferente.",
 "es": "   → El flujo está dañado o cambia de formato a mitad de archivo (trozos de formatos distintos unidos, o archivo truncado). Rehaz el archivo o separa la parte distinta."},
"hint_nospeech": {
 "en": "   → The file may be corrupted, truncated, or contain no audible speech.",
 "ko": "   → 파일이 손상됐거나 잘렸거나, 들리는 음성이 없는 파일일 수 있습니다.",
 "ja": "   → ファイルが破損・途中切断されているか、音声が含まれていない可能性があります。",
 "zh": "   → 文件可能损坏、被截断，或不含可识别的语音。",
 "fr": "   → Le fichier est peut-être corrompu, tronqué ou sans parole audible.",
 "pt": "   → O arquivo pode estar corrompido, truncado ou sem fala audível.",
 "es": "   → El archivo puede estar dañado, truncado o sin voz audible."},
"hint_memory": {
 "en": "   → Out of memory. Close other programs, or process fewer/shorter files at once.",
 "ko": "   → 메모리 부족입니다. 다른 프로그램을 닫거나, 한 번에 처리하는 파일 수/길이를 줄여 보세요.",
 "ja": "   → メモリ不足です。他のプログラムを閉じるか、一度に処理するファイルを減らしてください。",
 "zh": "   → 内存不足。请关闭其他程序，或减少一次处理的文件数量/长度。",
 "fr": "   → Mémoire insuffisante. Fermez d'autres programmes ou traitez moins de fichiers à la fois.",
 "pt": "   → Memória insuficiente. Feche outros programas ou processe menos arquivos por vez.",
 "es": "   → Memoria insuficiente. Cierra otros programas o procesa menos archivos a la vez."},
})


I18N.update({
"mi_skip_existing": {
 "en": "Skip files that already have subtitles (.srt)",
 "ko": "이미 자막(.srt)이 있는 파일 건너뛰기",
 "ja": "既に字幕(.srt)があるファイルをスキップ",
 "zh": "跳过已有字幕(.srt)的文件",
 "fr": "Ignorer les fichiers ayant déjà des sous-titres (.srt)",
 "pt": "Pular arquivos que já têm legendas (.srt)",
 "es": "Omitir archivos que ya tienen subtítulos (.srt)"},
"log_skip_exist": {
 "en": "Skipped — subtitle already exists: {p}",
 "ko": "건너뜀 — 자막이 이미 있음: {p}",
 "ja": "スキップ — 字幕が既に存在: {p}",
 "zh": "已跳过 — 字幕已存在：{p}",
 "fr": "Ignoré — sous-titre déjà présent : {p}",
 "pt": "Pulado — legenda já existe: {p}",
 "es": "Omitido — el subtítulo ya existe: {p}"},
"sum_skip": {
 "en": "({n} skipped — subtitles already existed)",
 "ko": "(이미 자막이 있어 건너뛴 파일 {n}개)",
 "ja": "（字幕が既にありスキップ: {n}件）",
 "zh": "（因已有字幕而跳过 {n} 个）",
 "fr": "({n} ignorés — sous-titres déjà présents)",
 "pt": "({n} pulados — legendas já existiam)",
 "es": "({n} omitidos — ya existían subtítulos)"},
"btn_add": {"en": "Add...", "ko": "추가...", "ja": "追加...", "zh": "添加...",
 "fr": "Ajouter...", "pt": "Adicionar...", "es": "Añadir..."},
"btn_remove": {"en": "Remove selected", "ko": "선택 제거", "ja": "選択を削除", "zh": "移除所选",
 "fr": "Retirer la sélection", "pt": "Remover selecionados", "es": "Quitar seleccionados"},
"btn_clear": {"en": "Clear all", "ko": "전체 비우기", "ja": "すべてクリア", "zh": "全部清空",
 "fr": "Tout vider", "pt": "Limpar tudo", "es": "Vaciar todo"},
"log_added": {"en": "Added: {p}", "ko": "추가됨: {p}", "ja": "追加: {p}", "zh": "已添加: {p}",
 "fr": "Ajouté : {p}", "pt": "Adicionado: {p}", "es": "Añadido: {p}"},
"lbl_engine": {"en": "AI engine:", "ko": "AI 엔진:", "ja": "AIエンジン:", "zh": "AI 引擎:",
 "fr": "Moteur IA :", "pt": "Motor de IA:", "es": "Motor de IA:"},
# v1.2: 셋 중 하나를 반드시 고르게 되었으므로 라벨이 '무엇을 고르는지'를 바로 알려준다.
"prov_free": {
 "en": "free API · recommended", "ko": "무료 API · 권장", "ja": "無料API・推奨",
 "zh": "免费 API · 推荐", "fr": "API gratuite · recommandé", "pt": "API grátis · recomendado",
 "es": "API gratis · recomendado"},
"prov_paid": {
 "en": "paid API · top quality", "ko": "유료 API · 최고 품질", "ja": "有料API・最高品質",
 "zh": "付费 API · 最佳质量", "fr": "API payante · qualité max", "pt": "API paga · melhor qualidade",
 "es": "API de pago · máxima calidad"},
"hq_open_key": {"en": "Get a {p} API key", "ko": "{p} API 키 발급받기", "ja": "{p} APIキーを取得",
 "zh": "获取 {p} API 密钥", "fr": "Obtenir une clé API {p}", "pt": "Obter chave de API {p}",
 "es": "Obtener clave API de {p}"},
"log_http_wait": {
 "en": "{c} {k} — retrying in {s}s... ({i}/{n})",
 "ko": "{c} {k} — {s}초 후 자동 재시도... ({i}/{n})",
 "ja": "{c} {k} — {s}秒後に自動再試行... ({i}/{n})",
 "zh": "{c} {k} — {s} 秒后自动重试... ({i}/{n})",
 "fr": "{c} {k} — nouvel essai dans {s}s... ({i}/{n})",
 "pt": "{c} {k} — repetindo em {s}s... ({i}/{n})",
 "es": "{c} {k} — reintentando en {s}s... ({i}/{n})"},
"why_429": {"en": "your rate limit", "ko": "내 요청 한도 초과", "ja": "レート制限",
 "zh": "达到速率限制", "fr": "votre limite de débit", "pt": "seu limite de taxa",
 "es": "tu límite de peticiones"},
"why_503": {"en": "the server is busy", "ko": "서버 과부하 (내 탓 아님)",
 "ja": "サーバー混雑（こちらの問題ではない）", "zh": "服务器繁忙（非本机问题）",
 "fr": "serveur surchargé", "pt": "servidor ocupado", "es": "servidor saturado"},
"why_5xx": {"en": "a server error", "ko": "서버 오류", "ja": "サーバーエラー",
 "zh": "服务器错误", "fr": "erreur serveur", "pt": "erro do servidor",
 "es": "error del servidor"},
"why_other": {"en": "a temporary error", "ko": "일시적 오류", "ja": "一時的なエラー",
 "zh": "临时错误", "fr": "erreur temporaire", "pt": "erro temporário",
 "es": "error temporal"},
"log_rate_wait": {
 "en": "Free-tier rate limit reached — retrying in {s}s... ({i}/{n})",
 "ko": "무료 한도(분당 요청) 초과 — {s}초 후 자동 재시도... ({i}/{n})",
 "ja": "無料枠のレート制限 — {s}秒後に自動再試行... ({i}/{n})",
 "zh": "达到免费额度速率限制 — {s} 秒后自动重试... ({i}/{n})",
 "fr": "Limite du niveau gratuit atteinte — nouvel essai dans {s}s... ({i}/{n})",
 "pt": "Limite da cota grátis atingido — repetindo em {s}s... ({i}/{n})",
 "es": "Límite del nivel gratis alcanzado — reintentando en {s}s... ({i}/{n})"},
})


I18N.update({
# v1.2: '실험' 표기를 뗐다. 로컬 모델을 Gemma 4 로 바꾼 뒤 품질이 무료 API 에 근접했다.
#   대신 '끄기'가 사라진 만큼 하드웨어 조건을 알려 준다 — 품질이 아니라 GPU 가 관건이다.
#   모델 이름은 넣지 않는다 (Settings 메뉴에서 바꿀 수 있으므로 라벨이 금방 낡는다).
"prov_local_tag": {"en": "free · offline · needs a GPU", "ko": "무료 · 오프라인 · GPU 필요",
 "ja": "無料・オフライン・GPU必須", "zh": "免费 · 离线 · 需要 GPU",
 "fr": "gratuit · hors ligne · GPU requis", "pt": "grátis · offline · precisa de GPU",
 "es": "gratis · offline · requiere GPU"},
# v1.2: 이 문구의 목적이 바뀌었다.
#   v1.1까지는 "품질이 나쁘니 쓰지 마세요"로 기대치를 낮추는 게 목적이었다. 로컬 모델을
#   Gemma 4 로 교체한 뒤 품질이 무료 API 에 근접해, 이제는 "품질은 괜찮은데 하드웨어를
#   탄다"는 점을 알려 주는 게 목적이다. 다시 품질 경고로 되돌리지 말 것.
"local_quality_note": {
 "en": ("NOTE — Local AI runs entirely on your own PC. Quality is now close to the free API,\n"
        "but speed depends heavily on your graphics card. With enough VRAM a short video takes\n"
        "a few minutes; with too little, the model spills over to the CPU and can take ten times\n"
        "longer. If you have internet, the free Gemini API is faster and needs no download.\n"
        "Pick Local AI when you must work offline, or when the subtitle text must never leave\n"
        "this computer."),
 "ko": ("참고 — 로컬 AI는 이 PC 안에서만 돌아갑니다. 품질은 이제 무료 API에 가깝지만,\n"
        "속도는 그래픽카드에 크게 좌우됩니다. VRAM이 넉넉하면 짧은 영상에 몇 분이면 되고,\n"
        "부족하면 모델이 CPU로 흘러넘쳐 열 배까지 느려질 수 있습니다.\n"
        "인터넷이 된다면 무료 Gemini API가 더 빠르고 다운로드도 필요 없습니다.\n"
        "오프라인으로 작업해야 하거나, 자막 텍스트가 이 컴퓨터를 절대 벗어나면 안 될 때\n"
        "로컬 AI를 고르세요."),
 "ja": ("注意 — ローカルAIはこのPC内だけで動作します。品質は無料APIに近づきましたが、\n"
        "速度はグラフィックカードに大きく左右されます。VRAMが十分なら短い動画で数分、\n"
        "不足するとモデルがCPUに溢れて10倍近く遅くなることがあります。\n"
        "インターネットが使えるなら無料のGemini APIの方が速く、ダウンロードも不要です。\n"
        "オフライン作業が必要な場合や、字幕テキストをPCの外に出したくない場合に選んでください。"),
 "zh": ("注意 — 本地 AI 完全在本机运行。质量已接近免费 API，但速度很大程度上取决于显卡。\n"
        "显存充足时，短视频只需几分钟；显存不足时模型会溢出到 CPU，可能慢上十倍。\n"
        "如果能联网，免费的 Gemini API 更快且无需下载。\n"
        "需要离线工作、或字幕文本绝不能离开本机时，再选择本地 AI。"),
 "fr": ("REMARQUE — L'IA locale tourne entièrement sur votre PC. La qualité est désormais proche\n"
        "de l'API gratuite, mais la vitesse dépend fortement de votre carte graphique. Avec assez\n"
        "de VRAM, une courte vidéo prend quelques minutes ; sinon le modèle déborde sur le CPU et\n"
        "peut être dix fois plus lent. Si vous avez internet, l'API Gemini gratuite est plus rapide\n"
        "et ne demande aucun téléchargement. Choisissez l'IA locale pour travailler hors ligne, ou\n"
        "si le texte ne doit jamais quitter cet ordinateur."),
 "pt": ("NOTA — A IA local roda inteiramente no seu PC. A qualidade agora é próxima da API grátis,\n"
        "mas a velocidade depende muito da placa de vídeo. Com VRAM suficiente, um vídeo curto leva\n"
        "alguns minutos; com pouca, o modelo transborda para a CPU e pode ficar dez vezes mais lento.\n"
        "Se você tem internet, a API grátis do Gemini é mais rápida e não exige download.\n"
        "Escolha a IA local quando precisar trabalhar offline, ou quando o texto das legendas não\n"
        "puder sair deste computador."),
 "es": ("NOTA — La IA local se ejecuta por completo en tu PC. La calidad ya es cercana a la API\n"
        "gratuita, pero la velocidad depende mucho de tu tarjeta gráfica. Con suficiente VRAM un\n"
        "vídeo corto tarda unos minutos; con poca, el modelo se desborda a la CPU y puede tardar\n"
        "diez veces más. Si tienes internet, la API gratuita de Gemini es más rápida y no requiere\n"
        "descarga. Elige la IA local cuando debas trabajar sin conexión, o cuando el texto de los\n"
        "subtítulos no pueda salir de este ordenador."),},
"local_ready": {
 "en": "✓ Local AI ready — {m} (no key needed)",
 "ko": "✓ 로컬 AI 준비됨 — {m} (키 필요 없음)",
 "ja": "✓ ローカルAI準備完了 — {m}（キー不要）",
 "zh": "✓ 本地 AI 已就绪 — {m}（无需密钥）",
 "fr": "✓ IA locale prête — {m} (aucune clé requise)",
 "pt": "✓ IA local pronta — {m} (sem chave)",
 "es": "✓ IA local lista — {m} (sin clave)"},
"local_no_model": {
 "en": "Local AI installed — model {m} not downloaded yet",
 "ko": "로컬 AI 설치됨 — 모델 {m}이(가) 아직 없습니다",
 "ja": "ローカルAIはインストール済み — モデル {m} が未ダウンロード",
 "zh": "本地 AI 已安装 — 模型 {m} 尚未下载",
 "fr": "IA locale installée — modèle {m} pas encore téléchargé",
 "pt": "IA local instalada — modelo {m} ainda não baixado",
 "es": "IA local instalada — el modelo {m} aún no está descargado"},
"local_no_server": {
 "en": "Ollama installed but not running",
 "ko": "Ollama가 설치되어 있지만 실행 중이 아닙니다",
 "ja": "Ollamaはインストール済みですが起動していません",
 "zh": "已安装 Ollama 但未运行",
 "fr": "Ollama installé mais non démarré",
 "pt": "Ollama instalado mas não em execução",
 "es": "Ollama instalado pero no en ejecución"},
"local_no_ollama": {
 "en": "Local AI (Ollama) is not installed yet — click Install",
 "ko": "로컬 AI(Ollama)가 아직 설치되지 않았습니다 — 설치 버튼을 누르세요",
 "ja": "ローカルAI（Ollama）は未インストール — インストールを押してください",
 "zh": "尚未安装本地 AI（Ollama）— 请点击安装",
 "fr": "IA locale (Ollama) non installée — cliquez sur Installer",
 "pt": "IA local (Ollama) não instalada — clique em Instalar",
 "es": "IA local (Ollama) no instalada — pulsa Instalar"},
"btn_install_local": {"en": "Install Local AI...", "ko": "로컬 AI 설치...",
 "ja": "ローカルAIをインストール...", "zh": "安装本地 AI...",
 "fr": "Installer l'IA locale...", "pt": "Instalar IA local...", "es": "Instalar IA local..."},
"btn_start_local": {"en": "Start", "ko": "시작", "ja": "起動", "zh": "启动",
 "fr": "Démarrer", "pt": "Iniciar", "es": "Iniciar"},
"btn_pull_model": {"en": "Download model", "ko": "모델 다운로드", "ja": "モデルをダウンロード",
 "zh": "下载模型", "fr": "Télécharger le modèle", "pt": "Baixar modelo", "es": "Descargar modelo"},
"local_install_info": {
 "en": ("This will set up a FREE AI that runs on YOUR computer (no key, no limits, offline):\n\n"
        "  1. Install Ollama (local AI runner)\n  2. Download the AI model {m}{s}\n\n"
        "Takes 10-30 minutes depending on your internet speed.\n"
        "An NVIDIA GPU with 10 GB VRAM is recommended (less VRAM works but slower;\n"
        "without a GPU it will be very slow).\n\nContinue?"),
 "ko": ("내 컴퓨터에서 직접 도는 무료 AI를 설치합니다 (키 없음·한도 없음·오프라인):\n\n"
        "  1. Ollama(로컬 AI 실행기) 설치\n  2. AI 모델 {m}{s} 다운로드\n\n"
        "인터넷 속도에 따라 10~30분 걸립니다.\n"
        "NVIDIA GPU VRAM 10GB 이상 권장 (그 이하도 동작하지만 느려질 수 있고,\n"
        "GPU가 없으면 매우 느려서 비추천).\n\n계속할까요?"),
 "ja": ("自分のPCで動く無料AIをセットアップします（キー不要・制限なし・オフライン）:\n\n"
        "  1. Ollama（ローカルAI実行環境）をインストール\n  2. AIモデル {m}{s} をダウンロード\n\n"
        "回線速度により10〜30分かかります。\nNVIDIA GPU VRAM 10GB以上推奨（それ以下でも動くが遅め、\nGPUなしは非推奨）。\n\n続行しますか？"),
 "zh": ("将安装在你电脑上直接运行的免费 AI（无密钥·无限制·离线）：\n\n"
        "  1. 安装 Ollama（本地 AI 运行器）\n  2. 下载 AI 模型 {m}{s}\n\n"
        "视网速需要 10-30 分钟。\n建议 NVIDIA GPU 显存 10GB 以上（更小可用但较慢，\n无 GPU 不推荐）。\n\n继续吗？"),
 "fr": ("Installe une IA GRATUITE qui tourne sur VOTRE ordinateur (sans clé, sans limites, hors ligne) :\n\n"
        "  1. Installer Ollama\n  2. Télécharger le modèle {m}{s}\n\n"
        "10 à 30 minutes selon votre connexion.\nGPU NVIDIA 10 Go de VRAM recommandé (moins possible mais plus lent ;\nsans GPU, très lent).\n\nContinuer ?"),
 "pt": ("Instala uma IA GRÁTIS que roda no SEU computador (sem chave, sem limites, offline):\n\n"
        "  1. Instalar o Ollama\n  2. Baixar o modelo {m}{s}\n\n"
        "Leva 10-30 minutos conforme sua internet.\nGPU NVIDIA com 10 GB de VRAM recomendada (menos funciona, mas mais lento;\nsem GPU fica muito lento).\n\nContinuar?"),
 "es": ("Instala una IA GRATIS que corre en TU ordenador (sin clave, sin límites, sin conexión):\n\n"
        "  1. Instalar Ollama\n  2. Descargar el modelo {m}{s}\n\n"
        "Tarda 10-30 minutos según tu internet.\nSe recomienda GPU NVIDIA con 10 GB de VRAM (menos funciona pero más lento;\nsin GPU es muy lento).\n\n¿Continuar?"),},
"log_local_installing": {
 "en": "Installing Ollama...", "ko": "Ollama 설치 중...", "ja": "Ollamaをインストール中...",
 "zh": "正在安装 Ollama...", "fr": "Installation d'Ollama...", "pt": "Instalando o Ollama...",
 "es": "Instalando Ollama..."},
"log_local_starting": {
 "en": "Starting local AI server...", "ko": "로컬 AI 서버 시작 중...",
 "ja": "ローカルAIサーバーを起動中...", "zh": "正在启动本地 AI 服务...",
 "fr": "Démarrage du serveur IA local...", "pt": "Iniciando o servidor de IA local...",
 "es": "Iniciando el servidor de IA local..."},
"log_local_pulling": {
 "en": "Downloading model {m}{s} — this takes several minutes...",
 "ko": "모델 {m}{s} 다운로드 중 — 수 분 걸립니다...",
 "ja": "モデル {m}{s} をダウンロード中 — 数分かかります...",
 "zh": "正在下载模型 {m}{s} — 需要几分钟...",
 "fr": "Téléchargement du modèle {m}{s} — plusieurs minutes...",
 "pt": "Baixando o modelo {m}{s} — leva vários minutos...",
 "es": "Descargando el modelo {m}{s} — tarda varios minutos..."},
"log_wh_release": {
 "en": "Speech recognition released from the graphics card (~3 GB freed for the AI)",
 "ko": "받아쓰기를 그래픽카드에서 내렸습니다 (AI 몫으로 3GB쯤 비웠습니다)",
 "ja": "音声認識をグラフィックカードから降ろしました（AI用に約3GB確保）",
 "zh": "已将语音识别从显卡卸载（为 AI 腾出约 3GB）",
 "fr": "Reconnaissance vocale déchargée de la carte graphique (~3 Go libérés pour l'IA)",
 "pt": "Reconhecimento de fala descarregado da placa de vídeo (~3 GB livres para a IA)",
 "es": "Reconocimiento de voz descargado de la tarjeta gráfica (~3 GB libres para la IA)"},
"log_wh_reload": {
 "en": "Loading speech recognition again for the song section...",
 "ko": "노래 구간을 위해 받아쓰기를 다시 올립니다...",
 "ja": "歌区間のために音声認識を再度読み込みます...",
 "zh": "为歌曲片段重新加载语音识别...",
 "fr": "Rechargement de la reconnaissance vocale pour la partie chantée...",
 "pt": "Recarregando o reconhecimento de fala para a parte cantada...",
 "es": "Recargando el reconocimiento de voz para la parte cantada..."},
"log_local_upgrade": {
 "en": "Graphics card {v} has room for a better model — switching to {m}",
 "ko": "그래픽카드 {v} 는 더 좋은 모델이 들어갑니다 — {m} 로 바꿉니다",
 "ja": "グラフィックカード {v} ならより良いモデルが載ります — {m} に切り替えます",
 "zh": "显卡 {v} 可以容纳更好的模型 — 切换为 {m}",
 "fr": "La carte {v} peut accueillir un meilleur modèle — passage à {m}",
 "pt": "A placa {v} comporta um modelo melhor — mudando para {m}",
 "es": "La tarjeta {v} admite un modelo mejor — cambiando a {m}"},
"log_local_tune": {
 "en": "Graphics card {v}, {f} free for context — using {c} tokens ({l} lines per request)",
 "ko": "그래픽카드 {v}, 문맥에 쓸 자리 {f} — 컨텍스트 {c} 토큰 (한 번에 {l}줄)",
 "ja": "グラフィックカード {v}、コンテキスト用の空き {f} — {c} トークン（1回 {l} 行）",
 "zh": "显卡 {v}，可用于上下文 {f} — 使用 {c} 词元（每次 {l} 行）",
 "fr": "Carte graphique {v}, {f} libres pour le contexte — {c} jetons ({l} lignes par requête)",
 "pt": "Placa de vídeo {v}, {f} livres para o contexto — {c} tokens ({l} linhas por requisição)",
 "es": "Tarjeta gráfica {v}, {f} libres para el contexto — {c} tokens ({l} líneas por petición)"},
"log_local_tight": {
 "en": "  {m} leaves almost no room for context on this card, so requests stay small. "
       "A smaller model would let each request carry far more lines.",
 "ko": "  이 카드에서는 {m} 이(가) 문맥 쓸 자리를 거의 안 남겨서 조금씩만 보냅니다. "
       "더 작은 모델을 고르면 한 번에 훨씬 많은 줄을 보낼 수 있습니다.",
 "ja": "  このカードでは {m} が文脈用の余地をほとんど残さないため、少しずつ送ります。"
       "小さいモデルを選べば1回にもっと多くの行を送れます。",
 "zh": "  在这张显卡上 {m} 几乎不留上下文空间，因此每次只发送少量。"
       "选择更小的模型可以每次发送更多行。",
 "fr": "  Sur cette carte, {m} ne laisse presque pas de place au contexte : les requêtes restent petites. "
       "Un modèle plus petit permettrait beaucoup plus de lignes par requête.",
 "pt": "  Nesta placa, {m} quase não deixa espaço para o contexto, então as requisições ficam pequenas. "
       "Um modelo menor permitiria muito mais linhas por requisição.",
 "es": "  En esta tarjeta, {m} casi no deja espacio para el contexto, así que las peticiones son pequeñas. "
       "Un modelo más pequeño permitiría muchas más líneas por petición."},
"log_local_ready": {
 "en": "Local AI is ready!", "ko": "로컬 AI 준비 완료!", "ja": "ローカルAIの準備完了！",
 "zh": "本地 AI 已就绪！", "fr": "IA locale prête !", "pt": "IA local pronta!",
 "es": "¡IA local lista!"},
"log_local_fail": {
 "en": "Local AI setup failed: {e}", "ko": "로컬 AI 설치 실패: {e}",
 "ja": "ローカルAIのセットアップ失敗: {e}", "zh": "本地 AI 安装失败：{e}",
 "fr": "Échec de l'installation de l'IA locale : {e}", "pt": "Falha na instalação da IA local: {e}",
 "es": "Fallo al instalar la IA local: {e}"},
"hint_local": {
 "en": "   → The Local AI (Ollama) isn't running. Select the Local AI engine and use its Install/Start button.",
 "ko": "   → 로컬 AI(Ollama)가 실행되고 있지 않습니다. AI 엔진에서 Local AI를 선택하고 설치/시작 버튼을 사용하세요.",
 "ja": "   → ローカルAI（Ollama）が起動していません。Local AIエンジンを選び、インストール/起動ボタンを使ってください。",
 "zh": "   → 本地 AI（Ollama）未运行。请选择 Local AI 引擎并使用安装/启动按钮。",
 "fr": "   → L'IA locale (Ollama) ne tourne pas. Sélectionnez le moteur Local AI et utilisez Installer/Démarrer.",
 "pt": "   → A IA local (Ollama) não está em execução. Selecione o motor Local AI e use Instalar/Iniciar.",
 "es": "   → La IA local (Ollama) no está en ejecución. Selecciona el motor Local AI y usa Instalar/Iniciar."},
"mi_local_model": {
 "en": "Local AI model... (now: {m})", "ko": "로컬 AI 모델 선택... (현재: {m})",
 "ja": "ローカルAIモデル...（現在: {m}）", "zh": "本地 AI 模型...（当前：{m}）",
 "fr": "Modèle IA locale... (actuel : {m})", "pt": "Modelo de IA local... (atual: {m})",
 "es": "Modelo de IA local... (actual: {m})"},
"dlg_local_model": {
 "en": "Choose the local AI model. It downloads on first use.\n\n"
       "  gemma4:12b            7.6 GB   VRAM 12 GB+\n"
       "  gemma4:26b-a4b-it-qat  16 GB   VRAM 24 GB+   smarter, much larger\n\n"
       "You do not have to choose. Left alone, JQSubtitle picks the best model your\n"
       "graphics card can hold and sets how much it reads at once — a 24 GB card gets\n"
       "the 26b automatically. Once you pick one here, that choice is kept and nothing\n"
       "is changed for you.\n\n"
       "Under 12 GB the local engine is refused: the model alone needs more room than\n"
       "the card has. Use Gemini or Claude instead.\n\n"
       "You can also type a model name that is not listed — the size is read from\n"
       "Ollama, so the settings still come out right.",
 "ko": "로컬 AI 모델을 고르세요. 처음 쓸 때 다운로드됩니다.\n\n"
       "  gemma4:12b            7.6GB   VRAM 12GB↑\n"
       "  gemma4:26b-a4b-it-qat  16GB   VRAM 24GB↑   더 똑똑하지만 훨씬 큽니다\n\n"
       "고르지 않으셔도 됩니다. 그냥 두면 그래픽카드에 들어가는 가장 좋은 모델을\n"
       "알아서 고르고, 한 번에 읽는 양도 카드에 맞춰 정합니다 — 24GB 카드는\n"
       "26b 가 자동으로 선택됩니다. 여기서 한 번 고르시면 그 선택을 지키고\n"
       "다시 바꾸지 않습니다.\n\n"
       "12GB 미만은 로컬을 쓸 수 없습니다. 모델만으로도 카드보다 크기 때문입니다.\n"
       "제미나이나 Claude 를 쓰세요.\n\n"
       "목록에 없는 이름을 직접 적어도 됩니다 — 크기는 Ollama 에게 물어보므로\n"
       "설정은 그대로 맞게 잡힙니다.",
 "ja": "ローカルAIモデルを選択。初回使用時にダウンロードされます。\n\n"
       "  gemma4:12b            7.6GB   VRAM 12GB↑\n"
       "  gemma4:26b-a4b-it-qat  16GB   VRAM 24GB↑   賢いがはるかに大きい\n\n"
       "選ばなくても構いません。そのままにすると、グラフィックカードに収まる中で\n"
       "最も良いモデルを自動で選び、一度に読む量もカードに合わせます\n"
       "（24GB カードなら 26b が自動選択）。ここで一度選ぶとその選択を維持します。\n\n"
       "12GB 未満ではローカルを使えません。モデルだけでカードより大きいためです。",
 "zh": "选择本地 AI 模型。首次使用时下载。\n\n"
       "  gemma4:12b            7.6GB   显存 12GB↑\n"
       "  gemma4:26b-a4b-it-qat  16GB   显存 24GB↑   更聪明但大得多\n\n"
       "你可以不选。保持不动时，程序会自动挑选显卡装得下的最好模型，\n"
       "并按显卡决定一次读取的量（24GB 显卡会自动选 26b）。\n"
       "一旦你在这里选择，就会保留你的选择，不再自动更改。\n\n"
       "低于 12GB 无法使用本地引擎：仅模型就超过显卡容量。",
 "fr": "Choisissez le modèle local. Téléchargé à la première utilisation.\n\n"
       "  gemma4:12b            7,6 Go   VRAM 12 Go+\n"
       "  gemma4:26b-a4b-it-qat  16 Go   VRAM 24 Go+   plus intelligent, bien plus gros\n\n"
       "Vous n'êtes pas obligé de choisir. Sans intervention, JQSubtitle prend le meilleur\n"
       "modèle que votre carte peut contenir et règle la quantité lue d'un coup —\n"
       "une carte de 24 Go reçoit le 26b automatiquement. Un choix fait ici est conservé.\n\n"
       "En dessous de 12 Go, le moteur local est refusé : le modèle seul dépasse la carte.",
 "pt": "Escolha o modelo local. Baixado no primeiro uso.\n\n"
       "  gemma4:12b            7,6 GB   VRAM 12 GB+\n"
       "  gemma4:26b-a4b-it-qat  16 GB   VRAM 24 GB+   mais inteligente, bem maior\n\n"
       "Você não precisa escolher. Sem intervenção, o JQSubtitle pega o melhor modelo que\n"
       "cabe na sua placa e ajusta quanto lê de uma vez — uma placa de 24 GB recebe o 26b\n"
       "automaticamente. Uma escolha feita aqui é mantida.\n\n"
       "Abaixo de 12 GB o motor local é recusado: só o modelo já excede a placa.",
 "es": "Elige el modelo local. Se descarga en el primer uso.\n\n"
       "  gemma4:12b            7,6 GB   VRAM 12 GB+\n"
       "  gemma4:26b-a4b-it-qat  16 GB   VRAM 24 GB+   más inteligente, mucho más grande\n\n"
       "No hace falta elegir. Si no tocas nada, JQSubtitle toma el mejor modelo que quepa\n"
       "en tu tarjeta y ajusta cuánto lee de una vez — una tarjeta de 24 GB recibe el 26b\n"
       "automáticamente. Si eliges aquí, se respeta tu elección.\n\n"
       "Por debajo de 12 GB se rechaza el motor local: solo el modelo supera la tarjeta."}
})


# ---- v1.3: 묶음 처리 / VRAM 경고 ----
I18N.update({
"log_chunk": {
 "en": "  [{l}] block {c} ({t} lines)...",
 "ko": "  [{l}] 묶음 {c} ({t}줄)...",
 "ja": "  [{l}] ブロック {c}（{t}行）...",
 "zh": "  [{l}] 分块 {c}（{t} 行）...",
 "fr": "  [{l}] bloc {c} ({t} lignes)...",
 "pt": "  [{l}] bloco {c} ({t} linhas)...",
 "es": "  [{l}] bloque {c} ({t} líneas)..."},
"log_chunk_misaligned": {
 "en": "  [{l}] block {c}: the reply does not line up with the source ({w}) - discarded, retrying",
 "ko": "  [{l}] 묶음 {c}: 응답이 원문과 어긋납니다 ({w}) — 버리고 다시 시도합니다",
 "ja": "  [{l}] ブロック {c}: 応答が原文とずれています（{w}）— 破棄して再試行",
 "zh": "  [{l}] 块 {c}：回复与原文错位（{w}）— 丢弃并重试",
 "fr": "  [{l}] bloc {c} : la réponse ne correspond pas à la source ({w}) - rejetée, nouvelle tentative",
 "pt": "  [{l}] bloco {c}: a resposta não corresponde à fonte ({w}) - descartada, tentando de novo",
 "es": "  [{l}] bloque {c}: la respuesta no cuadra con el original ({w}) - descartada, reintentando"},
"bad_renumber": {
 "en": "renumbered 1-{n} for {t} lines", "ko": "{t}줄인데 1~{n}로 다시 매김",
 "ja": "{t}行なのに1~{n}に振り直し", "zh": "共 {t} 行却重新编号为 1~{n}",
 "fr": "renumérotée 1-{n} pour {t} lignes", "pt": "renumerada 1-{n} para {t} linhas",
 "es": "renumerada 1-{n} para {t} líneas"},
"bad_shift": {
 "en": "lines shifted", "ko": "줄이 밀림", "ja": "行がずれている", "zh": "行错位",
 "fr": "lignes décalées", "pt": "linhas deslocadas", "es": "líneas desplazadas"},
"log_chunk_retry": {
 "en": "  [{l}] block {c}: only {n}/{t} lines — retrying (attempt {a})",
 "ko": "  [{l}] 묶음 {c}: {t}줄 중 {n}줄만 옴 — 다시 시도 ({a}회차)",
 "ja": "  [{l}] ブロック {c}: {t}行中 {n}行のみ — 再試行（{a}回目）",
 "zh": "  [{l}] 分块 {c}：{t} 行中仅 {n} 行 — 重试（第 {a} 次）",
 "fr": "  [{l}] bloc {c} : {n}/{t} lignes — nouvelle tentative ({a})",
 "pt": "  [{l}] bloco {c}: {n}/{t} linhas — tentando de novo ({a})",
 "es": "  [{l}] bloque {c}: {n}/{t} líneas — reintentando ({a})"},
"log_chunk_retry_ok": {
 "en": "  [{l}] block {c}: recovered on attempt {a}",
 "ko": "  [{l}] 묶음 {c}: {a}회차에 성공",
 "ja": "  [{l}] ブロック {c}: {a}回目で成功",
 "zh": "  [{l}] 分块 {c}：第 {a} 次成功",
 "fr": "  [{l}] bloc {c} : réussi à la tentative {a}",
 "pt": "  [{l}] bloco {c}: recuperado na tentativa {a}",
 "es": "  [{l}] bloque {c}: recuperado en el intento {a}"},
"log_chunk_partial": {
 "en": "  [{l}] block {c}: keeping {n}/{t} lines, rest will be retried later",
 "ko": "  [{l}] 묶음 {c}: {t}줄 중 {n}줄 확보, 나머지는 뒤에서 보충",
 "ja": "  [{l}] ブロック {c}: {t}行中 {n}行を確保、残りは後で補完",
 "zh": "  [{l}] 分块 {c}：保留 {t} 行中的 {n} 行，其余稍后补充",
 "fr": "  [{l}] bloc {c} : {n}/{t} lignes gardées, le reste plus tard",
 "pt": "  [{l}] bloco {c}: {n}/{t} linhas mantidas, resto depois",
 "es": "  [{l}] bloque {c}: {n}/{t} líneas guardadas, el resto después"},
"log_gap": {
 "en": "  [{l}] filling {n} missing line(s) — round {r}...",
 "ko": "  [{l}] 빠진 {n}줄 보충 중 — {r}바퀴...",
 "ja": "  [{l}] 欠落 {n}行を補完中 — {r}周目...",
 "zh": "  [{l}] 补充缺失的 {n} 行 — 第 {r} 轮...",
 "fr": "  [{l}] complément de {n} ligne(s) — tour {r}...",
 "pt": "  [{l}] preenchendo {n} linha(s) — rodada {r}...",
 "es": "  [{l}] completando {n} línea(s) — ronda {r}..."},
"log_pace": {
 "en": "  waiting {s}s to stay under the {p} rate limit...",
 "ko": "  {p} 분당 한도를 지키려고 {s}초 대기 중...",
 "ja": "  {p} のレート制限を守るため {s}秒待機中...",
 "zh": "  为遵守 {p} 速率限制，等待 {s} 秒...",
 "fr": "  attente de {s}s pour respecter la limite {p}...",
 "pt": "  aguardando {s}s para respeitar o limite do {p}...",
 "es": "  esperando {s}s para respetar el límite de {p}..."},
"log_extra_stage": {
 "en": "=== Targeted fixes ===",
 "ko": "=== 콕 집어 고치기 ===",
 "ja": "=== 追加リクエストを反映中 ===",
 "zh": "=== 正在应用您的额外要求 ===",
 "fr": "=== Application de votre demande supplémentaire ===",
 "pt": "=== Aplicando seu pedido extra ===",
 "es": "=== Aplicando tu petición adicional ==="},
"log_extra_call": {
 "en": "  showing the AI all {n} subtitles and your request...",
 "ko": "  자막 {n}줄 전부와 요청을 보여줍니다...",
 "ja": "  字幕 {n}行とリクエストを送信します...",
 "zh": "  正在发送 {n} 行字幕与您的要求...",
 "fr": "  envoi de {n} sous-titres avec votre demande...",
 "pt": "  enviando {n} legendas com seu pedido...",
 "es": "  enviando {n} subtítulos con tu petición..."},
"log_extra_done": {
 "en": "  done — {a} subtitles in, {b} out",
 "ko": "  완료 — 자막 {a}줄 -> {b}줄",
 "ja": "  完了 — 字幕 {a}行が {b}行になりました",
 "zh": "  完成 — {a} 行字幕整理为 {b} 行",
 "fr": "  terminé — {a} sous-titres retravaillés en {b}",
 "pt": "  concluído — {a} legendas reorganizadas em {b}",
 "es": "  listo — {a} subtítulos reorganizados en {b}"},
"log_extra_retry": {
 "en": "  Targeted fixes: {w} — asking again (attempt {a})",
 "ko": "  콕 집어 고치기: {w} — 다시 물어봅니다 (시도 {a})",
 "ja": "  追加リクエスト: {w} — もう一度尋ねます（試行 {a}）",
 "zh": "  额外请求：{w} — 重新询问（第 {a} 次）",
 "fr": "  Requête supplémentaire : {w} — nouvelle demande (tentative {a})",
 "pt": "  Pedido extra: {w} — perguntando de novo (tentativa {a})",
 "es": "  Petición extra: {w} — preguntando de nuevo (intento {a})"},
"log_extra_retry_ok": {
 "en": "  Targeted fixes: usable reply on attempt {a}",
 "ko": "  콕 집어 고치기: {a}번째 시도에서 제대로 된 응답을 받았습니다",
 "ja": "  追加リクエスト: {a} 回目で完全な応答を受け取りました",
 "zh": "  额外请求：第 {a} 次收到完整回复",
 "fr": "  Requête supplémentaire : réponse complète à la tentative {a}",
 "pt": "  Pedido extra: resposta completa na tentativa {a}",
 "es": "  Petición extra: respuesta completa en el intento {a}"},
"err_vram_small": {
 "en": "Graphics card {v} is too small for {m}: the model alone needs {s}, and about {n} "
       "is required once the display is counted. Choose a smaller model, or use Gemini or Claude.",
 "ko": "그래픽카드 {v} 로는 {m} 을(를) 돌릴 수 없습니다. 모델만 {s} 이고, 화면 표시분까지 "
       "더하면 약 {n} 이 필요합니다. 더 작은 모델을 고르거나 제미나이·Claude 를 쓰세요.",
 "ja": "グラフィックカード {v} では {m} を動かせません。モデルだけで {s}、画面表示分を"
       "含めると約 {n} 必要です。小さいモデルを選ぶか、Gemini・Claude をお使いください。",
 "zh": "显卡 {v} 无法运行 {m}：模型本身需要 {s}，加上显示占用约需 {n}。"
       "请选择更小的模型，或改用 Gemini / Claude。",
 "fr": "La carte {v} est trop petite pour {m} : le modèle seul demande {s}, et environ {n} "
       "en comptant l'affichage. Choisissez un modèle plus petit, ou utilisez Gemini ou Claude.",
 "pt": "A placa {v} é pequena demais para {m}: só o modelo precisa de {s}, e cerca de {n} "
       "contando o vídeo. Escolha um modelo menor, ou use Gemini ou Claude.",
 "es": "La tarjeta {v} es demasiado pequeña para {m}: el modelo solo necesita {s}, y unos {n} "
       "contando la pantalla. Elige un modelo más pequeño, o usa Gemini o Claude."},
"log_extra_edits": {
 "en": "  {c} changed · {d} deleted · {i} added{s}",
 "ko": "  {c}줄 고침 · {d}줄 지움 · {i}줄 넣음{s}",
 "ja": "  {c}行修正 · {d}行削除 · {i}行追加{s}",
 "zh": "  修改 {c} 行 · 删除 {d} 行 · 新增 {i} 行{s}",
 "fr": "  {c} modifiée(s) · {d} supprimée(s) · {i} ajoutée(s){s}",
 "pt": "  {c} alterada(s) · {d} removida(s) · {i} adicionada(s){s}",
 "es": "  {c} cambiada(s) · {d} borrada(s) · {i} añadida(s){s}"},
"log_extra_skipped": {
 "en": "{n} edit(s) ignored (line number out of range)",
 "ko": "{n}개는 무시했습니다 (없는 줄 번호)",
 "ja": "{n} 件は無視しました（存在しない行番号）",
 "zh": "忽略 {n} 处（行号不存在）",
 "fr": "{n} ignorée(s) (numéro de ligne inexistant)",
 "pt": "{n} ignorada(s) (número de linha inexistente)",
 "es": "{n} ignorada(s) (número de línea inexistente)"},
"log_extra_none": {
 "en": "  the AI found nothing to change",
 "ko": "  AI 가 고칠 것이 없다고 했습니다",
 "ja": "  AI は変更点がないと答えました",
 "zh": "  AI 认为无需更改",
 "fr": "  l'IA n'a rien trouvé à changer",
 "pt": "  a IA não encontrou nada para mudar",
 "es": "  la IA no encontró nada que cambiar"},
"extra_bad_format": {
 "en": "the reply was not in the expected form ({n} unreadable line(s), {c} chars)",
 "ko": "응답이 정해진 형식이 아닙니다 (못 읽은 줄 {n}개, {c}자)",
 "ja": "応答が所定の形式ではありません（読めない行 {n}、{c} 文字）",
 "zh": "回复格式不符（无法读取 {n} 行，共 {c} 字）",
 "fr": "la réponse n'a pas la forme attendue ({n} ligne(s) illisible(s), {c} caractères)",
 "pt": "a resposta não veio no formato esperado ({n} linha(s) ilegível(is), {c} caracteres)",
 "es": "la respuesta no tiene el formato esperado ({n} línea(s) ilegible(s), {c} caracteres)"},
"log_extra_split": {
 "en": "  {n} subtitles at a time is too many — sending {s} at a time, in {n} parts",
 "ko": "  한 번에 보내기엔 많습니다 — {s}줄씩 {n}개로 나눠 보냅니다",
 "ja": "  一度に送るには多すぎます — {s} 行ずつ {n} 個に分けて送ります",
 "zh": "  一次发送过多 — 每次 {s} 行，分 {n} 份发送",
 "fr": "  trop de sous-titres d'un coup — envoi par {s}, en {n} parties",
 "pt": "  legendas demais de uma vez — enviando {s} por vez, em {n} partes",
 "es": "  demasiados subtítulos de una vez — enviando {s} cada vez, en {n} partes"},
"log_extra_part": {
 "en": "  part {i}/{n} ({a} subtitles)...",
 "ko": "  {i}/{n}번째 묶음 (자막 {a}줄)...",
 "ja": "  {i}/{n} 番目（字幕 {a} 行）...",
 "zh": "  第 {i}/{n} 份（字幕 {a} 行）...",
 "fr": "  partie {i}/{n} ({a} sous-titres)...",
 "pt": "  parte {i}/{n} ({a} legendas)...",
 "es": "  parte {i}/{n} ({a} subtítulos)..."},
"log_extra_part_fail": {
 "en": "  part {i}/{n} failed — those subtitles were left as they were: {e}",
 "ko": "  {i}/{n}번째 묶음 실패 — 그 구간 자막은 원래대로 뒀습니다: {e}",
 "ja": "  {i}/{n} 番目が失敗 — その区間はそのままにしました: {e}",
 "zh": "  第 {i}/{n} 份失败 — 该区间字幕保持原样：{e}",
 "fr": "  partie {i}/{n} échouée — ces sous-titres sont restés inchangés : {e}",
 "pt": "  parte {i}/{n} falhou — essas legendas ficaram como estavam: {e}",
 "es": "  parte {i}/{n} falló — esos subtítulos quedaron como estaban: {e}"},
"log_extra_part_kept": {
 "en": "  {n} of {t} parts could not be reworked and were kept as they were",
 "ko": "  {t}개 묶음 중 {n}개는 손대지 못하고 원래대로 뒀습니다",
 "ja": "  {t} 個中 {n} 個は手を加えられず、そのままです",
 "zh": "  {t} 份中有 {n} 份未能处理，保持原样",
 "fr": "  {n} parties sur {t} n'ont pas pu être retravaillées et sont inchangées",
 "pt": "  {n} de {t} partes não puderam ser refeitas e ficaram como estavam",
 "es": "  {n} de {t} partes no pudieron rehacerse y quedaron como estaban"},
"log_extra_big": {
 "en": "  ⚠ this looks larger than the local AI can read at once "
       "(about {e} vs a limit of {c}) — trying anyway",
 "ko": "  ⚠ 로컬 AI가 한 번에 읽을 수 있는 양을 넘을 것 같습니다 "
       "(약 {e}칸 / 한도 {c}칸) — 그래도 시도합니다",
 "ja": "  ⚠ ローカルAIが一度に読める量を超えそうです（約{e} / 上限{c}）— それでも試します",
 "zh": "  ⚠ 可能超出本地 AI 单次可读取的量（约 {e} / 上限 {c}）— 仍会尝试",
 "fr": "  ⚠ semble dépasser ce que l'IA locale peut lire d'un coup "
       "(environ {e} contre une limite de {c}) — tentative quand même",
 "pt": "  ⚠ parece maior do que a IA local consegue ler de uma vez "
       "(cerca de {e} contra um limite de {c}) — tentando mesmo assim",
 "es": "  ⚠ parece mayor de lo que la IA local puede leer de una vez "
       "(unos {e} frente a un límite de {c}) — se intenta igualmente"},
"log_extra_fail": {
 "en": "  Targeted fixes failed: {e}",
 "ko": "  콕 집어 고치기 실패: {e}",
 "ja": "  追加リクエスト失敗: {e}",
 "zh": "  额外要求失败：{e}",
 "fr": "  Demande supplémentaire échouée : {e}",
 "pt": "  Pedido extra falhou: {e}",
 "es": "  La petición adicional falló: {e}"},
"log_extra_kept": {
 "en": "  Subtitles were saved as they were before this step.",
 "ko": "  자막은 이 단계 이전 상태로 저장했습니다.",
 "ja": "  字幕はこの段階の前の状態で保存しました。",
 "zh": "  字幕已按此步骤之前的状态保存。",
 "fr": "  Les sous-titres ont été enregistrés tels qu'avant cette étape.",
 "pt": "  As legendas foram salvas como estavam antes desta etapa.",
 "es": "  Los subtítulos se guardaron tal como estaban antes de este paso."},
"log_extra_stop": {
 "en": "  Skipping translation — translating subtitles that ignored your request "
       "would not be useful.",
 "ko": "  번역을 건너뜁니다 — 요청이 반영되지 않은 자막을 번역해도 의미가 없습니다.",
 "ja": "  翻訳をスキップします — リクエストが反映されていない字幕を翻訳しても意味がありません。",
 "zh": "  跳过翻译 — 翻译未反映您要求的字幕没有意义。",
 "fr": "  Traduction ignorée — traduire des sous-titres qui n'ont pas suivi votre demande "
       "n'aurait pas d'intérêt.",
 "pt": "  Pulando a tradução — traduzir legendas que ignoraram seu pedido não seria útil.",
 "es": "  Se omite la traducción — traducir subtítulos que ignoraron tu petición no serviría."},
"err_extra_short": {
 "en": "targeted fixes failed", "ko": "콕 집어 고치기 실패", "ja": "追加リクエスト失敗",
 "zh": "额外要求失败", "fr": "demande supplémentaire échouée",
 "pt": "pedido extra falhou", "es": "petición adicional fallida"},
"hint_extra_fail": {
 "en": "   → Shorten the request, switch to Gemini or Claude, or try a shorter video.\n"
       "     The subtitles from before this step were still saved.",
 "ko": "   → 요청을 줄이거나, Gemini·Claude로 바꾸거나, 짧은 영상으로 시도해 보세요.\n"
       "     이 단계 이전의 자막은 저장되어 있습니다.",
 "ja": "   → リクエストを短くするか、Gemini・Claudeに変えるか、短い動画で試してください。\n"
       "     この段階より前の字幕は保存されています。",
 "zh": "   → 请缩短要求、改用 Gemini/Claude，或换用较短的视频。\n"
       "     此步骤之前的字幕已保存。",
 "fr": "   → Raccourcissez la demande, passez à Gemini ou Claude, ou essayez une vidéo plus courte.\n"
       "     Les sous-titres d'avant cette étape ont bien été enregistrés.",
 "pt": "   → Encurte o pedido, mude para Gemini ou Claude, ou tente um vídeo mais curto.\n"
       "     As legendas anteriores a esta etapa foram salvas.",
 "es": "   → Acorta la petición, cambia a Gemini o Claude, o prueba con un vídeo más corto.\n"
       "     Los subtítulos previos a este paso sí se guardaron."},
"log_think_retry": {
 "en": "  {m} rejected the '{k}' thinking setting — trying another",
 "ko": "  {m} 이(가) '{k}' 사고 설정을 거부했습니다 — 다른 방식으로 시도",
 "ja": "  {m} が '{k}' の思考設定を拒否 — 別の方式で再試行",
 "zh": "  {m} 拒绝了「{k}」思考设置 — 改用其他方式",
 "fr": "  {m} a refusé le réglage de réflexion « {k} » — essai d'un autre",
 "pt": "  {m} recusou a configuração de pensamento \"{k}\" — tentando outra",
 "es": "  {m} rechazó el ajuste de pensamiento «{k}» — probando otro"},
"log_think_mode": {
 "en": "  {m} accepts the '{k}' thinking setting — remembered",
 "ko": "  {m} 은(는) '{k}' 사고 설정을 받습니다 — 기억해 둡니다",
 "ja": "  {m} は '{k}' の思考設定を受け付けます — 記憶しました",
 "zh": "  {m} 接受「{k}」思考设置 — 已记住",
 "fr": "  {m} accepte le réglage « {k} » — mémorisé",
 "pt": "  {m} aceita a configuração \"{k}\" — memorizada",
 "es": "  {m} acepta el ajuste «{k}» — recordado"},
"log_rebuild_retry": {
 "en": "  Block {c}: reply failed validation ({r}) — retrying (attempt {a})",
 "ko": "  묶음 {c}: 응답 검증 실패 ({r}) — 다시 시도 ({a}회차)",
 "ja": "  ブロック {c}: 応答の検証に失敗 ({r}) — 再試行（{a}回目）",
 "zh": "  分块 {c}：响应校验失败（{r}）— 重试（第 {a} 次）",
 "fr": "  Bloc {c} : réponse invalide ({r}) — nouvelle tentative ({a})",
 "pt": "  Bloco {c}: resposta inválida ({r}) — tentando de novo ({a})",
 "es": "  Bloque {c}: respuesta inválida ({r}) — reintentando ({a})"},
"log_rebuild_mend": {
 "en": "  Block {c}: closed {n} small gap(s) in the AI's ranges and kept the result",
 "ko": "  {c}번 묶음: AI 가 낸 구간의 빈틈 {n}칸을 메워서 살렸습니다",
 "ja": "  ブロック {c}: AI の区間の隙間 {n} 個を埋めて採用しました",
 "zh": "  第 {c} 块：补上了 AI 区间中的 {n} 处小缺口并采用",
 "fr": "  Bloc {c} : {n} petit(s) trou(s) comblé(s) dans les plages de l'IA, résultat conservé",
 "pt": "  Bloco {c}: {n} pequena(s) falha(s) preenchida(s) nos intervalos da IA, resultado mantido",
 "es": "  Bloque {c}: se rellenaron {n} hueco(s) pequeño(s) en los rangos de la IA y se conservó"},
"log_rebuild_retry_ok": {
 "en": "  Block {c}: recovered on attempt {a}",
 "ko": "  묶음 {c}: {a}회차에 성공",
 "ja": "  ブロック {c}: {a}回目で成功",
 "zh": "  分块 {c}：第 {a} 次成功",
 "fr": "  Bloc {c} : réussi à la tentative {a}",
 "pt": "  Bloco {c}: recuperado na tentativa {a}",
 "es": "  Bloque {c}: recuperado en el intento {a}"},
"log_model_retired": {
 "en": "  ! {m} has been retired by Google — replacement: {n}",
 "ko": "  ! {m} 은(는) 구글이 서비스를 종료한 모델입니다 — 대체 모델: {n}",
 "ja": "  ! {m} はGoogleが提供終了したモデルです — 代替: {n}",
 "zh": "  ! {m} 已被 Google 停用 — 替代模型：{n}",
 "fr": "  ! {m} a été retiré par Google — remplacement : {n}",
 "pt": "  ! {m} foi descontinuado pelo Google — substituto: {n}",
 "es": "  ! {m} fue retirado por Google — reemplazo: {n}"},
"log_model_unknown": {
 "en": "(not stated)", "ko": "(안내 없음)", "ja": "(記載なし)", "zh": "（未说明）",
 "fr": "(non précisé)", "pt": "(não informado)", "es": "(no indicado)"},
"log_engine_switch": {
 "en": "  model busy or limited — switching to {m}",
 "ko": "  모델이 붐비거나 한도에 걸림 — {m} 으로 전환",
 "ja": "  モデルが混雑/制限中 — {m} に切り替え",
 "zh": "  模型繁忙或受限 — 切换到 {m}",
 "fr": "  modèle occupé ou limité — passage à {m}",
 "pt": "  modelo ocupado ou limitado — mudando para {m}",
 "es": "  modelo ocupado o limitado — cambiando a {m}"},
"quota_daily": {
 "en": "daily", "ko": "일일", "ja": "1日", "zh": "每日",
 "fr": "quotidien", "pt": "diário", "es": "diario"},
"quota_minute": {
 "en": "per-minute", "ko": "분당", "ja": "毎分", "zh": "每分钟",
 "fr": "par minute", "pt": "por minuto", "es": "por minuto"},
"stage_rebuild": {
 "en": "Rebuild", "ko": "재조립", "ja": "再構成", "zh": "重组",
 "fr": "Reconstruction", "pt": "Remontagem", "es": "Reconstrucción"},
"tag_gap": {
 "en": "fill{r}", "ko": "보충{r}", "ja": "補完{r}", "zh": "补充{r}",
 "fr": "compl{r}", "pt": "compl{r}", "es": "compl{r}"},
"log_quota_hit": {
 "en": "  [{l}] {c}: API {k} quota reached",
 "ko": "  [{l}] {c}: API {k} 한도에 걸렸습니다",
 "ja": "  [{l}] {c}: API {k}制限に達しました",
 "zh": "  [{l}] {c}：已达 API {k}配额",
 "fr": "  [{l}] {c} : quota {k} de l'API atteint",
 "pt": "  [{l}] {c}: cota {k} da API atingida",
 "es": "  [{l}] {c}: cuota {k} de la API alcanzada"},
"log_quota_abort": {
 "en": "  [{l}] API quota exhausted — stopping this stage instead of retrying.\n"
       "     Retrying now would fail every time. Try again later, or switch to Local AI.",
 "ko": "  [{l}] API 한도가 소진되어 이 단계를 중단합니다.\n"
       "     지금 다시 시도해도 계속 실패합니다. 나중에 다시 하시거나 로컬 AI로 바꾸세요.",
 "ja": "  [{l}] APIの割り当てを使い切ったため、この段階を中止します。\n"
       "     今再試行しても失敗し続けます。後で試すかローカルAIに切り替えてください。",
 "zh": "  [{l}] API 配额已用尽，中止此阶段。\n"
       "     现在重试只会持续失败。请稍后再试或改用本地 AI。",
 "fr": "  [{l}] Quota API épuisé — arrêt de cette étape.\n"
       "     Réessayer maintenant échouerait à chaque fois. Réessayez plus tard ou passez à l'IA locale.",
 "pt": "  [{l}] Cota da API esgotada — interrompendo esta etapa.\n"
       "     Tentar agora falharia sempre. Tente mais tarde ou mude para IA local.",
 "es": "  [{l}] Cuota de API agotada — se detiene esta etapa.\n"
       "     Reintentar ahora fallaría siempre. Inténtalo más tarde o cambia a IA local."},
"log_still_missing": {
 "en": "  [{l}] {n} line(s) could not be translated — original kept",
 "ko": "  [{l}] {n}줄은 끝내 번역하지 못했습니다 — 원문 유지",
 "ja": "  [{l}] {n}行は翻訳できませんでした — 原文維持",
 "zh": "  [{l}] {n} 行未能翻译 — 保留原文",
 "fr": "  [{l}] {n} ligne(s) non traduites — original conservé",
 "pt": "  [{l}] {n} linha(s) não traduzidas — original mantido",
 "es": "  [{l}] {n} línea(s) sin traducir — se mantiene el original"},
"log_chunk_fail": {
 "en": "  [{l}] block {c} failed — kept as-is: {e}",
 "ko": "  [{l}] 묶음 {c} 실패 — 원문 유지: {e}",
 "ja": "  [{l}] ブロック {c} 失敗 — 原文維持: {e}",
 "zh": "  [{l}] 分块 {c} 失败 — 保留原文：{e}",
 "fr": "  [{l}] bloc {c} échoué — conservé tel quel : {e}",
 "pt": "  [{l}] bloco {c} falhou — mantido como está: {e}",
 "es": "  [{l}] bloque {c} falló — se mantiene igual: {e}"},
"log_chunk_reject": {
 "en": "  [{l}] block {c} rejected — only {n} of {t} lines came back (format broken)",
 "ko": "  [{l}] 묶음 {c} 거부 — {t}줄 중 {n}줄만 돌아옴 (형식 깨짐)",
 "ja": "  [{l}] ブロック {c} 却下 — {t}行中 {n}行のみ（形式が崩れた）",
 "zh": "  [{l}] 分块 {c} 拒绝 — {t} 行中仅返回 {n} 行（格式损坏）",
 "fr": "  [{l}] bloc {c} rejeté — seulement {n} lignes sur {t} (format cassé)",
 "pt": "  [{l}] bloco {c} rejeitado — só {n} de {t} linhas (formato quebrado)",
 "es": "  [{l}] bloque {c} rechazado — solo {n} de {t} líneas (formato roto)"},
"log_chunk_sum": {
 "en": "  [{l}] {ok} of {n} lines done",
 "ko": "  [{l}] {n}줄 중 {ok}줄 완료",
 "ja": "  [{l}] {n}行中 {ok}行完了",
 "zh": "  [{l}] {n} 行中完成 {ok} 行",
 "fr": "  [{l}] {ok} lignes sur {n} traitées",
 "pt": "  [{l}] {ok} de {n} linhas concluídas",
 "es": "  [{l}] {ok} de {n} líneas completadas"},
"log_tr_dead": {
 "en": "Translation produced nothing usable — no file written for this language.",
 "ko": "번역에서 쓸 만한 결과가 하나도 나오지 않았습니다 — 이 언어는 파일을 만들지 않습니다.",
 "ja": "翻訳から使える結果が得られませんでした — この言語のファイルは作成しません。",
 "zh": "翻译没有产生可用结果 — 不会为该语言生成文件。",
 "fr": "La traduction n'a rien donné d'utilisable — aucun fichier créé pour cette langue.",
 "pt": "A tradução não produziu nada utilizável — nenhum arquivo criado para este idioma.",
 "es": "La traducción no produjo nada utilizable — no se creó archivo para este idioma."},
"log_vram_spill": {
 "en": "\n⚠ {p}% of the model did not fit on the GPU and moved to system RAM.\n"
       "  Expect this to run 3-5x slower ({m}, {v} of {t} on GPU).\n",
 "ko": "\n⚠ 모델의 {p}%가 그래픽카드에 들어가지 못해 본체 메모리로 넘어갔습니다.\n"
       "  작업이 3~5배 느려집니다 ({m}, GPU에 {t} 중 {v}).\n",
 "ja": "\n⚠ モデルの{p}%がGPUに収まらずRAMへ退避しました。\n"
       "  3~5倍遅くなります（{m}、GPU上 {t} 中 {v}）。\n",
 "zh": "\n⚠ 模型有 {p}% 未能装入显卡，已转到内存。\n"
       "  速度将下降 3~5 倍（{m}，显存中 {v}/{t}）。\n",
 "fr": "\n⚠ {p}% du modèle n'est pas entré dans le GPU et est passé en RAM.\n"
       "  Ce sera 3-5x plus lent ({m}, {v} sur {t} en GPU).\n",
 "pt": "\n⚠ {p}% do modelo não coube na GPU e foi para a RAM.\n"
       "  Vai ficar 3-5x mais lento ({m}, {v} de {t} na GPU).\n",
 "es": "\n⚠ El {p}% del modelo no cupo en la GPU y pasó a la RAM.\n"
       "  Será 3-5x más lento ({m}, {v} de {t} en GPU).\n"},
"st_vram": {
 "en": "⚠ GPU short by {p}% — running slow",
 "ko": "⚠ GPU 메모리 {p}% 부족 — 느리게 진행 중",
 "ja": "⚠ GPUメモリ {p}% 不足 — 低速で進行中",
 "zh": "⚠ 显存不足 {p}% — 正在低速运行",
 "fr": "⚠ GPU insuffisant de {p}% — exécution lente",
 "pt": "⚠ GPU {p}% insuficiente — execução lenta",
 "es": "⚠ GPU {p}% insuficiente — ejecución lenta"},
"st_cancelling": {
 "en": "Stopping...", "ko": "멈추는 중...", "ja": "停止中...", "zh": "正在停止...",
 "fr": "Arrêt...", "pt": "Parando...", "es": "Deteniendo..."},
"log_cancelling": {
 "en": "\nStopping — finishing the current step...\n",
 "ko": "\n멈추는 중 — 진행 중인 단계를 정리합니다...\n",
 "ja": "\n停止中 — 現在の処理を終了しています...\n",
 "zh": "\n正在停止 — 结束当前步骤...\n",
 "fr": "\nArrêt — fin de l'étape en cours...\n",
 "pt": "\nParando — finalizando a etapa atual...\n",
 "es": "\nDeteniendo — terminando el paso actual...\n"},
"vram_title": {
 "en": "Not enough GPU memory", "ko": "그래픽카드 메모리 부족",
 "ja": "GPUメモリ不足", "zh": "显存不足",
 "fr": "Mémoire GPU insuffisante", "pt": "Memória de GPU insuficiente",
 "es": "Memoria de GPU insuficiente"},
"vram_msg": {
 "en": "{p}% of the model ({m}) did not fit on your graphics card and was\n"
       "moved to system RAM. It still works, but roughly 3-5x slower.\n\n"
       "What you can do:\n"
       "  • Close other programs using the GPU (games, browsers, video apps)\n"
       "  • Settings -> Local AI model: pick a smaller model\n"
       "  • Use a free Gemini API key instead — much faster than local AI\n\n"
       "This message is shown once per run.",
 "ko": "모델({m})의 {p}%가 그래픽카드에 들어가지 못해 본체 메모리로\n"
       "넘어갔습니다. 작동은 하지만 3~5배 느려집니다.\n\n"
       "해결 방법:\n"
       "  • GPU를 쓰는 다른 프로그램을 닫으세요 (게임, 브라우저, 영상 프로그램)\n"
       "  • 설정 → 로컬 AI 모델에서 더 작은 모델을 고르세요\n"
       "  • 무료 Gemini API 키를 쓰세요 — 로컬 AI보다 훨씬 빠릅니다\n\n"
       "이 안내는 실행당 한 번만 표시됩니다.",
 "ja": "モデル（{m}）の{p}%がGPUに収まらずRAMへ退避しました。\n"
       "動作はしますが3~5倍遅くなります。\n\n"
       "対処:\n"
       "  • GPUを使う他のアプリを閉じる\n"
       "  • 設定 → ローカルAIモデルで小さいモデルを選ぶ\n"
       "  • 無料のGemini APIキーを使う（ローカルより大幅に高速）\n\n"
       "この案内は実行ごとに一度だけ表示されます。",
 "zh": "模型（{m}）有 {p}% 未装入显卡，已转到内存。\n"
       "仍可运行，但速度下降约 3~5 倍。\n\n"
       "解决方法:\n"
       "  • 关闭其他占用显存的程序（游戏、浏览器、视频软件）\n"
       "  • 设置 → 本地 AI 模型：选择更小的模型\n"
       "  • 改用免费 Gemini API 密钥 — 比本地 AI 快得多\n\n"
       "此提示每次运行只显示一次。",
 "fr": "{p}% du modèle ({m}) n'est pas entré dans la carte graphique et est\n"
       "passé en RAM. Cela fonctionne, mais 3-5x plus lentement.\n\n"
       "Solutions :\n"
       "  • Fermez les autres programmes utilisant le GPU\n"
       "  • Paramètres -> Modèle IA locale : choisissez un modèle plus petit\n"
       "  • Utilisez une clé Gemini gratuite — bien plus rapide\n\n"
       "Ce message n'apparaît qu'une fois par exécution.",
 "pt": "{p}% do modelo ({m}) não coube na placa de vídeo e foi para a RAM.\n"
       "Ainda funciona, mas cerca de 3-5x mais lento.\n\n"
       "O que fazer:\n"
       "  • Feche outros programas que usam a GPU\n"
       "  • Configurações -> Modelo de IA local: escolha um modelo menor\n"
       "  • Use uma chave Gemini gratuita — muito mais rápida\n\n"
       "Esta mensagem aparece uma vez por execução.",
 "es": "El {p}% del modelo ({m}) no cupo en la tarjeta gráfica y pasó a la RAM.\n"
       "Sigue funcionando, pero unas 3-5x más lento.\n\n"
       "Qué puedes hacer:\n"
       "  • Cierra otros programas que usen la GPU\n"
       "  • Configuración -> Modelo de IA local: elige uno más pequeño\n"
       "  • Usa una clave gratuita de Gemini — mucho más rápida\n\n"
       "Este mensaje se muestra una vez por ejecución."},
})


I18N.update({
"yt_banner": {
 "en": "🎬 Kids STEM animation by the developer — {ch}",
 "ko": "🎬 제작자가 만드는 어린이 STEM 애니메이션 — {ch}",
 "ja": "🎬 開発者が作る子ども向けSTEMアニメ — {ch}",
 "zh": "🎬 开发者制作的儿童 STEM 动画 — {ch}",
 "fr": "🎬 Animation STEM pour enfants par le développeur — {ch}",
 "pt": "🎬 Animação STEM infantil do desenvolvedor — {ch}",
 "es": "🎬 Animación STEM infantil del desarrollador — {ch}"},
"yt_watch": {"en": "▶ Watch", "ko": "▶ 최신 영상", "ja": "▶ 動画を見る", "zh": "▶ 观看",
 "fr": "▶ Regarder", "pt": "▶ Assistir", "es": "▶ Ver"},
"yt_channel": {"en": "Channel", "ko": "채널 보기", "ja": "チャンネル", "zh": "频道",
 "fr": "Chaîne", "pt": "Canal", "es": "Canal"},
})


# ---- 자동 업데이트 (1.1) ----
I18N.update({
"mi_check_update": {
 "en": "Check for updates...", "ko": "업데이트 확인...", "ja": "アップデートを確認...",
 "zh": "检查更新...", "fr": "Rechercher des mises à jour...",
 "pt": "Procurar atualizações...", "es": "Buscar actualizaciones..."},
"mi_auto_update": {
 "en": "Check for updates on start", "ko": "시작할 때 업데이트 확인",
 "ja": "起動時にアップデートを確認", "zh": "启动时检查更新",
 "fr": "Vérifier les mises à jour au démarrage",
 "pt": "Procurar atualizações ao iniciar", "es": "Buscar actualizaciones al iniciar"},
"upd_title": {
 "en": "A new version is available", "ko": "새 버전이 있습니다",
 "ja": "新しいバージョンがあります", "zh": "有新版本",
 "fr": "Une nouvelle version est disponible", "pt": "Há uma nova versão disponível",
 "es": "Hay una nueva versión disponible"},
"upd_body": {
 "en": "{app} {v} is available.  (installed: {c})",
 "ko": "{app} {v} 이(가) 나왔습니다.  (현재 버전: {c})",
 "ja": "{app} {v} が公開されています。（現在: {c}）",
 "zh": "{app} {v} 已发布。（当前版本：{c}）",
 "fr": "{app} {v} est disponible.  (installée : {c})",
 "pt": "{app} {v} está disponível.  (instalada: {c})",
 "es": "{app} {v} ya está disponible.  (instalada: {c})"},
"upd_whats_new": {
 "en": "What's new", "ko": "변경 내용", "ja": "変更内容", "zh": "更新内容",
 "fr": "Nouveautés", "pt": "Novidades", "es": "Novedades"},
"upd_now": {
 "en": "Update now", "ko": "지금 업데이트", "ja": "今すぐ更新", "zh": "立即更新",
 "fr": "Mettre à jour", "pt": "Atualizar agora", "es": "Actualizar ahora"},
"upd_later": {
 "en": "Later", "ko": "나중에", "ja": "後で", "zh": "以后再说",
 "fr": "Plus tard", "pt": "Depois", "es": "Más tarde"},
"upd_skip": {
 "en": "Skip this version", "ko": "이 버전 건너뛰기", "ja": "このバージョンをスキップ",
 "zh": "跳过此版本", "fr": "Ignorer cette version", "pt": "Ignorar esta versão",
 "es": "Omitir esta versión"},
"upd_downloading": {
 "en": "Downloading and installing...", "ko": "다운로드하고 설치하는 중...",
 "ja": "ダウンロードしてインストール中...", "zh": "正在下载并安装...",
 "fr": "Téléchargement et installation...", "pt": "Baixando e instalando...",
 "es": "Descargando e instalando..."},
"upd_done": {
 "en": "Updated. {app} will restart now.",
 "ko": "업데이트 완료. {app}을(를) 다시 시작합니다.",
 "ja": "更新完了。{app} を再起動します。",
 "zh": "更新完成。即将重启 {app}。",
 "fr": "Mise à jour terminée. {app} va redémarrer.",
 "pt": "Atualizado. O {app} vai reiniciar agora.",
 "es": "Actualizado. {app} se reiniciará ahora."},
"upd_fail": {
 "en": "Update failed — {e}\nYou can download it from GitHub instead.",
 "ko": "업데이트 실패 — {e}\nGitHub에서 직접 받으실 수 있습니다.",
 "ja": "更新に失敗しました — {e}\nGitHubから直接ダウンロードできます。",
 "zh": "更新失败 — {e}\n你可以改从 GitHub 下载。",
 "fr": "Échec de la mise à jour — {e}\nVous pouvez la télécharger depuis GitHub.",
 "pt": "Falha na atualização — {e}\nVocê pode baixar pelo GitHub.",
 "es": "Error al actualizar — {e}\nPuedes descargarla desde GitHub."},
"upd_latest": {
 "en": "{app} {v} is the latest version.", "ko": "{app} {v}이(가) 최신 버전입니다.",
 "ja": "{app} {v} が最新です。", "zh": "{app} {v} 已是最新版本。",
 "fr": "{app} {v} est la dernière version.", "pt": "{app} {v} é a versão mais recente.",
 "es": "{app} {v} es la última versión."},
"upd_offline": {
 "en": "Could not reach GitHub. Check your internet connection.",
 "ko": "GitHub에 연결하지 못했습니다. 인터넷 연결을 확인해 주세요.",
 "ja": "GitHubに接続できませんでした。ネット接続を確認してください。",
 "zh": "无法连接 GitHub，请检查网络连接。",
 "fr": "Impossible de joindre GitHub. Vérifiez votre connexion.",
 "pt": "Não foi possível acessar o GitHub. Verifique sua conexão.",
 "es": "No se pudo conectar con GitHub. Comprueba tu conexión."},
"upd_reinstall": {
 "en": ("This version needs new components, so it cannot update itself.\n"
        "Please run the one-line installer again (see GitHub)."),
 "ko": ("이 버전은 새 구성요소가 필요해서 자체 업데이트가 되지 않습니다.\n"
        "설치 명령(한 줄 설치)을 다시 실행해 주세요 (GitHub 참고)."),
 "ja": ("このバージョンは新しい構成要素が必要なため、自動更新できません。\n"
        "インストールコマンドを再実行してください（GitHub参照）。"),
 "zh": ("此版本需要新的组件，无法自行更新。\n请重新运行一行安装命令（见 GitHub）。"),
 "fr": ("Cette version nécessite de nouveaux composants et ne peut pas se mettre à jour seule.\n"
        "Relancez l'installateur en une ligne (voir GitHub)."),
 "pt": ("Esta versão precisa de novos componentes e não pode se atualizar sozinha.\n"
        "Execute novamente o instalador de uma linha (veja o GitHub)."),
 "es": ("Esta versión necesita componentes nuevos y no puede actualizarse sola.\n"
        "Vuelve a ejecutar el instalador de una línea (ver GitHub).")},
"upd_open_github": {
 "en": "Open GitHub", "ko": "GitHub 열기", "ja": "GitHubを開く", "zh": "打开 GitHub",
 "fr": "Ouvrir GitHub", "pt": "Abrir o GitHub", "es": "Abrir GitHub"},
"log_update_found": {
 "en": "A new version is available: {v} (Help -> Check for updates)",
 "ko": "새 버전이 나왔습니다: {v} (도움말 -> 업데이트 확인)",
 "ja": "新しいバージョン {v} があります（ヘルプ -> アップデートを確認）",
 "zh": "有新版本 {v}（帮助 -> 检查更新）",
 "fr": "Nouvelle version disponible : {v} (Aide -> Rechercher des mises à jour)",
 "pt": "Nova versão disponível: {v} (Ajuda -> Procurar atualizações)",
 "es": "Nueva versión disponible: {v} (Ayuda -> Buscar actualizaciones)"},
})


def T(key, **kw):
    d = I18N.get(key)
    if d is None:
        return key
    s = d.get(UI["lang"]) or d.get("en") or key
    if kw:
        try:
            s = s.format(**kw)
        except Exception:
            pass
    return s


def lang_label(code):
    """언어 코드 -> 표시 이름 (원어 이름, auto만 UI 언어를 따름)"""
    if code == "auto":
        return T("auto_detect")
    return NATIVE.get(code, code)


# ---------------- config ----------------
def load_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        ensure_gitignore()
    except Exception:
        pass

def ensure_gitignore():
    folder = os.path.dirname(os.path.abspath(__file__))
    gi = os.path.join(folder, ".gitignore")
    try:
        existing = ""
        if os.path.exists(gi):
            with open(gi, encoding="utf-8") as f:
                existing = f.read()
        missing = [ln for ln in ("config.json", "*.py.bak", "*.py.new") if ln not in existing]
        if missing:
            with open(gi, "a", encoding="utf-8") as f:
                pre = "" if (not existing or existing.endswith("\n")) else "\n"
                f.write(pre + "\n".join(missing) + "\n")
    except Exception:
        pass


# ---------------- 자동 업데이트 (1.1) ----------------
def _ver_tuple(s):
    """'1.10' > '1.9' 가 되도록 숫자 단위로 비교."""
    out = []
    for part in re.split(r"[._\-]", str(s or "").strip().lstrip("vV")):
        m = re.match(r"\d+", part)
        out.append(int(m.group()) if m else 0)
    while len(out) < 3:
        out.append(0)
    return tuple(out[:3])


def _update_request(url, timeout):
    import urllib.request
    req = urllib.request.Request(url, headers={
        "User-Agent": f"{APP_NAME}/{VERSION}",
        "Cache-Control": "no-cache",
    })
    return urllib.request.urlopen(req, timeout=timeout)


def fetch_update_info(timeout=6):
    """GitHub의 version.json 조회. 실패하면 None (조용히 무시)."""
    try:
        with _update_request(UPDATE_INFO_URL, timeout) as r:
            info = json.loads(r.read().decode("utf-8"))
        if not isinstance(info, dict) or not info.get("version"):
            return None
        return info
    except Exception:
        return None


def update_available(info):
    if not info:
        return False
    return _ver_tuple(info.get("version")) > _ver_tuple(VERSION)


def download_new_version(info, timeout=90):
    """새 버전 .py 내려받기. 내용 검증까지 통과해야 bytes를 돌려준다."""
    name = str(info.get("file") or "").strip()
    if not name or not name.endswith(".py") or "/" in name or "\\" in name or ".." in name:
        raise ValueError("version.json: invalid file name")
    with _update_request(UPDATE_RAW_BASE + "/" + name, timeout) as r:
        data = r.read()
    if len(data) < 50000:
        raise ValueError("downloaded file is too small")
    text = data.decode("utf-8")
    if "JQSubtitle" not in text or "class App" not in text:
        raise ValueError("downloaded file does not look like JQSubtitle")
    compile(text, name, "exec")   # 문법이 깨진 파일로 덮어쓰지 않도록
    return data


def apply_update(data):
    """현재 실행 중인 .py를 새 내용으로 교체. 기존 파일은 .bak으로 남긴다."""
    import shutil
    target = os.path.abspath(__file__)
    tmp = target + ".new"
    with open(tmp, "wb") as f:
        f.write(data)
    try:
        shutil.copy2(target, target + ".bak")
    except Exception:
        pass
    os.replace(tmp, target)
    return target


def restart_app():
    """교체된 파일로 다시 실행하고 현재 프로세스는 종료."""
    target = os.path.abspath(__file__)
    exe = sys.executable or "python"
    kwargs = {}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = 0x00000008  # DETACHED_PROCESS
    try:
        subprocess.Popen([exe, target], cwd=os.path.dirname(target), **kwargs)
    except Exception:
        pass
    os._exit(0)


def update_note_text(info):
    """version.json의 notes에서 현재 UI 언어에 맞는 설명을 꺼낸다."""
    notes = info.get("notes")
    if isinstance(notes, dict):
        return str(notes.get(UI["lang"]) or notes.get("en") or "").strip()
    if isinstance(notes, str):
        return notes.strip()
    return ""


# ---------------- 엔진 설치 확인 ----------------
def ensure_faster_whisper(root):
    # v4.6: 무거운 import 대신 설치 여부만 빠르게 확인 (실제 로딩은 생성 시점)
    import importlib.util as _ilu
    if _ilu.find_spec("faster_whisper") is not None:
        return True

    info = tk.Toplevel(root)
    info.title(T("inst_title"))
    info.geometry("420x120")
    info.transient(root)
    ttk.Label(info, text=T("inst_msg"), justify="center").pack(expand=True, padx=16, pady=12)
    bar = ttk.Progressbar(info, mode="indeterminate")
    bar.pack(fill="x", padx=16, pady=(0, 12)); bar.start(12); info.update()

    result = {"ok": False, "err": ""}

    def do_install():
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "faster-whisper"])
            result["ok"] = True
        except Exception as e:
            result["err"] = str(e)
            return
        # v1.3.8: CUDA 런타임. 없으면 GPU 를 못 쓴다 (load_whisper_model 주석 참고).
        #   실패해도 설치를 실패로 보지 않는다 — CPU 로도 동작한다.
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install",
                                   "nvidia-cublas-cu12", "nvidia-cudnn-cu12"])
        except Exception:
            pass

    t = threading.Thread(target=do_install, daemon=True); t.start()
    while t.is_alive():
        info.update(); time.sleep(0.05)
    bar.stop(); info.destroy()

    if result["ok"]:
        if _ilu.find_spec("faster_whisper") is not None:
            return True
        messagebox.showinfo(T("inst_done_t"), T("inst_done_b"))
        root.destroy(); sys.exit(0)
    else:
        messagebox.showerror(T("inst_fail_t"), T("inst_fail_b", e=result["err"][:300]))
        return False


# ---------------- 시간/문장 ----------------
def fmt_time(s):
    h = int(s // 3600); m = int((s % 3600) // 60)
    sec = int(s % 60); ms = int((s - int(s)) * 1000)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"

def human_dur(seconds):
    seconds = int(max(0, seconds))
    if seconds < 60:
        return T("dur_s", s=seconds)
    m, s = divmod(seconds, 60)
    if m < 60:
        return T("dur_m", m=m, s=s)
    h, m = divmod(m, 60)
    return T("dur_h", h=h, m=m)


def dur_mmss(seconds):
    """완료 요약용 짧은 시간 표기 — 19:22 / 1:05:30.

    human_dur() 는 '약 19분 22초' 처럼 쓰는데, 그건 남은 시간 추정에 맞는 말투다.
    끝난 뒤의 실측값에 '약' 을 붙이면 어색하고, 단계마다 반복되면 줄이 지저분해진다.
    """
    seconds = int(max(0, round(seconds)))
    h, rem = divmod(seconds, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return "%d:%02d:%02d" % (h, m, sec)
    return "%d:%02d" % (m, sec)


def split_into_sentences(words):
    """반환: [(start, end, text, seg_words), ...]
    seg_words = [(word_text, start, end), ...] (그 문장을 이루는 단어들, 실측 타이밍)"""
    sentences = []; cur = []; cur_w = []; cs = None
    for w in words:
        if cs is None:
            cs = w.start
        cur.append(w.word)
        cur_w.append((w.word, w.start, w.end))
        st = w.word.strip()
        if st and st[-1] in SENT_END:
            txt = "".join(cur).strip()
            if txt:
                sentences.append((cs, w.end, txt, cur_w))
            cur = []; cur_w = []; cs = None
    if cur:
        txt = "".join(cur).strip()
        if txt:
            sentences.append((cs, words[-1].end, txt, cur_w))
    return sentences

def build_srt(entries):
    out = []
    for e in entries:
        lines = [ln.replace("\r", "") for ln in e["lines"]]
        out.append(e["index"] + "\n" + e["time"] + "\n" + "\n".join(lines))
    return ("\n\n".join(out) + "\n").replace("\n", "\r\n")


def apply_trailing_delay(entries, extra=1.0, gap=0.05):
    """각 자막 끝을 다음 자막과 안 겹치는 선에서 extra초 늘린다 (time 문자열도 갱신)."""
    n = len(entries)
    extra_ms = int(extra * 1000)
    gap_ms = int(gap * 1000)
    for i in range(n):
        e = entries[i]
        end_ms = e["end_ms"]
        if i + 1 < n:
            nxt = entries[i + 1]["start_ms"]
            max_end = max(end_ms, nxt - gap_ms)
        else:
            max_end = end_ms + extra_ms
        new_end = min(end_ms + extra_ms, max_end)
        if new_end > end_ms:
            e["end_ms"] = new_end
            s = e["start_ms"] / 1000.0
            en = new_end / 1000.0
            e["time"] = f"{fmt_time(s)} --> {fmt_time(en)}"
    return entries



def apply_song_padding(entries, lead=1.0, tail=1.0, gap=0.05):
    """
    가사 줄만 앞뒤로 늘린다 (겹치지 않는 선에서).

    ★ 왜 가사만 따로 하는가
      apply_trailing_delay() 는 노래 단계보다 먼저 돈다. 가사 줄은 그 뒤에
      들어오기 때문에 여유를 못 받고 '칼같이 딱 맞는' 자막이 된다.
      대사 타이밍은 이미 잘 돌고 있으므로 건드리지 않는다.

    ★ 가사는 앞쪽 여유가 특히 필요하다.
      따라 부르려면 미리 읽어야 한다. 소리와 동시에 뜨면 이미 늦다.
    """
    lead_ms, tail_ms, gap_ms = int(lead * 1000), int(tail * 1000), int(gap * 1000)
    n = len(entries)
    for i, e in enumerate(entries):
        if not e.get("song"):
            continue
        st, en = e["start_ms"], e["end_ms"]
        prev_end = entries[i - 1]["end_ms"] if i > 0 else 0
        new_st = max(0, st - lead_ms, prev_end + gap_ms if i > 0 else 0)
        new_st = min(new_st, st)                      # 뒤로 밀지는 않는다
        nxt_st = entries[i + 1]["start_ms"] if i + 1 < n else None
        new_en = en + tail_ms
        if nxt_st is not None:
            new_en = min(new_en, max(en, nxt_st - gap_ms))
        if new_en <= new_st:
            new_en = new_st + 300
        if new_st != st or new_en != en:
            e["start_ms"], e["end_ms"] = new_st, new_en
            e["time"] = "%s --> %s" % (fmt_time(new_st / 1000.0),
                                       fmt_time(new_en / 1000.0))
    return entries


def _split_one_by_ratio(start, end, pieces):
    """글자 수 비율로 시간 배분 (단어 매칭 실패 시 폴백)."""
    total_chars = sum(max(1, len(p)) for p in pieces)
    span = max(0.001, end - start)
    out = []
    cur = start
    for i, p in enumerate(pieces):
        frac = max(1, len(p)) / total_chars
        seg = span * frac
        s = cur
        e = end if i == len(pieces) - 1 else cur + seg
        out.append((s, e, p.strip()))
        cur = e
    return out


def _norm(s):
    return re.sub(r"[^0-9a-z가-힣]", "", s.lower())


def _split_one_by_words(pieces, seg_words):
    """Claude가 나눈 문장(pieces)을 단어 실측 타임스탬프(seg_words)에 매칭.
    매칭 실패 문장은 앞뒤 사이에 비례 배분. 전부 실패 시 None."""
    if not seg_words:
        return None
    norm_words = [_norm(t) for (t, _, _) in seg_words]
    char_to_word = []
    for wi, nw in enumerate(norm_words):
        for _ in nw:
            char_to_word.append(wi)
    full_norm = "".join(norm_words)
    if not full_norm:
        return None

    seg_start = seg_words[0][1]
    seg_end = seg_words[-1][2]

    raw = []
    search_pos = 0
    for sent in pieces:
        ns = _norm(sent)
        if not ns:
            continue
        idx = full_norm.find(ns, search_pos)
        if idx == -1:
            idx = full_norm.find(ns[:max(6, len(ns) // 2)], search_pos)
        if idx == -1:
            idx = full_norm.find(ns[:max(5, int(len(ns) * 0.4))], search_pos)
        if idx == -1:
            raw.append((None, None, sent.strip()))
            continue
        end_char = idx + len(ns) - 1
        ws = char_to_word[idx] if idx < len(char_to_word) else 0
        we = char_to_word[min(end_char, len(char_to_word) - 1)]
        raw.append((seg_words[ws][1], seg_words[we][2], sent.strip()))
        search_pos = end_char + 1

    if not raw or all(r[0] is None for r in raw):
        return None

    res = [[s, e, t] for s, e, t in raw]
    n = len(res)
    i = 0
    while i < n:
        if res[i][0] is None:
            j = i
            while j < n and res[j][0] is None:
                j += 1
            left = res[i - 1][1] if i > 0 and res[i - 1][1] is not None else seg_start
            right = res[j][0] if j < n else seg_end
            span = max(0.001, right - left)
            cnt = j - i
            for k in range(i, j):
                res[k][0] = left + span * (k - i) / cnt
                res[k][1] = left + span * (k - i + 1) / cnt
            i = j
        else:
            i += 1
    return [(s, e, t) for s, e, t in res]


PAUSE_MARK = "⏸"

def _mark_pauses(seg_words, min_gap=0.5):
    """단어 사이 침묵이 min_gap초 이상인 지점에 ⏸ 표시 (Claude 요청문 전용)."""
    if not seg_words:
        return ""
    parts = []
    for i, (t, s, e) in enumerate(seg_words):
        parts.append(t)
        if i + 1 < len(seg_words) and (seg_words[i + 1][1] - e) >= min_gap:
            parts.append(f" {PAUSE_MARK} ")
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def split_by_pauses(entries, log, max_chars=60, max_secs=8.0):
    """Claude 없이 뭉친 자막을 침묵 기준으로 분할 (무료 폴백)."""
    targets = []
    for i, e in enumerate(entries):
        text = " ".join(e["lines"])
        dur = (e["end_ms"] - e["start_ms"]) / 1000.0
        if (len(text) > max_chars or dur > max_secs) and e.get("words"):
            targets.append(i)

    if not targets:
        log(T("log_no_runon") + "\n")
        return entries

    log(T("log_runon_found_p", n=len(targets)) + "\n")

    def too_big(ws):
        txt = "".join(t for (t, _, _) in ws).strip()
        dur = ws[-1][2] - ws[0][1]
        return len(txt) > max_chars or dur > max_secs

    def pick_cut(piece):
        gaps = [piece[i + 1][1] - piece[i][2] for i in range(len(piece) - 1)]
        max_gap = max(gaps)
        mid = (len(piece) - 1) / 2.0
        cands = [i for i, g in enumerate(gaps) if g >= max_gap - 0.05]
        return min(cands, key=lambda i: abs(i - mid))

    def split_all(ws):
        out = [ws]
        changed = True
        while changed:
            changed = False
            nxt = []
            for piece in out:
                if len(piece) >= 2 and too_big(piece):
                    cut = pick_cut(piece)
                    nxt.append(piece[:cut + 1])
                    nxt.append(piece[cut + 1:])
                    changed = True
                else:
                    nxt.append(piece)
            out = nxt
        return out

    new_entries = []
    for i, e in enumerate(entries):
        if i not in targets:
            new_entries.append(e)
            continue
        pieces = split_all(e["words"])
        if len(pieces) <= 1:
            new_entries.append(e)
            continue
        for ws in pieces:
            txt = "".join(t for (t, _, _) in ws).strip()
            if not txt:
                continue
            ps, pend = ws[0][1], ws[-1][2]
            new_entries.append({
                "index": "0",
                "time": f"{fmt_time(ps)} --> {fmt_time(pend)}",
                "lines": [txt],
                "start_ms": int(round(ps * 1000)),
                "end_ms": int(round(pend * 1000)),
                "words": ws,
            })
        log(T("log_piece", i=e["index"], n=len(pieces)) + "\n")

    for idx, e in enumerate(new_entries, 1):
        e["index"] = str(idx)
    return new_entries


# ============================================================================
#  v1.2 — 단어 타임스탬프 기반 문장 재조립 (rebuild_from_words)
# ============================================================================
#
#  [왜 바꿨나]
#   v1.1 까지는 "무음으로 자른 자막"을 AI 에게 주고 고치라고 했다. 그래서
#     - 60자/8초를 넘는 줄만 검사 -> 짧게 붙어버린 두 문장은 손도 못 댔고
#     - 자막 하나를 여러 조각으로 나누는 것만 가능 -> 옆 자막으로 잘려 넘어간
#       단어를 되돌리거나 두 자막을 합치는 건 구조적으로 불가능했으며
#     - AI 가 다시 써서 보낸 텍스트를 검증 없이 그대로 덮어써서
#       단어가 사라지거나 없던 말이 생기는 사고가 났다.
#
#  [지금 방식]
#   기준은 언제나 Whisper 의 단어별 실측 타임스탬프(=_words.srt 의 내용)다.
#   AI 에게는 번호를 붙인 단어 목록을 주고, 자막 경계를 "번호 범위"로 답하게 한다.
#   기존 자막은 고칠 대상이 아니라 참고 자료로만 함께 넣는다.
#
#     보내는 것:  1:안녕 2:하세요⏸ 3:오늘은 4:날씨가 5:좋네요
#     받는 것  :  1-2 | 3-5
#     만드는 것:  "안녕하세요"  (words[1].start ~ words[2].end)
#                 "오늘은 날씨가 좋네요"  (words[3].start ~ words[5].end)
#
#   시간은 항상 단어에서 그대로 가져오므로 비율 추정 폴백이 필요 없다.
#   텍스트는 원칙적으로 단어를 그대로 이어 붙이되, 인식이 흘려들어 말이 끊긴
#   자리는 AI 가 'A-B: 고친 문장' 형태로 보정할 수 있게 열어 뒀다.
#   단, 보정본은 원문과의 유사도 검사를 통과해야만 채택한다(지어내기 차단).
#
#  ★ 이 함수는 _words.srt 와 같은 데이터를 쓴다. ALWAYS_SAVE_WORDS 를 끄면
#    디버깅 근거가 사라지므로 절대 끄지 말 것 (파일 상단 주석 참고).
# ============================================================================

# (한 번에 보내는 단어 수는 ENGINES 표의 "rebuild_chunk_words" — 엔진마다 다르다)
REBUILD_MIN_SIMILARITY = 0.70  # 재조립 중 AI 텍스트 보정을 채택할 최소 유사도
REBUILD_RETRIES = 2            # v1.3.5: 블록 검증 실패 시 재시도 횟수
REBUILD_MEND = 2               # v1.7.13: 구간이 이 칸 이하로 어긋나면 메워서 살린다
                               #          (근거는 _parse_rebuild_reply 주석)
                               #   (첫 시도 포함 최대 3번. 교정·번역과 같은 값)
                               #   ★ 0 으로 되돌리지 말 것 — 실패가 무작위라
                               #     재시도 없이는 약 10% 구간이 무음 폴백으로 버려진다
CORRECT_MIN_SIMILARITY = 0.55  # 교정 단계에서 수용할 최소 유사도
                               #  (외국어 -> 한국어 치환은 글자가 통째로 바뀌므로
                               #   재조립보다 느슨하게 둔다)


def _flatten_words(entries):
    """entries 안의 단어들을 (텍스트, 시작, 끝) 하나의 목록으로 펼친다."""
    flat = []
    for e in entries:
        for w in (e.get("words") or []):
            if str(w[0]).strip():
                flat.append((w[0], w[1], w[2]))
    return flat


def _similar(a, b):
    """문장 두 개의 유사도(0~1). 공백·문장부호는 무시하고 글자만 비교."""
    from difflib import SequenceMatcher
    na, nb = _norm(a), _norm(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def _words_to_text(flat, a, b):
    """flat[a-1..b-1] 단어를 이어 붙여 자막 한 줄 텍스트로 만든다 (1-기반 번호)."""
    txt = "".join(t for (t, _, _) in flat[a - 1:b])
    return re.sub(r"\s+", " ", txt).strip()


def _numbered_words(flat, base, count, min_gap=0.5):
    """AI 에게 보낼 번호 붙은 단어 줄. 뒤에 쉼이 있는 단어에는 ⏸ 를 붙인다."""
    out = []
    for k in range(count):
        i = base + k
        t = flat[i][0].strip()
        mark = ""
        if i + 1 < len(flat) and (flat[i + 1][1] - flat[i][2]) >= min_gap:
            mark = PAUSE_MARK
        out.append(f"{k + 1}:{t}{mark}")
    return " ".join(out)


def _parse_rebuild_reply(text, count):
    """'1-7' / '8-12: 고친 문장' 형태의 응답을 파싱하고 검증한다.
    반환: (구간목록, 실패사유). 실패하면 (None, 사유)."""
    spans = []
    for line in text.replace("|", "\n").split("\n"):
        line = line.strip().strip("`").lstrip("-• \t")
        if not line:
            continue
        m = re.match(r"^(\d+)\s*[-~–]\s*(\d+)\s*(?:[:：]\s*(.*))?$", line)
        if not m:
            m2 = re.match(r"^(\d+)\s*(?:[:：]\s*(.*))?$", line)   # 단어 하나짜리 자막
            if not m2:
                continue
            a = b = int(m2.group(1))
            override = (m2.group(2) or "").strip()
        else:
            a, b = int(m.group(1)), int(m.group(2))
            override = (m.group(3) or "").strip()
        spans.append((a, b, override))

    if not spans:
        return None, "no valid ranges"

    # -----------------------------------------------------------------
    #  검증: 1..count 를 빠짐없이, 겹치지 않게, 순서대로 덮어야 한다
    #
    #  ★ v1.7.13: 한두 칸 어긋난 것은 **메워서 살린다.**
    #
    #    AI 는 글자를 만드는 게 아니라 '몇 번부터 몇 번까지가 한 문장인지'를
    #    답한다. 500~700개 번호를 세는 산수라서 한두 개씩 흘린다.
    #    지금까지는 하나만 어긋나도 그 묶음의 답을 통째로 버리고 무음 기준으로
    #    잘랐다 — 그 결과가 대문자도 마침표도 없는 줄이다.
    #
    #    2026-08-28 실측 (5,214단어 / 9묶음 중 4묶음이 버려졌다):
    #        gap/overlap at 27  (expected 26)    1칸
    #        gap/overlap at 396 (expected 395)   1칸
    #        gap/overlap at 9   (expected 7)     2칸
    #        gap/overlap at 151 (expected 147)   4칸
    #      대부분 1~2칸이다. 앞 구간의 끝을 옮겨 주면 그대로 통과한다.
    #
    #    ★ 글자는 건드리지 않는다. 문장 경계가 한두 단어 옮겨질 뿐이고,
    #      단어도 시각도 whisper 가 잰 그대로다. 그래서 안전하다.
    #    ★ REBUILD_MEND 를 키우지 말 것. 크게 어긋난 것은 AI 가 문장을 통째로
    #      잘못 나눈 것이라, 억지로 이으면 엉뚱한 자리에서 끊긴 자막이 된다.
    #      그건 지금처럼 버리고 다시 물어보는 게 맞다.
    # -----------------------------------------------------------------
    fixed = []
    mended = 0
    pos = 1
    for (a, b, ov) in spans:
        if a != pos:
            if abs(a - pos) > REBUILD_MEND:
                return None, f"gap/overlap at {a} (expected {pos})"
            # 빈틈이면 앞 구간을 늘리고, 겹치면 이번 구간의 시작을 밀어낸다
            if a > pos and fixed:
                pa, pb, pov = fixed[-1]
                fixed[-1] = (pa, a - 1, pov)
            else:
                a = pos
            mended += 1
        if b < a:
            return None, f"reversed range {a}-{b}"
        if b > count:
            return None, f"out of range {b} > {count}"
        fixed.append((a, b, ov))
        pos = b + 1

    if pos != count + 1:
        # 끝이 조금 모자란 것도 같은 이유로 메운다
        if fixed and 0 < (count + 1 - pos) <= REBUILD_MEND:
            pa, pb, pov = fixed[-1]
            fixed[-1] = (pa, count, pov)
            mended += 1
        else:
            return None, f"only {pos - 1} of {count} words covered"

    return fixed, (f"mended {mended}" if mended else "")


def rebuild_from_words(entries, provider, api_key, log, extra="", prog=None,
                       report=None):
    """단어 타임스탬프를 근거로 자막을 처음부터 다시 조립한다.
    entries 는 '참고 초안'으로만 쓰이고, 결과는 단어에서 새로 만들어진다."""
    flat = _flatten_words(entries)
    if len(flat) < 2:
        log(T("log_rebuild_nowords") + "\n")
        return split_by_pauses(entries, log)

    log(T("log_rebuild", n=len(flat)) + "\n")

    extra_clause = ""
    if extra.strip():
        extra_clause = (
            "\n[운영자 추가 지시]\n"
            "이 도구를 돌리는 사람이 남긴 요청입니다. 위 규칙과 충돌하지 않는 선에서만 반영하세요.\n"
            + extra.strip() + "\n")

    system = (
        "당신은 자막 편집자입니다. 아래 단어 목록은 음성 인식이 실제로 들은 단어들이고, "
        "각 단어에는 고유 번호가 붙어 있습니다. 이 단어들을 자연스러운 자막 단위로 묶는 것이 당신의 일입니다.\n"
        "\n[입력]\n"
        "  번호가 붙은 단어 목록. 단어 뒤에 붙은 " + PAUSE_MARK + " 는 그 단어 다음에 "
        "실제로 쉼(무음)이 있다는 뜻입니다. " + PAUSE_MARK + " 자체는 단어가 아니며 번호도 없습니다.\n"
        "  참고용으로 현재 자막 초안도 함께 줍니다. 이 초안은 무음만 보고 기계적으로 자른 것이라 "
        "틀린 곳이 많습니다. 참고만 하고 얽매이지 마세요.\n"
        "\n[출력]\n"
        "  자막 한 줄당 한 항목, 한 줄에 하나씩. 형식은 '시작번호-끝번호' 입니다.\n"
        "  텍스트를 손봐야 할 때만 '시작번호-끝번호: 고친 텍스트' 로 적으세요.\n"
        "  예:\n"
        "    1-6\n"
        "    7-11: 오늘은 날씨가 참 좋네요\n"
        "    12-12\n"
        "\n[규칙]\n"
        "1. 한 자막 = 한 문장. 두 문장이 한 자막에 붙어 있으면 반드시 나누세요. 이게 가장 중요합니다.\n"
        "2. 한 문장이 화면을 넘칠 만큼 길면(대략 40자 이상) 절이나 접속사, 숨 쉬는 자리에서 "
        "두 조각으로 나누세요. 셋 이상으로 잘게 쪼개지는 마세요.\n"
        "3. 문장이 앞뒤로 잘려 나가지 않게 하세요. 한 문장에 속한 단어는 같은 자막에 모으세요.\n"
        "4. " + PAUSE_MARK + " 는 힌트일 뿐입니다. 문장 한가운데의 " + PAUSE_MARK + " 는 무시하고, "
        "문장이 끝나는 자리의 " + PAUSE_MARK + " 는 좋은 분할점입니다.\n"
        "5. 자막 길이는 글자 수가 아니라 내용으로 판단하세요. '우와!', '네.' 처럼 그 자체로 "
        "완결된 짧은 발화는 한 줄로 두는 것이 맞습니다. 반대로 의미 없이 잘려 나온 토막"
        "('그런데', '저는' 같은 것)은 앞뒤 자막에 붙이세요.\n"
        "6. 단어를 임의로 바꾸지 마세요. 다만 음성 인식이 확실히 흘려들어 말이 되지 않는 곳"
        "(조사가 빠졌거나 단어 하나가 없어서 문장이 끊기는 경우)은 자연스럽게 채워도 됩니다. "
        "확신이 없으면 그냥 두세요.\n"
        "7. 모든 번호를 빠짐없이, 한 번씩만 사용하세요. 첫 자막은 1번에서 시작하고 "
        "마지막 자막은 마지막 번호에서 끝나야 합니다.\n"
        + extra_clause +
        "\n[출력 전 스스로 확인]\n"
        "답을 내놓기 전에, 만든 결과를 처음부터 끝까지 다시 읽고 아래를 점검하세요.\n"
        "  ㄱ. 번호를 빠뜨렸거나 두 번 쓴 곳이 없는가?\n"
        "  ㄴ. 한 자막 안에 문장이 두 개 이상 들어간 곳이 없는가?\n"
        "  ㄷ. 문장이 어중간하게 잘려 다음 자막으로 넘어간 곳이 없는가?\n"
        "  ㄹ. 화면을 넘칠 만큼 긴 줄이 남아 있지 않은가?\n"
        "  ㅁ. 텍스트를 고친 줄이 있다면, 실제로 들린 말에서 벗어나지 않았는가?\n"
        "문제가 있으면 고쳐서 최종본만 출력하세요.\n"
        "점검 과정은 쓰지 말고, 결과만 출력하세요. 설명·인사·코드블록 없이 목록만 출력합니다."
    )

    # v1.2: 로컬 AI 는 한 번에 적게 보낸다.
    #   ① 컨텍스트가 짧아 프롬프트가 잘릴 위험이 줄고
    #   ② 한 번의 대기가 짧아져 진행이 눈에 보이며
    #   ③ 응답이 형식을 어겨 거부돼도 날아가는 구간이 작다
    chunk_words = EOPT(provider, "rebuild_chunk_words")   # v1.3.2: 엔진 표에서

    new_entries = []
    total = len(flat)
    base = 0
    block = 0
    n_fb_blocks = 0        # v1.7.4: AI 대신 무음 폴백으로 처리한 묶음 수
    n_fb_words = 0         #         그 묶음에 든 단어 수
    n_mend = 0             # v1.7.13: 구간을 메워서 살린 횟수
    n_blocks_est = max(1, (total + chunk_words - 1) // chunk_words)
    while base < total:
        raise_if_cancelled()      # v1.3: 블록 사이에서도 확인 (안쪽은 스트리밍 루프가 담당)
        block += 1
        if prog:
            prog(min(1.0, base / total), block, n_blocks_est)
        count = min(chunk_words, total - base)
        # 묶음 경계가 문장 한가운데를 자르지 않도록, 끝에서 가장 긴 쉼 위치로 살짝 당긴다
        if base + count < total:
            best, best_gap = count, -1.0
            lo = max(int(count * 0.7), 1)
            for k in range(lo, count):
                gap = flat[base + k][1] - flat[base + k - 1][2]
                if gap > best_gap:
                    best_gap, best = gap, k
            count = best

        numbered = _numbered_words(flat, base, count)
        draft = "\n".join(
            _words_to_text(flat, base + 1, base + count).split(". "))  # 참고용(가벼운 형태)
        user_text = ("[단어 목록]\n" + numbered +
                     "\n\n[참고 초안 — 틀릴 수 있음]\n" + draft)

        # ---------------------------------------------------------------
        #  v1.3.5: 재조립에도 재시도를 넣는다.
        #
        #  ★ 그동안 재조립만 재시도가 없었다. 검증에 걸리면 곧바로 무음 폴백으로
        #    떨어져, 그 구간은 AI 문장 조립을 못 받고 기계적 분할로 남았다.
        #    실측: 66블록 중 6~8개(약 10%)가 이렇게 버려졌다.
        #      Block 27: AI reply failed validation (gap/overlap at 36) — original kept
        #
        #  ★ 교정·번역에서 확인했듯 이 실패는 무작위다(내용과 무관).
        #    같은 블록을 다시 물어보면 대개 통과한다. 폴백은 정말 마지막 수단으로만.
        #
        #  ★ 한도 오류(QuotaError)는 재시도 대상이 아니다 — 다시 물어도 실패가
        #    확정이고, 무료 티어에서는 요청 한 번이 아깝다. 바로 폴백으로 간다.
        # ---------------------------------------------------------------
        spans = None
        if quota_dead():
            # ★ 한도가 소진됐다. 남은 블록은 호출해 봐야 전부 실패한다.
            #   조용히 무음 기준 폴백으로 넘긴다 (같은 오류를 수십 번 찍지 않는다).
            spans = None
        else:
            for attempt in range(1, REBUILD_RETRIES + 2):
                raise_if_cancelled()
                why = ""
                try:
                    reply = ai_call(provider, api_key, system, user_text,
                                    max_tokens=8000, log=log)
                    spans, why = _parse_rebuild_reply(reply, count)
                    if spans is not None:
                        if attempt > 1:
                            log(T("log_rebuild_retry_ok", c=block, a=attempt) + "\n")
                        # v1.7.13: 메워서 살렸으면 조용히 넘어가지 않는다
                        if why.startswith("mended"):
                            n_mend += int(why.split()[1])
                            log(T("log_rebuild_mend", c=block,
                                  n=why.split()[1]) + "\n")
                        break
                except CancelledError:
                    raise    # v1.3: 취소는 실패가 아니다 — 폴백 없이 그대로 올린다
                except QuotaError as qe:
                    note_quota_fail(provider, qe.daily)
                    log(T("log_quota_hit", l=T("stage_rebuild"), c=block,
                          k=T("quota_daily") if qe.daily else T("quota_minute")) + "\n")
                    if quota_dead():
                        log(T("log_quota_abort", l=T("stage_rebuild")) + "\n")
                    spans = None
                    break    # 한도 문제는 재시도해도 소용없다
                except Exception as ce:
                    # v1.3.6: 여기서 따로 찍지 않는다. 아래 재시도/거부 줄에
                    #   같은 내용이 한 번 더 나가 로그가 두 배로 불어났다.
                    spans = None
                    why = str(ce).replace("\n", " ")[:90]

                # 여기까지 왔으면 이번 시도는 실패다
                if attempt <= REBUILD_RETRIES:
                    log(T("log_rebuild_retry", c=block, r=why or "?", a=attempt) + "\n")
                else:
                    log(T("log_rebuild_reject", c=block, r=why or "?") + "\n")

        if spans is None:
            # 이 묶음만 침묵 기준으로 안전하게 처리 (전체를 버리지 않는다)
            #
            # ★ v1.7.4: 여기로 떨어진 양을 세어 둔다.
            #   2026-08-27 사고: 503 으로 2블록 전부 여기로 떨어졌는데
            #   로그 중간에 "original kept" 두 줄만 지나가고 끝에는 아무 말이 없었다.
            #   결과 자막은 소문자에 마침표 없는 문장이 그대로 남았는데,
            #   로그를 끝까지 읽지 않으면 "잘 나왔네" 하고 그대로 쓰게 된다.
            #   교정·번역과 같은 대접을 해준다 (sum_skipped 에 실린다).
            n_fb_blocks += 1
            n_fb_words += count
            spans = _fallback_spans(flat, base, count)

        for (a, b, override) in spans:
            gs, ge = base + a, base + b          # 전역 번호로 변환
            s = flat[gs - 1][1]
            e_ = flat[ge - 1][2]
            orig_text = _words_to_text(flat, gs, ge)
            text = orig_text
            if override and override != orig_text:
                sim = _similar(orig_text, override)
                if sim >= REBUILD_MIN_SIMILARITY:
                    log(T("log_rebuild_fix", a=orig_text, b=override) + "\n")
                    text = override
                else:
                    log(T("log_rebuild_reject_fix", a=orig_text, b=override) + "\n")
            if not text:
                continue
            new_entries.append({
                "index": "0",
                "time": f"{fmt_time(s)} --> {fmt_time(e_)}",
                "lines": [text],
                "start_ms": int(round(s * 1000)),
                "end_ms": int(round(e_ * 1000)),
                "words": flat[gs - 1:ge],
            })

        base += count

    if isinstance(report, dict):
        report["blocks"] = block
        report["fallback_blocks"] = n_fb_blocks
        report["words"] = total
        report["fallback_words"] = n_fb_words
        # 전부 폴백이면 재조립이 아예 안 된 것과 같다
        report["none"] = (block > 0 and n_fb_blocks >= block)

    if not new_entries:
        log(T("log_rebuild_fail", e="empty result") + "\n")
        return entries

    for idx, e in enumerate(new_entries, 1):
        e["index"] = str(idx)
    log(T("log_rebuild_done", a=len(entries), b=len(new_entries)) + "\n")
    return new_entries


def _fallback_spans(flat, base, count, max_chars=60, max_secs=8.0):
    """AI 응답을 못 쓸 때, 해당 묶음만 침묵 기준으로 나눈 구간 목록을 만든다."""
    pieces = [list(range(1, count + 1))]
    changed = True
    while changed:
        changed = False
        nxt = []
        for p in pieces:
            txt = _words_to_text(flat, base + p[0], base + p[-1])
            dur = flat[base + p[-1] - 1][2] - flat[base + p[0] - 1][1]
            if len(p) >= 2 and (len(txt) > max_chars or dur > max_secs):
                gaps = [flat[base + p[i + 1] - 1][1] - flat[base + p[i] - 1][2]
                        for i in range(len(p) - 1)]
                mx = max(gaps)
                mid = (len(p) - 1) / 2.0
                cands = [i for i, g in enumerate(gaps) if g >= mx - 0.05]
                cut = min(cands, key=lambda i: abs(i - mid))
                nxt.append(p[:cut + 1]); nxt.append(p[cut + 1:])
                changed = True
            else:
                nxt.append(p)
        pieces = nxt
    return [(p[0], p[-1], "") for p in pieces if p]


def split_long_entries(entries, provider, api_key, log, max_chars=60, max_secs=8.0, extra=""):
    """[v1.1 방식 — v1.2부터 미사용] 뭉친 자막(60자/8초 초과)만 AI로 문장 분할.
    rebuild_from_words 로 대체되었다. 되돌릴 일이 있을까 해서 남겨 둔 코드이니
    새로 호출하지 말 것."""
    targets = []
    for i, e in enumerate(entries):
        text = " ".join(e["lines"])
        dur = (e["end_ms"] - e["start_ms"]) / 1000.0
        if len(text) > max_chars or dur > max_secs:
            targets.append(i)

    if not targets:
        log(T("log_no_runon") + "\n")
        return entries

    log(T("log_runon_found_c", n=len(targets)) + "\n")

    extra_clause = ""
    if extra.strip():
        extra_clause = ("OPERATOR PREFERENCES — the person running this tool added the following instructions. Apply them ONLY where they do not conflict with the strict formatting rules in this prompt (never change the number of lines, never reorder lines, keep timing untouched): "
                        + extra.strip() + " -- END OF OPERATOR PREFERENCES. ")

    SEP = "|||"
    system = (
        "You are given multiple run-on subtitles with little or no punctuation, ONE PER LINE, "
        "each prefixed with its number like 'N: '. "
        "For EACH input line, split its text into natural separate sentences. "
        f"{extra_clause}"
        f"The marker {PAUSE_MARK} in the input marks a real pause (silence) in the audio. "
        f"Prefer splitting at {PAUSE_MARK} positions when consistent with sentence structure. "
        f"NEVER include {PAUSE_MARK} in your output. "
        "Keep the wording faithful — do NOT add, remove, reword, or reorder any words. "
        "You MAY add sentence-ending punctuation (. ? !) and capitalization at the "
        "sentence boundaries you identify, since the input has none. "
        "Split song/lyric or dialogue at natural clause boundaries so each piece is a "
        "readable subtitle (roughly 3-12 words). "
        f"Return ONLY the results, one line per input, keeping the SAME numbers, in the format "
        f"'N: first sentence. {SEP} second sentence.' — separate sentences with ' {SEP} ', "
        "nothing else."
    )

    # 요청 라인 구성 (침묵 위치 힌트 포함)
    req_lines = []
    for i in targets:
        e = entries[i]
        text = " ".join(e["lines"]).strip()
        marked = _mark_pauses(e.get("words") or [])
        req_lines.append(f"{i + 1}: {marked if marked else text}")

    # 한 번(많으면 40개 단위)에 묶어 호출
    parsed = {}
    CHUNK = 40
    for c0 in range(0, len(req_lines), CHUNK):
        chunk = req_lines[c0:c0 + CHUNK]
        try:
            reply = ai_call(provider, api_key, system, "\n".join(chunk),
                            max_tokens=8000, log=log)
        except Exception as ce:
            log(T("log_split_fail", e=ce) + "\n")
            continue
        for line in reply.split("\n"):
            m = re.match(r"\s*(\d+)\s*[:：]\s*(.*)$", line)
            if not m:
                continue
            pieces = [re.sub(r"\s+", " ", p.replace(PAUSE_MARK, " ")).strip()
                      for p in m.group(2).split(SEP)]
            pieces = [p for p in pieces if p]
            if pieces:
                parsed[int(m.group(1))] = pieces

    target_set = set(targets)
    new_entries = []
    for i, e in enumerate(entries):
        pieces = parsed.get(i + 1)
        if i not in target_set or not pieces or len(pieces) <= 1:
            new_entries.append(e)
            continue
        seg_words = e.get("words") or []
        parts = _split_one_by_words(pieces, seg_words)
        if not parts:
            parts = _split_one_by_ratio(e["start_ms"] / 1000.0, e["end_ms"] / 1000.0, pieces)
        for (ps, pe, pt) in parts:
            new_entries.append({
                "index": "0",
                "time": f"{fmt_time(ps)} --> {fmt_time(pe)}",
                "lines": [pt],
                "start_ms": int(round(ps * 1000)),
                "end_ms": int(round(pe * 1000)),
            })
        log(T("log_piece", i=e["index"], n=len(pieces)) + "\n")

    for idx, e in enumerate(new_entries, 1):
        e["index"] = str(idx)
    return new_entries



def _est_tokens(s):
    """대략적인 토큰 수. 정확할 필요는 없고 '넘칠 것 같은가'만 알면 된다.
    한글/한자/가나는 글자당 약 1토큰, 라틴 문자는 3.5글자당 1토큰으로 잡는다."""
    cjk = 0
    for ch in s:
        if ('　' <= ch <= '鿿') or ('가' <= ch <= '힯'):
            cjk += 1
    return int(cjk + (len(s) - cjk) / 3.5)


def _budget_for(joined, floor=800, cap=None, provider=None):
    """이 묶음의 답변에 필요한 출력 토큰을 어림잡는다.

    v1.2 까지는 항상 8000 을 넘겼다. Ollama 에서 num_ctx 는 '프롬프트 + 생성분'을
    합친 전체 창이라, 8192 짜리 창에 8000 을 예약하면 입력 자리가 거의 안 남는다.
    번역·교정 결과는 원문과 길이가 비슷하므로 입력 기준으로 잡는 것이 맞다.

    ★ v1.7.11: 상한(cap)이 8000 에 **박혀 있었다.**
      v1.7.6 에서 묶음을 40줄 -> 300줄로 키웠는데 여기는 그대로였다.
      300줄짜리 답이 8000 토큰에 안 들어가면 뒤가 잘리고, 그만큼 보충 라운드를
      더 돈다(제미나이는 하루 한도까지 깎인다).
      이제 엔진 표의 max_tokens_cap 을 따른다 — 카드가 크면 그 값도 크다."""
    if cap is None:
        cap = EOPT(provider, "max_tokens_cap") if provider else 8000
    return max(floor, min(cap, int(_est_tokens(joined) * 2.2) + 300))


# 모델이 번호를 붙이는 방식이 매번 같지 않다. 아래를 모두 같은 것으로 본다:
#   "12: text"  "12. text"  "12) text"  "**12:** text"  "- 12: text"  "12 - text"
# (v1.3 은 'N:' 하나만 받아서, 형식이 조금만 달라도 그 줄을 통째로 놓쳤다.)
_NUM_LINE = re.compile(
    r"^\s*[-*>•\s]*(?:\*\*|__)?\s*(\d{1,4})\s*(?:\*\*|__)?\s*[:：.)\]\-–]\s*(.+?)\s*$")


def _parse_numbered(text, n):
    """AI 응답에서 'N: 텍스트' 줄만 뽑아 {번호: 텍스트} 로 돌려준다.
    번호가 1..n 범위를 벗어나면 버린다(모델이 지어낸 번호 방지)."""
    got = {}
    for line in text.split("\n"):
        s = line.strip()
        if not s or s.startswith("```"):     # 코드펜스로 감싸는 모델 대비
            continue
        m = _NUM_LINE.match(s)
        if not m:
            continue
        k = int(m.group(1))
        if 1 <= k <= n:
            v = m.group(2).strip()
            # '**3:** Hello' 처럼 구분자 뒤에 남는 마크다운 잔여물을 걷어낸다
            v = re.sub(r"^(?:\*\*|__|\*)\s*", "", v)
            v = re.sub(r"\s*(?:\*\*|__)$", "", v)
            v = v.strip().strip('"').strip()
            if v:
                got[k] = v
    return got



def _shift_score(part, got, lo, hi, offset):
    """[lo, hi) 구간에서 원문 길이와 응답 길이가 offset 만큼 어긋난 정도.

    ★ v1.7.11: hi 를 part 길이로 자른다.
      2026-08-28 사고: `list index out of range` 로 교정과 번역이 통째로 날아갔다.
      호출부가 창 크기(win=40)를 그대로 hi 로 넘기는데, 보충 라운드의 묶음은
      12줄짜리다. AI 가 12줄짜리 요청에 40개 번호를 붙여 보내면
      `j in got` 을 통과한 뒤 part[12..39] 에서 터진다.
      part 는 우리가 보낸 것이고 got 은 AI 가 보낸 것이다 —
      **둘의 길이가 같다고 가정하면 안 된다.**"""
    import math
    v = []
    hi = min(hi, len(part))
    for i in range(lo, hi):
        j = i + 1 + offset            # got 은 1부터
        if j in got:
            src = len(" ".join(part[i]["lines"]))
            v.append(abs(math.log((len(got[j]) + 2) / (src + 2))))
    if len(v) < 10:
        return None
    v.sort()
    return v[len(v) // 2]             # 중앙값 — 튀는 줄에 안 흔들린다


def numbered_is_shifted(part, got, win=40, step=20, ratio=0.75, need=2):
    """
    응답이 통째로 밀렸는지 본다.

    ★ 번호가 빠짐없이 왔는지만 보면 안 된다.
      2026-08-23 사고: 261줄을 요청했는데 AI 가 두 줄을 합치고 나머지를
      1..259 로 다시 매겨 보냈다. 번호는 반듯해서 검사를 통과했고,
      "2줄 모자라네" 하고 빈 자리만 채웠다. 파일은 261줄로 멀쩡한데
      200번부터 끝까지 내용이 두 줄씩 밀렸다.
      줄 수도 시각도 맞아서 눈으로는 안 보인다 — 제일 나쁜 종류의 고장이다.

    ★ '길이가 서로 어울리는가' 를 본다.
      짧은 감탄사("Huh?")는 번역도 짧고 긴 문장은 길다. 밀리면 그 대응이 무너진다.

    ★ 묶음 전체가 아니라 창(窓) 단위로 본다.
      밀림은 대개 중간부터 시작한다. 전체 중앙값으로 보면 앞쪽 멀쩡한 부분에
      묻혀서 안 잡힌다(실제로 못 잡았다). 40줄 창을 20줄씩 밀며 보고,
      **연속 두 창**이 어긋나야 밀림으로 본다 — 한 창만 튀는 건 우연이다.
    """
    n = min(len(part), max(got) if got else 0)
    run = 0
    for lo in range(0, max(1, n - win + 1), step):
        base = _shift_score(part, got, lo, lo + win, 0)
        if base is None:
            continue
        hit = any((_shift_score(part, got, lo, lo + win, o) or 9) < base * ratio
                  for o in (1, 2, -1, -2))
        run = run + 1 if hit else 0
        if run >= need:
            return True
    return False


def numbered_is_renumbered(got, n):
    """1..N 로 반듯하게 왔는데 N 이 요청 수보다 적다 = 다시 매긴 것."""
    if not got or len(got) >= n:
        return False
    ks = sorted(got)
    return ks == list(range(1, len(ks) + 1)) and len(ks) >= n * 0.5


def _numbered_block(part, provider, api_key, system_fn, log, label, tag,
                    min_match=NUMBERED_MIN_MATCH, attempts=NUMBERED_RETRIES + 1):
    """묶음 하나를 처리한다. 형식이 깨지면 다시 시도한다.
    반환: {묶음내_번호(1부터): 텍스트}  — 부분만 와도 그대로 돌려준다(버리지 않는다)."""
    n = len(part)
    joined = "\n".join(f"{i}: {' '.join(e['lines'])}"
                       for i, e in enumerate(part, 1))
    best = {}
    for attempt in range(1, attempts + 1):
        raise_if_cancelled()
        try:
            text = ai_call(provider, api_key, system_fn(n), joined,
                           max_tokens=_budget_for(joined, provider=provider), log=log)
        except CancelledError:
            raise            # 취소는 '묶음 실패'가 아니다 — 그대로 올린다
        except QuotaError as qe:
            # ★ 한도 오류는 '이 묶음이 깨졌다'가 아니라 '더는 못 쓴다'는 뜻이다.
            #   재시도해도 실패가 확정이라, 차단 상태가 되면 단계를 접는다.
            #   (quota_guard 를 끈 엔진에서는 note_quota_fail 이 항상 False)
            note_quota_fail(provider, qe.daily)
            log(T("log_quota_hit", l=label, c=tag,
                  k=T("quota_daily") if qe.daily else T("quota_minute")) + "\n")
            if quota_dead():
                raise
            continue
        except Exception as ce:
            log(T("log_chunk_fail", l=label, c=tag, e=str(ce)[:120]) + "\n")
            continue

        got = _parse_numbered(text, n)

        # ★ 줄이 통째로 밀렸거나 번호를 다시 매겨 보냈으면 통째로 버린다.
        #   부분이라도 건지는 평소 방침의 예외다 — 밀린 응답은 '부족한 결과'가
        #   아니라 '틀린 결과'라서, 남겨 두면 조용히 잘못된 자막이 된다.
        bad_why = ""
        if numbered_is_renumbered(got, n):
            bad_why = T("bad_renumber", n=len(got), t=n)
        elif numbered_is_shifted(part, got):
            bad_why = T("bad_shift")
        if bad_why:
            log(T("log_chunk_misaligned", l=label, c=tag, w=bad_why) + "\n")
            got = {}

        if len(got) > len(best):
            best = got                       # ★ 부분 성공도 보관해 둔다
        if len(got) >= n * min_match:
            if attempt > 1:
                log(T("log_chunk_retry_ok", l=label, c=tag, a=attempt) + "\n")
            return got
        # 기준 미달 — 다시 시도한다. 무작위 실패라 재시도로 대개 해결된다.
        if attempt < attempts:
            log(T("log_chunk_retry", l=label, c=tag,
                  n=len(got), t=n, a=attempt) + "\n")
    if best:
        log(T("log_chunk_partial", l=label, c=tag, n=len(best), t=n) + "\n")
    else:
        log(T("log_chunk_reject", l=label, c=tag, n=0, t=n) + "\n")
    return best


def _numbered_chunk_call(entries, provider, api_key, system_fn, log,
                         chunk_lines, label, min_match=NUMBERED_MIN_MATCH,
                         prog=None):
    """entries 를 chunk_lines 씩 잘라 'N: 텍스트' 형식으로 AI 에 보낸다.

    반환: ({전역번호(1부터): 결과텍스트}, 처리된_줄수, 전체_줄수)

    ★ 묶음 안에서는 번호를 1..len(part) 로 새로 매긴다.
      800번대 큰 숫자를 다루게 하면 로컬 모델이 번호를 건너뛰거나 중복시키는 일이 잦다.
      결과를 담을 때 base 를 더해 전역 번호로 되돌린다.

    ★ system_fn 은 문자열이 아니라 함수다(묶음 줄 수를 받는다).
      교정 프롬프트에는 "1번부터 N번까지 빠짐없이 있는지 확인하라"는 자기검증 문구가
      들어 있는데, 쪼갠 뒤에는 그 N 이 묶음마다 달라지기 때문이다.

    ★ 2단계로 돈다.
      1단계 — 묶음 순서대로. 형식이 깨지면 그 묶음만 다시 시도한다.
      2단계 — 그래도 빠진 줄이 있으면, 그 줄들만 모아 작은 묶음으로 다시 묻는다.
              문맥이 짧아지는 손해가 있지만, 원문(한국어)을 그대로 두는 것보다 낫다.
    """
    result = {}
    total = len(entries)
    if total == 0:
        return result, 0, 0
    n_chunks = (total + chunk_lines - 1) // chunk_lines

    batch = EOPT(provider, "gap_fill_batch")
    aborted = False

    # ---------- 1단계: 순서대로 ----------
    for ci in range(n_chunks):
        raise_if_cancelled()
        base = ci * chunk_lines
        part = entries[base:base + chunk_lines]
        log(T("log_chunk", l=label, c=f"{ci + 1}/{n_chunks}", t=len(part)) + "\n")
        try:
            got = _numbered_block(part, provider, api_key, system_fn, log,
                                  label, f"{ci + 1}/{n_chunks}", min_match)
        except QuotaError:
            # 한도 소진 — 남은 묶음도 똑같이 실패한다. 여기서 접는다.
            aborted = True
            log(T("log_quota_abort", l=label) + "\n")
            break
        for k, v in got.items():
            if 1 <= k <= len(part):       # v1.7.11: 범위 밖 번호는 버린다
                result[base + k] = v      # 전역 번호로 복원
        if prog:
            prog((ci + 1) / n_chunks, ci + 1, n_chunks)   # 묶음 하나 = 진짜 진행

    # ---------- 2단계: 빠진 줄만 보충 ----------
    #
    #  ★ 한도가 소진된 상태에서는 보충을 시도하지 않는다.
    #    v1.3.1 은 여기서 377줄을 12줄씩 32묶음으로 나눠 전부 재시도했다.
    #    한 묶음당 2회 × 120초 = 128분을 확정된 실패에 썼다.
    missing = [i for i in range(1, total + 1) if not result.get(i)]
    rounds = 0
    while missing and rounds < GAP_FILL_ROUNDS and not aborted:
        rounds += 1
        log(T("log_gap", l=label, n=len(missing), r=rounds) + "\n")
        for b0 in range(0, len(missing), batch):
            raise_if_cancelled()
            idxs = missing[b0:b0 + batch]
            part = [entries[i - 1] for i in idxs]
            try:
                got = _numbered_block(part, provider, api_key, system_fn, log,
                                      label, T("tag_gap", r=rounds), min_match,
                                      attempts=2)
            except QuotaError:
                aborted = True
                log(T("log_quota_abort", l=label) + "\n")
                break
            for k, v in got.items():
                # ★ v1.7.11: k 는 AI 가 매긴 번호다. 범위를 벗어날 수 있다.
                #   2026-08-28 사고: 작은 모델(e2b)이 12개짜리 묶음에 45번을
                #   붙여 보내 idxs[44] 에서 터졌고, 그 예외가 교정 단계 전체를
                #   날렸다. 6블록 중 5블록이 이미 성공한 뒤였는데도 다 버려졌다.
                #     Correction failed (keeping original): list index out of range
                #   범위 밖 번호는 그 줄만 버린다. 어차피 보충 라운드가 다시 채운다.
                if 1 <= k <= len(idxs):
                    result[idxs[k - 1]] = v   # 묶음내 번호 -> 원래 전역 번호
        before = len(missing)
        missing = [i for i in range(1, total + 1) if not result.get(i)]
        if len(missing) >= before:
            break                          # 더 못 줄이면 그만한다 (무한 반복 방지)

    done = total - len(missing)
    log(T("log_chunk_sum", l=label, ok=done, n=total) + "\n")
    if missing:
        log(T("log_still_missing", l=label, n=len(missing)) + "\n")
    return result, done, total


def _chunk_lines_for(provider):
    return EOPT(provider, "lines_chunk")                  # v1.3.2: 엔진 표에서


# ---------------- Claude 교정 ----------------
def correct_with_claude(entries, provider, api_key, lang_code, log, extra="",
                        prog=None, report=None):
    lang_name = LANG_FULLNAME.get(lang_code, "the target language")

    # v1.3: 여기서 전체를 하나의 문자열로 합치지 않는다.
    #       _numbered_chunk_call 이 묶음별로 만들어 보낸다.

    extra_clause = ""
    if extra.strip():
        extra_clause = ("OPERATOR PREFERENCES — the person running this tool added the following instructions. Apply them ONLY where they do not conflict with the strict formatting rules in this prompt (never change the number of lines, never reorder lines, keep timing untouched): "
                        + extra.strip() + " -- END OF OPERATOR PREFERENCES. ")

    # v1.2: 이 단계는 rebuild_from_words 로 문장이 온전해진 "뒤에" 돈다.
    #       토막난 자막이 아니라 완성된 문장을 보므로 문맥 판단이 훨씬 정확하다.
    #       순서를 되돌리지 말 것 (재조립 -> 교정 -> 번역).
    # v1.3: 묶음마다 줄 수가 다르므로 시스템 프롬프트를 그때그때 만든다.
    def system_fn(n):
        return (
            f"You are a subtitle proofreader. The subtitles should be entirely in {lang_name}. "
            f"Each line is a complete sentence, already split correctly — judge each line "
            f"in the context of the lines around it. "
            f"Some lines contain foreign words that were mis-transcribed and "
            f"should be in {lang_name} instead, or contain small transcription errors. "
            f"{extra_clause}"
            f"Fix ONLY: foreign words that should be {lang_name}, clearly mis-heard names or "
            f"terms, obvious typos, and spacing. "
            f"When unsure, prefer leaving text unchanged. "
            f"Do NOT change meaning, do NOT merge or split lines, "
            f"do NOT add or remove lines. Keep the exact same number of lines. "
            f"You will be given exactly {n} numbered lines. "
            f"Return ONLY the corrected lines in the SAME numbered format 'N: text', nothing else."
            f"\n\nBEFORE YOU ANSWER — check your own output:\n"
            f"  (a) Does your reply contain every number from 1 to {n}, exactly once?\n"
            f"  (b) Did any line change meaning, or get reworded beyond a genuine transcription fix?\n"
            f"  (c) Did you accidentally merge, split, reorder or drop a line?\n"
            f"Fix any problems, then output only the final list. Do not show your checking."
        )

    log(T("log_api_call", p=PROVIDERS[provider]["name"]) + "\n")
    corrected, n_done, n_total = _numbered_chunk_call(
        entries, provider, api_key, system_fn, log,
        chunk_lines=_chunk_lines_for(provider), label=lang_name, prog=prog)

    # v1.2: 응답이 일부만 와도 조용히 넘어가지 않고 경고를 남긴다.
    # v1.3: 교정은 '선택적 다듬기'이므로 실패해도 예외를 올리지 않는다.
    #       재조립 결과를 그대로 쓰는 것이 맞다. 다만 로그에는 반드시 남긴다.
    if len(corrected) < len(entries):
        log(T("log_correct_lines_bad", n=len(corrected), t=len(entries)) + "\n")
    if report is not None and not corrected:
        # 한 줄도 못 받았다 = 교정 단계가 사실상 안 돈 것. 끝에 요약으로 알린다.
        report["none"] = True

    changed = 0
    for i, e in enumerate(entries, 1):
        orig = " ".join(e["lines"])
        new = corrected.get(i, "")
        if not new or new == orig:
            continue
        # v1.2: 교정을 빙자한 재작성 차단 — 원문과 너무 다르면 원본을 지킨다.
        if _similar(orig, new) < CORRECT_MIN_SIMILARITY:
            log(T("log_correct_reject", i=i, a=orig, b=new) + "\n")
            continue
        log(f"  #{i}: '{orig}' -> '{new}'\n")
        e["lines"] = [new]; changed += 1
    log(T("log_correct_done", n=changed) + "\n")
    return entries


# =============================================================================
#  추가 요청 단계 (v1.3.7) — 자막이 완성된 뒤 한 번 도는 자유 편집
# =============================================================================
#
#  ★ 이 단계에 안전장치를 새로 만들지 말 것. 그게 이 기능을 망친 원인이다.
#
#    v1.3.6 까지 추가 요청은 재조립·교정·번역 프롬프트에 끼워 넣는 방식이었다.
#    그런데 그 프롬프트들의 대전제가 "줄 수 바꾸지 마, 순서 바꾸지 마, 타이밍
#    건드리지 마" 라서, 구조를 바꾸는 요청은 전부 무시됐다. 유사도 검사까지
#    걸려 있어 텍스트를 크게 고치는 것도 거부됐다.
#
#    사용자가 요청을 직접 적었다는 것 자체가 "고쳐도 된다"는 뜻이다.
#    유사도 검사는 *아무도 시키지 않았는데 AI 가 멋대로 바꾸는 것*을 막는 장치이지,
#    시켜서 하는 일을 막으라고 만든 게 아니다.
#
#  풀어 주는 것:  텍스트 · 줄 수 · 시간 전부 자유. 겹침·역전도 검사하지 않는다.
#  남기는 것:    ① 파싱 실패 시 이전 자막 유지  ② 시간순 정렬
#                — 둘 다 '제약'이 아니라 '처리'다.
#
#  ★ 엔진으로 막지 말 것. 676줄은 로컬 컨텍스트에 안 들어가지만 200줄짜리
#    짧은 영상은 들어간다. 미리 막으면 될 수 있었던 경우까지 막게 된다.
#    해 보고, 안 되면 이유를 알려 준다.
#
#  ★ 실측 타임스탬프 원칙(§0-1)의 유일한 예외다. 2분 공백에 단어 5개만 들렸는데
#    가사 8줄을 넣으려면 나머지 시간은 추정할 수밖에 없다. 여기서만 예외다.

_EXTRA_LINE = re.compile(
    r"^\s*(\d{1,2}):(\d{2}):(\d{2})[.,](\d{1,3})\s*-->\s*"
    r"(\d{1,2}):(\d{2}):(\d{2})[.,](\d{1,3})\s*\|\s*(.+?)\s*$")


def _ms(h, m, s, ms):
    return ((int(h) * 3600 + int(m) * 60 + int(s)) * 1000
            + int(str(ms).ljust(3, "0")[:3]))


_TIME_PAIR = (r"(\d{1,2}):(\d{2}):(\d{2})[.,](\d{1,3})\s*-->\s*"
              r"(\d{1,2}):(\d{2}):(\d{2})[.,](\d{1,3})")
_EX_CHANGE_T = re.compile(r"^\s*CHANGE\s+(\d+)\s*\|\s*" + _TIME_PAIR + r"\s*\|\s*(.+?)\s*$", re.I)
_EX_CHANGE   = re.compile(r"^\s*CHANGE\s+(\d+)\s*\|\s*(.+?)\s*$", re.I)
_EX_DELETE   = re.compile(r"^\s*DELETE\s+(\d+)\s*\.?\s*$", re.I)
_EX_INSERT   = re.compile(r"^\s*INSERT\s+" + _TIME_PAIR + r"\s*\|\s*(.+?)\s*$", re.I)


def _parse_extra_reply(text, n_src=0):
    """'바뀐 것만' 응답을 읽는다 (v1.7.16).

    CHANGE N | text                       글자만 고침
    CHANGE N | 시각 --> 시각 | text        시각까지 고침 (= 옮기기)
    DELETE N                              지움
    INSERT 시각 --> 시각 | text            새로 넣음

    반환: (편집목록, 못읽은줄수). 편집목록은 (종류, 번호, 시작, 끝, 글자).

    ★ 못 읽는 줄은 버린다. 설명문·코드펜스가 섞여 오는 게 흔하다.
    ★ 번호 검사는 여기서 하지 않는다 — 적용할 때 범위를 본다.
      (2026-08-28 에 'AI 가 준 번호를 그대로 믿고 색인' 하다 터진 적이 있다)
    """
    edits, bad = [], 0
    for line in text.split("\n"):
        line = line.strip().strip("`").lstrip("-•* \t")
        if not line or line.upper() == "NONE":
            continue
        m = _EX_CHANGE_T.match(line)
        if m:
            g = m.groups()
            edits.append(("change", int(g[0]), _ms(*g[1:5]), _ms(*g[5:9]), g[9].strip()))
            continue
        m = _EX_INSERT.match(line)
        if m:
            g = m.groups()
            edits.append(("insert", 0, _ms(*g[0:4]), _ms(*g[4:8]), g[8].strip()))
            continue
        m = _EX_DELETE.match(line)
        if m:
            edits.append(("delete", int(m.group(1)), 0, 0, ""))
            continue
        m = _EX_CHANGE.match(line)
        if m:
            edits.append(("change", int(m.group(1)), None, None, m.group(2).strip()))
            continue
        bad += 1
    return edits, bad


def _apply_extra_edits(entries, edits, log=None):
    """편집 목록을 자막에 적용한다. 새 목록을 돌려준다.

    ★ 범위 밖 번호는 그 줄만 버린다. AI 가 준 번호는 믿지 않는다.
    ★ 원본을 고치지 않는다 — 실패해도 호출부가 이전 자막을 지킬 수 있어야 한다.
    """
    out = [dict(e, lines=list(e["lines"])) for e in entries]
    drop = set()
    n_ch = n_del = n_ins = n_skip = 0
    added = []
    for kind, idx, a, b, txt in edits:
        if kind == "insert":
            if txt and b > a:
                added.append({"index": "0", "start_ms": a, "end_ms": b, "lines": [txt]})
                n_ins += 1
            else:
                n_skip += 1
            continue
        if not (1 <= idx <= len(out)):
            n_skip += 1
            continue
        if kind == "delete":
            drop.add(idx - 1)
            n_del += 1
        else:
            e = out[idx - 1]
            if txt:
                e["lines"] = [txt]
            if a is not None and b is not None and b > a:
                e["start_ms"], e["end_ms"] = a, b
            n_ch += 1
    got = [e for i, e in enumerate(out) if i not in drop] + added
    if log:
        log(T("log_extra_edits", c=n_ch, d=n_del, i=n_ins,
              s=(" · " + T("log_extra_skipped", n=n_skip)) if n_skip else "") + "\n")
    return got


# =============================================================================
#  ④ 추가 요청 — 통째로 보내기 / 나눠 보내기 (v1.7.12)
# =============================================================================
#
#  ★ 왜 나눠야 했나
#    이 단계만 자막을 **통째로** 보낸다. 다른 단계는 전부 묶음으로 나눈다.
#    그래서 영상이 길어지면 책상에 안 들어간다 (2026-08-28 계산):
#        16분  자막  230줄 + 단어 1,226개 ->  13,700칸   OK
#        45분  자막  650줄 + 단어 3,450개 ->  37,500칸   OK
#        2시간 자막 1800줄 + 단어 9,200개 -> 100,700칸   책상 65,536 초과
#    45분이 한계였고 그 위는 아예 못 썼다.
#
#  ★ 짧으면 지금처럼 통째로 보낸다. 이게 중요하다.
#    통째로 보내야만 되는 요청이 있다 — "3분 대사를 12분으로 옮겨",
#    "중복된 줄을 전부 찾아 지워" 같은 것. 들어가는 한 그 능력을 뺏지 않는다.
#    §6-1 "제약을 만들지 말 것" 은 여기서도 유효하다.
#
#  ★ 안 들어갈 때만 나눈다. 그때 포기하는 것은 '전역 재배치' 하나뿐이고,
#    실제 요청의 대부분(이름 표기, 빠진 대사 넣기, 문장 다듬기)은 국소 편집이라
#    나눠도 그대로 된다.
#
#  ★ 앞뒤를 겹쳐서 보낸다(EXTRA_OVERLAP). 경계에 걸친 문장을 AI 가 보고
#    판단할 수 있어야 한다. 다만 **결과는 겹치지 않는 구간만 취한다** —
#    안 그러면 같은 줄이 두 묶음에서 와서 중복된다.
#
#  ★★ v1.7.17: 받아쓴 단어 목록(_extra_words_block)을 **뺐다.**
#    v1.3.7 에서 "2분 공백에 가사 8줄을 넣으려면 들린 단어를 기준점으로
#    삼아야 한다" 는 이유로 넣었는데, v1.5.0 에 ⑤ 노래 단계가 생기면서
#    그 일은 거기로 갔다(보컬 분리 후 다시 받아쓰기 — 추정이 아니라 실측).
#    남은 일(이름 고치기·빠진 대사 넣기·시각 옮기기)에는 쓸모가 없다.
#    빠진 대사는 whisper 가 못 들은 것이라 단어 목록에도 없다.
#
#    그런데 **보내는 양의 절반**을 차지하고 있었다 (자막 31,000 / 단어 31,000).
#    2026-08-29 배치에서 13개 중 9개가 여기서 죽은 원인의 절반이 이것이다.
EXTRA_OVERLAP = 20        # 앞뒤로 몇 줄을 참고용으로 더 보낼 것인가


def apply_extra_request(entries, provider, api_key, log, extra, all_words):
    """사용자의 추가 요청대로 완성 자막을 다시 손본다.

    들어가면 통째로, 안 들어가면 시간 순으로 나눠서 보낸다.
    성공하면 새 entries, 실패하면 예외. 호출부는 예외를 받으면
    이전 자막을 유지하고 번역으로 넘어가지 않는다."""
    if not entries:
        return entries

    # ★★ v1.7.17: 한 번에 보내는 줄 수에 상한을 둔다.
    #
    #   그전에는 '책상에 들어가면 통째로' 였다. 850줄이 그 기준을 통과했고,
    #   2026-08-29 배치 13개 중 **9개가 여기서 죽었다**:
    #       Local AI sent nothing for 300s          5분 동안 한 글자도 안 나옴
    #       the reply was not in the expected form  형식을 무시하고 통째로 다시 씀
    #   같은 파일에서 500줄씩 나눠 보내는 교정 단계는 13개 전부 성공했다.
    #
    #   자리에 들어가는 것과 AI 가 제대로 해내는 것은 다르다.
    #   읽을 게 많으면 읽는 데만 5분이 걸리고, 다 읽고 나면 맨 앞의 지시를
    #   놓쳐서 형식을 깬다. **교정과 같은 줄 수(lines_chunk)로 맞춘다.**
    step = max(50, _chunk_lines_for(provider))

    if len(entries) <= step:
        got = _extra_once(entries, provider, api_key, log, extra, all_words)
        log(T("log_extra_done", a=len(entries), b=len(got)) + "\n")
        return got

    # ---- 나눠 보내기 ------------------------------------------------
    n_parts = (len(entries) + step - 1) // step
    log(T("log_extra_split", n=n_parts, s=step) + "\n")

    out = []
    failed = 0
    for pi in range(n_parts):
        a, b = pi * step, min(len(entries), (pi + 1) * step)
        lo = max(0, a - EXTRA_OVERLAP)
        hi = min(len(entries), b + EXTRA_OVERLAP)
        part = entries[lo:hi]
        log(T("log_extra_part", i=pi + 1, n=n_parts, a=len(part)) + "\n")
        # ★ 한 묶음이 실패해도 전부를 버리지 않는다.
        #   2시간짜리에서 4묶음 중 하나가 튕겼다고 나머지 셋의 결과까지
        #   버리는 건 손해가 너무 크다. 그 구간만 원본으로 두고 넘어간다.
        #   (요청의 대부분은 국소 편집이라 구간별로 독립적이다)
        try:
            got = _extra_once(part, provider, api_key, log, extra, all_words)
        except CancelledError:
            raise
        except Exception as pe:
            log(T("log_extra_part_fail", i=pi + 1, n=n_parts,
                  e=str(pe).replace("\n", " ")[:120]) + "\n")
            out.extend(entries[a:b])
            failed += 1
            continue

        # ★ 참고용으로 겹쳐 보낸 부분은 버리고 '내 구간' 만 취한다.
        #   첫/마지막 묶음은 바깥쪽 경계를 열어 둔다 (AI 가 끝에 줄을 더할 수 있다).
        s_lim = entries[a]["start_ms"] if a > 0 else -1
        e_lim = entries[b]["start_ms"] if b < len(entries) else float("inf")
        out.extend(g for g in got if s_lim <= g["start_ms"] < e_lim)

    if failed >= n_parts:
        raise RuntimeError(f"every part failed ({failed}/{n_parts})")
    if failed:
        log(T("log_extra_part_kept", n=failed, t=n_parts) + "\n")
    if not out:
        raise RuntimeError("no usable subtitle lines came back from any part")
    out.sort(key=lambda e: e["start_ms"])
    for i, e in enumerate(out, 1):
        e["index"] = str(i)
        e["time"] = (f"{fmt_time(e['start_ms'] / 1000.0)} --> "
                     f"{fmt_time(e['end_ms'] / 1000.0)}")
    log(T("log_extra_done", a=len(entries), b=len(out)) + "\n")
    return out


def _extra_subs_block(entries):
    return "\n".join(
        f"{fmt_time(e['start_ms'] / 1000.0)} --> {fmt_time(e['end_ms'] / 1000.0)} | "
        f"{' '.join(e['lines'])}"
        for e in entries)


def _extra_once(entries, provider, api_key, log, extra, all_words):
    """추가 요청 한 번. 통째로든 한 묶음이든 이 함수가 실제 호출을 맡는다.

    ★★ v1.7.16: **바뀐 것만 받는다.** 전체를 다시 써 달라고 하지 않는다.

      2026-08-29 사고: 자막 851줄(약 55,000자)을 보내고 "전부 다시 써라" 고
      했더니, AI 가 **64,212자를 쓰고도 51분 중 29분까지밖에 못 갔다.**
      끝까지 가려면 115,000자가 필요한데 출력 한도가 그 절반이었다.
      이름 두 개 고쳐 달라는 요청이었는데도 851줄을 처음부터 다 쓴 것이다.

      답의 크기가 **영상 길이**에 비례하니 긴 영상에서는 구조적으로 실패한다.
      고칠 것만 받으면 답의 크기가 **고칠 양**에 비례한다 — 영상이 아무리
      길어도 이름 두 개면 스무 줄이다.

    ★ 보내는 것은 그대로 전부 보여준다. 이게 중요하다.
      자막을 잘라 보내면(나눠 보내기) AI 가 다른 구간을 못 봐서
      "3분 대사를 12분으로 옮겨" 같은 요청이 불가능해진다.
      **전부 보여주고 답만 짧게 받으면** 그 능력을 잃지 않는다.

    ★ 시각도 고칠 수 있다. CHANGE 에 시각을 함께 적으면 그 줄이 옮겨진다.
      마지막에 시간순으로 다시 정렬하므로 순서가 바뀌어도 문제없다.
    """
    subs = "\n".join(
        f"{i}. {fmt_time(e['start_ms'] / 1000.0)} --> {fmt_time(e['end_ms'] / 1000.0)} | "
        f"{' '.join(e['lines'])}"
        for i, e in enumerate(entries, 1))

    system = (
        "You are editing a finished subtitle file. The operator has a request; do what they ask.\n\n"
        "You are given:\n"
        "  [SUBTITLES] the current subtitles, numbered, as 'N. start --> end | text'\n\n"
        "Do NOT return the whole file. Return ONLY the edits you want made, one per line,\n"
        "using exactly these three forms:\n\n"
        "  CHANGE N | text\n"
        "      replace the text of subtitle N, keeping its timing\n"
        "  CHANGE N | 00:01:23,450 --> 00:01:25,900 | text\n"
        "      replace both the timing and the text of subtitle N (use this to move a line)\n"
        "  DELETE N\n"
        "      remove subtitle N\n"
        "  INSERT 00:01:23,450 --> 00:01:25,900 | text\n"
        "      add a new subtitle at that time\n\n"
        "N is the number shown in [SUBTITLES]. Nothing is off limits — you may change text,\n"
        "move lines in time, delete them, and add new ones. When you add a line, put it in\n"
        "the gap between the subtitles around it.\n\n"
        "Leave every other line alone — say nothing about lines you are not changing.\n"
        "If nothing needs changing, reply with the single word NONE.\n"
        "No commentary, no code fences, no numbering of your own.\n\n"
        "OPERATOR REQUEST:\n" + extra.strip())

    user = f"[SUBTITLES]\n{subs}"

    # 넘칠 것 같으면 미리 알려만 준다. 막지는 않는다 — 추정이 틀릴 수 있다.
    if provider == "local":
        est = _est_tokens(system) + _est_tokens(user)
        if est > local_num_ctx() * 0.9:
            log(T("log_extra_big", e=f"{est:,}", c=f"{local_num_ctx():,}") + "\n")

    log(T("log_extra_call", n=len(entries)) + "\n")

    # -----------------------------------------------------------------
    #  ★ v1.7.9: '하다 만 답' 을 걸러낸다. 줄 수는 세지 않는다.
    #
    #  2026-08-28 사고: ④ 를 처음 켜고 돌렸더니 **마지막 80초가 통째로 사라졌다.**
    #      _en_words  1226단어 -> 15:53   정상
    #      _nosong     218줄   -> 15:52   정상 (노래 단계 직전)
    #      최종        218줄   -> 14:32   엔딩 인사까지 18줄이 없다
    #    노래 단계가 31줄을 넣고 13줄을 지워 236줄이 됐는데, 여기서 218줄만
    #    돌아왔다. 검사가 `len(got) < 1` 하나뿐이라 그대로 저장됐다.
    #
    #  ★ 줄 수로 막으면 안 된다. §6-1 대로 이 단계는 합치고 나누고 지우는 것이
    #    **허용돼야 한다.** 그게 추가 요청의 존재 이유다.
    #    하지만 "AI 가 줄을 지운 것" 과 "AI 가 답을 하다 만 것" 은 다르다.
    #    구별되는 지점은 **시간 범위**다. 요청대로 편집했다면 끝 시각은
    #    비슷하게 남는다. 출력 한도에 걸려 끊기면 뒤쪽이 통째로 비어 버린다.
    #
    # -----------------------------------------------------------------
    #  ★ v1.7.16: '잘렸는지' 를 시각으로 재던 검사를 없앴다.
    #    전체를 다시 쓰게 하던 시절에는 "끝 시각이 원본보다 한참 이르다" 가
    #    잘림의 신호였다. 이제는 바뀐 것만 받으므로 **답이 짧은 게 정상**이다.
    #    이름 두 개 고치는 요청이면 스무 줄만 온다.
    #    남은 실패는 "형식을 아예 못 읽는 답" 하나뿐이고, 그건 아래에서 본다.
    got = None
    why = ""
    for attempt in range(1, EXTRA_RETRIES + 2):
        raise_if_cancelled()
        reply = ai_call(provider, api_key, system, user,
                        max_tokens=EOPT(provider, "max_tokens_cap"), log=log)
        edits, bad = _parse_extra_reply(reply, len(entries))

        if edits:
            got = _apply_extra_edits(entries, edits, log)
            if attempt > 1:
                log(T("log_extra_retry_ok", a=attempt) + "\n")
            break

        # 편집이 하나도 없다 — 두 가지 경우를 구분한다
        if bad <= 2 and len(reply.strip()) < 400:
            # "NONE" 이나 그에 가까운 짧은 답. 고칠 게 없다는 뜻이다.
            log(T("log_extra_none") + "\n")
            got = [dict(e, lines=list(e["lines"])) for e in entries]
            break

        why = T("extra_bad_format", n=bad, c=len(reply))
        if attempt <= EXTRA_RETRIES:
            log(T("log_extra_retry", w=why, a=attempt) + "\n")

    if got is None:
        # ★ 원본을 그대로 돌려주지 말 것. 호출부가 예외를 받아야
        #   "추가 요청은 못 했지만 자막은 멀쩡하다" 를 로그에 남긴다.
        raise RuntimeError(f"extra request could not be understood — {why}")

    got.sort(key=lambda e: e["start_ms"])      # SRT 는 시간순 파일이다
    for i, e in enumerate(got, 1):
        e["index"] = str(i)
        e["time"] = (f"{fmt_time(e['start_ms'] / 1000.0)} --> "
                     f"{fmt_time(e['end_ms'] / 1000.0)}")
    return got


# ---------------- Claude 번역 ----------------
def translate_with_claude(src_entries, provider, api_key, target_code, log, extra="", source_name="English", prog=None):
    """기준 자막을 target_code 언어로 번역 (타이밍/줄 수 유지, 텍스트만 교체)."""
    target_name = LANG_FULLNAME.get(target_code, target_code)

    extra_clause = ""
    if extra.strip():
        extra_clause = ("OPERATOR PREFERENCES — the person running this tool added the following instructions. Apply them ONLY where they do not conflict with the strict formatting rules in this prompt (never change the number of lines, never reorder lines, keep timing untouched): "
                        + extra.strip() + " -- END OF OPERATOR PREFERENCES. ")

    def system_fn(n):
        return (
            f"You are a professional subtitle translator for a children's educational animation. "
            f"Translate each {source_name} subtitle line into natural, age-appropriate {target_name}. "
            f"{extra_clause}"
            f"These are subtitles including song lyrics and dialogue — keep translations concise "
            f"so they fit on screen, natural for children, and matching the tone of the original. "
            f"For song lyrics, prioritize natural {target_name} phrasing over literal word-for-word. "
            f"Do NOT merge or split lines, do NOT add or remove lines. "
            f"You will be given exactly {n} numbered lines. "
            f"Keep the EXACT same number of lines and the same line numbers. "
            f"Return ONLY the translated lines in the SAME numbered format 'N: text', nothing else."
            f"\n\nBEFORE YOU ANSWER — check that your reply contains every number "
            f"from 1 to {n}, exactly once, each followed by {target_name} text. "
            f"Do not show your checking."
        )

    log(T("log_tr_call", l=target_name) + "\n")
    translated, n_done, n_total = _numbered_chunk_call(
        src_entries, provider, api_key, system_fn, log,
        chunk_lines=_chunk_lines_for(provider), label=target_name, prog=prog)

    # ---------------------------------------------------------------
    # ★ v1.3: 한 묶음도 못 건졌으면 예외를 올린다. 절대 원문을 돌려주지 말 것.
    #
    #   v1.2 는 매칭이 0줄이어도 원문을 그대로 반환했고, 호출부는 그것을 성공으로
    #   보고 저장했다. 그래서 한국어가 그대로 담긴 파일이 '_en.srt' 라는 이름으로
    #   만들어졌다. 사용자는 파일이 생긴 것을 보고 성공한 줄 안다 —
    #   그냥 실패하는 것보다 나쁘다. 호출부의 except 는 이미 올바르게 짜여 있으니
    #   여기서 실패를 실패라고 말해 주기만 하면 된다.
    # ---------------------------------------------------------------
    raise_if_cancelled()      # v1.3: 취소를 '번역 실패'로 잘못 보고하지 않도록 먼저 확인
    if n_done == 0:
        log(T("log_tr_dead") + "\n")
        raise RuntimeError(
            f"translation produced no usable lines (0 of {n_total})")

    out = []
    for i, e in enumerate(src_entries, 1):
        new_e = {k: v for k, v in e.items()}
        if translated.get(i):
            new_e["lines"] = [translated[i]]
        out.append(new_e)
    missing = len(src_entries) - len(translated)
    if missing > 0:
        log(T("log_tr_missing", n=missing) + "\n")
    log(T("log_tr_done", n=len(translated)) + "\n")
    return out


# ---------------- AI API 호출 (v1.1: Gemini/Qwen/Claude 공용, SDK 없이 REST) ----------------
class HttpFail(RuntimeError):
    """HTTP 오류. code 를 보고 '다음 모델로 넘길지'를 판단할 수 있게 담아 둔다."""
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code



def _http_reason(code):
    """로그에 쓸 짧은 이유. 429 와 503 을 뭉뚱그리지 않기 위한 것."""
    return {429: T("why_429"), 500: T("why_5xx"), 502: T("why_5xx"),
            503: T("why_503"), 529: T("why_503")}.get(code, T("why_other"))



def _brief_error(body, limit=160):
    """
    로그에 찍을 짧은 오류 문구.

    ★ 구글이 보내는 429 응답은 JSON 통짜라, 그대로 찍으면 로그에 중괄호와
      따옴표가 열 줄씩 쏟아진다 (2026-08-23). 사람이 읽을 부분은 message 하나뿐이다.
    ★ 판별(_is_daily_quota)은 전체 본문으로 한다 — 여기서 줄이는 건 표시용이다.
    """
    txt = body or ""
    try:
        import json as _j
        d = _j.loads(txt)
        m = (d.get("error") or {}).get("message")
        if m:
            txt = str(m)
    except Exception:
        pass
    txt = " ".join(txt.split())          # 줄바꿈·연속 공백 정리
    return txt[:limit] + ("..." if len(txt) > limit else "")


def _post_json(url, payload, headers, timeout=180, log=None, retries=3,
               provider=None, quota_fast_fail=False):
    """POST 요청. 일시적 오류는 대기 후 자동 재시도.

    v1.3.2: provider 를 받아 엔진별 정책(재시도 대상 코드, 한도 처리)을 따른다.
            provider=None 이면 v1.3.1과 똑같이 동작한다."""
    import urllib.request
    import urllib.error
    data = json.dumps(payload).encode("utf-8")
    waits = [20, 40, 60]  # 재시도 대기(초) — 무료 티어 분당 한도 회복용
    retry_codes = (EOPT(provider, "retry_codes") if provider
                   else (429, 500, 502, 503, 529))
    guard = bool(provider) and EOPT(provider, "quota_guard")
    last_err = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = ""
            try:
                # ★ 2000자까지 읽는다. 300자로 자르지 말 것.
                #   구글의 429 응답은 앞부분이 일반 안내문이고, '분당인지 일일인지'를
                #   알려 주는 quota metric 이름이 그 뒤에 온다. 300자에서 자르면
                #   하필 그 부분이 날아가 _is_daily_quota() 가 항상 False 를 돌려준다.
                #   그래서 일일 한도인데도 20/40/60초를 헛되이 기다렸다 (2026-08-20 사고).
                #   로그에 찍을 때만 짧게 줄인다 — 판별은 전체 본문으로 한다.
                body = e.read().decode(errors="ignore")[:2000]
            except Exception:
                pass
            # 판별은 위의 전체 body 로, 로그·예외 메시지는 짧게
            brief = _brief_error(body)
            last_err = HttpFail(e.code, f"{e.code} {e.reason}: {brief}")

            # ---- 한도 오류: quota_guard 를 켠 엔진에서만 특별 취급 ----------
            #   ★ 이 분기는 Gemini 에만 들어온다. Claude 는 표에서 꺼져 있고,
            #     로컬은 애초에 _post_json 을 쓰지 않는다(스트리밍을 쓴다).
            if guard and e.code == 429:
                if _is_daily_quota(body):
                    # 일일 한도 — 20/40/60초를 기다려도 오늘은 안 풀린다.
                    # 기다리는 것 자체가 순손해라 바로 올린다.
                    raise QuotaError(f"429 daily quota: {brief}", daily=True) from None
                # ★ 쓸 수 있는 다른 모델이 남아 있으면 기다리지 않는다.
                #   분당 한도는 모델별로 따로 센다(§8). 20+40+60초를 기다리느니
                #   다음 모델로 바로 넘어가는 쪽이 거의 항상 빠르다.
                #   2026-08-23 실측: gemini-flash-latest 가 매번 막혀
                #   재조립 2분 55초 중 2분이 순수 대기였다. 넘어가자 바로 성공.
                #   마지막 모델까지 갔을 때는 예전대로 기다렸다 다시 시도한다.
                if quota_fast_fail:
                    raise QuotaError(f"429 rate limit: {brief}", daily=False) from None
                if attempt < retries:
                    w = waits[min(attempt, len(waits) - 1)]
                    if log:
                        log(T("log_http_wait", c=429, k=_http_reason(429),
                              s=w, i=attempt + 1, n=retries) + "\n")
                    time.sleep(w)
                    continue
                raise QuotaError(f"429 rate limit: {brief}", daily=False) from None

            # ★ 429 만이 아니다. 503(서버 과부하) 도 여기로 온다.
            #   매뉴얼 §8: "429 와 503 은 다른 것" — 429 는 내가 너무 빨리 보낸 것,
            #   503 은 구글 서버가 바쁜 것이다. 503 은 기다린다고 내 차례가
            #   돌아오지 않는다. 게다가 새 모델일수록 사람이 몰려 503 이 잦다.
            #   → 쓸 수 있는 다른 모델이 남아 있으면 여기서도 기다리지 않는다.
            #
            # ★★ v1.7.5: 여기서 반드시 last_err(HttpFail) 를 던질 것.
            #   `raise e` 로 원본 HTTPError 를 던지면 안 된다.
            #   받는 쪽(_call_gemini)은 `except HttpFail` 로만 잡는데
            #   HTTPError 는 HttpFail 이 아니라서 **전환 코드를 그냥 지나쳤다.**
            #
            #   2026-08-27 실측 로그가 이걸 그대로 보여 준다. 503 이 열 번 넘게
            #   났는데 "switching to" 는 한 번뿐이었다 — 그 한 번은 429(QuotaError)
            #   경로였고, 503 은 전부 다음 모델을 못 가 보고 블록째 포기했다.
            #   v1.7.4 에서 후보를 4개로 늘린 것이 통째로 무용지물이었다.
            #
            #   ★ 이 파일에서 예외를 새로 던질 때는 항상 HttpFail 인지 확인할 것.
            #     종류가 다르면 조용히 안 잡히고, 로그에는 실패만 남는다.
            if e.code in retry_codes and quota_fast_fail:
                raise last_err from None
            if e.code in retry_codes and attempt < retries:
                w = waits[min(attempt, len(waits) - 1)]
                if log:
                    log(T("log_http_wait", c=e.code, k=_http_reason(e.code),
                          s=w, i=attempt + 1, n=retries) + "\n")
                time.sleep(w)
                continue
            raise last_err from None
        except urllib.error.URLError as ue:
            if "11434" in url or "127.0.0.1" in url:
                raise RuntimeError(f"local AI server not reachable ({ue.reason})") from None
            raise RuntimeError(f"network error: {ue.reason}") from None
    raise last_err


# =============================================================================
#  엔진별 호출 함수
#
#  ★ 각 함수는 자기 엔진만 안다. 다른 엔진을 신경 쓰지 않는다.
#    새 엔진을 붙일 때는 아래 형식으로 함수 하나를 더 쓰고
#    ENGINES 표에 항목을 추가하면 끝이다.
#
#    시그니처:  fn(api_key, system, user_text, max_tokens, log) -> str
# =============================================================================

@engine_call("claude")
def _call_claude(api_key, system, user_text, max_tokens, log=None):
    """Anthropic Messages API. 유료라 한도가 넉넉해 간격·차단기가 없다."""
    data = _post_json(
        "https://api.anthropic.com/v1/messages",
        {"model": ENGINES["claude"]["model"], "max_tokens": max_tokens,
         "system": system,
         "messages": [{"role": "user", "content": user_text}]},
        {"x-api-key": api_key, "anthropic-version": "2023-06-01",
         "content-type": "application/json"},
        log=log, provider="claude")
    return "".join(b.get("text", "") for b in data.get("content", [])
                   if b.get("type") == "text")


@engine_call("gemini")
def _call_gemini(api_key, system, user_text, max_tokens, log=None):
    """Google Generative Language API.

    ★ 대체 모델 전환 조건이 v1.3.1보다 넓다.
      예전에는 404(모델 없음)에서만 다음 후보로 넘어갔다. 그래서
      gemini-3-flash 가 503(과부하)이면 2.5-flash 는 멀쩡한데도 그냥 죽었다.
      이제 fallback_codes(404/429/5xx) 전부에서 다음 후보를 시도한다.

    ★ v1.7.6: 순서를 바꾸지 않는다. 표에 적힌 대로 위에서 아래로만 내려간다."""
    models = list(EOPT("gemini", "models") or [ENGINES["gemini"]["model"]])

    # ★ 이번 실행에서 한도가 소진된 모델은 건너뛴다.
    #   하루 20회뿐이라 "어차피 실패할 모델"에 한 번 던지는 것도 아깝다.
    #   이게 없으면 소진된 모델을 매 요청마다 먼저 시도해 요청을 계속 태운다.
    alive = [m for m in models if m not in _GEMINI_DEAD]
    if alive:
        models = alive
    # ★ v1.7.6: 성공한 모델을 앞으로 끌어올리던 것을 없앴다.
    #   **항상 표에 적힌 순서대로 간다** — latest 부터, 실패하면 한 칸씩 아래로.
    #
    #   2026-08-27 로그가 왜 문제인지 보여 준다.
    #       switching to gemini-3.6-flash      (블록1: latest 실패 -> 3.6 성공)
    #       switching to gemini-flash-latest   (블록2: 3.6 이 1순위가 됨 -> 실패 -> 되돌아감)
    #       switching to gemini-3.5-flash
    #   3.6 이 한 번 성공했다고 1순위가 되니, 다음 블록에서 순서가 뒤엉켰다.
    #
    #   표의 순서는 **품질 순서**다(⑲). 앞이 될 때는 앞을 써야 한다.
    #   503 은 몇 초 만에도 풀렸다 막혔다 하므로, 한 번 막혔다고 그 모델을
    #   뒤로 미루면 더 좋은 모델을 쓸 기회를 계속 놓친다.
    #
    #   ★ _GEMINI_DEAD(일일 한도 소진)는 그대로 둔다. 그건 오늘 안 풀린다 —
    #     매번 다시 두드리면 요청만 버린다. "잠깐 막힘"과 "오늘 끝"은 다르다.
    #   ★ 순서를 바꾸는 코드를 다시 넣지 말 것.
    fallback = EOPT("gemini", "fallback_codes")
    last = None
    for mi, model in enumerate(models):
        has_next = mi + 1 < len(models)
        try:
            data = _gemini_generate(model, api_key, system, user_text, max_tokens,
                                    log, fast_fail=has_next)
            try:
                return "".join(pt.get("text", "")
                               for pt in data["candidates"][0]["content"]["parts"])
            except (KeyError, IndexError):
                raise RuntimeError(f"unexpected Gemini response: {str(data)[:200]}")

        except QuotaError as qe:
            last = qe
            if qe.daily:
                _GEMINI_DEAD.add(model)   # 오늘 이 모델은 끝. 다시 시도하지 않는다
            # ★ 분당·일일 한도 모두 '모델별'로 따로 센다 — 프로젝트 단위가 아니다.
            #   2026-08-21 콘솔 확인: 같은 날 2.5 Flash 27회 / 3.6 Flash 21회로
            #   각각 따로 집계돼 있었다. 즉 한 모델이 소진돼도 다른 모델은 살아 있다.
            if has_next:
                if log:
                    log(T("log_engine_switch", m=models[mi + 1]) + "\n")
                pace_engine("gemini", log)
                continue
            raise
        except HttpFail as he:
            last = he
            # 404 = 그 모델이 은퇴했다. 구글이 대체 모델명을 알려 주므로 로그에 남긴다.
            if he.code == 404 and log:
                hint = _retired_model_hint(str(he))
                log(T("log_model_retired", m=model,
                      n=hint or T("log_model_unknown")) + "\n")
            if he.code in fallback and has_next:
                if log:
                    log(T("log_engine_switch", m=models[mi + 1]) + "\n")
                pace_engine("gemini", log)
                continue
            raise
    raise last


def _gemini_generate(model, api_key, system, user_text, max_tokens, log=None,
                     fast_fail=False):
    """Gemini 한 모델에 한 번 요청한다.

    ★ 사고(thinking) 설정은 모델마다 받는 이름이 다르다. 통하는 것을 찾아
      기억해 두고, 다음부터는 바로 그것만 쓴다 (THINK_MODES 주석 참고).
      400 INVALID_ARGUMENT 는 '그 설정을 못 알아들었다'는 신호로 보고 다음 방식을 시도한다."""
    url = (f"https://generativelanguage.googleapis.com/v1beta/"
           f"models/{model}:generateContent")
    headers = {"x-goog-api-key": api_key, "content-type": "application/json"}

    start = _GEMINI_THINK.get(model, 0)
    order = list(range(start, len(THINK_MODES))) + list(range(0, start))
    last_400 = None
    for idx in order:
        name, think = THINK_MODES[idx]
        gen = {"maxOutputTokens": max_tokens}
        gen.update(think)
        try:
            data = _post_json(
                url,
                {"systemInstruction": {"parts": [{"text": system}]},
                 "contents": [{"role": "user", "parts": [{"text": user_text}]}],
                 "generationConfig": gen},
                headers, log=log, provider="gemini",
                quota_fast_fail=fast_fail)
            if _GEMINI_THINK.get(model) != idx:
                _GEMINI_THINK[model] = idx        # 통했다 — 이 방식을 기억한다
                if log and idx != 0:
                    log(T("log_think_mode", m=model, k=name) + "\n")
            return data
        except HttpFail as he:
            # 400 만 '설정을 못 알아들었다'로 본다. 404·429·5xx 는 설정 문제가 아니다.
            if he.code != 400:
                raise
            last_400 = he
            if log:
                log(T("log_think_retry", m=model, k=name) + "\n")
            pace_engine("gemini", log)
    raise last_400


@engine_call("local")
def _call_local(api_key, system, user_text, max_tokens, log=None):
    """Ollama /api/chat 스트리밍.

    v1.2: 통짜 POST(timeout=180)는 응답이 다 올 때까지 화면이 멈췄고, 느린
    GPU에서 180초를 넘기면 "서버에 연결할 수 없음"이라는 엉뚱한 에러가 났다.
    스트리밍이면 총 시간 제한이 사라지고 진행 상황도 실시간으로 보인다.
    (api_key 는 쓰지 않는다 — 내 컴퓨터에서 돌기 때문)"""
    return _local_chat_stream(system, user_text, max_tokens, log=log,
                              read_timeout=LOCAL_READ_TIMEOUT)


def ai_call(provider, api_key, system, user_text, max_tokens=8000, log=None,
            over_cap=False):
    """엔진 이름으로 호출 함수를 찾아 넘긴다.

    ★ 여기에 `if provider == ...` 를 추가하지 말 것.
      엔진별 처리는 각 호출 함수 안에, 엔진별 값은 ENGINES 표에 둔다."""
    fn = ENGINE_CALLS.get(provider)
    if fn is None:
        raise ValueError(f"unknown engine: {provider}")
    # ★ v1.7.13: over_cap=True 면 표의 상한을 넘겨 보낼 수 있다.
    #   2026-08-28 사고: ⑤ 가 잘려서 출력 몫을 48,000 으로 올려 다시 물어봤는데
    #   여기서 32,000 으로 도로 깎여 **똑같은 답이 두 번 왔다**(글자 수까지 같았다).
    #   252초를 확정된 실패에 썼다. 늘려서 재시도하는 쪽이 상한을 넘길 수 있어야
    #   그 재시도가 의미가 있다.
    #   ★ 기본값은 그대로 두어야 한다. 아무 데서나 넘기면 엔진이 오류를 낸다.
    cap = EOPT(provider, "max_tokens_cap")
    limit = max_tokens if over_cap else min(max_tokens, cap)
    pace_engine(provider, log)          # min_interval=0 인 엔진은 그냥 통과한다
    out = fn(api_key, system, user_text, limit, log=log)
    note_quota_ok()                     # 성공했으니 연속 실패 기록을 지운다
    return out


def _human_bytes(n):
    """1234567 -> '1.2MB'"""
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f}{unit}" if unit in ("B", "KB") else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def _stream_ndjson(url, payload, read_timeout, log=None, stall_key=None):
    """POST 후 NDJSON(한 줄에 JSON 하나)을 오는 대로 하나씩 넘겨주는 제너레이터.

    read_timeout 은 '한 줄과 다음 줄 사이' 제한이지 전체 작업 제한이 아니다.
    따라서 오래 걸리는 작업이라도 데이터가 계속 오는 한 끊기지 않는다."""
    import urllib.request
    import urllib.error
    import socket
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"}, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=read_timeout)
    except (socket.timeout, TimeoutError):
        # 서버가 연결은 받아 놓고 응답 헤더를 안 주는 상태 (모델 로딩 중 등).
        # URLError 가 아니므로 아래 except 로 안 잡힌다 — 반드시 따로 처리할 것.
        if log and stall_key:
            log("\n" + T(stall_key, s=read_timeout) + "\n")
        raise RuntimeError(f"local AI did not respond within {read_timeout}s") from None
    except urllib.error.HTTPError as he:
        body = ""
        try:
            body = he.read().decode(errors="ignore")[:200]
        except Exception:
            pass
        raise RuntimeError(f"local AI error {he.code}: {body or he.reason}") from None
    except (urllib.error.URLError, OSError) as ue:
        reason = getattr(ue, "reason", ue)
        raise RuntimeError(f"local AI server not reachable ({reason})") from None
    with resp:
        while True:
            try:
                line = resp.readline()
            except (socket.timeout, TimeoutError):
                if log and stall_key:
                    log("\n" + T(stall_key, s=read_timeout) + "\n")
                raise RuntimeError(f"local AI sent nothing for {read_timeout}s") from None
            except OSError as oe:
                raise RuntimeError(f"local AI connection lost ({oe})") from None
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line.decode("utf-8", "ignore"))
            except json.JSONDecodeError:
                continue


def pull_local_model(model, log, read_timeout=120):
    """Ollama /api/pull 을 스트리밍으로 호출해 진행률을 로그에 표시한다.

    v1.2: 예전에는 `ollama pull` 을 subprocess 로 돌리면서 stdout/stderr 를 DEVNULL 로
    버렸다. 9GB 를 아무 표시 없이 받으니 멈춘 것처럼 보였다. HTTP 로 직접 받으면
    받은 바이트/전체 바이트가 그대로 넘어와 정확한 %를 보여줄 수 있다.

    ★ v1.7.4: 진행률을 **조각별이 아니라 전체 기준**으로 센다.
      Ollama 는 모델을 여러 조각(layer)으로 나눠 보내고, 조각마다
      total/completed 를 처음부터 다시 보낸다. 예전 코드는 그 값을 그대로 썼다.
      2026-08-27 실측 로그:
          downloading gemma4:26b ... 3.0%  (486.8MB / 15.8GB)   <- 본체 조각
          downloading gemma4:26b ... 100.0% (440.4MB / 440.4MB)  <- 딸린 작은 조각
      15.8GB 중 3% 를 받다가 갑자기 100% 로 끝난 것처럼 보인다.
      조각을 digest 로 구분해 각각의 최신값을 기억하고 전부 더해서 보여준다."""
    last_shown = -1.0
    last_step = ""
    seen = {}          # {digest: [받은 바이트, 전체 바이트]} — 조각별 최신값
    _anon = 0          # digest 를 안 주는 조각용 일련번호
    for msg in _stream_ndjson(f"{OLLAMA_URL}/api/pull",
                              {"model": model, "stream": True},
                              read_timeout, log=log, stall_key="log_local_stall"):
        if msg.get("error"):
            raise RuntimeError(str(msg["error"])[:200])
        status = str(msg.get("status") or "")
        total = msg.get("total") or 0
        done = msg.get("completed") or 0
        if total:
            key = msg.get("digest") or ""
            if not key:
                # digest 가 없으면 크기로 조각을 구분한다 (같은 크기면 같은 조각)
                key = "size:%d" % total
            prev = seen.get(key)
            if prev is None:
                _anon += 1
                seen[key] = [done, total]
            else:
                # 되돌아가는 값은 무시한다 (재시도로 0 부터 다시 오는 경우)
                prev[0] = max(prev[0], done)
                prev[1] = max(prev[1], total)
            all_done = sum(v[0] for v in seen.values())
            all_total = sum(v[1] for v in seen.values())
            pct = all_done * 100.0 / all_total if all_total else 0.0
            # ★ 아직 안 온 조각이 있을 수 있으니 스트림이 끝나기 전에는 100% 를
            #   찍지 않는다. 100% 를 본 뒤에도 계속 받는 모습이 제일 헷갈린다.
            #   진짜 완료는 아래 log_pull_done 한 줄이 맡는다.
            pct = min(pct, 99.9)
            # 0.5% 이상 움직였을 때만 갱신 (로그 폭주 방지)
            if pct - last_shown >= 0.5 or all_done >= all_total:
                last_shown = pct
                log("\r" + T("log_pull_pct", m=model, p=f"{pct:.1f}",
                             d=_human_bytes(all_done),
                             t=_human_bytes(all_total), e=""))
        elif status and status != last_step:
            last_step = status
            log(T("log_pull_step", s=status) + "\n")
    log(T("log_pull_done",
          t=_human_bytes(sum(v[1] for v in seen.values()))) + "\n")
    return True


def _local_chat_stream(system, user_text, max_tokens, log=None, read_timeout=180):
    """Ollama /api/chat 스트리밍. 받는 동안 로그에 진행 상황을 갱신한다.

    v1.2: 아래 세 옵션이 로컬 AI 품질·속도를 좌우한다. 지우거나 기본값에 맡기지 말 것.
      think=False   추론형 모델이 사고 과정에 수천 토큰을 소모하는 것을 막는다. 우리 작업은
                    '번호 범위를 고르는 일'이라 긴 사고가 필요 없다. 모델 계열별 우회
                    (qwen3 의 /no_think 등)는 LOCAL_TUNING 의 prompt_suffix 로 붙인다.
      num_ctx       ★ 가장 중요. Ollama 기본 컨텍스트는 4096 토큰이라, 우리 시스템 프롬프트
                    (약 2000 토큰) + 단어 목록 + 출력이 이를 넘어가면 앞부분이 조용히 잘린다.
                    규칙을 못 본 채로 답하게 되어 결과가 엉망이 된다. 반드시 명시할 것.
      샘플링         모델 제조사 권장값을 그대로 쓴다 (LOCAL_TUNING). 임의 조정 금지.
    """
    tune = local_tuning()
    payload = {
        "model": LOCAL_MODEL["name"],
        "stream": True,
        "think": False,
        "messages": [{"role": "system", "content": system + tune["prompt_suffix"]},
                     {"role": "user", "content": user_text}],
        "options": {
            "num_predict": max_tokens,
            "num_ctx": local_num_ctx(),
            "temperature": tune["temperature"],
            "top_p": tune["top_p"],
            "top_k": tune["top_k"],
            "repeat_penalty": 1.0,   # 번호 목록에 반복 페널티를 주면 오히려 형식이 깨진다
        },
    }
    buf = []
    t0 = time.time()
    last_tick = 0.0
    for msg in _stream_ndjson(f"{OLLAMA_URL}/api/chat", payload,
                              read_timeout, log=log, stall_key="log_local_stall"):
        # ★ v1.3: 취소 확인은 여기가 가장 중요한 자리다.
        #   글자가 하나씩 들어올 때마다 확인하므로 멈춤을 누르면 1초 안에 반응한다.
        #   바깥 루프에만 두면 이 호출(최대 100초)이 끝날 때까지 기다려야 한다.
        #   for 문을 빠져나가면 제너레이터가 정리되며 연결도 닫힌다.
        if is_cancelled():
            raise CancelledError("cancelled during local AI generation")
        if msg.get("error"):
            raise RuntimeError(str(msg["error"])[:200])
        piece = (msg.get("message") or {}).get("content") or ""
        if piece:
            buf.append(piece)
        now = time.time()
        if log and (now - last_tick) >= 0.4:
            last_tick = now
            joined = "".join(buf)
            # 사고 블록 안에서만 돌고 있는 상태와, 실제 답을 쓰기 시작한 상태를 구분해 보여준다
            visible = strip_thinking(joined)
            secs = f"{now - t0:.0f}"
            if not visible and ("<think>" in joined or "thought" in joined):
                log("\r" + T("log_local_think", s=secs))
            else:
                log("\r" + T("log_local_gen", n=len(visible), s=secs))
        if msg.get("done"):
            break

    out = strip_thinking("".join(buf))
    if log:
        log("\r" + T("log_local_gen_done", n=len(out), s=f"{time.time() - t0:.0f}"))
        log("")   # 진행률 줄 마무리 (다음 일반 로그가 줄바꿈을 넣어 준다)
        check_local_vram(log)   # v1.3: 실행당 한 번, 모델이 GPU 밖으로 밀렸는지 확인
    if not out:
        raise RuntimeError("local AI returned an empty response")
    return out


# ---------------- GPU 메모리 실측 경고 (v1.3) ----------------
#
#  ★ 그래픽카드 용량을 보고 '추측'하지 않는다.
#    카드가 몇 GB인지는 알아도, 그 순간 게임·브라우저가 얼마를 쓰고 있는지는 모른다.
#    8GB 카드가 멀쩡히 돌아갈 수도 있고, 16GB 카드가 밀려날 수도 있다.
#    Ollama 는 모델을 올린 뒤 "전체 중 얼마를 GPU에 올렸는지"를 알려준다.
#    추측 대신 그 실측값을 쓴다.
#
#  왜 필요한가: Ollama 는 모델이 VRAM 에 안 들어가면 에러를 내지 않는다.
#  일부 레이어를 조용히 본체 메모리로 넘기고 계속 돌린다. 사용자 눈에는
#  "되긴 하는데 이유 없이 3~5배 느린" 상태로만 보인다. 그 침묵을 깨는 것이 목적이다.

_VRAM_STATE = {"checked": False, "spilled": False, "pct": 0,
               "model": "", "vram": "", "total": ""}


def check_local_vram(log=None, force=False):
    """Ollama 에 올라간 모델이 GPU 안에 다 들어갔는지 확인한다.
    실행당 한 번만 검사한다(force=True 면 다시 검사).
    반환: True = 밀려남(느려짐), False = 정상 또는 확인 불가."""
    if _VRAM_STATE["checked"] and not force:
        return _VRAM_STATE["spilled"]
    _VRAM_STATE["checked"] = True

    import urllib.request
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/ps", timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        return False        # 확인 못 했으면 조용히 넘어간다 (경고를 지어내지 않는다)

    want = (LOCAL_MODEL["name"] or "").strip()
    stem = want.split(":")[0]
    entry = None
    for m in (data.get("models") or []):
        nm = (m.get("model") or m.get("name") or "")
        if nm == want or nm.startswith(stem):
            entry = m
            break
    if not entry:
        return False

    total = int(entry.get("size") or 0)
    vram = int(entry.get("size_vram") or 0)
    if total <= 0:
        return False

    # 5% 미만 차이는 계산 버퍼 등 정상 오차로 본다
    spilled_ratio = 1.0 - (vram / float(total))
    if spilled_ratio < 0.05:
        return False

    _VRAM_STATE.update({
        "spilled": True,
        "pct": int(round(spilled_ratio * 100)),
        "model": want,
        "vram": _human_bytes(vram),
        "total": _human_bytes(total),
    })
    if log:
        log(T("log_vram_spill", p=_VRAM_STATE["pct"], m=want,
              v=_VRAM_STATE["vram"], t=_VRAM_STATE["total"]))
    return True



# ---------------- 로컬 AI (Ollama) 상태/설치 유틸 (v1.1) ----------------
def find_ollama():
    import shutil as _sh
    exe = _sh.which("ollama")
    if exe:
        return exe
    if sys.platform.startswith("win"):
        cand = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe")
        if os.path.exists(cand):
            return cand
    return None


def local_server_models(timeout=1.5, detail=False):
    """Ollama 서버가 떠 있으면 설치된 모델 목록, 아니면 None.

    detail=True 면 이름 대신 항목 전체를 준다 — size(바이트)가 여기 들어 있다
    (v1.7.11: _model_size_gb 가 실제 크기를 알아내는 데 쓴다)."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        ms = data.get("models") or []
        return ms if detail else [m.get("name", "") for m in ms]
    except Exception:
        return None


def local_status():
    """('ready'|'no_model'|'no_server'|'no_ollama', 부가정보)"""
    names = local_server_models()
    if names is not None:
        want = LOCAL_MODEL["name"]
        base = want.split(":")[0]
        if any(n == want or n.startswith(want + ":") or n.split(":")[0] == base and want == base
               for n in names) or any(n.startswith(want) for n in names):
            return "ready", names
        return "no_model", names
    exe = find_ollama()
    return ("no_server", exe) if exe else ("no_ollama", None)


def start_local_server(exe, wait_secs=25):
    """Ollama 서버를 백그라운드로 띄우고 응답할 때까지 대기."""
    try:
        kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        subprocess.Popen([exe, "serve"], **kwargs)
    except Exception:
        return False
    for _ in range(wait_secs * 2):
        if local_server_models(timeout=1) is not None:
            return True
        time.sleep(0.5)
    return False



# ---------------- ffmpeg 오디오 추출 폴백 (v4.6) ----------------
def _find_ffmpeg(log=None):
    """PATH의 ffmpeg -> imageio-ffmpeg 내장 exe -> 없으면 자동 설치 시도."""
    import shutil as _sh
    p = _sh.which("ffmpeg")
    if p:
        return p
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    if log:
        log(T("log_ffmpeg_missing") + "\n")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "imageio-ffmpeg"])
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def extract_audio_ffmpeg(path, log):
    """ffmpeg로 오디오만 16kHz 모노 wav로 추출 (깨진 구간은 건너뜀).
    성공 시 임시 wav 경로, 실패 시 None."""
    ff = _find_ffmpeg(log)
    if not ff:
        log(T("log_ffmpeg_fail", e="ffmpeg not available") + "\n")
        return None
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix=".wav", prefix="jqsub_")
    os.close(fd)
    cmd = [ff, "-y", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", "16000", tmp]
    try:
        kwargs = {"capture_output": True}
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        r = subprocess.run(cmd, **kwargs)
        # 중간에 에러가 있어도 부분 추출된 wav가 충분히 크면 사용
        if os.path.exists(tmp) and os.path.getsize(tmp) >= 16000:
            log(T("log_extracted") + "\n")
            return tmp
        err = (r.stderr or b"").decode(errors="ignore")[:200] or f"exit {r.returncode}"
        log(T("log_ffmpeg_fail", e=err) + "\n")
    except Exception as e:
        log(T("log_ffmpeg_fail", e=e) + "\n")
    try:
        os.remove(tmp)
    except Exception:
        pass
    return None


# =============================================================================
#  Whisper 모델 로딩 (v1.3.8)
# =============================================================================
#
#  ★ CUDA 가 되는지를 '모델이 만들어졌는지'로 판단하지 말 것.
#
#    cublas64_12.dll / cudnn64_9.dll 이 없어도
#    WhisperModel(device="cuda") 는 **성공한다**. 실제 연산에 들어가는
#    순간에야 터진다. v1.3.7 까지는 이걸 몰라서, 로그에 "GPU(CUDA) 사용 중"
#    이라고 찍어 놓고 정작 받아쓰기에서 예외가 나면 그 파일 하나가
#    통째로 실패로 처리됐다. 사용자는 GPU 를 쓰는 줄 알고 있었다.
#
#    그래서 여기서 1초짜리 소리를 실제로 한 번 돌려 본다. 그게 통과해야만
#    GPU 라고 말한다. 이 검사를 빼지 말 것.
#
def _is_cuda_error(e):
    m = str(e).lower()
    return any(k in m for k in ("cublas", "cudnn", "cuda", "cublaslt",
                                "libcu", ".dll", "gpu"))


def _gpu_smoke_test(model):
    """1초짜리 소리로 실제 연산을 한 번 돌려 본다. 실패하면 예외가 올라온다."""
    import numpy as np
    audio = (np.random.randn(16000) * 0.01).astype("float32")
    segs, _info = model.transcribe(audio, language="en", vad_filter=False,
                                   without_timestamps=True, beam_size=1)
    list(segs)                      # ★ 여기서 실제로 계산이 일어난다
    return True


def load_whisper_model(log):
    """(model, 'GPU' | 'CPU') 반환. GPU 라고 찍히면 정말로 GPU 다."""
    from faster_whisper import WhisperModel
    try:
        m = WhisperModel(MODEL_NAME, device="cuda", compute_type="float16")
        log(T("log_gpu_check") + "\n")
        _gpu_smoke_test(m)
        log(T("log_gpu") + "\n")
        return m, "GPU"
    except Exception as gpu_err:
        log(T("log_gpu_fail", e=str(gpu_err)[:200]) + "\n")
        if _is_cuda_error(gpu_err):
            log(T("log_cuda_hint") + "\n")
        return WhisperModel(MODEL_NAME, device="cpu", compute_type="int8"), "CPU"


# ---- whisper 를 GPU 에서 내렸다 다시 올리기 (v1.7.7) -----------------------
#
#  ★ 왜 필요한가
#    받아쓰기가 끝나도 whisper large-v3(약 3GB)가 GPU 에 그대로 남아 있었다.
#    그 뒤로 도는 재조립·교정·번역은 whisper 를 전혀 쓰지 않는데도,
#    로컬 AI 모델은 그 3GB 를 뺀 자리에 들어가야 했다.
#      16GB 카드 실제 예산 = 16 − 3(whisper) − 1.5(화면) ≈ 11.5GB
#    이것 때문에 13GB 짜리 모델이 16GB 카드에서 밀려났다.
#
#  ★ 공짜가 아니다. 노래 단계(⑤)에서 whisper 를 다시 쓴다.
#    그래서 되올리는 비용(30초~1분)이 붙는다. 그만큼 손해다.
#    → **로컬 AI 일 때만** 내린다. 클라우드 엔진은 GPU 를 안 쓰므로
#      내려 봐야 얻는 것이 없고 되올리는 비용만 남는다.
#
#  ★ 되올릴 때는 장치를 다시 판정하지 않는다. 이미 알고 있다.
#    _gpu_smoke_test 를 또 돌리면 1초를 더 쓰고 로그만 지저분해진다.
def release_whisper(wh, log=None):
    """whisper 를 GPU 에서 내린다. 실제로 내렸으면 True."""
    if wh.get("model") is None:
        return False
    wh["model"] = None
    try:
        import gc
        gc.collect()
    except Exception:
        pass
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass
    if log:
        log(T("log_wh_release") + "\n")
    return True


def ensure_whisper(wh, log=None):
    """내려놨으면 다시 올린다. 안 내렸으면 아무 일도 하지 않는다."""
    if wh.get("model") is not None:
        return
    from faster_whisper import WhisperModel
    if log:
        log(T("log_wh_reload") + "\n")
    if wh.get("dev") == "GPU":
        wh["model"] = WhisperModel(MODEL_NAME, device="cuda", compute_type="float16")
    else:
        wh["model"] = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8")


# =============================================================================
#  ⑤ 노래 구간 채우기 (v1.5.0)
# =============================================================================
#
#  왜 필요한가
#    whisper 의 VAD 는 음악을 '말이 아님'으로 보고 통째로 버린다. 그래서
#    에피소드 앞머리의 뮤지컬 구간에는 자막이 하나도 안 만들어진다.
#
#  어떻게 채우는가 — 순서를 바꾸지 말 것
#    ① 노래 구간 찾기   : AI 가 '가사 + 받아쓴 단어들' 을 보고 범위를 말한다.
#                        AI 는 소리를 못 듣지만, 망가진 가사를 알아보는 건
#                        읽기 문제라 잘한다 ("Top materials got a job"
#                        ↔ "Every material's got a JOB!").
#                        ★ 그 답을 그대로 믿지 말고 코드로 검산한다(§0-1 ③).
#                        AI 가 실패하면 글자 유사도만으로 찾는 길이 따로 있다.
#    ② 그 구간만 잘라서 Demucs 로 보컬 분리 (반주를 걷어내야 들린다)
#    ③ 보컬을 whisper 로 다시 받아쓴다 — VAD 를 끄고, 가사를 힌트로
#    ④ 받아쓴 단어의 '시각' 위에 진짜 가사를 겹쳐 얹는다
#
#  ★ 시각은 절대 만들지 않는다. 전부 whisper 가 실제로 잰 값이다.
#    못 알아들은 줄만 앞뒤 사이로 나눠 넣고, 그건 신뢰도 0 으로 표시한다.
#
#  ★ 순서를 지킬 것 — 교정 뒤, 추가 요청 앞.
#    교정보다 앞에 두면 AI 가 가사를 '오탈자'로 보고 고친다.
#    번역보다 앞이어야 가사도 15개 언어로 나간다.
#
#  ★ 확인 창을 띄우지 말 것.
#    파일 10개 걸어놓고 자리를 뜨는 게 이 프로그램의 핵심이다. 중간에 물어보면
#    기능이 아니라 짐이 된다. 대신 **바꾸기 전 자막을 따로 저장**한다
#    (`_nosong.srt`). 막는 대신 되돌릴 수 있게 두는 쪽이다.

SONG_MIN_SIM = 0.55        # 이 이상이면 같은 단어로 본다
SONG_PAD = 30.0            # 찾은 구간 앞뒤 여유(초).
#   ★ 줄이지 말 것. 구간 탐지는 'whisper 가 가사를 알아들은 자리'만 찾는다.
#     노래는 그보다 앞뒤로 더 길다 — S2 EP1 은 탐지 22.5~100초, 실제 2~136초였다.
#     넉넉히 잘라 Demucs 에 먹여도 결과는 같다(정렬이 알아서 찾는다). 모자라면
#     노래 앞뒤가 잘려 나간다. 넓게 잡는 쪽이 언제나 싸다.
SONG_MIN_LEN = 10.0        # 이보다 짧으면 노래 구간으로 보지 않는다

# 진행률에서 각 단계가 차지하는 몫 (v1.6.2)
#   ★ 정확할 필요는 없다. 틀리면 바가 고르지 않게 움직일 뿐, 뒤로 가거나
#     멈추지는 않는다. 완료 로그의 실측 시간이 쌓이면 그걸 보고 고치면 된다.
STAGE_W = {"asr": 2.0, "rebuild": 3.0, "correct": 3.0,
           "song": 2.0, "extra": 1.0, "translate": 2.0}


def song_tok(s):
    return re.findall(r"[0-9a-z가-힣ㄱ-ㆎ']+", s.lower())


_SONG_SECTION = re.compile(r"^\s*[\[\(\<].{0,40}?[\]\)\>]\s*$")


def song_parse_lyrics(text):
    """가사 원문 -> 자막 줄 목록.

    화면에 나갈 글자(display)와 맞춤에 쓸 글자(tokens)를 따로 들고 다닌다.
    정렬은 'METAL!' 의 대문자도 느낌표도 모르지만, 자막에는 그대로 나가야 한다.
    """
    out = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        s = raw.strip()
        if not s or _SONG_SECTION.match(s):
            continue
        if len(s) > 200:
            continue        # 문서를 통째로 붙여넣었을 때의 안전장치
        t = song_tok(s)
        if t:
            out.append({"display": s, "tokens": t})
    return out


def _song_sim(a, b):
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def song_align_tokens(A, B):
    """가사 단어열 A 와 받아쓴 단어열 B 를 순서를 지키며 맞춘다.

    ★ 되돌아가는 연결이 구조적으로 불가능하다. 후렴이 네 번 반복돼도
      1절 후렴이 마지막 후렴으로 튀지 않는다. 이 성질을 없애지 말 것.
    """
    n, m = len(A), len(B)
    if not n or not m:
        return {}
    GAP = -0.6
    prev = [j * GAP for j in range(m + 1)]
    ptr = [[1] * (m + 1) for _ in range(n + 1)]
    for j in range(m + 1):
        ptr[0][j] = 3
    for i in range(1, n + 1):
        cur = [i * GAP] + [0.0] * m
        ptr[i][0] = 2
        ai = A[i - 1]
        for j in range(1, m + 1):
            d = prev[j - 1] + (2.0 * _song_sim(ai, B[j - 1]) - 1.0)
            u = prev[j] + GAP
            l = cur[j - 1] + GAP
            if d >= u and d >= l:
                cur[j] = d; ptr[i][j] = 1
            elif u >= l:
                cur[j] = u; ptr[i][j] = 2
            else:
                cur[j] = l; ptr[i][j] = 3
        prev = cur
    pairs = {}
    i, j = n, m
    while i > 0 and j > 0:
        p = ptr[i][j]
        if p == 1:
            if _song_sim(A[i - 1], B[j - 1]) >= SONG_MIN_SIM:
                pairs[i - 1] = j - 1
            i -= 1; j -= 1
        elif p == 2:
            i -= 1
        else:
            j -= 1
    return pairs


def _song_est_dur(n_tok):
    return min(8.0, max(1.0, 0.45 * n_tok))


def song_build_lines(lyr, words, pairs, span, min_dur=0.45, max_dur=8.0):
    """맞춘 결과를 자막 줄로. 못 붙은 줄만 앞뒤 사이로 나눠 넣는다."""
    t0, t1 = span
    base = 0
    items = []
    for ln in lyr:
        k = len(ln["tokens"])
        idx = [pairs[base + x] for x in range(k) if (base + x) in pairs]
        if idx:
            st = min(words[q]["start"] for q in idx)
            en = max(words[q]["end"] for q in idx)
            conf = len(idx) / float(k)
        else:
            st = en = None
            conf = 0.0
        items.append({"display": ln["display"], "n_tok": k, "n_hit": len(idx),
                      "start": st, "end": en, "conf": round(conf, 3)})
        base += k

    known = [i for i, it in enumerate(items) if it["start"] is not None]
    if not known:
        total = sum(it["n_tok"] for it in items) or 1
        cur = t0
        for it in items:
            d = (t1 - t0) * it["n_tok"] / total
            it["start"], it["end"] = cur, cur + d
            cur += d
    else:
        first = known[0]
        if first > 0:                      # 앞쪽 빈 줄은 첫 앵커에 붙여 뒤로 몬다
            need = sum(_song_est_dur(items[i]["n_tok"]) for i in range(first))
            room = max(0.0, items[first]["start"] - t0)
            head = sum(items[i]["n_tok"] for i in range(first)) or 1
            cur = items[first]["start"] - need if room > need else t0
            for i in range(first):
                d = _song_est_dur(items[i]["n_tok"]) if room > need \
                    else room * items[i]["n_tok"] / head
                items[i]["start"], items[i]["end"] = cur, cur + d
                cur += d
        for a, b in zip(known, known[1:]):
            if b - a <= 1:
                continue
            gap0, gap1 = items[a]["end"], items[b]["start"]
            room = max(0.0, gap1 - gap0)
            tot = sum(items[i]["n_tok"] for i in range(a + 1, b)) or 1
            cur = gap0
            for i in range(a + 1, b):
                d = room * items[i]["n_tok"] / tot
                items[i]["start"], items[i]["end"] = cur, cur + d
                cur += d
        last = known[-1]
        if last < len(items) - 1:
            need = sum(_song_est_dur(items[i]["n_tok"])
                       for i in range(last + 1, len(items)))
            room = max(0.0, t1 - items[last]["end"])
            tail = sum(items[i]["n_tok"] for i in range(last + 1, len(items))) or 1
            cur = items[last]["end"]
            for i in range(last + 1, len(items)):
                d = _song_est_dur(items[i]["n_tok"]) if room > need \
                    else room * items[i]["n_tok"] / tail
                items[i]["start"], items[i]["end"] = cur, cur + d
                cur += d

    prev_end = t0
    for it in items:
        if it["start"] is None:
            it["start"] = prev_end
        if it["end"] is None or it["end"] <= it["start"]:
            it["end"] = it["start"] + min_dur
        if it["start"] < prev_end:
            it["start"] = prev_end
        if it["end"] < it["start"] + min_dur:
            it["end"] = it["start"] + min_dur
        if it["n_hit"] == 0 and it["end"] - it["start"] > max_dur:
            it["end"] = it["start"] + max_dur      # 추정한 줄만 자른다
        prev_end = it["end"]
        it["start"] = round(max(0.0, it["start"]), 3)
        it["end"] = round(it["end"], 3)
    return items


# ---------------------------------------------------------------- 구간 찾기

def song_range_by_words(all_words, lyr, log=None):
    """
    코드만으로 노래 구간 찾기 — AI 없이, 공짜로.

    노래 구간에서 whisper 가 엉터리로 받아썼어도 완전히 엉터리는 아니다.
    ("Squeeze them in when there's none" ↔ "squeeze 'em in, wind is GONE!")
    그러니 가사 단어가 시간축 어디에 몰려 있는지 보면 그게 노래 구간이다.

    ★ 단어 하나씩 대조하면 안 된다.
      the·a·in·on·my·we 같은 흔한 단어는 대사에도 그대로 나온다. 실제로
      S2 EP1 에서 그렇게 셌더니 1215단어 중 619개가 '가사와 일치'로 잡혀
      15분짜리 영상 전체가 노래 구간이 돼 버렸다.
      그래서 **연속 3단어가 가사의 연속 3단어와 맞을 때만** 한 표로 센다.
      대사가 우연히 그러기는 어렵다.
    """
    A = [t for l in lyr for t in l["tokens"]]
    W = []
    for w in all_words:
        t = song_tok(getattr(w, "word", "") or "")
        if t:
            W.append((float(w.start), float(w.end), t[0]))
    RUN = 3
    if len(W) < RUN or len(A) < RUN:
        return None

    pos = {}
    for j, a in enumerate(A):
        pos.setdefault(a, []).append(j)
    vocab = list(pos.keys())
    memo = {}

    def sim(x, y):
        k = (x, y)
        if k not in memo:
            memo[k] = _song_sim(x, y)
        return memo[k]

    hits = []
    for i in range(len(W) - RUN + 1):
        w0 = W[i][2]
        cand = pos.get(w0)
        if not cand and len(w0) >= 4:
            cand = [j for v in vocab if sim(w0, v) >= 0.8 for j in pos[v]]
        if not cand:
            continue
        for j in cand:
            if j + RUN > len(A):
                continue
            if all(sim(W[i + k][2], A[j + k]) >= 0.7 for k in range(1, RUN)):
                hits.append((W[i][0], W[i + RUN - 1][1]))
                break
    if len(hits) < 3:
        return None

    # 60초 이상 떨어지면 다른 덩어리로 본다.
    #   ★ 이 값을 줄이지 말 것. 노래 한가운데에 간주가 길게 들어가고, 거기서
    #     whisper 가 아무것도 못 알아들으면 구멍이 그대로 남는다. S2 EP1 은
    #     노래 중간에 52초짜리 구멍이 있었다.
    groups, cur = [], [hits[0]]
    for h in hits[1:]:
        if h[0] - cur[-1][1] > 60.0:
            groups.append(cur); cur = [h]
        else:
            cur.append(h)
    groups.append(cur)
    g = max(groups, key=lambda G: (G[-1][1] - G[0][0]) * len(G))
    s, e = g[0][0], g[-1][1]
    if e - s < SONG_MIN_LEN:
        return None
    if log:
        log(T("log_song_found_words", n=len(g), s=fmt_time(s), e=fmt_time(e)) + "\n")
    return (s, e, len(g))


def song_range_by_ai(entries, lyr, provider, api_key, log):
    """
    AI 에게 물어본다. AI 는 소리를 못 듣지만, 자막 글자와 가사를 나란히 놓고
    '망가진 가사'를 알아보는 건 읽기 문제라 잘한다.

    ★ 답을 그대로 쓰지 말 것. 부르는 쪽에서 song_range_by_words() 로 검산한다.
    """
    lines = []
    for i, e in enumerate(entries[:400], 1):
        lines.append("%d. [%s] %s" % (i, e["time"].split(" --> ")[0],
                                      " ".join(e["lines"])))
    system = (
        "당신은 자막 편집자입니다. 아래는 어떤 영상의 자막이고, 그 아래는 그 영상에 "
        "실제로 들어간 노래의 가사입니다.\n"
        "음성 인식은 노래를 제대로 못 알아듣기 때문에, 노래 구간의 자막은 "
        "가사가 뭉개진 형태로 남아 있거나 아예 비어 있습니다.\n"
        "예: 자막 'Top materials got a job' ← 가사 \"Every material's got a JOB!\"\n\n"
        "노래가 시작하고 끝나는 시각을 찾아 주세요.\n"
        "- 뭉개진 가사가 보이는 줄, 그리고 그 사이의 빈 구간까지 포함합니다\n"
        "- 확실하지 않으면 넉넉하게 잡으세요. 넓게 잡는 것은 문제가 되지 않습니다\n"
        "- 노래 구간을 찾을 수 없으면 NONE 이라고만 답하세요\n\n"
        "답은 반드시 다음 한 줄 형식으로만:\n"
        "SONG mm:ss mm:ss\n"
        "또는\n"
        "NONE")
    user = "[자막]\n" + "\n".join(lines) + "\n\n[가사]\n" + \
           "\n".join(l["display"] for l in lyr[:80])
    try:
        reply = ai_call(provider, api_key, system, user, max_tokens=200, log=log)
    except Exception as e:
        log(T("log_song_ai_fail", e=str(e)[:150]) + "\n")
        return None
    m = re.search(r"SONG\s+(\d+):(\d+(?:\.\d+)?)\s+(\d+):(\d+(?:\.\d+)?)",
                  strip_thinking(reply or ""))
    if not m:
        return None
    s = int(m.group(1)) * 60 + float(m.group(2))
    e = int(m.group(3)) * 60 + float(m.group(4))
    if e - s < SONG_MIN_LEN:
        return None
    return (s, e)


# ---------------------------------------------------------------- 오디오

def song_deps_ready():
    try:
        import importlib.util as _ilu
        return _ilu.find_spec("demucs") is not None
    except Exception:
        return False


def song_install_deps(log):
    """Demucs 는 처음 쓸 때만 설치한다. 노래를 안 쓰는 사람은 받을 이유가 없다."""
    log(T("log_song_install") + "\n")
    try:
        kwargs = {}
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = 0x08000000
        subprocess.check_call([sys.executable, "-m", "pip", "install", "demucs"],
                              **kwargs)
        return song_deps_ready()
    except Exception as e:
        log(T("log_song_install_fail", e=str(e)[:200]) + "\n")
        return False


def song_clip(src, start, end, log):
    """구간만 잘라 wav 로. ★ 정확히 자를 필요 없다 — 넉넉해도 결과는 같다."""
    ff = _find_ffmpeg(log)
    if not ff:
        return None
    out = os.path.join(tempfile.gettempdir(),
                       "jqs_song_%d.wav" % int(time.time() * 1000))
    cmd = [ff, "-y", "-v", "error", "-ss", "%.3f" % start, "-to", "%.3f" % end,
           "-i", src, "-ac", "2", "-ar", "44100", out]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL,
                       creationflags=(0x08000000 if sys.platform.startswith("win") else 0))
        return out if os.path.exists(out) else None
    except Exception as e:
        log(T("log_song_clip_fail", e=str(e)[:150]) + "\n")
        return None


def song_separate(wav_path, log):
    """Demucs 로 보컬만. 반주를 걷어내야 whisper 가 알아듣는다."""
    outdir = os.path.join(tempfile.gettempdir(), "jqs_demucs_%d" % int(time.time()))
    os.makedirs(outdir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(wav_path))[0]
    log(T("log_song_separate") + "\n")
    cmd = [sys.executable, "-m", "demucs", "--two-stems=vocals",
           "-n", "htdemucs", "-o", outdir, wav_path]
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace",
                             creationflags=(0x08000000 if sys.platform.startswith("win") else 0))
        last = ""
        for line in p.stdout:
            line = line.rstrip()
            if line and line != last and "%" not in line:
                log("  " + line + "\n")
                last = line
        p.wait()
    except Exception as e:
        log(T("log_song_separate_fail", e=str(e)[:200]) + "\n")
        return None, outdir
    voc = os.path.join(outdir, "htdemucs", stem, "vocals.wav")
    return (voc if os.path.exists(voc) else None), outdir


def song_active_span(path, drop_db=25.0):
    """보컬 트랙에서 실제로 노래하는 구간. 앞뒤 무음을 빼야 첫 줄이 안 늘어난다."""
    try:
        import numpy as np
        w = wave.open(path, "rb")
        sr, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
        w.close()
        if sw == 2:
            a = np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0
        elif sw == 4:
            a = np.frombuffer(raw, dtype="<i4").astype("float32") / 2147483648.0
        else:
            return None
        if ch > 1:
            a = a.reshape(-1, ch).mean(axis=1)
        hop = max(1, sr // 50)
        m = len(a) // hop
        if m < 4:
            return None
        rms = np.sqrt((a[:m * hop].reshape(m, hop).astype("float64") ** 2).mean(axis=1) + 1e-12)
        db = 20 * np.log10(rms)
        on = np.where(db > (float(np.percentile(db, 99)) - drop_db))[0]
        if not len(on):
            return None
        return (max(0.0, on[0] * hop / float(sr) - 0.2),
                min(len(a) / float(sr), (on[-1] + 1) * hop / float(sr) + 0.3))
    except Exception:
        return None


# ---------------------------------------------------------------- 병합

def song_merge(entries, song_items, rng, note=True):
    """
    기존 자막에서 노래 구간을 들어내고 가사 줄을 끼워 넣는다.

    ★ 지우는 기준은 '가사가 실제로 놓인 범위' 이지, Demucs 에 먹인 범위가 아니다.
      먹인 범위는 일부러 넓게 잡았기 때문에(SONG_PAD) 그걸로 지우면 노래가
      아닌 대사까지 날아간다.
    ★ 시작 시각이 아니라 '겹치는가' 로 본다.
      S2 EP1 의 "Crank down tiny magnets in a row." 는 5.02초에 시작해서
      25.29초까지 갔다 — 시작만 보면 노래 밖이라 살아남아 가사와 겹친다.
    """
    lo = min(it["start"] for it in song_items)
    hi = max(it["end"] for it in song_items)
    kept, dropped = [], []
    for e in entries:
        st = e.get("start_ms")
        st = (st / 1000.0) if st is not None else _srt_start_sec(e["time"])
        en = e.get("end_ms")
        en = (en / 1000.0) if en is not None else st + 0.1
        (dropped if (st < hi and en > lo) else kept).append(e)
    new = []
    for it in song_items:
        txt = ("♪ %s ♪" % it["display"]) if note else it["display"]
        new.append({"index": "0",
                    "time": "%s --> %s" % (fmt_time(it["start"]), fmt_time(it["end"])),
                    "lines": [txt],
                    "start_ms": int(round(it["start"] * 1000)),
                    "end_ms": int(round(it["end"] * 1000)),
                    "words": [], "song": True, "conf": it["conf"]})
    merged = sorted(kept + new, key=lambda e: e.get("start_ms") or 0)
    for i, e in enumerate(merged, 1):
        e["index"] = str(i)
    return merged, len(dropped)


def _srt_start_sec(t):
    m = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)", t or "")
    if not m:
        return 0.0
    return (int(m.group(1)) * 3600 + int(m.group(2)) * 60
            + int(m.group(3)) + int(m.group(4)) / 1000.0)


def classify_error(msg):
    """에러 메시지 -> 원인 힌트 i18n 키 (모르면 None)"""
    m = str(msg).lower()
    if ("avcodec" in m or "invalid data" in m or "av_" in m or "errno" in m
            or "moov" in m or "demux" in m or "packet" in m):
        return "hint_decode"
    if "memory" in m or "alloc" in m or "cuda out" in m or "cublas" in m:
        return "hint_memory"
    if "11434" in m or "local ai server" in m or "refused" in m:
        return "hint_local"
    return None



# ====================== GUI ======================
class App:
    def __init__(self, root):
        self.root = root
        cfg = load_config()
        UI["lang"] = cfg.get("ui_lang", "en")  # 첫 실행: English

        root.title(f"{APP_NAME} {VERSION} — {APP_FULL}")
        # v1.4.0: 가로 폭 고정.
        #   배너(680px)가 잘리지 않는 폭으로 맞추고, 가로 조절은 잠근다.
        #   세로만 늘어난다. 폭을 바꾸면 배너부터 확인할 것.
        #   ④·⑤ 를 동시에 펼쳐도 로그가 남도록 세로를 크게 잡되,
        #   화면 밖으로 나가면 안 되므로 모니터 높이에 맞춰 줄인다.
        #   ★ 고정값으로 되돌리지 말 것 — 작은 노트북에서 창이 화면을 넘어가면
        #     아래쪽 시작 버튼·로그가 통째로 안 보인다.
        try:
            _sh = root.winfo_screenheight()
        except Exception:
            _sh = 1080
        _h = max(700, min(1120, _sh - 80))
        root.geometry("712x%d" % _h)
        root.minsize(712, 640)
        root.resizable(False, True)

        # ----- 상태 (언어를 바꿔도 유지) -----
        self.audio_path = tk.StringVar()
        self.selected_files = []
        # v4.8: 음성 언어 선택을 저장/복원 (첫 실행 기본값: 자동 감지)
        saved_audio = cfg.get("audio_lang", "auto")
        self.audio_lang_code = saved_audio if saved_audio in (["auto"] + LANG_CODES) else "auto"

        self.lang_vars = {}
        self._lang_sync_guard = False
        for code in LANG_CODES:
            self.lang_vars[code] = tk.BooleanVar(value=(code == "en"))
        self.select_all_var = tk.BooleanVar(value=False)

        # v1.1: AI 엔진 선택 + 엔진별 API 키 저장
        keys = dict(cfg.get("api_keys") or {})
        if cfg.get("api_key") and not keys.get("claude"):
            keys["claude"] = cfg["api_key"]  # 구버전 키 이전
        self.api_keys = keys
        prov = cfg.get("ai_provider")
        if prov not in PROVIDERS:
            # 기존 Claude 사용자는 Claude 유지, 신규는 무료 엔진 기본
            prov = "claude" if keys.get("claude") else DEFAULT_PROVIDER
        self.ai_provider = prov
        LOCAL_MODEL["name"] = cfg.get("local_model", LOCAL_MODEL["name"])  # v1.1 로컬 모델
        if LOCAL_MODEL["name"] not in LOCAL_MODELS:  # 목록에서 빠진 구모델(qwen3:8b 등)은 기본값으로
            LOCAL_MODEL["name"] = LOCAL_MODELS[0]
        # v1.7.13: 사용자가 모델을 직접 고른 적이 있는가.
        #   없으면 카드를 보고 알아서 올려 준다(pick_local_tuning).
        #   한 번이라도 직접 골랐으면 그 선택을 존중한다 — 안 그러면 고를 이유가 없다.
        LOCAL_MODEL["chosen"] = bool(cfg.get("local_model_chosen"))
        self.api_key = tk.StringVar(value=self.api_keys.get(prov, ""))
        # v1.2: 첫 실행(키가 하나도 없고 안내를 본 적 없음) -> Gemini 권장 안내 1회
        self.show_intro = not cfg.get("intro_shown") and not any(self.api_keys.values())
        # AI 추가 지시 자유 입력칸 — 사용자가 직접 입력한 내용만 config에 저장/복원
        self.extra_prompt_value = (cfg.get("extra_prompt") or "").strip()
        try:
            self.extra_h = min(12, max(3, int(cfg.get("extra_h", 4))))  # v4.7: 5줄 시작
            _extra_on = bool(cfg.get("extra_on", bool(self.extra_prompt_value)))
        except Exception:
            self.extra_h = 4
            _extra_on = bool(self.extra_prompt_value)
        # v1.4.0: ④ 체크박스. 체크를 풀면 '숨기기'가 아니라 '안 쓰기'다.
        #   get_extra() 가 빈 문자열을 돌려주므로 아래 단계 전체가 그냥 건너뛴다.
        #   ★ 이걸 '보이기 토글'로 바꾸지 말 것 — 꺼놓은 줄 알았는데 계속 도는
        #     상황이 제일 나쁘다. 내용은 config 에 남아 있다가 다시 체크하면 돌아온다.
        self.extra_on = tk.BooleanVar(value=_extra_on)

        # v1.4.0: ⑤ 노래 가사. ④와 똑같은 방식(제목 자리 체크박스).
        #   ★ 아직 기능이 없다. 화면 배치를 먼저 확정하려고 칸만 만들어 둔 것이고,
        #     가사를 넣어도 generate() 는 로그에 "아직 동작 안 함"만 남긴다.
        #     기능을 붙일 때는 get_song() 을 쓰는 쪽만 만들면 된다.
        self.song_prompt_value = (cfg.get("song_lyrics") or "").strip()
        try:
            self.song_h = min(16, max(4, int(cfg.get("song_h", 5))))
            _song_on = bool(cfg.get("song_on", bool(self.song_prompt_value)))
        except Exception:
            self.song_h = 5
            _song_on = bool(self.song_prompt_value)
        self.song_on = tk.BooleanVar(value=_song_on)
        # v1.2: AI 는 항상 켜져 있다 (엔진 3종 중 하나를 반드시 고르는 방식).
        #   config 에서 읽지 않고 저장하지도 않는다. 옛 config 의 use_claude=false 는 무시된다.
        #   이 변수는 기존 코드 곳곳의 분기를 그대로 두기 위해 남겨 둔 것이니 지우지 말고,
        #   False 가 될 수 있게 만들지도 말 것. (파일 상단 build_ui 의 ③ 섹션 주석 참고)
        self.use_claude = tk.BooleanVar(value=True)
        # _words.srt 는 상수 ALWAYS_SAVE_WORDS 로 고정 (파일 상단 주석 참고).
        # config 에서 읽지 않고, config 에 쓰지도 않고, 끄는 UI 도 없다.
        self.skip_existing = tk.BooleanVar(value=bool(cfg.get("skip_existing", False)))  # v4.12
        # 1.0: 후원 안내 (마일스톤 1회 팝업 + 완료 로그 한 줄)
        try:
            self.files_done = int(cfg.get("files_done", 0))
            self.donate_next = int(cfg.get("donate_next", 10))
        except Exception:
            self.files_done, self.donate_next = 0, 10
        self.donate_never = bool(cfg.get("donate_never", False))
        # 1.1: 자동 업데이트 확인
        self.auto_update = tk.BooleanVar(value=bool(cfg.get("update_check", True)))
        self.skip_version = str(cfg.get("skip_version") or "")
        self._update_busy = False
        self.files_expanded = False   # v4.12: 파일 목록 펼침 여부 (세션 내)
        self._cur_file = ""           # v4.12: 진행률에 표시할 현재 파일
        self.show_key = tk.BooleanVar(value=False)
        self.ui_lang_var = tk.StringVar(value=UI["lang"])
        self.busy = False
        self.cancel_flag = False
        self._ph_active = False       # API 키 입력칸 안내문 표시 중인지
        self._extra_ph_active = False  # 추가 지시 입력칸 안내문 표시 중인지

        self.api_key.trace_add("write", lambda *a: (
            self.api_keys.__setitem__(self.ai_provider, self.api_key.get().strip()),
            self.save_settings(), self.update_key_hint()))
        for var in self.lang_vars.values():
            var.trace_add("write", lambda *a: self.on_lang_var_changed())

        self.body = None
        self.build_menu()
        self.build_ui()
        # v4.12: 드래그 앤 드롭 등록 (tkinterdnd2가 있을 때만)
        try:
            if DND_OK:
                from tkinterdnd2 import DND_FILES
                self.root.drop_target_register(DND_FILES)
                self.root.dnd_bind("<<Drop>>", self.on_drop)
        except Exception:
            pass
        self.write_log(T("log_ready") + "\n")
        # v1.2: 키가 하나도 없는 첫 실행이면 Gemini 권장 안내를 한 번만 띄운다.
        #       (업데이트 확인 팝업과 겹치지 않게 먼저 보여준다)
        if self.show_intro:
            self.root.after(400, self.show_intro_popup)
        # 1.1: 시작 직후 백그라운드로 새 버전 확인 (실패하면 조용히 무시)
        if self.auto_update.get():
            self.root.after(1500 if not self.show_intro else 3000,
                            lambda: self.check_updates(manual=False))

    # ----- 자동 업데이트 (1.1) -----
    def _run_bg(self, fn, on_done, interval=200, limit=900):
        """fn()을 스레드에서 돌리고 결과는 메인 스레드에서 on_done(ok, value)로 전달.
        (작업 스레드가 tkinter를 직접 건드리지 않도록 폴링 방식)"""
        box = {}

        def worker():
            try:
                box["v"] = fn()
                box["ok"] = True
            except Exception as e:
                box["v"] = e
                box["ok"] = False

        def poll(n=0):
            try:
                if not self.root.winfo_exists():
                    return          # 창이 닫혔으면 조용히 종료
            except Exception:
                return
            if "ok" in box:
                on_done(box["ok"], box["v"])
                return
            if n >= limit:
                on_done(False, TimeoutError("timeout"))
                return
            self.root.after(interval, lambda: poll(n + 1))

        threading.Thread(target=worker, daemon=True).start()
        self.root.after(interval, poll)

    def check_updates(self, manual=False):
        if self._update_busy:
            return
        self._update_busy = True
        self._run_bg(fetch_update_info,
                     lambda ok, v: self._update_checked(v if ok else None, manual))

    def _update_checked(self, info, manual):
        self._update_busy = False
        if info is None:
            if manual:
                messagebox.showinfo(T("mi_check_update"), T("upd_offline"))
            return
        newest = str(info.get("version"))
        if not update_available(info):
            if manual:
                messagebox.showinfo(T("mi_check_update"),
                                    T("upd_latest", app=APP_NAME, v=VERSION))
            return
        if not manual and newest == self.skip_version:
            return   # 사용자가 건너뛰기로 표시한 버전
        self.write_log(T("log_update_found", v=newest) + "\n")
        self.show_update_dialog(info)

    def show_update_dialog(self, info):
        newest = str(info.get("version"))
        win = tk.Toplevel(self.root)
        win.title(T("upd_title"))
        win.transient(self.root)
        win.resizable(False, False)

        frame = ttk.Frame(win)
        frame.pack(fill="both", expand=True, padx=20, pady=(16, 12))
        ttk.Label(frame, text=T("upd_body", app=APP_NAME, v=newest, c=VERSION),
                  font=("", 10, "bold"), justify="left").pack(anchor="w")

        note = update_note_text(info)
        if note:
            ttk.Label(frame, text=T("upd_whats_new"), justify="left").pack(
                anchor="w", pady=(10, 2))
            box = tk.Text(frame, wrap="word", height=min(10, max(3, note.count("\n") + 2)),
                          width=58, relief="solid", borderwidth=1)
            box.insert("1.0", note)
            box.configure(state="disabled")
            box.pack(anchor="w")

        status = ttk.Label(frame, text="", justify="left")
        status.pack(anchor="w", pady=(10, 0))

        brow = ttk.Frame(win)
        brow.pack(pady=(0, 16))

        if info.get("requires_reinstall"):
            # 새 라이브러리가 필요한 버전 — 자체 교체 대신 설치 명령 재실행 안내
            status.configure(text=T("upd_reinstall"), foreground="#b26a00")
            ttk.Button(brow, text=T("upd_open_github"),
                       command=lambda: webbrowser.open(GITHUB_URL)).pack(side="left", padx=4)
            ttk.Button(brow, text=T("upd_later"), command=win.destroy).pack(side="left", padx=4)
            return

        btn_now = ttk.Button(brow, text=T("upd_now"))
        btn_later = ttk.Button(brow, text=T("upd_later"), command=win.destroy)
        btn_skip = ttk.Button(brow, text=T("upd_skip"))
        btn_now.pack(side="left", padx=4)
        btn_later.pack(side="left", padx=4)
        btn_skip.pack(side="left", padx=4)

        def do_skip():
            self.skip_version = newest
            self.save_settings()
            win.destroy()
        btn_skip.configure(command=do_skip)

        def do_update():
            for b in (btn_now, btn_later, btn_skip):
                b.configure(state="disabled")
            status.configure(text=T("upd_downloading"), foreground="")
            win.update_idletasks()

            def done():
                status.configure(text=T("upd_done", app=APP_NAME), foreground="#2e7d32")
                win.update_idletasks()
                self.root.after(900, restart_app)

            def fail(e):
                status.configure(text=T("upd_fail", e=e), foreground="#c62828")
                btn_later.configure(state="normal")
                ttk.Button(brow, text=T("upd_open_github"),
                           command=lambda: webbrowser.open(GITHUB_URL)).pack(side="left", padx=4)

            self._run_bg(lambda: apply_update(download_new_version(info)),
                         lambda ok, v: done() if ok else fail(v))

        btn_now.configure(command=do_update)

    # ----- 메뉴바 -----
    def build_menu(self):
        menubar = tk.Menu(self.root)

        m_set = tk.Menu(menubar, tearoff=0)
        m_set.add_checkbutton(label=T("mi_skip_existing"), variable=self.skip_existing,
                              command=self.save_settings)
        m_set.add_command(label=T("mi_local_model", m=LOCAL_MODEL["name"]),
                          command=self.pick_local_model)
        # _words.srt 는 항상 생성 (v1.1.1) — 끌 수 없는 항목이라 체크박스를 두지 않는다.
        # 무엇인지 궁금한 사용자를 위해 설명만 볼 수 있게 남겨둔다.
        # ※ 여기에 다시 체크박스(끄기 옵션)를 만들지 말 것. 파일 상단 ALWAYS_SAVE_WORDS 주석 참고.
        m_set.add_command(label=T("mi_save_words"),
                          command=lambda: self.show_text(T("mi_save_words"), T("words_info")))
        menubar.add_cascade(label=T("menu_settings"), menu=m_set)

        m_lang = tk.Menu(menubar, tearoff=0)
        for code, name in UI_LANGS:
            m_lang.add_radiobutton(label=name, value=code, variable=self.ui_lang_var,
                                   command=lambda c=code: self.set_ui_lang(c))
        menubar.add_cascade(label=T("menu_language"), menu=m_lang)

        m_help = tk.Menu(menubar, tearoff=0)
        m_help.add_command(label=T("mi_quickstart"),
                           command=lambda: self.show_text(T("mi_quickstart"), T("qs_b")))
        m_help.add_command(label=T("mi_trouble"),
                           command=lambda: self.show_text(T("mi_trouble"), T("tr_b")))
        m_help.add_separator()
        m_help.add_command(label=T("mi_check_update"),
                           command=lambda: self.check_updates(manual=True))
        m_help.add_checkbutton(label=T("mi_auto_update"), variable=self.auto_update,
                               command=self.save_settings)
        m_help.add_separator()
        m_help.add_command(label=T("btn_issues"),
                           command=lambda: webbrowser.open(ISSUES_URL))
        m_help.add_command(label="☕ " + T("btn_donate"),
                           command=lambda: webbrowser.open(DONATE_URL))
        m_help.add_separator()
        m_help.add_command(label=T("mi_about"), command=self.show_about)
        menubar.add_cascade(label=T("menu_help"), menu=m_help)

        self.root.config(menu=menubar)

    def on_toggle_words(self):
        # v1.1.1: _words.srt 는 항상 생성하도록 고정되어 더 이상 토글이 아니다.
        # 예전 버전 호환용으로만 남겨둔 껍데기 (설명만 표시).
        self.show_text(T("mi_save_words"), T("words_info"))

    def set_ui_lang(self, code):
        if self.busy:
            self.ui_lang_var.set(UI["lang"])  # 작업 중에는 변경 보류
            return
        if code == UI["lang"]:
            return
        UI["lang"] = code
        self.save_settings()
        self.rebuild()

    def rebuild(self):
        """UI 언어 변경: 로그 내용을 보존한 채 화면 전체를 다시 그린다."""
        old_log = ""
        try:
            old_log = self.log.get("1.0", "end-1c")
        except Exception:
            pass
        self.build_menu()
        if self.body is not None:
            self.body.destroy()
        self.build_ui()
        if old_log:
            self.log.configure(state="normal")
            self.log.insert("1.0", old_log + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")

    # ----- 공용: 작은 ? 버튼 / 텍스트 창 -----
    def qbtn(self, parent, title_key, body_key, link=None, link_label_key=None):
        return ttk.Button(parent, text="?", width=2,
                          command=lambda: self.show_text(
                              T(title_key), T(body_key), link=link,
                              link_label=T(link_label_key) if link_label_key else None))

    def show_text(self, title, body, link=None, link_label=None):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry("660x540")
        win.transient(self.root)
        frame = ttk.Frame(win); frame.pack(fill="both", expand=True, padx=10, pady=10)
        txt = tk.Text(frame, wrap="word")
        sb = ttk.Scrollbar(frame, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        txt.insert("1.0", body)
        txt.configure(state="disabled")
        txt.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        if link:
            ttk.Button(win, text=link_label or link,
                       command=lambda: webbrowser.open(link)).pack(pady=(0, 10))

    def show_intro_popup(self):
        """v1.2: 첫 실행 시 Gemini 를 강력 권장하는 안내. 한 번만 뜬다."""
        self.show_intro = False
        try:
            self.show_text(T("intro_t"), T("intro_b"),
                           link=PROVIDERS["gemini"]["key_url"],
                           link_label=T("intro_btn"))
        except Exception:
            pass
        self.save_settings()   # intro_shown = True 기록

    def show_about(self):
        win = tk.Toplevel(self.root)
        win.title(T("mi_about"))
        win.transient(self.root)
        win.resizable(False, False)
        body = T("ab_b", app=APP_NAME, v=VERSION, full=APP_FULL, m=MODEL_NAME, c=COPYRIGHT)
        ttk.Label(win, text=body, justify="center").pack(padx=24, pady=(18, 12))
        if ISSUES_URL:
            ttk.Button(win, text=T("btn_issues"), width=34,
                       command=lambda: webbrowser.open(ISSUES_URL)).pack(pady=(0, 6))
        if DONATE_URL:
            ttk.Button(win, text=T("btn_donate"), width=34,
                       command=lambda: webbrowser.open(DONATE_URL)).pack(pady=(0, 14))

    # ----- 메인 화면 -----
    def build_ui(self):
        self.body = ttk.Frame(self.root)
        self.body.pack(fill="both", expand=True)
        pad = {"padx": 12, "pady": 5}

        # --- 제작자 채널 배너 (어두운 바탕 + 노란 글자, 클릭 시 유튜브) ---
        banner = tk.Frame(self.body, bg="#263238")
        banner.pack(fill="x", padx=12, pady=(8, 2))
        lbl = tk.Label(banner, text=T("yt_banner", ch=YT_CHANNEL_NAME),
                       bg="#263238", fg="#FFD54F", cursor="hand2", anchor="w",
                       font=("", 9, "bold"))
        lbl.pack(side="left", padx=(10, 6), pady=6)
        lbl.bind("<Button-1>", lambda e: webbrowser.open(YT_VIDEO_URL))
        btn_ch = tk.Label(banner, text=T("yt_channel"), bg="#37474F", fg="#FFD54F",
                          cursor="hand2", padx=8, pady=2)
        btn_ch.pack(side="right", padx=(4, 10), pady=6)
        btn_ch.bind("<Button-1>", lambda e: webbrowser.open(YT_CHANNEL_URL))
        btn_w = tk.Label(banner, text=T("yt_watch"), bg="#37474F", fg="#FFEE58",
                         cursor="hand2", padx=8, pady=2)
        btn_w.pack(side="right", padx=(4, 0), pady=6)
        btn_w.bind("<Button-1>", lambda e: webbrowser.open(YT_VIDEO_URL))

        # --- ① 파일 선택 ---
        frm_file = ttk.LabelFrame(self.body, text=T("frm_file"))
        frm_file.pack(fill="x", **pad)
        frow = ttk.Frame(frm_file); frow.pack(fill="x", padx=10, pady=8)
        ttk.Entry(frow, textvariable=self.audio_path, state="readonly").pack(
            side="left", fill="x", expand=True)
        ttk.Button(frow, text=T("btn_browse"), command=self.pick_audio).pack(side="left", padx=(8, 0))
        ttk.Button(frow, text=("▾" if self.files_expanded else "▸"), width=2,
                   command=self.toggle_files).pack(side="left", padx=(6, 0))
        self.file_list = None
        if self.files_expanded:
            lst_frame = ttk.Frame(frm_file); lst_frame.pack(fill="x", padx=10, pady=(0, 4))
            sb = ttk.Scrollbar(lst_frame, orient="vertical")
            self.file_list = tk.Listbox(lst_frame, height=6, selectmode="extended",
                                        yscrollcommand=sb.set)
            sb.configure(command=self.file_list.yview)
            self.file_list.pack(side="left", fill="x", expand=True)
            sb.pack(side="right", fill="y")
            btns = ttk.Frame(frm_file); btns.pack(fill="x", padx=10, pady=(0, 8))
            ttk.Button(btns, text=T("btn_add"), command=self.add_files).pack(side="left")
            ttk.Button(btns, text=T("btn_remove"), command=self.remove_selected).pack(
                side="left", padx=(6, 0))
            ttk.Button(btns, text=T("btn_clear"), command=self.clear_files).pack(
                side="left", padx=(6, 0))
        self._update_file_display()

        # --- ② 음성 언어 ---
        frm_src = ttk.LabelFrame(self.body, text=T("frm_src"))
        frm_src.pack(fill="x", **pad)
        srow = ttk.Frame(frm_src); srow.pack(fill="x", padx=10, pady=8)
        ttk.Label(srow, text=T("lbl_src")).pack(side="left")
        self._combo_codes = ["auto"] + LANG_CODES  # v4.7: 자동 감지가 맨 위
        self.audio_lang_combo = ttk.Combobox(
            srow, state="readonly", width=24,
            values=[lang_label(c) for c in self._combo_codes])
        self.audio_lang_combo.current(self._combo_codes.index(self.audio_lang_code))
        self.audio_lang_combo.pack(side="left", padx=(6, 0))
        self.audio_lang_combo.bind("<<ComboboxSelected>>", self.on_audio_lang_changed)
        self.qbtn(srow, "hq_src_t", "hq_src_b").pack(side="left", padx=(8, 0))
        # v1.3.9: 회색 설명 줄을 없앴다. 같은 내용이 바로 옆 물음표(hq_src_b)에 있어
        #   두 번 말하고 있었고, 창만 길어졌다. 다시 넣지 말 것 — 설명은 물음표에.

        # --- ③ AI (출력 언어 + 교정·분할·번역 통합 섹션) ---
        #
        # v1.2: AI 켬/끔 체크박스를 없앴다. 이제 엔진 3종 중 하나를 반드시 고른다.
        #   AI 유무의 품질 차이가 너무 커서(문장 재조립·교정·번역이 전부 AI 단계다)
        #   "끄기"는 사실상 고장난 결과를 만드는 선택지였다. 실제로 v1.1까지
        #   기본값이 꺼짐이라, 사용자가 그걸 모른 채 침묵 분할 결과를 보고
        #   프로그램 품질을 오해하는 일이 있었다.
        #   ★ 체크박스를 다시 만들지 말 것. 키가 없을 때의 안내는 start_generate()
        #     의 확인 대화상자(nokey_t/nokey_b)가 담당한다.
        frm_key = ttk.LabelFrame(self.body, text=T("frm_claude"))
        frm_key.pack(fill="x", **pad)
        krow = ttk.Frame(frm_key); krow.pack(fill="x", padx=10, pady=8)
        self.lang_checks = {}

        if True:
            # ----- 엔진 선택 + API 키 + 출력 언어 + 추가 지시 -----
            ttk.Label(krow, text=T("lbl_engine")).pack(side="left", padx=(4, 0))
            self._prov_codes = list(PROVIDER_ORDER)
            # v1.2: 라벨에 품질/조건 설명이 붙어 길어졌다. 폭을 고정값으로 두면
            #   "Gemini (free API · recommende…" 처럼 잘린다. 언어마다 길이가 크게
            #   달라서(스페인어 47자 vs 일본어 25자) 가장 긴 라벨에 맞춰 잡는다.
            #   ★ width 를 다시 상수로 되돌리지 말 것.
            _labels = [self.prov_label(c) for c in self._prov_codes]
            self.prov_combo = ttk.Combobox(
                krow, state="readonly",
                width=min(46, max(24, max(len(s) for s in _labels) + 2)),
                values=_labels)
            self.prov_combo.current(self._prov_codes.index(self.ai_provider))
            self.prov_combo.pack(side="left", padx=(6, 0))
            self.prov_combo.bind("<<ComboboxSelected>>", self.on_provider_changed)
            self.key_entry = None
            if not EOPT(self.ai_provider, "needs_key"):
                # 키가 필요 없는 엔진(현재 로컬 AI): 키 칸 대신 상태/설치 버튼
                self._local_state, _info = local_status()
                self.local_btn = None
                if self._local_state != "ready":
                    btn_key = {"no_ollama": "btn_install_local",
                               "no_server": "btn_start_local",
                               "no_model": "btn_pull_model"}[self._local_state]
                    self.local_btn = ttk.Button(krow, text=T(btn_key),
                                                command=self.local_setup)
                    self.local_btn.pack(side="left", padx=(8, 0))
                ttk.Button(krow, text="?", width=2, command=self.show_api_help).pack(
                    side="left", padx=(6, 0))
                self.key_hint = ttk.Label(frm_key, text="", foreground="#666",
                                          wraplength=600, justify="left")
                self.key_hint.pack(anchor="w", padx=10, pady=(0, 4))
                m0 = LOCAL_MODEL["name"]
                if self._local_state == "ready":
                    self.key_hint.configure(text=T("local_ready", m=m0), foreground="#2e7d32")
                elif self._local_state == "no_model":
                    self.key_hint.configure(text=T("local_no_model", m=m0))
                elif self._local_state == "no_server":
                    self.key_hint.configure(text=T("local_no_server"))
                else:
                    self.key_hint.configure(text=T("local_no_ollama"))
            else:
                self.key_entry = ttk.Entry(krow)
                self.key_entry.pack(side="left", fill="x", expand=True, padx=(4, 0))
                self.key_entry.bind("<FocusIn>", self._ph_focus_in)
                self.key_entry.bind("<FocusOut>", self._ph_focus_out)
                self.key_entry.bind("<KeyRelease>", self._ph_key_release)
                ttk.Checkbutton(krow, text=T("show_key"), variable=self.show_key,
                                command=self.toggle_show).pack(side="left", padx=(8, 0))
                ttk.Button(krow, text="?", width=2, command=self.show_api_help).pack(
                    side="left", padx=(6, 0))
                self.key_hint = ttk.Label(frm_key, text="", foreground="#666",
                                          wraplength=600, justify="left")
                self.key_hint.pack(anchor="w", padx=10, pady=(0, 4))

            # 출력 자막 언어
            out_row = ttk.Frame(frm_key); out_row.pack(fill="x", padx=10, pady=(2, 0))
            ttk.Label(out_row, text=T("frm_out")).pack(side="left")
            ttk.Checkbutton(out_row, text=T("chk_all"), variable=self.select_all_var,
                            command=self.toggle_select_all).pack(side="left", padx=(12, 0))
            self.qbtn(out_row, "hq_out_t", "hq_out_b").pack(side="right")
            lang_grid = ttk.Frame(frm_key)
            lang_grid.pack(fill="x", padx=10, pady=(4, 2))
            # v1.4.0: 창 폭이 712 로 고정되면서 자리가 남는다. 4칸(4줄) -> 5칸(3줄).
            #   columnconfigure(weight=1) 로 좌우로 고르게 펴서 왼쪽 쏠림도 없앤다.
            cols = 5
            for c in range(cols):
                lang_grid.columnconfigure(c, weight=1)
            for idx, code in enumerate(LANG_CODES):
                r, c = divmod(idx, cols)
                chk = ttk.Checkbutton(lang_grid, text=lang_label(code),
                                      variable=self.lang_vars[code])
                chk.grid(row=r, column=c, sticky="w", padx=4, pady=2)
                self.lang_checks[code] = chk
            # v1.3.9: hint_out 회색 설명 제거 — 같은 내용이 위 물음표에 있다.

        # --- ④ AI 추가 지시 (v1.3.9: ③에서 떼어내 독립 섹션 + 접기) ---
        #
        #  ★ 체크박스로 만들지 말 것.
        #    체크 상태와 내용이 어긋나는 상태("내용은 넣었는데 체크는 안 함")가
        #    생기고, 그러면 조용히 무시된다. 접기는 보이고 안 보이고일 뿐이라
        #    동작이 안 바뀐다 — 비어 있으면 안 돌고 차 있으면 돈다. 기준이 하나다.
        #
        #  ★ 접었을 때 머리줄에 '입력됨'을 반드시 표시할 것.
        #    안 그러면 예전에 넣어둔 지시가 접힌 채 살아 있는 걸 모르고 실행한다.
        #    접기가 만드는 유일한 위험이 이것이다.
        # 체크박스를 항목 제목 자리에 앉힌다.
        # 체크하면 아래 입력칸이 열리고, 풀면 닫히면서 그 요청을 안 쓴다.
        #
        # ★ labelwidget 은 반드시 '프레임을 먼저 만들고 → 그 자식으로 체크박스 →
        #   configure' 순서로 붙일 것. 순서를 바꾸면 항목이 통째로 안 보인다.
        frm_extra = ttk.LabelFrame(self.body, text=" ")
        frm_extra.pack(fill="x", **pad)
        extra_chk = ttk.Checkbutton(frm_extra, text=T("frm_extra"),
                                    variable=self.extra_on,
                                    command=self.toggle_extra)
        try:
            frm_extra.configure(labelwidget=extra_chk)
        except Exception:
            # 어떤 테마에서 labelwidget 이 안 먹으면 그냥 안쪽 첫 줄에 둔다.
            frm_extra.configure(text="")
            extra_chk.pack(anchor="w", padx=10, pady=(6, 0))

        self.extra_body = ttk.Frame(frm_extra)
        hrow = ttk.Frame(self.extra_body); hrow.pack(fill="x", padx=10, pady=(6, 0))
        self.qbtn(hrow, "hq_extra_t", "hq_extra_b").pack(side="right")
        ttk.Button(hrow, text="+", width=2,
                   command=lambda: self.resize_extra(+1)).pack(side="right", padx=(0, 6))
        ttk.Button(hrow, text="−", width=2,
                   command=lambda: self.resize_extra(-1)).pack(side="right", padx=(6, 2))
        self.extra_text = tk.Text(self.extra_body, height=self.extra_h,
                                  wrap="word", undo=True)
        self.extra_text.pack(fill="x", expand=False, padx=10, pady=(2, 8))
        self.extra_text.bind("<FocusIn>", self._extra_focus_in)
        self.extra_text.bind("<FocusOut>", self._extra_focus_out)
        self.extra_text.bind("<KeyRelease>", self._extra_changed)
        self._extra_fg = str(self.extra_text.cget("foreground") or "black")
        self._refresh_extra_text()
        # 체크를 풀었을 때 프레임이 0 높이로 찌부러져 제목까지 안 보이는 걸 막는다
        ttk.Frame(frm_extra, height=4).pack(fill="x")
        if self.extra_on.get():
            self.extra_body.pack(fill="x")

        # --- ⑤ 노래 가사 (v1.4.0) — ④와 완전히 같은 방식 ---
        frm_song = ttk.LabelFrame(self.body, text=" ")
        frm_song.pack(fill="x", **pad)
        song_chk = ttk.Checkbutton(frm_song, text=T("frm_song"),
                                   variable=self.song_on,
                                   command=self.toggle_song)
        try:
            frm_song.configure(labelwidget=song_chk)
        except Exception:
            frm_song.configure(text="")
            song_chk.pack(anchor="w", padx=10, pady=(6, 0))

        self.song_body = ttk.Frame(frm_song)
        srow2 = ttk.Frame(self.song_body); srow2.pack(fill="x", padx=10, pady=(6, 0))
        self.qbtn(srow2, "hq_song_t", "hq_song_b").pack(side="right")
        ttk.Button(srow2, text="+", width=2,
                   command=lambda: self.resize_song(+1)).pack(side="right", padx=(0, 6))
        ttk.Button(srow2, text="−", width=2,
                   command=lambda: self.resize_song(-1)).pack(side="right", padx=(6, 2))
        self.song_text = tk.Text(self.song_body, height=self.song_h,
                                 wrap="word", undo=True)
        self.song_text.pack(fill="x", expand=False, padx=10, pady=(2, 8))
        self.song_text.bind("<FocusIn>", self._song_focus_in)
        self.song_text.bind("<FocusOut>", self._song_focus_out)
        self.song_text.bind("<KeyRelease>", self._song_changed)
        self._song_fg = str(self.song_text.cget("foreground") or "black")
        self._refresh_song_text()
        ttk.Frame(frm_song, height=4).pack(fill="x")
        if self.song_on.get():
            self.song_body.pack(fill="x")

        # --- 시작/취소 버튼 ---
        brow = ttk.Frame(self.body); brow.pack(fill="x", padx=12, pady=6)
        self.btn = ttk.Button(brow, text=T("btn_go"), command=self.start_generate)
        self.btn.pack(side="left", fill="x", expand=True, ipady=6)
        self.cancel_btn = ttk.Button(brow, text=T("btn_cancel"), command=self.cancel,
                                     state="disabled")
        self.cancel_btn.pack(side="left", padx=(8, 0), ipady=6)

        # --- 진행률 ---
        frm_prog = ttk.LabelFrame(self.body, text=T("frm_prog"))
        frm_prog.pack(fill="x", **pad)
        self.progress = ttk.Progressbar(frm_prog, mode="determinate", maximum=100)
        self.progress.pack(fill="x", padx=10, pady=(8, 4))
        self.status = ttk.Label(frm_prog, text=T("st_idle"))
        self.status.pack(anchor="w", padx=10, pady=(0, 8))

        # --- 로그 ---
        # --- 채널 배너 (v1.4.0) ---
        #
        #  ★ 로그보다 '먼저' 놓는다.
        #    창이 짧아지면 pack 은 나중에 놓인 것부터 잘라낸다. 배너를 뒤에 두면
        #    창을 조금만 줄여도 배너가 먼저 잘려 나갔다. 앞에 두면 대신
        #    로그(expand=True)가 줄어든다 — 로그는 스크롤되니 줄어도 괜찮다.
        #
        #  ★ 로그 '안'에 넣지 말 것. 로그는 계속 흘러가서 배너가 위로 사라진다.
        self.build_banner(self.body)

        frm_log = ttk.LabelFrame(self.body, text=T("frm_log"))
        frm_log.pack(fill="both", expand=True, **pad)
        self.log = tk.Text(frm_log, height=7, wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True, padx=6, pady=6)

        # 초기 상태 반영
        if self.use_claude.get() and self.key_entry is not None:
            self._entry_fg = str(self.key_entry.cget("foreground") or "")
            self._refresh_key_entry()
            self.update_key_hint()
        self._apply_audio_lang_lock()
        self._sync_select_all()

    # ----- AI 엔진 선택 (v1.1) -----
    def prov_label(self, code):
        if code == "claude":
            tag = T("prov_paid")
        elif code == "local":
            tag = T("prov_local_tag")
        else:
            tag = T("prov_free")
        return f'{PROVIDERS[code]["name"]} ({tag})'

    def on_provider_changed(self, event=None):
        idx = self.prov_combo.current()
        code = self._prov_codes[idx] if 0 <= idx < len(self._prov_codes) else DEFAULT_PROVIDER
        if code == self.ai_provider:
            return
        self.ai_provider = code
        self.api_key.set(self.api_keys.get(code, ""))  # 엔진별 키 불러오기
        self.save_settings()
        self.rebuild()  # local은 키 대신 상태/설치 버튼 레이아웃

    def show_api_help(self):
        prov = PROVIDERS[self.ai_provider]
        body = T("hq_api_b")
        # 로컬 AI를 고른 상태면 품질 안내를 맨 아래 덧붙임 (실망 방지)
        if self.ai_provider == "local":
            body = body + "\n\n" + T("local_quality_note")
        self.show_text(T("hq_api_t"), body,
                       link=prov["key_url"],
                       link_label=T("hq_open_key", p=prov["name"]))

    # ----- 로컬 AI 설치/시작/모델 다운로드 (v1.1) -----
    def local_setup(self):
        state = getattr(self, "_local_state", "no_ollama")
        if state in ("no_ollama", "no_model"):
            if not messagebox.askokcancel(
                    "Local AI",
                    T("local_quality_note") + "\n\n" +
                    T("local_install_info", m=LOCAL_MODEL["name"],
                      s=local_model_size(LOCAL_MODEL["name"]))):
                return
        if self.local_btn is not None:
            self.local_btn.configure(state="disabled")
        threading.Thread(target=self._local_worker, daemon=True).start()

    def _local_worker(self):
        try:
            exe = find_ollama()
            # 1) Ollama 설치
            if not exe:
                self.write_log("\n" + T("log_local_installing") + "\n")
                ok = False
                try:
                    kwargs = {}
                    if sys.platform.startswith("win"):
                        kwargs["creationflags"] = 0x08000000
                    subprocess.check_call(
                        ["winget", "install", "-e", "--id", "Ollama.Ollama",
                         "--silent", "--accept-package-agreements",
                         "--accept-source-agreements"], **kwargs)
                    ok = True
                except Exception:
                    pass
                if not ok and sys.platform.startswith("win"):
                    import urllib.request
                    import tempfile
                    tmp = os.path.join(tempfile.gettempdir(), "OllamaSetup.exe")
                    urllib.request.urlretrieve("https://ollama.com/download/OllamaSetup.exe", tmp)
                    subprocess.run([tmp, "/VERYSILENT", "/NORESTART"], check=True)
                exe = find_ollama()
                if not exe:
                    raise RuntimeError("Ollama install failed")
            # 2) 서버 시작
            if local_server_models() is None:
                self.write_log(T("log_local_starting") + "\n")
                if not start_local_server(exe):
                    raise RuntimeError("could not start Ollama server")
            # 3) 모델 다운로드
            st, _ = local_status()
            if st == "no_model":
                self.write_log(T("log_local_pulling", m=LOCAL_MODEL["name"],
                                       s=local_model_size(LOCAL_MODEL["name"])) + "\n")
                # v1.2: HTTP 스트리밍으로 받아 진행률(%)을 로그에 표시한다.
                #  ★ subprocess + DEVNULL 방식으로 되돌리지 말 것 — 9GB를 아무 표시 없이
                #    받게 되어 사용자가 멈춘 줄 알고 강제 종료하는 문제가 있었다.
                try:
                    pull_local_model(LOCAL_MODEL["name"], self.write_log)
                except Exception as pe:
                    # HTTP 경로가 막힌 환경이면 예전 CLI 방식으로 한 번 더 시도
                    self.write_log(T("log_local_fail", e=pe) + "\n")
                    kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
                    if sys.platform.startswith("win"):
                        kwargs["creationflags"] = 0x08000000
                    r = subprocess.run([exe, "pull", LOCAL_MODEL["name"]], **kwargs)
                    if r.returncode != 0:
                        raise RuntimeError(f"model download failed (exit {r.returncode})")
            self.write_log(T("log_local_ready") + "\n")
        except Exception as e:
            self.write_log(T("log_local_fail", e=e) + "\n")
        finally:
            self.root.after(0, self.rebuild)

    def pick_local_model(self):
        win = tk.Toplevel(self.root)
        win.title(T("mi_local_model", m=LOCAL_MODEL["name"]))
        win.transient(self.root)
        win.resizable(False, False)
        ttk.Label(win, text=T("dlg_local_model"), justify="left").pack(padx=20, pady=(16, 4))
        ttk.Label(win, text=T("local_quality_note"), justify="left",
                  foreground="#b26a00").pack(padx=20, pady=(0, 8))
        combo = ttk.Combobox(win, values=LOCAL_MODELS, width=28)
        combo.set(LOCAL_MODEL["name"])
        combo.pack(padx=20, pady=(0, 12))

        def ok():
            val = combo.get().strip()
            if val:
                LOCAL_MODEL["name"] = val
                LOCAL_MODEL["chosen"] = True     # v1.7.13: 이제 자동으로 안 바꾼다
                # v1.7.8: 모델이 바뀌면 남는 자리도 바뀐다 — 다음 실행 때 다시 고른다
                LOCAL_CTX["picked"] = False
                self.save_settings()
                self.build_menu()
                if self.ai_provider == "local" and self.use_claude.get():
                    self.rebuild()
            win.destroy()

        brow = ttk.Frame(win); brow.pack(pady=(0, 16))
        ttk.Button(brow, text="OK", command=ok).pack(side="left", padx=4)
        ttk.Button(brow, text=T("btn_cancel"), command=win.destroy).pack(side="left", padx=4)

    # ----- API 키 입력칸 (안내문 placeholder) -----
    def _refresh_key_entry(self):
        """실제 키 값/placeholder 상태에 맞춰 입력칸 내용을 다시 그린다."""
        key = self.api_key.get()
        self.key_entry.delete(0, "end")
        if key:
            self._ph_active = False
            self.key_entry.configure(show="" if self.show_key.get() else "*",
                                     foreground=self._entry_fg or "black")
            self.key_entry.insert(0, key)
        else:
            self._ph_active = True
            self.key_entry.configure(show="", foreground="#999")
            self.key_entry.insert(0, T("api_placeholder", p=PROVIDERS[self.ai_provider]["name"]))

    def _ph_focus_in(self, event=None):
        if self._ph_active:
            self._ph_active = False
            self.key_entry.delete(0, "end")
            self.key_entry.configure(show="" if self.show_key.get() else "*",
                                     foreground=self._entry_fg or "black")

    def _ph_focus_out(self, event=None):
        if not self.key_entry.get().strip():
            self.api_key.set("")
            self._refresh_key_entry()

    def _ph_key_release(self, event=None):
        if not self._ph_active:
            val = self.key_entry.get().strip()
            if val != self.api_key.get():
                self.api_key.set(val)

    # ----- AI 추가 지시 입력칸 (안내문 placeholder + config 저장) -----
    def _refresh_extra_text(self):
        self.extra_text.configure(state="normal")
        self.extra_text.delete("1.0", "end")
        if self.extra_prompt_value:
            self._extra_ph_active = False
            self.extra_text.configure(foreground=self._extra_fg)
            self.extra_text.insert("1.0", self.extra_prompt_value)
        else:
            self._extra_ph_active = True
            self.extra_text.configure(foreground="#999")
            self.extra_text.insert("1.0", T("ph_extra"))

    def _extra_focus_in(self, event=None):
        if self._extra_ph_active:
            self._extra_ph_active = False
            self.extra_text.delete("1.0", "end")
            self.extra_text.configure(foreground=self._extra_fg)

    def _extra_focus_out(self, event=None):
        if not self.extra_text.get("1.0", "end-1c").strip():
            self.extra_prompt_value = ""
            self.save_settings()
            self._refresh_extra_text()

    def _extra_changed(self, event=None):
        if not self._extra_ph_active:
            val = self.extra_text.get("1.0", "end-1c").strip()
            if val != self.extra_prompt_value:
                self.extra_prompt_value = val
                self.save_settings()

    def toggle_extra(self):
        """v1.4.0: ④ 체크. 체크하면 칸이 열리고, 풀면 닫히면서 '안 쓴다'."""
        if self.extra_on.get():
            self.extra_body.pack(fill="x")
        else:
            self.extra_body.pack_forget()
        self.save_settings()

    def run_song_stage(self, src_entries, all_words, song_txt, media_path,
                       base, base_code, prov, key, out_paths, tmp_wav, wh, prog=None):
        """
        ⑤ 노래 구간 채우기. 실패하면 src_entries 를 그대로 돌려준다.

        ★ 확인 창을 띄우지 않는다. 대신 바꾸기 전 자막을 `_nosong.srt` 로 남긴다.
          배치로 10개 걸어놓고 자리를 뜨는 게 이 프로그램의 핵심이라,
          중간에 물어보면 기능이 아니라 짐이 된다.
        """
        log = self.write_log
        log("\n" + T("log_song_stage") + "\n")

        lyr = song_parse_lyrics(song_txt)
        if not lyr:
            return src_entries

        # ① 구간 찾기 — AI 가 짚고, 코드가 검산한다 (§0-1 ③)
        by_words = song_range_by_words(all_words, lyr, log)
        rng, how = None, ""
        if key:
            got = song_range_by_ai(src_entries, lyr, prov, key, log)
            if got:
                if by_words:
                    # 검산 — '겹치는가' 만 보면 안 된다.
                    #
                    #   ★ 2026-08-23 사고: 로컬 AI 가 노래 구간을 5초~12분 03초라고
                    #     답했다(영상 전체가 15분). 단어 대조는 22초~1분 40초로 제대로
                    #     잡았는데, 두 구간이 겹치기는 하니 그대로 통과했다.
                    #     결과는 우연히 맞았지만 Demucs 가 2분 대신 12분을 처리했다.
                    #
                    #   그래서 두 가지를 더 본다.
                    #     ① 단어 대조 구간을 실제로 품고 있는가 (거의 다 덮는가)
                    #     ② 그보다 터무니없이 크지 않은가 (3배 + 여유 이내)
                    wl = by_words[1] - by_words[0]
                    ov = min(got[1], by_words[1]) - max(got[0], by_words[0])
                    covered = ov / wl if wl > 0 else 0.0
                    too_big = (got[1] - got[0]) > (wl * 3 + 2 * SONG_PAD)
                    if covered >= 0.6 and not too_big:
                        rng, how = got, "AI"
                    else:
                        why = T("song_bad_wide") if too_big else T("song_bad_off")
                        log(T("log_song_ai_reject", s=fmt_time(got[0]),
                              e=fmt_time(got[1]), why=why) + "\n")
                else:
                    rng, how = got, "AI"
        if rng is None and by_words:
            rng, how = (by_words[0], by_words[1]), T("song_src_words")
        if rng is None:
            log(T("log_song_none") + "\n")
            return src_entries

        s0 = max(0.0, rng[0] - SONG_PAD)
        s1 = rng[1] + SONG_PAD
        log(T("log_song_range", s=fmt_time(s0), e=fmt_time(s1), how=how) + "\n")

        # ② 그 구간만 잘라서 보컬 분리
        if not song_deps_ready() and not song_install_deps(log):
            return src_entries
        if prog: prog(0.15)
        clip = song_clip(tmp_wav or media_path, s0, s1, log)
        if not clip:
            return src_entries
        if prog: prog(0.25)
        voc, workdir = song_separate(clip, log)
        try:
            if not voc:
                return src_entries

            # 앞뒤 무음 제외 — 안 하면 첫 줄이 십수 초짜리가 된다
            span = song_active_span(voc) or (0.0, s1 - s0)

            # ③ 보컬 받아쓰기 — VAD 를 끈다. 켜면 노래가 통째로 사라진다.
            hint = " ".join(l["display"] for l in lyr)[:600]
            kw = dict(word_timestamps=True, vad_filter=False,
                      condition_on_previous_text=False, initial_prompt=hint,
                      beam_size=5)
            if base_code and base_code != "auto":
                kw["language"] = base_code
            if prog: prog(0.70)
            ensure_whisper(wh, log)      # v1.7.7: 내려놨으면 여기서 다시 올린다
            segs, _info = wh["model"].transcribe(voc, **kw)
            words = []
            for seg in segs:
                for w in (seg.words or []):
                    t = (w.word or "").strip()
                    if t:
                        words.append({"start": float(w.start) + s0,
                                      "end": float(w.end) + s0, "text": t})
            log(T("log_song_asr", n=len(words)) + "\n")
            if not words:
                return src_entries

            # ④ 받아쓴 단어의 '시각' 위에 진짜 가사를 얹는다
            A = [t for l in lyr for t in l["tokens"]]
            B = [(song_tok(w["text"]) or [""])[0] for w in words]
            if prog: prog(0.90)
            pairs = song_align_tokens(A, B)
            items = song_build_lines(lyr, words, pairs,
                                     (span[0] + s0, span[1] + s0))

            # 바꾸기 전 자막을 먼저 남긴다 — 되돌릴 수 있게
            nosong = f"{base}_nosong.srt"
            with open(nosong, "w", encoding="utf-8-sig", newline="") as f:
                f.write(build_srt(src_entries))
            out_paths.append(nosong)
            log(T("log_song_backup", p=os.path.basename(nosong)) + "\n")

            merged, n_drop = song_merge(src_entries, items, (s0, s1))
            # 가사 줄에도 앞뒤 여유를 준다 — 대사는 이미 받았고 가사만 못 받았다
            merged = apply_song_padding(merged)
            hit = sum(1 for it in items if it["n_hit"] > 0)
            log(T("log_song_done", n=len(items), d=n_drop,
                  hit=hit, est=len(items) - hit) + "\n")
            return merged
        finally:
            for p in (clip,):
                try:
                    os.remove(p)
                except Exception:
                    pass
            try:
                shutil.rmtree(workdir, ignore_errors=True)
            except Exception:
                pass

    # ----- ⑤ 노래 가사 (v1.4.0) -----
    def _refresh_song_text(self):
        self.song_text.configure(state="normal")
        self.song_text.delete("1.0", "end")
        if self.song_prompt_value:
            self._song_ph_active = False
            self.song_text.configure(foreground=self._song_fg)
            self.song_text.insert("1.0", self.song_prompt_value)
        else:
            self._song_ph_active = True
            self.song_text.configure(foreground="#999")
            self.song_text.insert("1.0", T("ph_song"))

    def _song_focus_in(self, event=None):
        if self._song_ph_active:
            self._song_ph_active = False
            self.song_text.delete("1.0", "end")
            self.song_text.configure(foreground=self._song_fg)

    def _song_focus_out(self, event=None):
        if not self.song_text.get("1.0", "end-1c").strip():
            self.song_prompt_value = ""
            self.save_settings()
            self._refresh_song_text()

    def _song_changed(self, event=None):
        if not self._song_ph_active:
            val = self.song_text.get("1.0", "end-1c").strip()
            if val != self.song_prompt_value:
                self.song_prompt_value = val
                self.save_settings()

    def toggle_song(self):
        if self.song_on.get():
            self.song_body.pack(fill="x")
        else:
            self.song_body.pack_forget()
        self.save_settings()

    def resize_song(self, delta):
        self.song_h = min(16, max(4, self.song_h + delta))
        self.song_text.configure(height=self.song_h)
        self.save_settings()

    def get_song(self):
        """가사. ④와 같은 규칙 — 체크가 풀려 있으면 빈 문자열."""
        if not self.song_on.get():
            return ""
        return "" if self._song_ph_active else self.song_prompt_value

    def resize_extra(self, delta):
        # v4.7: 추가 지시 칸 높이 조절 (3~12줄, 설정에 저장)
        self.extra_h = min(12, max(3, self.extra_h + delta))
        self.extra_text.configure(height=self.extra_h)
        self.save_settings()

    def get_extra(self):
        """
        실제로 AI 에게 넘길 추가 지시.

        ★ 여기 한 곳에서만 판단한다.
          체크가 풀려 있으면 빈 문자열을 돌려주고, 그러면 아래 단계 전체가
          알아서 건너뛴다 (기존에 '비어 있으면 안 돈다'로 돼 있기 때문).
          호출하는 쪽마다 체크 상태를 따로 보게 만들지 말 것 — 그러면
          한 군데만 빠뜨려도 '꺼놓은 요청이 도는' 사고가 난다.
        """
        if not self.extra_on.get():
            return ""
        return "" if self._extra_ph_active else self.extra_prompt_value

    def toggle_show(self):
        if not self._ph_active:
            self.key_entry.configure(show="" if self.show_key.get() else "*")

    def update_key_hint(self):
        if not self.use_claude.get():
            return  # 끔 상태에서는 힌트 라벨 자체가 없음
        if (not EOPT(self.ai_provider, "needs_key")) or self.key_entry is None:
            return  # 키가 없는 엔진은 build_ui에서 상태를 직접 표시한다
        if self.api_key.get().strip():
            self.key_hint.configure(text=T("hint_on", p=PROVIDERS[self.ai_provider]["name"]),
                                    foreground="#2e7d32")
        else:
            self.key_hint.configure(text=T("hint_need_key"), foreground="#666")

    def toggle_claude(self):
        # v1.2: AI 켬/끔 체크박스가 사라져 더 이상 호출되지 않는다.
        # 옛 설정 파일·단축키 경로에서 불릴 가능성만 대비해 남겨 둔 껍데기.
        self.rebuild()

    # ----- 음성 언어 <-> 출력 언어 잠금 -----
    def _other_codes(self):
        return [c for c in self.lang_vars if c != self.audio_lang_code]

    def _apply_audio_lang_lock(self):
        self._lang_sync_guard = True
        try:
            for c in self.lang_vars:
                w = self.lang_checks.get(c)
                if self.audio_lang_code != "auto" and c == self.audio_lang_code:
                    self.lang_vars[c].set(True)
                    if w:
                        w.configure(state="disabled", text=f"{lang_label(c)} {T('lock_base')}")
                else:
                    self.lang_vars[c].set(False)
                    if w:
                        w.configure(state="normal", text=lang_label(c))
        finally:
            self._lang_sync_guard = False

    def on_audio_lang_changed(self, event=None):
        idx = self.audio_lang_combo.current()
        code = self._combo_codes[idx] if 0 <= idx < len(self._combo_codes) else "en"
        self.audio_lang_code = code
        if code == "auto":
            self._lang_sync_guard = True
            try:
                for c in self.lang_vars:
                    w = self.lang_checks.get(c)
                    if w:
                        w.configure(state="normal", text=lang_label(c))
                    self.lang_vars[c].set(False)
            finally:
                self._lang_sync_guard = False
        else:
            self._apply_audio_lang_lock()
        self._sync_select_all()
        self.save_settings()

    def _sync_select_all(self):
        others = self._other_codes()
        self.select_all_var.set(bool(others) and all(self.lang_vars[c].get() for c in others))

    # ----- 설정 저장 -----
    def save_settings(self):
        cfg = {}
        cfg["ai_provider"] = self.ai_provider
        cfg["local_model"] = LOCAL_MODEL["name"]
        cfg["local_model_chosen"] = bool(LOCAL_MODEL.get("chosen"))
        ks = {k: v for k, v in self.api_keys.items() if v}
        if ks:
            cfg["api_keys"] = ks
        if self.extra_prompt_value.strip():
            cfg["extra_prompt"] = self.extra_prompt_value.strip()
        # ※ use_claude 는 저장하지 않는다 (v1.2부터 항상 켜짐). 다시 넣지 말 것.
        cfg["intro_shown"] = not self.show_intro   # v1.2: 첫 실행 안내를 봤는지
        # ※ save_words 는 config 에 저장하지 않는다 (ALWAYS_SAVE_WORDS 상수로 고정).
        #   예전 config 에 남아 있는 save_words 값은 읽지도 않으므로 자동으로 무시된다.
        #   여기에 다시 cfg["save_words"] = ... 를 넣지 말 것.
        cfg["skip_existing"] = bool(self.skip_existing.get())
        cfg["files_done"] = int(self.files_done)
        cfg["donate_next"] = int(self.donate_next)
        cfg["donate_never"] = bool(self.donate_never)
        cfg["extra_h"] = int(self.extra_h)
        cfg["extra_on"] = bool(self.extra_on.get())
        if self.song_prompt_value.strip():
            cfg["song_lyrics"] = self.song_prompt_value.strip()
        cfg["song_h"] = int(self.song_h)
        cfg["song_on"] = bool(self.song_on.get())
        cfg["audio_lang"] = self.audio_lang_code
        cfg["ui_lang"] = UI["lang"]
        cfg["update_check"] = bool(self.auto_update.get())   # 1.1
        if self.skip_version:
            cfg["skip_version"] = self.skip_version
        save_config(cfg)

    def toggle_select_all(self):
        self._lang_sync_guard = True
        try:
            new_val = self.select_all_var.get()
            for code in self._other_codes():
                self.lang_vars[code].set(new_val)
            if self.audio_lang_code != "auto":
                self.lang_vars[self.audio_lang_code].set(True)
        finally:
            self._lang_sync_guard = False
        self.save_settings()

    def on_lang_var_changed(self):
        if self._lang_sync_guard:
            return
        self._lang_sync_guard = True
        try:
            if self.audio_lang_code != "auto" and not self.lang_vars[self.audio_lang_code].get():
                self.lang_vars[self.audio_lang_code].set(True)
        finally:
            self._lang_sync_guard = False
        self._sync_select_all()
        self.save_settings()

    # ----- 파일 목록 (v4.12) -----
    def _update_file_display(self):
        n = len(self.selected_files)
        if n == 0:
            self.audio_path.set("")
        elif n == 1:
            self.audio_path.set(self.selected_files[0])
        else:
            self.audio_path.set(T("lbl_nfiles", n=n))
        if self.file_list is not None:
            self.file_list.delete(0, "end")
            for f in self.selected_files:
                self.file_list.insert("end", os.path.basename(f))

    def toggle_files(self):
        self.files_expanded = not self.files_expanded
        self.rebuild()

    def _ask_files(self):
        return filedialog.askopenfilenames(
            title=T("fd_title"),
            filetypes=[(T("fd_media"), "*.mp3 *.wav *.m4a *.mp4 *.mov *.avi *.mkv *.aac *.flac *.ogg *.vob"),
                       (T("fd_all"), "*.*")])

    def pick_audio(self):
        ps = self._ask_files()
        if ps:
            self.selected_files = list(ps)
            for p in ps:
                self.write_log(T("log_sel", p=p) + "\n")
            self._update_file_display()

    def add_files(self, paths=None):
        ps = paths if paths is not None else self._ask_files()
        added = 0
        for p in ps or []:
            if os.path.isfile(p) and p not in self.selected_files:
                self.selected_files.append(p)
                self.write_log(T("log_added", p=p) + "\n")
                added += 1
        if added:
            self._update_file_display()

    def remove_selected(self):
        if self.file_list is None:
            return
        for idx in sorted(self.file_list.curselection(), reverse=True):
            if 0 <= idx < len(self.selected_files):
                del self.selected_files[idx]
        self._update_file_display()

    def clear_files(self):
        self.selected_files = []
        self._update_file_display()

    def on_drop(self, event):
        # v4.12: 드래그 앤 드롭 — 기존 목록에 추가
        if self.busy:
            return
        try:
            paths = self.root.tk.splitlist(event.data)
        except Exception:
            return
        self.add_files([p for p in paths if os.path.isfile(p)])

    # ----- helpers -----

    def write_log(self, text):
        """일반 로그 출력.

        v1.2: 문자열이 '\\r' 로 시작하면 '진행률 줄'로 보고 마지막 줄을 덮어쓴다.
        (다운로드 %·응답 생성 중처럼 초당 여러 번 갱신되는 표시가 로그를
         수백 줄로 불어나게 하지 않도록. 진행이 끝나 일반 줄이 들어오면
         마지막 진행률 줄은 그대로 남겨 둔다.)"""
        prog = text.startswith("\r")
        if prog:
            text = text[1:]
        self.log.configure(state="normal")
        if getattr(self, "_prog_line", False):
            if prog:
                self.log.delete("end-1c linestart", "end-1c")   # 같은 줄 갱신
            else:
                self.log.insert("end", "\n")                    # 마지막 값은 보존
        self.log.insert("end", text)
        self._prog_line = prog
        self.log.see("end")
        self.log.configure(state="disabled")
        self.root.update_idletasks()

    def set_progress(self, pct, eta_text):
        self.progress["value"] = pct
        txt = T("st_prog", p=f"{pct:.0f}", t=eta_text)
        if self._cur_file:
            txt = f"{self._cur_file}   ·   {txt}"  # v4.12: 현재 파일 표시
        # v1.3: GPU 밖으로 밀린 상태면 상태줄에 계속 띄워 둔다.
        #   진행률이 갱신될 때마다 다시 붙으므로 작업 내내 보인다.
        #   팝업과 달리 창을 잠그지 않아, 보고서 직접 멈출 수 있다.
        if _VRAM_STATE.get("spilled"):
            txt = T("st_vram", p=_VRAM_STATE["pct"]) + "   ·   " + txt
        self.status.configure(text=txt)
        self.root.update_idletasks()

    def lock(self, on):
        self.busy = on
        self.btn.configure(state="disabled" if on else "normal",
                           text=T("btn_busy") if on else T("btn_go"))
        self.cancel_btn.configure(state="normal" if on else "disabled")

    def cancel(self):
        self.cancel_flag = True
        self.write_log("\n" + T("log_cancel_req") + "\n")
        self.write_log(T("log_cancelling"))
        self.cancel_btn.configure(state="disabled")
        self.status.configure(text=T("st_cancelling"))

    # ----- 생성 -----
    def start_generate(self):
        if self.busy:
            return
        files = list(self.selected_files) if self.selected_files else []
        if not files:
            single = self.audio_path.get().strip()
            if single and os.path.exists(single):
                files = [single]
        files = [f for f in files if os.path.exists(f)]
        if not files:
            messagebox.showwarning(T("t_notice"), T("w_no_file")); return
        selected = [code for code, var in self.lang_vars.items() if var.get()]
        if not selected and self.audio_lang_code != "auto":
            messagebox.showwarning(T("t_notice"), T("w_no_lang")); return
        # v1.2: AI 는 켰는데 키가 비어 있으면 조용히 넘어가지 않고 확인을 받는다.
        #  (v1.1까지는 로그 한 줄뿐이라, AI 가 도는 줄 알고 결과를 보고 당황하는 일이 있었다.
        #   "왜 자막이 이상하지?" 의 가장 흔한 원인이므로 여기서 확실히 알려 준다.)
        if (self.use_claude.get() and self.ai_provider != "local"
                and not self.api_key.get().strip()):
            go = messagebox.askyesno(
                T("nokey_t"),
                T("nokey_b", p=PROVIDERS[self.ai_provider]["name"]),
                icon="warning", default="no")
            if not go:
                return
            self.write_log("\n" + T("log_no_key_note") + "\n")
        self.cancel_flag = False
        self.lock(True)
        self.progress["value"] = 0
        self.status.configure(text=T("st_preparing"))
        # v1.3: GPU 메모리 경고는 '실행당 한 번'이다. 새 실행이니 상태를 되돌린다.
        _VRAM_STATE.update({"checked": False, "spilled": False, "pct": 0})
        self._vram_popup_shown = False
        reset_quota_state()          # v1.3.2: 지난 실행의 한도 상태를 지운다
        _LAST_CALL.clear()           #          요청 간격 기록도 초기화
        _GEMINI_DEAD.clear()         # v1.3.4: 소진 모델 표시도 초기화 (날짜가 바뀌었을 수 있다)
        # v1.3: 안쪽 루프(스트리밍·재조립·묶음)가 취소를 즉시 알아채도록 훅을 등록한다.
        set_cancel_check(lambda: self.cancel_flag)
        threading.Thread(target=self.generate,
                         args=(files, selected, self.audio_lang_code), daemon=True).start()

    def generate(self, files, langs, audio_code):
        try:
            from faster_whisper import WhisperModel

            self.write_log("\n" + T("log_loading", m=MODEL_NAME) + "\n")
            self.write_log(T("log_first") + "\n")
            # v1.3.8: GPU 판정은 load_whisper_model() 안에서 실제 연산으로 한다.
            #         받아쓰는 도중에 갈아탈 수 있어야 해서 통에 담아 둔다.
            _m, _dev = load_whisper_model(self.write_log)
            wh = {"model": _m, "dev": _dev}

            # v1.6.1: 단계별 소요 시간 (끝에 한 줄로 요약)
            t_all = time.time()
            stage_t = {}
            # v1.7.3: 중간에 조용히 건너뛴 단계를 모아 끝에 한 번 더 알린다.
            #   ★ 로그가 길어서 중간 경고는 놓치기 쉽다. 한도가 바닥나면
            #     교정이 0줄이고 번역 파일이 아예 안 생기는데, 그걸 모르고
            #     '잘 나왔네' 하고 쓰게 된다 (2026-08-23 실제로 그랬다).
            skipped = []

            def _tick(name, t0):
                stage_t[name] = stage_t.get(name, 0.0) + (time.time() - t0)


            use_ai = self.use_claude.get()
            prov = self.ai_provider
            key = self.api_key.get().strip() if use_ai else ""
            if use_ai and not EOPT(prov, "needs_key"):
                # 키가 필요 없는 엔진. 아래 코드가 key 의 참/거짓으로 'AI 사용 가능'을
                # 판단하므로, 빈 문자열이 아닌 자리표시자를 넣어 준다.
                key = key or "-"

            # v1.7.6: 로컬 AI 는 카드 크기를 보고 컨텍스트·묶음 크기를 정한다.
            #   ★ 반드시 여기서, 첫 단계가 시작되기 **전에** 불러야 한다.
            #     재조립·교정이 EOPT("local","lines_chunk") 를 읽는 시점보다
            #     늦으면 예전 값(40줄)으로 돌아 버린다.
            if use_ai and prov == "local":
                pick_local_tuning(self.write_log)

            out_paths = []
            errors = []   # v4.6: (파일명, 에러 요약, 힌트 i18n 키 or None)
            n_ok = 0
            n_skip = 0    # v4.12: 자막이 이미 있어 건너뛴 파일
            n_files = len(files)

            for fi, path in enumerate(files):
                if self.cancel_flag:
                    break
                fname = os.path.basename(path)
                self._cur_file = f"[{fi+1}/{n_files}] {fname}"  # v4.12: 진행률에 표시
                self.write_log(f"\n########## [{fi+1}/{n_files}] {fname} ##########\n")

                # v4.12: 이미 자막이 있으면 건너뛰기 (Settings 옵션, 기본 꺼짐=덮어쓰기)
                if self.skip_existing.get():
                    base0, _ = os.path.splitext(path)
                    if os.path.exists(base0 + ".srt"):
                        self.write_log(T("log_skip_exist", p=os.path.basename(base0) + ".srt") + "\n")
                        n_skip += 1
                        continue

                src_label = lang_label(audio_code)
                lang_arg = None if audio_code == "auto" else audio_code

                # ---------- 진행률 (v1.6.2) ----------
                #
                #  ★ 남은 시간을 보여주지 않는다.
                #    AI 에게 "얼마나 남았냐"고 물어볼 방법이 없다. v1.6.1 까지는
                #    받아쓰기에서만 재고 나머지는 안 셌는데, 그래서 바가 74% 에
                #    멈춘 채로 제일 오래 걸리는 구간(재조립·교정)을 통과했고
                #    남은 시간은 0 으로 굳어 있었다. 틀린 숫자는 없느니만 못하다.
                #
                #  ★ 대신 '실제로 일어난 일'만 센다.
                #    묶음 하나가 끝나면 그건 진짜 진행이다. 바가 못 움직이는
                #    구간에서는 옆의 글자(단계 이름·묶음 번호)가 대신 움직인다.
                st = {"done": 0.0, "w": 1.0, "label": "stg_asr", "total": 1.0}

                def prog_set(frac, blk=None, nblk=None, _fi=fi):
                    frac = min(1.0, max(0.0, frac))
                    pct = ((_fi + (st["done"] + st["w"] * frac) / st["total"])
                           / n_files) * 100
                    txt = T(st["label"])
                    if blk and nblk and nblk > 1:
                        txt = "%s (%d/%d)" % (txt, blk, nblk)
                    self.root.after(0, self.set_progress, pct, txt)

                def stage_begin(label, weight):
                    st["label"], st["w"] = label, weight
                    prog_set(0.0)

                def stage_end():
                    st["done"] += st["w"]
                    prog_set(1.0)

                def prog(frac, eta_text=None):     # 옛 호출 자리 호환
                    prog_set(frac)

                def _transcribe_once(media_path, jobs_this):
                    """(all_words, info, cancelled) 반환 — 디코딩 실패 시 예외 발생"""
                    ensure_whisper(wh, self.write_log)   # v1.7.7: 배치 2번째 파일부터
                    segments, info = wh["model"].transcribe(
                        media_path, language=lang_arg, word_timestamps=True,
                        vad_filter=True,
                        vad_parameters=dict(min_silence_duration_ms=500),
                        condition_on_previous_text=False)
                    total = max(0.1, getattr(info, "duration", 0) or 0.1)
                    start_t = time.time()
                    words = []
                    for seg in segments:
                        if self.cancel_flag:
                            return words, info, True
                        if seg.words:
                            words.extend(seg.words)
                        done = min(seg.end, total)
                        prog_set(done / total)
                    return words, info, False

                def do_transcribe(media_path, jobs_this):
                    """
                    v1.3.8: 받아쓰는 '도중에' CUDA 쪽이 터지는 경우를 여기서 받는다.

                    ★ 이 폴백을 지우지 말 것.
                      cublas64_12.dll 문제는 모델을 만들 때가 아니라 첫 연산에서
                      터진다. 여기서 그냥 예외를 올리면 파일 하나가 통째로
                      '실패'로 기록되고, 사용자는 자막을 못 받는다.
                      CPU 는 느릴 뿐 결과는 같다. 느린 결과가 없는 결과보다 낫다.
                    """
                    try:
                        return _transcribe_once(media_path, jobs_this)
                    except CancelledError:
                        raise                      # 취소는 실패가 아니다
                    except Exception as te:
                        if wh["dev"] != "GPU" or not _is_cuda_error(te):
                            raise
                        self.write_log("\n" + T("log_gpu_runtime_fail",
                                                e=str(te)[:200]) + "\n")
                        self.write_log(T("log_cuda_hint") + "\n")
                        from faster_whisper import WhisperModel as _WM
                        wh["model"] = _WM(MODEL_NAME, device="cpu",
                                          compute_type="int8")
                        wh["dev"] = "CPU"
                        return _transcribe_once(media_path, jobs_this)

                # v4.6: 파일별 에러 격리 — 한 파일이 실패해도 다음 파일로 계속
                tmp_wav = None
                try:
                    # ---------- 1) 음성 인식 (whisper) ----------
                    self.write_log("\n" + T("log_recog", l=src_label) + "\n")
                    # 이 파일에서 돌 단계들의 무게 합 (번역 언어 수는 받아쓰기 뒤에 확정)
                    _others = len([c for c in langs if c != audio_code])
                    st["total"] = (STAGE_W["asr"]
                                   + (STAGE_W["rebuild"] + STAGE_W["correct"] if key else 0)
                                   + (STAGE_W["song"] if self.get_song().strip() else 0)
                                   + (STAGE_W["extra"] if (key and self.get_extra().strip()) else 0)
                                   + STAGE_W["translate"] * _others) or 1.0
                    st["done"] = 0.0
                    stage_begin("stg_asr", STAGE_W["asr"])
                    jobs_est = _others
                    try:
                        _t = time.time()
                        all_words, info, cancelled = do_transcribe(path, jobs_est)
                        _tick("asr", _t)
                    except Exception:
                        # v4.6: 디코딩 실패 -> ffmpeg로 오디오만 추출해서 재시도
                        self.write_log(T("log_fallback") + "\n")
                        tmp_wav = extract_audio_ffmpeg(path, self.write_log)
                        if tmp_wav is None:
                            raise
                        _t = time.time()
                        all_words, info, cancelled = do_transcribe(tmp_wav, jobs_est)
                        _tick("asr", _t)
                    if cancelled:
                        self.write_log("\n" + T("log_cancel_recog") + "\n")
                        break

                    if not all_words and tmp_wav is None:
                        # v4.6: 인식 0개 -> ffmpeg 추출로 한 번 더 시도
                        self.write_log(T("log_fallback2") + "\n")
                        tmp_wav = extract_audio_ffmpeg(path, self.write_log)
                        if tmp_wav is not None:
                            all_words, info, cancelled = do_transcribe(tmp_wav, jobs_est)
                            if cancelled:
                                self.write_log("\n" + T("log_cancel_recog") + "\n")
                                break

                    if audio_code == "auto":
                        base_code = getattr(info, "language", None) or "en"
                        prob = getattr(info, "language_probability", None)
                        base_label = lang_label(base_code)
                        ptxt = f" ({prob*100:.0f}%)" if prob else ""
                        self.write_log(T("log_detected", l=base_label, p=ptxt) + "\n")
                    else:
                        base_code = audio_code
                        base_label = lang_label(base_code)

                    other_langs = [c for c in langs if c != base_code]
                    stage_end()
                    # 자동 감지로 언어가 바뀌었으면 남은 무게를 다시 잡는다
                    st["total"] = (st["done"]
                                   + (STAGE_W["rebuild"] + STAGE_W["correct"] if key else 0)
                                   + (STAGE_W["song"] if self.get_song().strip() else 0)
                                   + (STAGE_W["extra"] if (key and self.get_extra().strip()) else 0)
                                   + STAGE_W["translate"] * len(other_langs)) or 1.0

                    # 인식 결과 0개 -> 빈 자막을 만들지 않고 경고 + 요약에 기록
                    if not all_words:
                        self.write_log("\n" + T("log_no_speech") + "\n")
                        errors.append((fname, T("err_nospeech_short"), "hint_nospeech"))
                        prog_set(1.0)
                        continue

                    self.write_log(T("log_organize") + "\n")

                    base, _ = os.path.splitext(path)
                    # ---------------------------------------------------------
                    # 단어 단위 원본 SRT (_{언어}_words.srt) — 무조건, 항상 저장한다.
                    #
                    # ★ 이 블록에 조건(if 옵션 / if 설정값 / try 생략 등)을 붙이지 말 것.
                    #   사용자 설정이 아니라 프로그램 규격이다. 파일 상단
                    #   ALWAYS_SAVE_WORDS 주석에 이유가 적혀 있다.
                    #   AI 2차 검수가 문장을 다시 자를 때 쓰는 타이밍 근거이자,
                    #   결과가 이상할 때 원인을 추적하는 유일한 파일이다.
                    # ---------------------------------------------------------
                    if ALWAYS_SAVE_WORDS:
                        word_entries = [{"index": str(i),
                                         "time": f"{fmt_time(w.start)} --> {fmt_time(w.end)}",
                                         "lines": [w.word.strip()]}
                                        for i, w in enumerate(all_words, 1) if w.word.strip()]
                        if word_entries:
                            words_srt = f"{base}_{base_code}_words.srt"
                            with open(words_srt, "w", encoding="utf-8-sig", newline="") as f:
                                f.write(build_srt(word_entries))
                            out_paths.append(words_srt)
                            self.write_log(T("log_saved", p=words_srt) + "\n")

                    sentences = split_into_sentences(all_words)
                    src_entries = [{"index": str(i),
                                    "time": f"{fmt_time(s)} --> {fmt_time(e)}",
                                    "lines": [t], "start_ms": int(round(s * 1000)),
                                    "end_ms": int(round(e * 1000)),
                                    "words": sw}
                                   for i, (s, e, t, sw) in enumerate(sentences, 1)]

                    # ---------- AI 단계 (v1.2: 재조립 -> 교정 순서) ----------
                    #
                    #  ★ 순서를 바꾸지 말 것.
                    #    1) rebuild_from_words : 단어 타임스탬프를 근거로 문장 경계를
                    #       다시 잡는다. 위 src_entries(무음 기준 초안)는 참고용일 뿐이다.
                    #    2) correct_with_claude : 온전해진 문장을 놓고 오탈자·오청취를
                    #       고친다. 재조립보다 먼저 돌리면 토막난 문장을 보게 되어
                    #       문맥 판단이 나빠진다(v1.1까지의 문제).
                    #    3) 번역은 이렇게 완성된 원 언어 자막을 원본으로 삼는다.
                    #
                    if key:
                        # v1.7.7: 받아쓰기는 끝났다. 로컬 AI 라면 GPU 자리를 비켜 준다.
                        #   ★ 로컬일 때만. 클라우드는 GPU 를 안 쓰므로 내려 봐야
                        #     얻는 것 없이 되올리는 비용(노래 단계)만 남는다.
                        if prov == "local":
                            release_whisper(wh, self.write_log)
                        try:
                            _t = time.time()
                            stage_begin("stg_rebuild", STAGE_W["rebuild"])
                            _rrep = {}
                            src_entries = rebuild_from_words(
                                src_entries, prov, key, self.write_log,
                                extra=self.get_extra(), prog=prog_set,
                                report=_rrep)
                            _tick("rebuild", _t)
                            stage_end()
                            # v1.7.4: 재조립이 통째로/부분적으로 폴백되면 끝에 알린다
                            if _rrep.get("none"):
                                skipped.append(T("skip_rebuild"))
                            elif _rrep.get("fallback_blocks"):
                                skipped.append(T(
                                    "skip_rebuild_part",
                                    n=_rrep["fallback_blocks"],
                                    t=_rrep.get("blocks", 0)))
                        except CancelledError:
                            raise      # v1.3: 취소는 실패가 아니다 — 폴백 없이 올린다
                        except Exception as se:
                            self.write_log(T("log_rebuild_fail", e=se) + "\n")
                            try:
                                src_entries = split_by_pauses(src_entries, self.write_log)
                            except Exception as pe:
                                self.write_log(T("log_pause_fail", e=pe) + "\n")

                        self.write_log("\n" + T("log_correct", l=base_label) + "\n")
                        try:
                            _t = time.time()
                            stage_begin("stg_correct", STAGE_W["correct"])
                            _crep = {}
                            src_entries = correct_with_claude(src_entries, prov, key, base_code, self.write_log,
                                                              extra=self.get_extra(), prog=prog_set,
                                                              report=_crep)
                            _tick("correct", _t)
                            stage_end()
                            if _crep.get("none"):
                                skipped.append(T("skip_correct"))
                        except CancelledError:
                            raise
                        except Exception as ce:
                            self.write_log(T("log_correct_fail", e=ce) + "\n")
                    else:
                        if not use_ai:
                            self.write_log("\n" + T("log_off_split") + "\n")
                        else:
                            self.write_log("\n" + T("log_nokey_split") + "\n")
                        try:
                            src_entries = split_by_pauses(src_entries, self.write_log)
                        except Exception as pe:
                            self.write_log(T("log_pause_fail", e=pe) + "\n")

                    # v1.3: AI 단계는 오래 걸린다. 끝나자마자 취소 여부를 확인한다.
                    #       취소했는데 반쪽짜리 자막을 저장하면 안 된다.
                    if self.cancel_flag:
                        break

                    # 최종 자막 기준으로 끝 1초 지연 적용 (겹침 방지)
                    src_entries = apply_trailing_delay(src_entries, extra=1.0)

                    # ---------- 1-a) 노래 구간 채우기 (v1.5.0) ----------
                    #
                    #  ★ 자리를 옮기지 말 것.
                    #    교정보다 뒤 — 앞에 두면 AI 가 가사를 '오탈자'로 보고 고친다.
                    #    번역보다 앞 — 뒤에 두면 가사가 15개 언어로 안 나간다.
                    #    추가 요청보다 앞 — 사용자 지시가 가사에도 닿아야 하고,
                    #      추가 요청이 실패해도 노래는 이미 들어가 있게 된다.
                    #
                    #  ★ 실패해도 그냥 지나간다. 노래 때문에 파일 하나를 통째로
                    #    잃으면 안 된다. 원래 자막이 그대로 남는 게 최악을 막는다.
                    song_txt = self.get_song().strip()
                    if song_txt:
                        try:
                            _t = time.time()
                            stage_begin("stg_song", STAGE_W["song"])
                            src_entries = self.run_song_stage(
                                src_entries, all_words, song_txt, path, base,
                                base_code, prov, key, out_paths, tmp_wav, wh,
                                prog=prog_set)
                            _tick("song", _t)
                            stage_end()
                        except CancelledError:
                            raise
                        except Exception as se:
                            self.write_log(T("log_song_fail",
                                             e=str(se).replace("\n", " ")[:200]) + "\n")

                    # ---------- 1-b) 추가 요청 단계 (v1.3.7) ----------
                    #
                    #  ★ 반드시 '한국어 저장보다 앞, 번역보다 앞' 이다.
                    #    뒤로 옮기면 저장된 파일에 요청 결과가 안 들어가거나,
                    #    언어마다 따로 돌아 결과가 서로 어긋난다.
                    #
                    #  ★ 실패하면 번역으로 넘어가지 않는다.
                    #    원하지 않는 자막을 번역하는 건 의미가 없다.
                    #    다만 한국어 자막은 저장한다 — 받아쓰기·재조립·교정까지는
                    #    정상 결과물이고, 이 기능이 없던 시절 파일과 같다.
                    extra_req = self.get_extra().strip()
                    extra_failed = False
                    if key and extra_req:
                        self.write_log("\n" + T("log_extra_stage") + "\n")
                        try:
                            _t = time.time()
                            stage_begin("stg_extra", STAGE_W["extra"])
                            src_entries = apply_extra_request(
                                src_entries, prov, key, self.write_log,
                                extra_req, all_words)
                            _tick("extra", _t)
                            stage_end()
                        except CancelledError:
                            raise
                        except Exception as ee:
                            extra_failed = True
                            msg = str(ee).replace("\n", " ")[:200]
                            self.write_log(T("log_extra_fail", e=msg) + "\n")
                            self.write_log(T("log_extra_kept") + "\n")
                            errors.append((fname, T("err_extra_short"), "hint_extra_fail"))

                    # 기준 언어 SRT (접미사 없음 -> 플레이어 자동 인식)
                    src_srt = f"{base}.srt"
                    with open(src_srt, "w", encoding="utf-8-sig", newline="") as f:
                        f.write(build_srt(src_entries))
                    out_paths.append(src_srt)
                    self.write_log(T("log_saved", p=src_srt) + "\n")

                    # v1.3.7: 추가 요청이 실패했으면 여기서 멈춘다.
                    #   요청대로 안 된 자막을 번역해 봐야 쓸모가 없다.
                    if extra_failed:
                        self.write_log(T("log_extra_stop") + "\n")
                        continue

                    # ---------- 2) 나머지 언어: 번역 ----------
                    source_name = LANG_FULLNAME.get(base_code, base_code)
                    for code in other_langs:
                        if self.cancel_flag:
                            break
                        lang_lbl = lang_label(code)
                        self.write_log("\n" + T("log_translate", l=lang_lbl) + "\n")

                        if not key:
                            if not use_ai:
                                self.write_log(T("log_skip_tr_off") + "\n")
                            else:
                                self.write_log(T("log_skip_tr_nokey") + "\n")

                            continue

                        try:
                            _t = time.time()
                            stage_begin("stg_translate", STAGE_W["translate"])
                            tr_entries = translate_with_claude(src_entries, prov, key, code, self.write_log,
                                                               extra=self.get_extra(),
                                                               source_name=source_name, prog=prog_set)
                            _tick("translate", _t)
                            stage_end()
                        except CancelledError:
                            break      # v1.3: 취소 — 이 언어 파일은 만들지 않는다
                        except Exception as te:
                            self.write_log(T("log_tr_fail", l=lang_lbl, e=te) + "\n")
                            skipped.append(T("skip_translate", l=lang_lbl))

                            continue

                        srt_path = f"{base}_{code}.srt"
                        with open(srt_path, "w", encoding="utf-8-sig", newline="") as f:
                            f.write(build_srt(tr_entries))
                        out_paths.append(srt_path)
                        self.write_log(T("log_saved", p=srt_path) + "\n")




                    n_ok += 1
                    # v1.4.0: 파일 하나 끝날 때마다 배너를 다음 장으로
                    self.root.after(0, self.next_banner)
                except CancelledError:
                    # v1.3: 취소는 오류 목록에 넣지 않는다. 요약에 '실패'로 뜨면 안 된다.
                    self.cancel_flag = True
                    break
                except Exception as fe:
                    msg = str(fe)
                    self.write_log("\n" + T("t_error") + f": {msg}\n")
                    errors.append((fname, msg[:200], classify_error(msg)))
                    continue
                finally:
                    if tmp_wav:
                        try:
                            os.remove(tmp_wav)
                        except Exception:
                            pass

            if self.cancel_flag:
                self.write_log("\n" + T("log_cancelled") + "\n")
                self.root.after(0, lambda: self.status.configure(text=T("st_cancelled")))
                return

            self.root.after(0, self.set_progress, 100, human_dur(0))
            # v1.6.1: 전체/단계 소요 시간 한 줄 요약
            _names = [("asr", "st_asr"), ("rebuild", "st_rebuild"),
                      ("correct", "st_correct"), ("song", "st_song"),
                      ("extra", "st_extra"), ("translate", "st_translate")]
            _parts = " · ".join("%s %s" % (T(k), dur_mmss(stage_t[n]))
                                for n, k in _names if stage_t.get(n, 0) >= 1)
            if skipped:
                self.write_log("\n" + T("sum_skipped") + "\n")
                for m in dict.fromkeys(skipped):     # 중복 제거, 순서 유지
                    self.write_log("  · " + m + "\n")
            self.write_log("\n" + T("log_all_done_t", n=len(out_paths),
                                    t=dur_mmss(time.time() - t_all),
                                    p=(" (%s)" % _parts) if _parts else "") + "\n")
            # v4.6: 파일별 결과 요약 (실패한 파일 + 원인 설명)
            if errors:
                self.write_log("\n" + T("sum_header", ok=n_ok, fail=len(errors)) + "\n")
                for ef, emsg, ehint in errors:
                    self.write_log(T("sum_item", f=ef, e=emsg) + "\n")
                    if ehint:
                        self.write_log(T(ehint) + "\n")
            else:
                self.write_log(T("sum_ok_all", ok=n_ok) + "\n")
            if n_skip:
                self.write_log(T("sum_skip", n=n_skip) + "\n")
            # 1.0: 후원 안내 — 성공한 작업 뒤에만, 조용히 한 줄
            if n_ok:
                self.files_done += n_ok
                self.save_settings()
                self.write_log(T("log_donate_line",
                                 u=DONATE_URL.replace("https://", "")) + "\n")
                if (not self.donate_never) and self.files_done >= self.donate_next:
                    self.root.after(600, self.show_donate_popup)
            self.root.after(0, self.notify_done)  # v4.12: 완료 알림
            # v1.3: GPU 메모리 경고 팝업은 '작업이 다 끝난 뒤'에 띄운다.
            #       작업 중에 띄우면 모달이라 창이 잠겨, 정작 멈춤 버튼을 못 누른다.
            self.root.after(900, self.maybe_warn_vram)
            if out_paths:
                self.root.after(0, lambda: self.open_folder(out_paths[0]))
        except Exception as e:
            self.write_log("\n" + T("t_error") + f": {e}\n")
            self.root.after(0, lambda: messagebox.showerror(T("t_error"), str(e)))
        finally:
            self._cur_file = ""
            set_cancel_check(None)          # v1.3: 훅 해제
            self.root.after(0, lambda: self.lock(False))

    def maybe_warn_vram(self):
        """v1.3: 모델이 GPU 밖으로 밀렸으면 실행당 한 번 알린다.

        ★ 작업 중에는 띄우지 않는다.
          messagebox 는 모달이라 창이 잠긴다. "3~5배 느립니다"를 알리려던 팝업이
          정작 멈춤 버튼을 못 누르게 막아 버린다. 작업 중에는 로그와 상태줄로만
          보여 주고(사용자가 보고 직접 멈출 수 있다), 팝업은 끝난 뒤에 띄운다."""
        if not _VRAM_STATE.get("spilled"):
            return
        if getattr(self, "_vram_popup_shown", False):
            return
        self._vram_popup_shown = True
        messagebox.showwarning(
            T("vram_title"),
            T("vram_msg", p=_VRAM_STATE["pct"], m=_VRAM_STATE["model"]))

    def show_donate_popup(self):
        """1.0: 누적 자막 수 마일스톤(10 -> 50 -> 250...)마다 딱 한 번 뜨는 후원 안내.
        '다시 보지 않기'를 누르면 영원히 안 뜬다."""
        self.donate_next = max(self.donate_next * 5, self.files_done + 1)
        self.save_settings()
        win = tk.Toplevel(self.root)
        win.title(APP_NAME)
        win.transient(self.root)
        win.resizable(False, False)
        # v1.1: \uc720\ud29c\ube0c \ucc44\ub110 \ud64d\ubcf4(\uc8fc) + \ud6c4\uc6d0(\ubd80)\uc744 \ud55c \ud31d\uc5c5\uc5d0 \ud568\uaed8 \ud45c\uc2dc
        ttk.Label(win, text=T("donate_msg", app=APP_NAME, n=self.files_done),
                  justify="center").pack(padx=28, pady=(20, 10))

        def do_yt():
            webbrowser.open(YT_VIDEO_URL); win.destroy()

        def do_donate():
            webbrowser.open(DONATE_URL); win.destroy()

        def do_never():
            self.donate_never = True
            self.save_settings()
            win.destroy()

        ytbox = tk.Frame(win, bg="#263238")
        ytbox.pack(fill="x", padx=20, pady=(0, 10))
        tk.Label(ytbox, text=T("popup_yt"), bg="#263238", fg="#FFD54F",
                 justify="center", font=("", 9, "bold")).pack(padx=12, pady=(10, 6))
        yb = tk.Label(ytbox, text=T("btn_yt_go", ch=YT_CHANNEL_NAME),
                      bg="#37474F", fg="#FFEE58", cursor="hand2", padx=10, pady=4)
        yb.pack(pady=(0, 10))
        yb.bind("<Button-1>", lambda e: do_yt())

        ttk.Button(win, text="\u2615 " + T("btn_donate"), width=34,
                   command=do_donate).pack(pady=(0, 8))
        brow = ttk.Frame(win); brow.pack(pady=(0, 16))
        ttk.Button(brow, text=T("btn_later"), command=win.destroy).pack(side="left", padx=4)
        ttk.Button(brow, text=T("btn_never"), command=do_never).pack(side="left", padx=4)

    # ----- 채널 배너 (v1.4.0) -----
    #
    #  ★ PhotoImage 는 파이썬 쪽에서 붙잡고 있지 않으면 지워져서 빈 칸이 된다.
    #    self._bn_cache 에 담아 두는 이유가 이것이다. 지우지 말 것.
    #
    #  ★ 창을 넓혔을 때 캐릭터가 오른쪽 끝에 붙어 있어야 한다.
    #    그래서 Label 이 아니라 Canvas 다 — Label 은 이미지를 못 자르고,
    #    넓히면 배너가 가운데로 떠서 양옆에 회색 여백이 생긴다.
    #    캔버스는 넘치는 부분을 잘라 주고, 위치도 마음대로 잡을 수 있다.
    def build_banner(self, parent):
        self._bn_cache = {}
        # UI 언어를 바꾸면 build_ui() 가 다시 도는데, 그때 배너까지 바뀌면
        # 엉뚱한 데서 그림이 튄다. 이미 정해진 장이 있으면 그대로 쓴다.
        if not hasattr(self, "_bn_index"):
            self._bn_index = random.randrange(len(BANNERS))
        self.bn_canvas = tk.Canvas(parent, height=BANNER_H, bd=0,
                                   highlightthickness=0,
                                   background=BANNERS[self._bn_index]["bg"])
        self.bn_canvas.pack(fill="x", padx=12, pady=(0, 10))
        self.bn_canvas.configure(cursor="hand2")
        self.bn_canvas.bind("<Button-1>", lambda e: webbrowser.open(YT_CHANNEL_URL))
        self.bn_canvas.bind("<Configure>", lambda e: self._banner_draw())

        # 배너 위에 올리는 작은 버튼 두 개 (위쪽 띠와 같은 색·같은 동작)
        def _btn(text, url, bg, fg):
            lb = tk.Label(self.bn_canvas, text=text, bg=bg, fg=fg,
                          padx=9, pady=3, cursor="hand2", font=("", 9, "bold"))
            lb.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
            return lb
        self._bn_btns = [
            _btn(T("yt_watch"), YT_VIDEO_URL, "#37474F", "#FFEE58"),
            _btn(T("yt_channel"), YT_CHANNEL_URL, "#37474F", "#FFD54F"),
        ]
        self._banner_draw()

    def _banner_photo(self, idx):
        """(배너, 왼쪽 연장용 띠) — 한 번 만들면 캐시에 둔다."""
        if idx not in self._bn_cache:
            b = BANNERS[idx]
            img = tk.PhotoImage(data=b["img"])
            # 2px 세로 띠를 가로로 크게 늘려 둔다. 창을 넓혀도 왼쪽이 이어진다.
            # 2 x 800 = 1600px. 배너 680 과 합쳐 2280px 폭까지 덮는다.
            # 그보다 넓히면 캔버스 바탕색(띠 평균색)이 보이는데 색이 거의 같다.
            edge = tk.PhotoImage(data=b["edge"]).zoom(800, 1)
            self._bn_cache[idx] = (img, edge)
        return self._bn_cache[idx]

    def _banner_draw(self):
        try:
            c = self.bn_canvas
            w = c.winfo_width()
            if w <= 1:
                return
            img, edge = self._banner_photo(self._bn_index)
            c.delete("all")
            c.configure(background=BANNERS[self._bn_index]["bg"])
            if w > BANNER_W:                      # 남는 왼쪽을 띠로 메운다
                c.create_image(w - BANNER_W, 0, anchor="ne", image=edge)
            c.create_image(w, 0, anchor="ne", image=img)
            # 글자 아래 빈 자리에 버튼 두 개. 배너 왼쪽 끝 기준으로 붙인다.
            x0 = max(0, w - BANNER_W)
            bx = x0 + 31
            for b in self._bn_btns:
                c.create_window(bx, 76, anchor="nw", window=b)
                bx += b.winfo_reqwidth() + 8
        except Exception:
            pass

    def next_banner(self):
        """파일 하나 끝날 때마다 다음 장으로. 같은 그림만 보면 눈에 안 들어온다."""
        try:
            self._bn_index = (self._bn_index + 1) % len(BANNERS)
            self._banner_draw()
        except Exception:
            pass

    def notify_done(self):
        """v4.12: 완료 알림음 + 작업표시줄 깜빡임"""
        try:
            if sys.platform.startswith("win"):
                import winsound
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
                import ctypes
                from ctypes import wintypes

                class FLASHWINFO(ctypes.Structure):
                    _fields_ = [("cbSize", wintypes.UINT), ("hwnd", wintypes.HWND),
                                ("dwFlags", wintypes.DWORD), ("uCount", wintypes.UINT),
                                ("dwTimeout", wintypes.DWORD)]
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
                info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, 3, 6, 0)  # FLASHW_ALL
                ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
            else:
                self.root.bell()
        except Exception:
            pass

    def open_folder(self, file_path):
        folder = os.path.dirname(os.path.abspath(file_path))
        try:
            if sys.platform.startswith("win"):
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.run(["open", folder])
            else:
                subprocess.run(["xdg-open", folder])
        except Exception as e:
            self.write_log(f"{e}\n")


def _icon_path():
    """앱 아이콘(.ico) 경로. 없으면 GitHub에서 한 번 내려받아 캐시한다."""
    try:
        base = os.path.dirname(os.path.abspath(__file__))
    except Exception:
        base = os.getcwd()
    path = os.path.join(base, ICON_NAME)
    if os.path.exists(path) and os.path.getsize(path) > 500:
        return path
    try:
        import urllib.request
        req = urllib.request.Request(ICON_URL, headers={"User-Agent": f"{APP_NAME}/{VERSION}"})
        with urllib.request.urlopen(req, timeout=4) as r:
            data = r.read()
        if len(data) > 500:
            with open(path, "wb") as f:
                f.write(data)
            return path
    except Exception:
        pass
    return None


def apply_icon(win):
    """루트/자식 창에 아이콘 적용. 실패해도 앱 동작에는 영향 없음."""
    path = _icon_path()
    if not path:
        return
    try:
        win.iconbitmap(default=path)   # Windows: 모든 Toplevel에 상속
    except Exception:
        try:
            win.iconbitmap(path)
        except Exception:
            pass


DND_OK = False

def _make_root():
    """v4.12: 드래그 앤 드롭 지원 루트 생성 (tkinterdnd2, 없으면 자동 설치 시도,
    그래도 없으면 일반 Tk로 폴백 — 드래그만 비활성)"""
    global DND_OK
    try:
        from tkinterdnd2 import TkinterDnD
        DND_OK = True
        return TkinterDnD.Tk()
    except Exception:
        pass
    try:
        kwargs = {}
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        subprocess.check_call([sys.executable, "-m", "pip", "install", "tkinterdnd2"], **kwargs)
        from tkinterdnd2 import TkinterDnD
        DND_OK = True
        return TkinterDnD.Tk()
    except Exception:
        return tk.Tk()


if __name__ == "__main__":
    root = _make_root()
    apply_icon(root)
    root.withdraw()
    UI["lang"] = load_config().get("ui_lang", "en")  # 설치 안내문도 저장된 언어로
    if not ensure_faster_whisper(root):
        root.destroy(); sys.exit(0)
    root.deiconify()
    App(root)
    root.mainloop()
