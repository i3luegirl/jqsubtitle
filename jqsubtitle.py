#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# JQSubtitle — Just Quality AI Subtitle Maker
# Copyright (c) 2026 JQ Park. Licensed under the MIT License (see LICENSE).
"""
JQSubtitle 1.1 — Just Quality AI Subtitle Maker
(구 SRT 자막 생성기 / JQSub 후속)

- 음성/영상 파일 -> SRT + SMI 자막 생성 (whisper large-v3, 문장 단위 분할, 단어 실측 타이밍)
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
VERSION = "1.2"
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

# ---- AI 엔진 (v1.1): Claude(유료·확실) / Gemini(무료 키) / 로컬 AI(Ollama, 설치형) ----
PROVIDERS = {
    "claude": {"name": "Claude", "model": "claude-sonnet-4-6",
               "key_url": "https://console.anthropic.com/settings/keys"},
    "gemini": {"name": "Gemini",
               # 무료 티어 모델은 구형화가 잦아 404 시 아래 순서로 자동 대체
               "models": ["gemini-3-flash", "gemini-flash-latest", "gemini-2.5-flash",
                          "gemini-2.0-flash"],
               "model": "gemini-3-flash",
               "key_url": "https://aistudio.google.com/apikey"},
    "local":  {"name": "Local AI", "model": "",  # 실제 모델명은 LOCAL_MODEL 참조
               "key_url": "https://ollama.com"},
}
PROVIDER_ORDER = ["claude", "gemini", "local"]
DEFAULT_PROVIDER = "gemini"
LOCAL_MODEL = {"name": "gemma4:12b"}  # Settings에서 변경 가능 (config: local_model)
# v1.2: gemma4:12b -> gemma4:12b 로 교체.
#   qwen3 는 추론형이라 <think> 에서 수천 토큰을 소모해 매우 느렸고, 형식 준수도 불안정했다.
#   gemma4:12b 는 7.6GB / 256K 컨텍스트 / 사고 모드 기본 꺼짐 / 140개 언어.
#   ※ 목록은 한 개만 유지한다 (사용자 방침). 늘리지 말 것.
LOCAL_MODELS = ["gemma4:12b"]
OLLAMA_URL = "http://127.0.0.1:11434"

# ---- 로컬 AI 튜닝값 (v1.2) — 값의 근거는 _local_chat_stream() 주석 참고 ----
LOCAL_NUM_CTX = 8192       # Ollama 기본 4096으로는 시스템 프롬프트가 잘린다
LOCAL_CHUNK_WORDS = 60     # 로컬은 한 번에 적게 — 대기 시간이 짧아지고 실패해도 손해가 적다
LOCAL_READ_TIMEOUT = 300   # 줄과 줄 사이 제한 (전체 시간 제한이 아님)

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
_GEMINI_OK_MODEL = {"name": None}    # 404 폴백으로 찾은 동작 모델 캐시
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
 "en": "Creates SRT + SMI subtitles from video/audio — Whisper transcription + AI correction & translation",
 "ko": "영상/음성에서 SRT+SMI 자막 자동 생성 — Whisper 받아쓰기 + AI 교정·번역",
 "ja": "動画/音声からSRT+SMI字幕を自動生成 — Whisper書き起こし + AI校正・翻訳",
 "zh": "从视频/音频自动生成 SRT+SMI 字幕 — Whisper 转写 + AI 校对·翻译",
 "fr": "Crée des sous-titres SRT + SMI depuis vidéo/audio — transcription Whisper + correction/traduction AI",
 "pt": "Cria legendas SRT + SMI de vídeo/áudio — transcrição Whisper + correção/tradução AI",
 "es": "Crea subtítulos SRT + SMI desde vídeo/audio — transcripción Whisper + corrección/traducción AI"},
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
 "en": "Each checked language is saved as SRT + SMI · base language: no suffix, translations: _ko style suffix",
 "ko": "체크된 언어는 모두 SRT+SMI 저장 · 음성 언어는 접미사 없음(영상과 동일), 번역은 _ko 식 접미사",
 "ja": "チェックした言語はSRT+SMIで保存 · 基準言語は接尾辞なし、翻訳は _ko 形式の接尾辞",
 "zh": "勾选的语言都会保存为 SRT+SMI · 基准语言无后缀，翻译带 _ko 式后缀",
 "fr": "Chaque langue cochée est enregistrée en SRT + SMI · langue de base : sans suffixe, traductions : suffixe _ko",
 "pt": "Cada idioma marcado é salvo como SRT + SMI · idioma base: sem sufixo, traduções: sufixo _ko",
 "es": "Cada idioma marcado se guarda como SRT + SMI · idioma base: sin sufijo, traducciones: sufijo _ko"},
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
        "  • translates into every other checked language\nWithout it you still get plain transcription (SRT+SMI).\n\n"
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
        "  • 체크한 다른 언어로 번역\n설정 안 해도 받아쓰기 자막(SRT+SMI)은 만들어집니다.\n\n"
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
        "  • チェックした他の言語へ翻訳\n未設定でも書き起こし字幕（SRT+SMI）は作成されます。\n\n"
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
        "不设置也能生成转写字幕（SRT+SMI）。\n\n"
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
        "  • traduit vers les autres langues cochées\nSans cela, vous obtenez quand même la transcription (SRT+SMI).\n\n"
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
        "  • traduz para os outros idiomas marcados\nSem isso, você ainda recebe a transcrição (SRT+SMI).\n\n"
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
        "  • traduce a los demás idiomas marcados\nSin ello, igualmente obtienes la transcripción (SRT+SMI).\n\n"
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
 "en": ("Every checked language is saved as BOTH .srt and .smi.\n\n"
        "• Base (audio) language: same filename as the video -> players load it automatically\n"
        "• Translations: filename gets a language suffix like _ko, _es, _ja\n"
        "• Translations need a AI API key and always translate from the corrected base subtitle\n\n"
        "SMI files use cp949/UTF-8 encoding and the KRCC/ENCC class names Korean players expect."),
 "ko": ("체크한 언어는 전부 .srt와 .smi 두 형식으로 저장됩니다.\n\n"
        "• 기준(음성) 언어: 영상과 같은 파일명 -> 플레이어가 자동으로 불러옴\n"
        "• 번역: 파일명 뒤에 _ko, _es, _ja 같은 언어 접미사\n"
        "• 번역에는 AI API 키가 필요하고, 항상 교정된 기준 자막을 원본으로 번역합니다\n\n"
        "SMI는 cp949/UTF-8 인코딩과 KRCC/ENCC 클래스명을 사용해 국내 플레이어와 호환됩니다."),
 "ja": ("チェックした言語はすべて .srt と .smi の両形式で保存されます。\n\n"
        "• 基準（音声）言語: 動画と同名 -> プレイヤーが自動で読み込み\n"
        "• 翻訳: ファイル名に _ko, _es, _ja のような接尾辞\n"
        "• 翻訳にはAI APIキーが必要で、常に校正済みの基準字幕から翻訳します\n\n"
        "SMIはcp949/UTF-8エンコーディングとKRCC/ENCCクラス名を使用します。"),
 "zh": ("勾选的语言都会同时保存为 .srt 和 .smi。\n\n"
        "• 基准（音频）语言：与视频同名 -> 播放器自动加载\n• 翻译：文件名带 _ko、_es、_ja 等后缀\n"
        "• 翻译需要 AI API 密钥，且始终以校对后的基准字幕为源\n\n"
        "SMI 使用 cp949/UTF-8 编码及 KRCC/ENCC 类名，兼容韩系播放器。"),
 "fr": ("Chaque langue cochée est enregistrée en .srt ET .smi.\n\n"
        "• Langue de base : même nom que la vidéo -> chargée automatiquement\n"
        "• Traductions : suffixe de langue (_ko, _es, _ja)\n"
        "• Les traductions nécessitent une clé API AI et partent du sous-titre de base corrigé\n\n"
        "Les SMI utilisent l'encodage cp949/UTF-8 et les classes KRCC/ENCC."),
 "pt": ("Cada idioma marcado é salvo em .srt E .smi.\n\n"
        "• Idioma base: mesmo nome do vídeo -> carregado automaticamente\n"
        "• Traduções: sufixo de idioma (_ko, _es, _ja)\n"
        "• Traduções exigem chave de API AI e partem da legenda base corrigida\n\n"
        "Os SMI usam codificação cp949/UTF-8 e classes KRCC/ENCC."),
 "es": ("Cada idioma marcado se guarda en .srt Y .smi.\n\n"
        "• Idioma base: mismo nombre que el vídeo -> se carga automáticamente\n"
        "• Traducciones: sufijo de idioma (_ko, _es, _ja)\n"
        "• Las traducciones requieren clave API de AI y parten del subtítulo base corregido\n\n"
        "Los SMI usan codificación cp949/UTF-8 y clases KRCC/ENCC.")},
})
I18N.update({
"qs_b": {
 "en": ("HOW TO USE (3 steps)\n\n"
        "  1. Select video/audio files ('Browse...' — multiple files OK)\n"
        "  2. Pick the audio language, then check the subtitle languages you want\n"
        "  3. Press 'Create subtitles'\n\n"
        "Subtitle files (.srt + .smi) are saved next to each video with matching names,\n"
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
        "자막 파일(.srt + .smi)은 영상과 같은 폴더에 같은 이름으로 저장되어\n"
        "대부분의 플레이어가 자동으로 불러옵니다.\n\n"
        "선택 사항 — AI\n"
        "AI API 키를 입력하면 자동 교정·문장 분할·번역이 켜집니다.\n"
        "자세한 내용은 키 입력칸 옆 ? 버튼을 누르세요.\n\n"
        "첫 실행\n"
        "첫 사용 시 Whisper 모델(~3GB)을 한 번 내려받습니다. NVIDIA GPU가 있으면\n"
        "훨씬 빠르고, 없으면 자동으로 CPU를 사용합니다."),
 "ja": ("使い方（3ステップ）\n\n  1. 動画/音声ファイルを選択（「参照...」— 複数可）\n"
        "  2. 音声言語を選び、欲しい字幕言語をチェック\n  3. 「字幕を作成」を押す\n\n"
        "字幕ファイル（.srt + .smi）は動画と同じフォルダに同名で保存され、\n多くのプレイヤーが自動で読み込みます。\n\n"
        "オプション — AI\nAPIキーを入力すると自動校正・文分割・翻訳が有効になります。\n詳細はキー入力欄横の?ボタンで。\n\n"
        "初回実行\n初回はWhisperモデル（約3GB）をダウンロードします。NVIDIA GPUがあれば\n高速、なければ自動的にCPUを使用します。"),
 "zh": ("使用方法（3 步）\n\n  1. 选择视频/音频文件（“浏览...”— 可多选）\n"
        "  2. 选择音频语言，勾选想要的字幕语言\n  3. 点击“生成字幕”\n\n"
        "字幕文件（.srt + .smi）会以相同文件名保存在视频旁边，\n大多数播放器会自动加载。\n\n"
        "可选 — AI\n填入 AI API 密钥即可启用自动校对、分句和翻译。\n详情请点密钥框旁的 ? 按钮。\n\n"
        "首次运行\n首次使用会下载 Whisper 模型（约 3GB）。有 NVIDIA GPU 会快很多，\n没有则自动使用 CPU。"),
 "fr": ("UTILISATION (3 étapes)\n\n  1. Sélectionnez les fichiers (« Parcourir... » — plusieurs possibles)\n"
        "  2. Choisissez la langue audio puis cochez les langues de sous-titres voulues\n"
        "  3. Cliquez sur « Créer les sous-titres »\n\n"
        "Les fichiers (.srt + .smi) sont enregistrés à côté de chaque vidéo avec le même nom :\nla plupart des lecteurs les chargent automatiquement.\n\n"
        "OPTIONNEL — AI\nSaisissez une clé API AI pour activer correction, découpage et traduction.\nDétails via le bouton ? à côté du champ.\n\n"
        "PREMIER LANCEMENT\nLe modèle Whisper (~3 Go) est téléchargé une fois. Avec un GPU NVIDIA c'est\nbien plus rapide ; sinon le CPU est utilisé automatiquement."),
 "pt": ("COMO USAR (3 passos)\n\n  1. Selecione os arquivos ('Procurar...' — vários permitidos)\n"
        "  2. Escolha o idioma do áudio e marque os idiomas de legenda desejados\n  3. Clique em 'Criar legendas'\n\n"
        "As legendas (.srt + .smi) são salvas ao lado de cada vídeo com o mesmo nome:\na maioria dos players carrega automaticamente.\n\n"
        "OPCIONAL — AI\nDigite uma chave de API AI para ativar correção, divisão e tradução.\nDetalhes no botão ? ao lado do campo.\n\n"
        "PRIMEIRA EXECUÇÃO\nO modelo Whisper (~3 GB) é baixado uma vez. Com GPU NVIDIA é muito mais\nrápido; sem ela, o CPU é usado automaticamente."),
 "es": ("CÓMO USAR (3 pasos)\n\n  1. Selecciona los archivos ('Examinar...' — varios permitidos)\n"
        "  2. Elige el idioma del audio y marca los idiomas de subtítulos deseados\n  3. Pulsa 'Crear subtítulos'\n\n"
        "Los subtítulos (.srt + .smi) se guardan junto a cada vídeo con el mismo nombre:\nla mayoría de reproductores los cargan solos.\n\n"
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
        "KOREAN PLAYER SHOWS BROKEN SMI TEXT\n"
        "SMI is saved as cp949 when possible (UTF-8 otherwise). In the player, set subtitle\n"
        "encoding to 'auto detect' or the matching encoding.\n\n"
        "CORRECTION/TRANSLATION SKIPPED\nA AI API key is required — see the ? next to the key box."),
 "ko": ("자막이 비어 나옴 / '음성을 인식하지 못했습니다'\n"
        "파일이 손상됐거나 잘린 파일일 수 있습니다 (예: DVD VOB가 1GB 단위로 쪼개진 조각).\n"
        "쪼개진 조각을 하나로 합치거나 원본을 다시 추출한 뒤 시도하세요.\n\n"
        "GPU가 안 잡힘 ('CPU로 전환')\n"
        "CUDA 지원 NVIDIA GPU가 필요합니다. 설치: pip install nvidia-cublas-cu12 nvidia-cudnn-cu12\n"
        "CPU로도 동작합니다 — 속도만 느려집니다.\n\n"
        "모델 다운로드가 느림\n첫 실행만 ~3GB를 받습니다. 이후에는 바로 시작합니다.\n\n"
        "플레이어에서 SMI 글자가 깨짐\n"
        "SMI는 가능하면 cp949, 아니면 UTF-8로 저장됩니다. 플레이어의 자막 인코딩을\n'자동 감지' 또는 해당 인코딩으로 설정하세요.\n\n"
        "교정/번역이 건너뛰어짐\nAI API 키가 필요합니다 — 키 입력칸 옆 ?를 참고하세요."),
 "ja": ("字幕が空になる / 「音声を認識できませんでした」\n"
        "ファイルが破損しているか途中で切れている可能性があります（例: 1GB単位に分割されたDVD VOB）。\n分割ファイルを結合するか、ソースを再抽出してから再試行してください。\n\n"
        "GPUが使われない（「CPUに切替」）\nCUDA対応NVIDIA GPUが必要です。pip install nvidia-cublas-cu12 nvidia-cudnn-cu12\nCPUでも動作します（遅くなるだけ）。\n\n"
        "モデルのダウンロードが遅い\n初回のみ約3GBをダウンロードします。\n\n"
        "SMIの文字化け\nSMIは可能ならcp949、それ以外はUTF-8で保存されます。プレイヤーの字幕\nエンコーディングを「自動検出」にしてください。\n\n"
        "校正/翻訳がスキップされる\nAI APIキーが必要です — キー欄横の?を参照。"),
 "zh": ("字幕是空的 /「未能识别到语音」\n文件可能损坏或被截断（例如按 1GB 切分的 DVD VOB 片段）。\n请先把分段文件合并成一个，或重新提取源文件后再试。\n\n"
        "没有使用 GPU（「改用 CPU」）\n需要支持 CUDA 的 NVIDIA GPU。安装：pip install nvidia-cublas-cu12 nvidia-cudnn-cu12\n用 CPU 也能运行，只是更慢。\n\n"
        "模型下载慢\n只有首次运行下载约 3GB。\n\n"
        "播放器中 SMI 乱码\nSMI 优先以 cp949 保存（否则 UTF-8）。请把播放器字幕编码设为“自动检测”。\n\n"
        "校对/翻译被跳过\n需要 AI API 密钥 — 见密钥框旁的 ?。"),
 "fr": ("SOUS-TITRE VIDE / « aucune parole reconnue »\nLe fichier est peut-être corrompu ou tronqué (ex. morceau de VOB DVD découpé en 1 Go).\nFusionnez d'abord les morceaux ou ré-extrayez la source.\n\n"
        "GPU NON UTILISÉ (« bascule sur CPU »)\nUn GPU NVIDIA avec CUDA est requis. pip install nvidia-cublas-cu12 nvidia-cudnn-cu12\nÇa fonctionne aussi sur CPU, juste plus lentement.\n\n"
        "TÉLÉCHARGEMENT DU MODÈLE LENT\nSeul le premier lancement télécharge ~3 Go.\n\n"
        "TEXTE SMI ILLISIBLE\nLe SMI est en cp949 si possible (sinon UTF-8). Réglez l'encodage des sous-titres\ndu lecteur sur « détection auto ».\n\n"
        "CORRECTION/TRADUCTION IGNORÉES\nUne clé API AI est requise — voir le ? à côté du champ."),
 "pt": ("LEGENDA SAIU VAZIA / 'nenhuma fala reconhecida'\nO arquivo pode estar corrompido ou truncado (ex.: pedaço de VOB de DVD dividido em 1GB).\nJunte os pedaços em um arquivo ou extraia a fonte de novo.\n\n"
        "GPU NÃO USADA ('usando CPU')\nÉ preciso GPU NVIDIA com CUDA. pip install nvidia-cublas-cu12 nvidia-cudnn-cu12\nFunciona na CPU também, só mais devagar.\n\n"
        "DOWNLOAD DO MODELO LENTO\nSó a primeira execução baixa ~3 GB.\n\n"
        "TEXTO SMI QUEBRADO NO PLAYER\nO SMI é salvo em cp949 quando possível (senão UTF-8). Ajuste a codificação de\nlegendas do player para 'detecção automática'.\n\n"
        "CORREÇÃO/TRADUÇÃO PULADAS\nÉ necessária uma chave de API AI — veja o ? ao lado do campo."),
 "es": ("SUBTÍTULO VACÍO / 'no se reconoció voz'\nEl archivo puede estar dañado o truncado (p. ej., trozo de VOB de DVD partido en 1GB).\nUne primero los trozos en un archivo o vuelve a extraer la fuente.\n\n"
        "GPU NO USADA ('usando CPU')\nSe requiere GPU NVIDIA con CUDA. pip install nvidia-cublas-cu12 nvidia-cudnn-cu12\nTambién funciona con CPU, solo más lento.\n\n"
        "DESCARGA DEL MODELO LENTA\nSolo la primera ejecución descarga ~3 GB.\n\n"
        "TEXTO SMI ILEGIBLE EN EL REPRODUCTOR\nEl SMI se guarda en cp949 si es posible (si no, UTF-8). Pon la codificación de\nsubtítulos del reproductor en 'detección automática'.\n\n"
        "CORRECCIÓN/TRADUCCIÓN OMITIDAS\nSe requiere una clave API de AI — mira el ? junto al campo.")},
"ab_b": {
 "en": "{app} {v}\n{full}\n\n{c}\n\nWhisper ({m}) transcription with word-level timing\nAI correction · sentence split · translation\nOutputs SRT + SMI for every selected language",
 "ko": "{app} {v}\n{full}\n\n{c}\n\nWhisper({m}) 받아쓰기 + 단어 실측 타이밍\nAI 교정 · 문장 분할 · 번역\n선택한 모든 언어를 SRT + SMI로 출력",
 "ja": "{app} {v}\n{full}\n\n{c}\n\nWhisper（{m}）書き起こし + 単語タイミング\nAI 校正・文分割・翻訳\n選択した全言語をSRT + SMIで出力",
 "zh": "{app} {v}\n{full}\n\n{c}\n\nWhisper（{m}）转写 + 单词级时间轴\nAI 校对 · 分句 · 翻译\n所有勾选语言均输出 SRT + SMI",
 "fr": "{app} {v}\n{full}\n\n{c}\n\nTranscription Whisper ({m}) avec timing par mot\nCorrection · découpage · traduction AI\nSortie SRT + SMI pour chaque langue choisie",
 "pt": "{app} {v}\n{full}\n\n{c}\n\nTranscrição Whisper ({m}) com timing por palavra\nCorreção · divisão · tradução AI\nSaída SRT + SMI para cada idioma escolhido",
 "es": "{app} {v}\n{full}\n\n{c}\n\nTranscripción Whisper ({m}) con timing por palabra\nCorrección · división · traducción AI\nSalida SRT + SMI para cada idioma elegido"},
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
 "en": "Extra requests for the AI (optional) — applied to correction & translation:",
 "ko": "AI에게 바라는 추가 요청 (선택) — 교정·번역할 때 반영됩니다:",
 "ja": "AIへの追加リクエスト（任意）— 校正・翻訳時に反映されます:",
 "zh": "给 AI 的附加要求（可选）— 在校对·翻译时生效:",
 "fr": "Demandes supplémentaires à l'IA (facultatif) — appliquées à la correction et traduction :",
 "pt": "Pedidos extras para a IA (opcional) — aplicados na correção e tradução:",
 "es": "Peticiones extra para la IA (opcional) — se aplican en corrección y traducción:"},
"ph_extra": {
 "en": "Optional: write anything you want the AI to follow during correction & translation. What you type is remembered for next time.\ne.g. If names like Titi or Sunny are mis-heard as similar words, correct them to these spellings. / Translate in a polite tone.",
 "ko": "선택 사항: 교정·번역 때 AI가 따라줬으면 하는 요청을 자유롭게 적는 칸입니다. 입력한 내용은 다음 실행 때도 기억됩니다.\n예: Titi, Sunny 같은 이름이 비슷한 단어로 잘못 적혀 있으면 이 표기로 바로잡아줘. / 번역은 존댓말로 해줘.",
 "ja": "任意: 校正・翻訳の際にAIに守ってほしい要望を自由に書く欄です。入力した内容は次回も記憶されます。\n例: TitiやSunnyのような名前が似た単語に間違っていたらこの表記に直して。/ 翻訳は丁寧語で。",
 "zh": "可选：在此自由写下希望 AI 在校对·翻译时遵循的要求。输入的内容下次会被记住。\n例：如果 Titi、Sunny 等名字被听错成相近的词，请改成这个拼写。/ 翻译用礼貌语气。",
 "fr": "Facultatif : écrivez librement ce que l'IA doit suivre lors de la correction et de la traduction. Le contenu saisi est mémorisé.\nex. Si des noms comme Titi ou Sunny sont mal transcrits, corrige-les. / Traduis sur un ton poli.",
 "pt": "Opcional: escreva livremente o que a IA deve seguir na correção e tradução. O que você digitar fica salvo para a próxima vez.\nex.: Se nomes como Titi ou Sunny forem mal ouvidos, corrija-os. / Traduza em tom educado.",
 "es": "Opcional: escribe libremente lo que la IA debe seguir en la corrección y traducción. Lo que escribas se recuerda la próxima vez.\nej.: Si nombres como Titi o Sunny se transcriben mal, corrígelos. / Traduce en tono cortés."},
"hint_extra": {
 "en": "Applied to correction · splitting · translation — the AI follows it where it doesn't break subtitle formatting",
 "ko": "교정·분할·번역 모두에 적용됩니다 — 자막 형식을 깨지 않는 범위에서 AI가 따릅니다",
 "ja": "校正・分割・翻訳すべてに適用 — 字幕形式を壊さない範囲でAIが従います",
 "zh": "会应用于校对·分句·翻译 — AI 在不破坏字幕格式的范围内遵循",
 "fr": "Appliqué à la correction · au découpage · à la traduction — suivi tant que le format des sous-titres est préservé",
 "pt": "Aplicado à correção · divisão · tradução — seguido sem quebrar o formato das legendas",
 "es": "Se aplica a corrección · división · traducción — se sigue sin romper el formato de los subtítulos"},
"hq_extra_t": {"en": "Extra instructions", "ko": "AI 추가 지시", "ja": "追加指示", "zh": "附加指示",
 "fr": "Instructions supplémentaires", "pt": "Instruções extras", "es": "Instrucciones extra"},
"hq_extra_b": {
 "en": ("Anything you type here is passed to the AI during correction, sentence splitting\n"
        "and translation. Useful examples:\n\n"
        "  • Fix mis-heard character names:  \"If you see names like Titi or Sunny spelled\n"
        "    as similar-sounding words, correct them to these exact spellings.\"\n"
        "  • Style:  \"Translate in a polite tone.\" / \"Use Arabic numerals for numbers.\"\n"
        "  • Vocabulary:  \"This is a science show — prefer scientific terms.\"\n\n"
        "The AI applies your instructions only where they don't conflict with subtitle\n"
        "formatting rules (line count, timing etc.). Saved automatically in config.json."),
 "ko": ("여기 적은 내용은 교정·문장 분할·번역 때 AI에게 그대로 전달됩니다. 활용 예:\n\n"
        "  • 잘못 들린 이름 교정:  \"Titi, Sunny 같은 이름이 비슷한 단어로 잘못 적혀\n"
        "    있으면 이 표기로 바로잡아줘\"\n"
        "  • 문체:  \"번역은 존댓말로 해줘\" / \"숫자는 아라비아 숫자로 써줘\"\n"
        "  • 용어:  \"과학 프로그램이니 과학 용어를 우선 사용해줘\"\n\n"
        "자막 형식 규칙(줄 수·타이밍 등)과 충돌하지 않는 범위에서만 적용되고,\n"
        "내용은 config.json에 자동 저장되어 다음 실행 때 복원됩니다."),
 "ja": ("ここに書いた内容は校正・文分割・翻訳の際にAIへそのまま渡されます。活用例:\n\n"
        "  • 聞き間違えた名前の修正: 「TitiやSunnyのような名前が似た単語になっていたら\n"
        "    この表記に直して」\n"
        "  • 文体: 「翻訳は丁寧語で」/「数字はアラビア数字で」\n"
        "  • 用語: 「科学番組なので科学用語を優先して」\n\n"
        "字幕形式のルール（行数・タイミング等）と矛盾しない範囲でのみ適用され、\n"
        "内容はconfig.jsonに自動保存されます。"),
 "zh": ("这里写的内容会在校对·分句·翻译时原样传给 AI。示例：\n\n"
        "  • 纠正听错的名字：“如果 Titi、Sunny 等名字被写成相近的词，请改成这个拼写”\n"
        "  • 文体：“翻译用礼貌语气” /“数字用阿拉伯数字”\n"
        "  • 用词：“这是科普节目，请优先使用科学术语”\n\n"
        "仅在不与字幕格式规则（行数·时间轴等）冲突时应用，内容会自动保存到 config.json。"),
 "fr": ("Tout ce que vous écrivez ici est transmis à l'IA lors de la correction, du découpage\n"
        "et de la traduction. Exemples utiles :\n\n"
        "  • Corriger des noms mal entendus : « Si des noms comme Titi ou Sunny apparaissent\n"
        "    sous une forme proche, corrige-les avec cette orthographe. »\n"
        "  • Style : « Traduis sur un ton poli. » / « Utilise des chiffres arabes. »\n"
        "  • Vocabulaire : « Émission scientifique — privilégie les termes scientifiques. »\n\n"
        "Appliqué uniquement sans casser le format des sous-titres. Enregistré dans config.json."),
 "pt": ("Tudo que você escrever aqui é passado à IA na correção, divisão e tradução.\n"
        "Exemplos úteis:\n\n"
        "  • Corrigir nomes mal ouvidos: \"Se nomes como Titi ou Sunny aparecerem como\n"
        "    palavras parecidas, corrija para esta grafia.\"\n"
        "  • Estilo: \"Traduza em tom educado.\" / \"Use algarismos arábicos.\"\n"
        "  • Vocabulário: \"É um programa de ciência — prefira termos científicos.\"\n\n"
        "Aplicado só onde não quebra o formato das legendas. Salvo em config.json."),
 "es": ("Todo lo que escribas aquí se pasa a la IA en la corrección, división y traducción.\n"
        "Ejemplos útiles:\n\n"
        "  • Corregir nombres mal oídos: \"Si nombres como Titi o Sunny aparecen como\n"
        "    palabras parecidas, corrígelos con esta ortografía.\"\n"
        "  • Estilo: \"Traduce en tono cortés.\" / \"Usa números arábigos.\"\n"
        "  • Vocabulario: \"Es un programa de ciencia — prefiere términos científicos.\"\n\n"
        "Se aplica solo donde no rompe el formato de los subtítulos. Se guarda en config.json."),},
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
 "es": "gratis · sin conexión · requiere GPU"},
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
        "  1. Install Ollama (local AI runner)\n  2. Download the AI model {m} (about 7.6 GB)\n\n"
        "Takes 10-30 minutes depending on your internet speed.\n"
        "An NVIDIA GPU with 10 GB VRAM is recommended (less VRAM works but slower;\n"
        "without a GPU it will be very slow).\n\nContinue?"),
 "ko": ("내 컴퓨터에서 직접 도는 무료 AI를 설치합니다 (키 없음·한도 없음·오프라인):\n\n"
        "  1. Ollama(로컬 AI 실행기) 설치\n  2. AI 모델 {m} 다운로드 (약 7.6GB)\n\n"
        "인터넷 속도에 따라 10~30분 걸립니다.\n"
        "NVIDIA GPU VRAM 10GB 이상 권장 (그 이하도 동작하지만 느려질 수 있고,\n"
        "GPU가 없으면 매우 느려서 비추천).\n\n계속할까요?"),
 "ja": ("自分のPCで動く無料AIをセットアップします（キー不要・制限なし・オフライン）:\n\n"
        "  1. Ollama（ローカルAI実行環境）をインストール\n  2. AIモデル {m} をダウンロード（約7.6GB）\n\n"
        "回線速度により10〜30分かかります。\nNVIDIA GPU VRAM 10GB以上推奨（それ以下でも動くが遅め、\nGPUなしは非推奨）。\n\n続行しますか？"),
 "zh": ("将安装在你电脑上直接运行的免费 AI（无密钥·无限制·离线）：\n\n"
        "  1. 安装 Ollama（本地 AI 运行器）\n  2. 下载 AI 模型 {m}（约 7.6GB）\n\n"
        "视网速需要 10-30 分钟。\n建议 NVIDIA GPU 显存 10GB 以上（更小可用但较慢，\n无 GPU 不推荐）。\n\n继续吗？"),
 "fr": ("Installe une IA GRATUITE qui tourne sur VOTRE ordinateur (sans clé, sans limites, hors ligne) :\n\n"
        "  1. Installer Ollama\n  2. Télécharger le modèle {m} (~9 Go)\n\n"
        "10 à 30 minutes selon votre connexion.\nGPU NVIDIA 10 Go de VRAM recommandé (moins possible mais plus lent ;\nsans GPU, très lent).\n\nContinuer ?"),
 "pt": ("Instala uma IA GRÁTIS que roda no SEU computador (sem chave, sem limites, offline):\n\n"
        "  1. Instalar o Ollama\n  2. Baixar o modelo {m} (~7.6GB)\n\n"
        "Leva 10-30 minutos conforme sua internet.\nGPU NVIDIA com 10 GB de VRAM recomendada (menos funciona, mas mais lento;\nsem GPU fica muito lento).\n\nContinuar?"),
 "es": ("Instala una IA GRATIS que corre en TU ordenador (sin clave, sin límites, sin conexión):\n\n"
        "  1. Instalar Ollama\n  2. Descargar el modelo {m} (~7.6GB)\n\n"
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
 "en": "Downloading model {m} (~7.6GB) — takes several minutes, progress not shown...",
 "ko": "모델 {m} 다운로드 중 (~7.6GB) — 수 분 걸립니다, 진행률은 표시되지 않아요...",
 "ja": "モデル {m} をダウンロード中（約7.6GB）— 数分かかります...",
 "zh": "正在下载模型 {m}（约 7.6GB）— 需要几分钟...",
 "fr": "Téléchargement du modèle {m} (~9 Go) — plusieurs minutes...",
 "pt": "Baixando o modelo {m} (~7.6GB) — leva vários minutos...",
 "es": "Descargando el modelo {m} (~7.6GB) — tarda varios minutos..."},
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
 "en": "Choose the local AI model. Bigger = better quality but needs more VRAM.\nThe model downloads on first use. gemma4:12b is the current default\n(10 GB+ VRAM). More models will be added here as better ones appear.",
 "ko": "로컬 AI 모델을 고르세요. 클수록 품질이 좋지만 VRAM을 더 씁니다.\n모델은 처음 사용할 때 다운로드됩니다. 현재 기본값은 gemma4:12b\n(VRAM 10GB 이상). 더 나은 모델이 나오면 여기에 추가됩니다.",
 "ja": "ローカルAIモデルを選択。大きいほど高品質ですがVRAMを多く使います。\n初回使用時にダウンロードされます。現在の既定は gemma4:12b（VRAM 10GB以上）。\nより良いモデルが出たらここに追加されます。",
 "zh": "选择本地 AI 模型。越大质量越好，但需要更多显存。\n首次使用时下载。当前默认为 gemma4:12b（显存 10GB 以上）。\n出现更好的模型后会添加到这里。",
 "fr": "Choisissez le modèle local. Plus grand = meilleure qualité mais plus de VRAM.\nTéléchargé à la première utilisation. Défaut actuel : gemma4:12b (10 Go+ VRAM).\nD'autres modèles seront ajoutés ici dès qu'il y en aura de meilleurs.",
 "pt": "Escolha o modelo local. Maior = melhor qualidade, mais VRAM.\nBaixado no primeiro uso. Padrão atual: gemma4:12b (10 GB+ de VRAM).\nOutros modelos serão adicionados aqui quando surgirem melhores.",
 "es": "Elige el modelo local. Más grande = mejor calidad, más VRAM.\nSe descarga en el primer uso. Predeterminado actual: gemma4:12b (10 GB+ de VRAM).\nSe añadirán más modelos aquí cuando aparezcan mejores."},
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

REBUILD_CHUNK_WORDS = 150      # 한 번에 보내는 단어 수 (문맥 이해와 응답 길이의 절충)
REBUILD_MIN_SIMILARITY = 0.70  # 재조립 중 AI 텍스트 보정을 채택할 최소 유사도
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

    # --- 검증: 1..count 를 빠짐없이, 겹치지 않게, 순서대로 덮어야 한다 ---
    pos = 1
    for (a, b, _ov) in spans:
        if a != pos:
            return None, f"gap/overlap at {a} (expected {pos})"
        if b < a:
            return None, f"reversed range {a}-{b}"
        if b > count:
            return None, f"out of range {b} > {count}"
        pos = b + 1
    if pos != count + 1:
        return None, f"only {pos - 1} of {count} words covered"
    return spans, ""


def rebuild_from_words(entries, provider, api_key, log, extra=""):
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
    chunk_words = LOCAL_CHUNK_WORDS if provider == "local" else REBUILD_CHUNK_WORDS

    new_entries = []
    total = len(flat)
    base = 0
    block = 0
    while base < total:
        block += 1
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

        spans = None
        try:
            reply = ai_call(provider, api_key, system, user_text, max_tokens=8000, log=log)
            spans, why = _parse_rebuild_reply(reply, count)
            if spans is None:
                log(T("log_rebuild_reject", c=block, r=why) + "\n")
        except Exception as ce:
            log(T("log_rebuild_fail", e=ce) + "\n")
            spans = None

        if spans is None:
            # 이 묶음만 침묵 기준으로 안전하게 처리 (전체를 버리지 않는다)
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


SMI_LOCALE = {
    "ko": ("ko-KR", "한국어"), "en": ("en-US", "English"), "ja": ("ja-JP", "日本語"),
    "zh": ("zh-CN", "中文"), "es": ("es-ES", "Español"), "fr": ("fr-FR", "Français"),
    "de": ("de-DE", "Deutsch"), "it": ("it-IT", "Italiano"), "pt": ("pt-BR", "Português"),
    "ru": ("ru-RU", "Русский"), "vi": ("vi-VN", "Tiếng Việt"), "th": ("th-TH", "ไทย"),
    "id": ("id-ID", "Indonesia"), "hi": ("hi-IN", "हिन्दी"), "ar": ("ar-SA", "العربية"),
}

def build_smi(entries, lang_code):
    """SAMI(.smi) 생성 — 각 자막마다 시작 SYNC + 종료(&nbsp;) SYNC, CRLF, 표준 헤더."""
    locale, cc_name = SMI_LOCALE.get(lang_code, (f"{lang_code}-{lang_code.upper()}", lang_code.upper()))
    css_class = "KRCC" if lang_code == "ko" else f"{lang_code.upper()}CC"

    body = []
    for e in entries:
        text = "<br>".join(ln.replace("\r", "").replace("\n", "") for ln in e["lines"])
        body.append(f'<SYNC Start={e["start_ms"]}><P Class={css_class}>{text}')
        body.append(f'<SYNC Start={e["end_ms"]}><P Class={css_class}>&nbsp;')

    lines = [
        "<SAMI>",
        "<HEAD>",
        f"<TITLE>{cc_name}</TITLE>",
        "<SAMIParam>",
        "  Metrics {time:ms;}",
        "  Spec {MSFT:1.0;}",
        "</SAMIParam>",
        "<STYLE TYPE=\"text/css\">",
        "<!--",
        "P { margin-left:8pt; margin-right:8pt; margin-bottom:2pt;",
        "    margin-top:2pt; font-size:18pt; text-align:center;",
        "    font-family:굴림, Arial; font-weight:normal; color:white;",
        "    background-color:black; }",
        f".{css_class} {{ Name:{cc_name}; lang:{locale}; SAMIType:CC; }}",
        "#STDPrn { Name:Standard Print; }",
        "#LargePrn { Name:Large Print; font-size:20pt; }",
        "#SmallPrn { Name:Small Print; font-size:10pt; }",
        "-->",
        "</STYLE>",
        "</HEAD>",
        "<BODY>",
    ]
    lines.extend(body)
    lines.append("</BODY>")
    lines.append("</SAMI>")
    return "\r\n".join(lines) + "\r\n"


# ---------------- Claude 교정 ----------------
def correct_with_claude(entries, provider, api_key, lang_code, log, extra=""):
    lang_name = LANG_FULLNAME.get(lang_code, "the target language")

    numbered = [f"{i}: {' '.join(e['lines'])}" for i, e in enumerate(entries, 1)]
    joined = "\n".join(numbered)

    extra_clause = ""
    if extra.strip():
        extra_clause = ("OPERATOR PREFERENCES — the person running this tool added the following instructions. Apply them ONLY where they do not conflict with the strict formatting rules in this prompt (never change the number of lines, never reorder lines, keep timing untouched): "
                        + extra.strip() + " -- END OF OPERATOR PREFERENCES. ")

    # v1.2: 이 단계는 rebuild_from_words 로 문장이 온전해진 "뒤에" 돈다.
    #       토막난 자막이 아니라 완성된 문장을 보므로 문맥 판단이 훨씬 정확하다.
    #       순서를 되돌리지 말 것 (재조립 -> 교정 -> 번역).
    system = (
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
        f"Return ONLY the corrected lines in the SAME numbered format 'N: text', nothing else."
        f"\n\nBEFORE YOU ANSWER — check your own output:\n"
        f"  (a) Does your reply contain every number from 1 to {len(entries)}, exactly once?\n"
        f"  (b) Did any line change meaning, or get reworded beyond a genuine transcription fix?\n"
        f"  (c) Did you accidentally merge, split, reorder or drop a line?\n"
        f"Fix any problems, then output only the final list. Do not show your checking."
    )
    log(T("log_api_call", p=PROVIDERS[provider]["name"]) + "\n")
    text = ai_call(provider, api_key, system, joined, max_tokens=8000, log=log)

    corrected = {}
    for line in text.split("\n"):
        m = re.match(r"\s*(\d+)\s*[:：]\s*(.*)$", line)
        if m:
            corrected[int(m.group(1))] = m.group(2).strip()

    # v1.2: 응답이 일부만 와도 조용히 넘어가지 않고 경고를 남긴다.
    if len(corrected) < len(entries):
        log(T("log_correct_lines_bad", n=len(corrected), t=len(entries)) + "\n")

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


# ---------------- Claude 번역 ----------------
def translate_with_claude(src_entries, provider, api_key, target_code, log, extra="", source_name="English"):
    """기준 자막을 target_code 언어로 번역 (타이밍/줄 수 유지, 텍스트만 교체)."""
    target_name = LANG_FULLNAME.get(target_code, target_code)

    numbered = [f"{i}: {' '.join(e['lines'])}" for i, e in enumerate(src_entries, 1)]
    joined = "\n".join(numbered)

    extra_clause = ""
    if extra.strip():
        extra_clause = ("OPERATOR PREFERENCES — the person running this tool added the following instructions. Apply them ONLY where they do not conflict with the strict formatting rules in this prompt (never change the number of lines, never reorder lines, keep timing untouched): "
                        + extra.strip() + " -- END OF OPERATOR PREFERENCES. ")

    system = (
        f"You are a professional subtitle translator for a children's educational animation. "
        f"Translate each {source_name} subtitle line into natural, age-appropriate {target_name}. "
        f"{extra_clause}"
        f"These are subtitles including song lyrics and dialogue — keep translations concise "
        f"so they fit on screen, natural for children, and matching the tone of the original. "
        f"For song lyrics, prioritize natural {target_name} phrasing over literal word-for-word. "
        f"Do NOT merge or split lines, do NOT add or remove lines. "
        f"Keep the EXACT same number of lines and the same line numbers. "
        f"Return ONLY the translated lines in the SAME numbered format 'N: text', nothing else."
    )
    log(T("log_tr_call", l=target_name) + "\n")
    text = ai_call(provider, api_key, system, joined, max_tokens=8000, log=log)

    translated = {}
    for line in text.split("\n"):
        m = re.match(r"\s*(\d+)\s*[:：]\s*(.*)$", line)
        if m:
            translated[int(m.group(1))] = m.group(2).strip()

    out = []
    for i, e in enumerate(src_entries, 1):
        new_e = {k: v for k, v in e.items()}
        if i in translated and translated[i]:
            new_e["lines"] = [translated[i]]
        out.append(new_e)
    missing = len(src_entries) - len(translated)
    if missing > 0:
        log(T("log_tr_missing", n=missing) + "\n")
    log(T("log_tr_done", n=len(translated)) + "\n")
    return out


# ---------------- AI API 호출 (v1.1: Gemini/Qwen/Claude 공용, SDK 없이 REST) ----------------
def _post_json(url, payload, headers, timeout=180, log=None, retries=3):
    """POST 요청. 429(무료 한도 초과)·일시적 5xx는 대기 후 자동 재시도."""
    import urllib.request
    import urllib.error
    data = json.dumps(payload).encode("utf-8")
    waits = [20, 40, 60]  # 재시도 대기(초) — 무료 티어 분당 한도 회복용
    last_err = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode(errors="ignore")[:300]
            except Exception:
                pass
            last_err = RuntimeError(f"{e.code} {e.reason}: {body}")
            if e.code in (429, 500, 502, 503, 529) and attempt < retries:
                w = waits[min(attempt, len(waits) - 1)]
                if log:
                    log(T("log_rate_wait", s=w, i=attempt + 1, n=retries) + "\n")
                time.sleep(w)
                continue
            raise last_err from None
        except urllib.error.URLError as ue:
            if "11434" in url or "127.0.0.1" in url:
                raise RuntimeError(f"local AI server not reachable ({ue.reason})") from None
            raise RuntimeError(f"network error: {ue.reason}") from None
    raise last_err


def ai_call(provider, api_key, system, user_text, max_tokens=8000, log=None):
    """선택된 AI 엔진으로 system+user 요청을 보내고 텍스트 응답을 돌려준다.
    (429 등 일시 오류는 _post_json에서 자동 재시도)"""
    if provider == "claude":
        data = _post_json(
            "https://api.anthropic.com/v1/messages",
            {"model": PROVIDERS["claude"]["model"], "max_tokens": max_tokens,
             "system": system,
             "messages": [{"role": "user", "content": user_text}]},
            {"x-api-key": api_key, "anthropic-version": "2023-06-01",
             "content-type": "application/json"}, log=log)
        return "".join(b.get("text", "") for b in data.get("content", [])
                       if b.get("type") == "text")

    if provider == "gemini":
        # 무료 티어 모델명이 구형화되면(404) 다음 후보를 자동으로 시도
        models = PROVIDERS["gemini"]["models"]
        if _GEMINI_OK_MODEL["name"]:
            models = [_GEMINI_OK_MODEL["name"]] + [m for m in models
                                                  if m != _GEMINI_OK_MODEL["name"]]
        last = None
        for mi, model in enumerate(models):
            try:
                data = _post_json(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    {"systemInstruction": {"parts": [{"text": system}]},
                     "contents": [{"role": "user", "parts": [{"text": user_text}]}],
                     "generationConfig": {"maxOutputTokens": max_tokens}},
                    {"x-goog-api-key": api_key, "content-type": "application/json"}, log=log)
                _GEMINI_OK_MODEL["name"] = model
                try:
                    return "".join(pt.get("text", "")
                                   for pt in data["candidates"][0]["content"]["parts"])
                except (KeyError, IndexError):
                    raise RuntimeError(f"unexpected Gemini response: {str(data)[:200]}")
            except RuntimeError as e:
                last = e
                if str(e).startswith("404") and mi + 1 < len(models):
                    continue  # 다음 모델 후보 시도
                raise
        raise last

    if provider == "local":
        # v1.2: 스트리밍으로 받는다.
        #   이전에는 통짜 POST(timeout=180)라 응답이 다 올 때까지 화면이 완전히 멈춰 있었고,
        #   느린 GPU에서 180초를 넘기면 "서버에 연결할 수 없음"이라는 엉뚱한 에러가 났다.
        #   스트리밍이면 토큰이 오는 동안 계속 살아 있으므로 총 소요 시간 제한이 사라지고,
        #   로그에 진행 상황을 실시간으로 보여줄 수 있다.
        return _local_chat_stream(system, user_text, max_tokens, log=log,
                                  read_timeout=LOCAL_READ_TIMEOUT)

    raise ValueError(f"unknown provider: {provider}")


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
    받은 바이트/전체 바이트가 그대로 넘어와 정확한 %를 보여줄 수 있다."""
    last_shown = -1.0
    last_step = ""
    total_final = 0
    for msg in _stream_ndjson(f"{OLLAMA_URL}/api/pull",
                              {"model": model, "stream": True},
                              read_timeout, log=log, stall_key="log_local_stall"):
        if msg.get("error"):
            raise RuntimeError(str(msg["error"])[:200])
        status = str(msg.get("status") or "")
        total = msg.get("total") or 0
        done = msg.get("completed") or 0
        if total:
            total_final = max(total_final, total)
            pct = done * 100.0 / total
            # 0.5% 이상 움직였을 때만 갱신 (로그 폭주 방지)
            if pct - last_shown >= 0.5 or done >= total:
                last_shown = pct
                log("\r" + T("log_pull_pct", m=model, p=f"{pct:.1f}",
                             d=_human_bytes(done), t=_human_bytes(total), e=""))
        elif status and status != last_step:
            last_step = status
            log(T("log_pull_step", s=status) + "\n")
    log(T("log_pull_done", t=_human_bytes(total_final)) + "\n")
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
            "num_ctx": LOCAL_NUM_CTX,
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
    if not out:
        raise RuntimeError("local AI returned an empty response")
    return out



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


