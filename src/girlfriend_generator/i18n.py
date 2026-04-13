"""Internationalization for menus and UI text."""

from __future__ import annotations

import json
from pathlib import Path


_STRINGS = {
    "ko": {
        "main_title": "♡ 무엇을 하시겠어요?",
        "new_chat": "새 대화",
        "new_chat_desc": "페르소나를 선택하고 대화 시작",
        "chat_rooms": "채팅방",
        "chat_rooms_desc": "저장된 대화 이어가기",
        "persona_studio": "페르소나 스튜디오",
        "persona_studio_desc": "나만의 페르소나 만들기",
        "settings": "설정",
        "settings_desc": "Provider, 성능, API 키",
        "setup_guide": "설정 가이드",
        "setup_guide_desc": "API 키 / 로그인 방식 안내",
        "quit": "종료",
        "quit_desc": "다음에 또 봐요",
        "move": "이동",
        "select": "선택",
        "back": "뒤로",
        "difficulty": "난이도",
        "easy": "쉬움",
        "normal": "보통",
        "hard": "어려움",
        "nightmare": "악몽",
        "language": "언어",
        "game_over": "게임 오버",
        "success": "해피 엔딩",
    },
    "en": {
        "main_title": "♡ What would you like to do?",
        "new_chat": "New Chat",
        "new_chat_desc": "Pick a persona and start chatting",
        "chat_rooms": "Chat Rooms",
        "chat_rooms_desc": "Continue saved conversations",
        "persona_studio": "Persona Studio",
        "persona_studio_desc": "Create your own persona",
        "settings": "Settings",
        "settings_desc": "Provider, performance, API keys",
        "setup_guide": "Setup Guide",
        "setup_guide_desc": "API key / login setup help",
        "quit": "Quit",
        "quit_desc": "See you next time",
        "move": "move",
        "select": "select",
        "back": "back",
        "difficulty": "Difficulty",
        "easy": "Easy",
        "normal": "Normal",
        "hard": "Hard",
        "nightmare": "Nightmare",
        "language": "Language",
        "game_over": "GAME OVER",
        "success": "HAPPY ENDING",
    },
    "ja": {
        "main_title": "♡ 何をしたいですか？",
        "new_chat": "新しい会話",
        "new_chat_desc": "ペルソナを選んで会話開始",
        "chat_rooms": "チャットルーム",
        "chat_rooms_desc": "保存された会話を続ける",
        "persona_studio": "ペルソナスタジオ",
        "persona_studio_desc": "オリジナルペルソナを作成",
        "settings": "設定",
        "settings_desc": "Provider、性能、APIキー",
        "setup_guide": "設定ガイド",
        "setup_guide_desc": "APIキー / ログイン案内",
        "quit": "終了",
        "quit_desc": "またね",
        "move": "移動",
        "select": "選択",
        "back": "戻る",
        "difficulty": "難易度",
        "easy": "簡単",
        "normal": "普通",
        "hard": "難しい",
        "nightmare": "悪夢",
        "language": "言語",
        "game_over": "ゲームオーバー",
        "success": "ハッピーエンド",
    },
    "zh": {
        "main_title": "♡ 你想做什么？",
        "new_chat": "新对话",
        "new_chat_desc": "选择角色开始聊天",
        "chat_rooms": "聊天室",
        "chat_rooms_desc": "继续之前的对话",
        "persona_studio": "角色工作室",
        "persona_studio_desc": "创建你的专属角色",
        "settings": "设置",
        "settings_desc": "提供商、性能、API密钥",
        "setup_guide": "设置指南",
        "setup_guide_desc": "API 密钥 / 登录说明",
        "quit": "退出",
        "quit_desc": "再见",
        "move": "移动",
        "select": "选择",
        "back": "返回",
        "difficulty": "难度",
        "easy": "简单",
        "normal": "普通",
        "hard": "困难",
        "nightmare": "噩梦",
        "language": "语言",
        "game_over": "游戏结束",
        "success": "完美结局",
    },
}


_PREFS_PATH = Path.home() / ".girlfriend-in-cli" / "prefs.json"


def get_language() -> str:
    try:
        data = json.loads(_PREFS_PATH.read_text(encoding="utf-8"))
        lang = data.get("language", "ko")
        if lang in _STRINGS:
            return lang
    except Exception:
        pass
    return "ko"


def set_language(lang: str) -> None:
    if lang not in _STRINGS:
        return
    _PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(_PREFS_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    data["language"] = lang
    _PREFS_PATH.write_text(json.dumps(data), encoding="utf-8")


def t(key: str, lang: str | None = None) -> str:
    lang = lang or get_language()
    return _STRINGS.get(lang, _STRINGS["ko"]).get(key, key)