def local_server_models(timeout=1.5):
    """Ollama 서버가 떠 있으면 설치된 모델 이름 목록, 아니면 None."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        return [m.get("name", "") for m in data.get("models", [])]
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
        root.geometry("660x940")
        root.minsize(600, 840)

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
        self.api_key = tk.StringVar(value=self.api_keys.get(prov, ""))
        # v1.2: 첫 실행(키가 하나도 없고 안내를 본 적 없음) -> Gemini 권장 안내 1회
        self.show_intro = not cfg.get("intro_shown") and not any(self.api_keys.values())
        # AI 추가 지시 자유 입력칸 — 사용자가 직접 입력한 내용만 config에 저장/복원
        self.extra_prompt_value = (cfg.get("extra_prompt") or "").strip()
        try:
            self.extra_h = min(12, max(3, int(cfg.get("extra_h", 5))))  # v4.7: 5줄 시작
        except Exception:
            self.extra_h = 5
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
        ttk.Label(frm_src, text=T("hint_src"), foreground="#666",
                  wraplength=600, justify="left").pack(anchor="w", padx=10, pady=(0, 8))

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
            self.prov_combo = ttk.Combobox(
                krow, state="readonly", width=24,
                values=[self.prov_label(c) for c in self._prov_codes])
            self.prov_combo.current(self._prov_codes.index(self.ai_provider))
            self.prov_combo.pack(side="left", padx=(6, 0))
            self.prov_combo.bind("<<ComboboxSelected>>", self.on_provider_changed)
            self.key_entry = None
            if self.ai_provider == "local":
                # 로컬 AI: 키 불필요 — 상태 표시 + 설치/시작/다운로드 버튼
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
            cols = 4
            for idx, code in enumerate(LANG_CODES):
                r, c = divmod(idx, cols)
                chk = ttk.Checkbutton(lang_grid, text=lang_label(code),
                                      variable=self.lang_vars[code])
                chk.grid(row=r, column=c, sticky="w", padx=4, pady=2)
                self.lang_checks[code] = chk
            ttk.Label(frm_key, text=T("hint_out"), foreground="#666",
                      wraplength=600, justify="left").pack(anchor="w", padx=10, pady=(0, 4))
            ttk.Separator(frm_key, orient="horizontal").pack(fill="x", padx=10, pady=(2, 4))

            # AI 추가 지시
            nrow = ttk.Frame(frm_key); nrow.pack(fill="x", padx=10, pady=(0, 2))
            ttk.Label(nrow, text=T("lbl_extra")).pack(side="left")
            ttk.Button(nrow, text="+", width=2,
                       command=lambda: self.resize_extra(+1)).pack(side="right")
            ttk.Button(nrow, text="−", width=2,
                       command=lambda: self.resize_extra(-1)).pack(side="right", padx=(6, 2))
            self.qbtn(nrow, "hq_extra_t", "hq_extra_b").pack(side="right", padx=(0, 6))
            self.extra_text = tk.Text(frm_key, height=self.extra_h, wrap="word", undo=True)
            self.extra_text.pack(fill="x", expand=False, padx=10, pady=(2, 2))
            self.extra_text.bind("<FocusIn>", self._extra_focus_in)
            self.extra_text.bind("<FocusOut>", self._extra_focus_out)
            self.extra_text.bind("<KeyRelease>", self._extra_changed)
            self._extra_fg = str(self.extra_text.cget("foreground") or "black")
            self._refresh_extra_text()
            ttk.Label(frm_key, text=T("hint_extra"), foreground="#888",
                      wraplength=600, justify="left").pack(anchor="w", padx=10, pady=(0, 8))

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
        frm_log = ttk.LabelFrame(self.body, text=T("frm_log"))
        frm_log.pack(fill="both", expand=True, **pad)
        self.log = tk.Text(frm_log, height=12, wrap="word", state="disabled")
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
                    T("local_install_info", m=LOCAL_MODEL["name"])):
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
                self.write_log(T("log_local_pulling", m=LOCAL_MODEL["name"]) + "\n")
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

    def resize_extra(self, delta):
        # v4.7: 추가 지시 칸 높이 조절 (3~12줄, 설정에 저장)
        self.extra_h = min(12, max(3, self.extra_h + delta))
        self.extra_text.configure(height=self.extra_h)
        self.save_settings()

    def get_extra(self):
        """실제 추가 지시 내용 (안내문 표시 중이면 빈 문자열)"""
        return "" if self._extra_ph_active else self.extra_prompt_value

    def toggle_show(self):
        if not self._ph_active:
            self.key_entry.configure(show="" if self.show_key.get() else "*")

    def update_key_hint(self):
        if not self.use_claude.get():
            return  # 끔 상태에서는 힌트 라벨 자체가 없음
        if self.ai_provider == "local" or self.key_entry is None:
            return  # 로컬 AI는 build_ui에서 상태를 직접 표시
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
        txt = T("st_remaining", p=f"{pct:.0f}", t=eta_text)
        if self._cur_file:
            txt = f"{self._cur_file}   ·   {txt}"  # v4.12: 현재 파일 표시
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
        self.cancel_btn.configure(state="disabled")

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
        threading.Thread(target=self.generate,
                         args=(files, selected, self.audio_lang_code), daemon=True).start()

    def generate(self, files, langs, audio_code):
        try:
            from faster_whisper import WhisperModel

            self.write_log("\n" + T("log_loading", m=MODEL_NAME) + "\n")
            self.write_log(T("log_first") + "\n")
            try:
                model = WhisperModel(MODEL_NAME, device="cuda", compute_type="float16")
                self.write_log(T("log_gpu") + "\n")
            except Exception as gpu_err:
                self.write_log(T("log_gpu_fail", e=gpu_err) + "\n")
                model = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8")

            use_ai = self.use_claude.get()
            prov = self.ai_provider
            key = self.api_key.get().strip() if use_ai else ""
            if use_ai and prov == "local":
                key = "local"  # 로컬 AI는 키가 필요 없음

            out_paths = []
            errors = []   # v4.6: (파일명, 에러 요약, 힌트 i18n 키 or None)
            n_ok = 0
            n_skip = 0    # v4.12: 자막이 이미 있어 건너뛴 파일
            n_files = len(files)
            W = 3  # whisper 가중치 (진행률 배분)

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

                def prog(frac, eta_text=None, _fi=fi):
                    overall = ((_fi + min(1.0, frac)) / n_files) * 100
                    self.root.after(0, self.set_progress, overall, eta_text or T("calc"))

                def do_transcribe(media_path, jobs_this):
                    """(all_words, info, cancelled) 반환 — 디코딩 실패 시 예외 발생"""
                    segments, info = model.transcribe(
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
                        elapsed = time.time() - start_t
                        eta_text = human_dur(elapsed * (total - done) / done) if done > 0 else T("calc")
                        prog((done / total) * (W / jobs_this), eta_text)
                    return words, info, False

                # v4.6: 파일별 에러 격리 — 한 파일이 실패해도 다음 파일로 계속
                tmp_wav = None
                try:
                    # ---------- 1) 음성 인식 (whisper) ----------
                    self.write_log("\n" + T("log_recog", l=src_label) + "\n")
                    jobs_est = W + len([c for c in langs if c != audio_code])
                    try:
                        all_words, info, cancelled = do_transcribe(path, jobs_est)
                    except Exception:
                        # v4.6: 디코딩 실패 -> ffmpeg로 오디오만 추출해서 재시도
                        self.write_log(T("log_fallback") + "\n")
                        tmp_wav = extract_audio_ffmpeg(path, self.write_log)
                        if tmp_wav is None:
                            raise
                        all_words, info, cancelled = do_transcribe(tmp_wav, jobs_est)
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
                    jobs_this = W + len(other_langs)
                    units_done = W

                    # 인식 결과 0개 -> 빈 자막을 만들지 않고 경고 + 요약에 기록
                    if not all_words:
                        self.write_log("\n" + T("log_no_speech") + "\n")
                        errors.append((fname, T("err_nospeech_short"), "hint_nospeech"))
                        prog(1.0)
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
                            with open(words_srt, "w", encoding="utf-8", newline="") as f:
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
                        try:
                            src_entries = rebuild_from_words(
                                src_entries, prov, key, self.write_log,
                                extra=self.get_extra())
                        except Exception as se:
                            self.write_log(T("log_rebuild_fail", e=se) + "\n")
                            try:
                                src_entries = split_by_pauses(src_entries, self.write_log)
                            except Exception as pe:
                                self.write_log(T("log_pause_fail", e=pe) + "\n")

                        self.write_log("\n" + T("log_correct", l=base_label) + "\n")
                        try:
                            src_entries = correct_with_claude(src_entries, prov, key, base_code, self.write_log,
                                                              extra=self.get_extra())
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

                    # 최종 자막 기준으로 끝 1초 지연 적용 (겹침 방지)
                    src_entries = apply_trailing_delay(src_entries, extra=1.0)

                    # 기준 언어: SRT + SMI (접미사 없음 -> 플레이어 자동 인식)
                    src_srt = f"{base}.srt"
                    with open(src_srt, "w", encoding="utf-8", newline="") as f:
                        f.write(build_srt(src_entries))
                    out_paths.append(src_srt)
                    self.write_log(T("log_saved", p=src_srt) + "\n")

                    src_smi = f"{base}.smi"
                    src_smi_content = build_smi(src_entries, base_code)
                    try:
                        with open(src_smi, "w", encoding="cp949", newline="") as f:
                            f.write(src_smi_content)
                    except UnicodeEncodeError:
                        with open(src_smi, "w", encoding="utf-8", newline="") as f:
                            f.write(src_smi_content)
                    out_paths.append(src_smi)
                    self.write_log(T("log_saved", p=src_smi) + "\n")

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
                            units_done += 1
                            prog(units_done / jobs_this)
                            continue

                        try:
                            tr_entries = translate_with_claude(src_entries, prov, key, code, self.write_log,
                                                               extra=self.get_extra(),
                                                               source_name=source_name)
                        except Exception as te:
                            self.write_log(T("log_tr_fail", l=lang_lbl, e=te) + "\n")
                            units_done += 1
                            prog(units_done / jobs_this)
                            continue

                        srt_path = f"{base}_{code}.srt"
                        with open(srt_path, "w", encoding="utf-8", newline="") as f:
                            f.write(build_srt(tr_entries))
                        out_paths.append(srt_path)
                        self.write_log(T("log_saved", p=srt_path) + "\n")

                        smi_path = f"{base}_{code}.smi"
                        smi_content = build_smi(tr_entries, code)
                        try:
                            with open(smi_path, "w", encoding="cp949", newline="") as f:
                                f.write(smi_content)
                        except UnicodeEncodeError:
                            with open(smi_path, "w", encoding="utf-8", newline="") as f:
                                f.write(smi_content)
                        out_paths.append(smi_path)
                        self.write_log(T("log_saved", p=smi_path) + "\n")

                        units_done += 1
                        prog(units_done / jobs_this)


                    n_ok += 1
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
            self.write_log("\n" + T("log_all_done", n=len(out_paths)) + "\n")
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
            if out_paths:
                self.root.after(0, lambda: self.open_folder(out_paths[0]))
        except Exception as e:
            self.write_log("\n" + T("t_error") + f": {e}\n")
            self.root.after(0, lambda: messagebox.showerror(T("t_error"), str(e)))
        finally:
            self._cur_file = ""
            self.root.after(0, lambda: self.lock(False))

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
