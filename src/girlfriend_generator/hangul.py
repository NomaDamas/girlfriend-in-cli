"""App-level Korean Hangul composer using 2-set (두벌식) keyboard layout.

The user types in ENGLISH keyboard mode. This module converts keystrokes
to Korean jamo and composes them into Hangul syllables in real-time.

Usage:
    composer = HangulComposer()
    composer.feed('r')   # ㄱ
    composer.feed('k')   # 가
    composer.feed('s')   # 간
    print(composer.text)  # "간"
"""

from __future__ import annotations

# 두벌식 keyboard mapping: English key → Korean jamo
_CONSONANT_MAP = {
    'r': 'ㄱ', 'R': 'ㄲ', 's': 'ㄴ', 'e': 'ㄷ', 'E': 'ㄸ',
    'f': 'ㄹ', 'a': 'ㅁ', 'q': 'ㅂ', 'Q': 'ㅃ', 't': 'ㅅ',
    'T': 'ㅆ', 'd': 'ㅇ', 'w': 'ㅈ', 'W': 'ㅉ', 'c': 'ㅊ',
    'z': 'ㅋ', 'x': 'ㅌ', 'v': 'ㅍ', 'g': 'ㅎ',
}

_VOWEL_MAP = {
    'k': 'ㅏ', 'o': 'ㅐ', 'i': 'ㅑ', 'O': 'ㅒ', 'j': 'ㅓ',
    'p': 'ㅔ', 'u': 'ㅕ', 'P': 'ㅖ', 'h': 'ㅗ', 'y': 'ㅛ',
    'n': 'ㅜ', 'b': 'ㅠ', 'm': 'ㅡ', 'l': 'ㅣ',
}

# Compound vowels: (vowel1, vowel2) → compound
_COMPOUND_VOWELS = {
    ('ㅗ', 'ㅏ'): 'ㅘ', ('ㅗ', 'ㅐ'): 'ㅙ', ('ㅗ', 'ㅣ'): 'ㅚ',
    ('ㅜ', 'ㅓ'): 'ㅝ', ('ㅜ', 'ㅔ'): 'ㅞ', ('ㅜ', 'ㅣ'): 'ㅟ',
    ('ㅡ', 'ㅣ'): 'ㅢ',
}

# 초성 (leading consonant) index
_CHOSEONG = list('ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ')
# 중성 (vowel) index
_JUNGSEONG = list('ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ')
# 종성 (trailing consonant) index — 0 = none
_JONGSEONG = [''] + list('ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ')

# Compound jongseong: (jong1, added_consonant) → compound_jong
_COMPOUND_JONG = {
    ('ㄱ', 'ㅅ'): 'ㄳ', ('ㄴ', 'ㅈ'): 'ㄵ', ('ㄴ', 'ㅎ'): 'ㄶ',
    ('ㄹ', 'ㄱ'): 'ㄺ', ('ㄹ', 'ㅁ'): 'ㄻ', ('ㄹ', 'ㅂ'): 'ㄼ',
    ('ㄹ', 'ㅅ'): 'ㄽ', ('ㄹ', 'ㅌ'): 'ㄾ', ('ㄹ', 'ㅍ'): 'ㄿ',
    ('ㄹ', 'ㅎ'): 'ㅀ', ('ㅂ', 'ㅅ'): 'ㅄ',
}

# Decompose compound jongseong back to (first, second)
_DECOMPOSE_JONG = {v: k for k, v in _COMPOUND_JONG.items()}

# Jamo that can be both choseong and jongseong
_JONGSEONG_TO_CHOSEONG = {
    'ㄱ': 'ㄱ', 'ㄲ': 'ㄲ', 'ㄴ': 'ㄴ', 'ㄷ': 'ㄷ', 'ㄹ': 'ㄹ',
    'ㅁ': 'ㅁ', 'ㅂ': 'ㅂ', 'ㅅ': 'ㅅ', 'ㅆ': 'ㅆ', 'ㅇ': 'ㅇ',
    'ㅈ': 'ㅈ', 'ㅊ': 'ㅊ', 'ㅋ': 'ㅋ', 'ㅌ': 'ㅌ', 'ㅍ': 'ㅍ',
    'ㅎ': 'ㅎ',
}


def _compose_syllable(cho: str, jung: str, jong: str = '') -> str:
    """Compose a Hangul syllable from jamo."""
    if cho not in _CHOSEONG or jung not in _JUNGSEONG:
        return cho + jung + jong
    cho_i = _CHOSEONG.index(cho)
    jung_i = _JUNGSEONG.index(jung)
    jong_i = _JONGSEONG.index(jong) if jong in _JONGSEONG else 0
    code = 0xAC00 + (cho_i * 21 + jung_i) * 28 + jong_i
    return chr(code)


class HangulComposer:
    """Real-time Hangul composition state machine."""

    def __init__(self) -> None:
        self.committed = ""  # Completed text
        self._cho: str = ""   # Current leading consonant
        self._jung: str = ""  # Current vowel
        self._jong: str = ""  # Current trailing consonant
        self.korean_mode = False  # Toggle with right-Alt or Han/Eng key

    @property
    def composing(self) -> str:
        """The character currently being composed (not yet committed)."""
        if self._cho and self._jung:
            return _compose_syllable(self._cho, self._jung, self._jong)
        if self._cho:
            return self._cho
        if self._jung:
            return self._jung
        return ""

    @property
    def text(self) -> str:
        """Full text including composing character."""
        return self.committed + self.composing

    def feed(self, key: str) -> None:
        """Process a single keystroke."""
        if not key or len(key) != 1:
            return

        consonant = _CONSONANT_MAP.get(key)
        vowel = _VOWEL_MAP.get(key)

        if consonant:
            self._feed_consonant(consonant)
        elif vowel:
            self._feed_vowel(vowel)
        else:
            # Non-Korean key: commit current composition and pass through
            self._commit()
            self.committed += key

    def _feed_consonant(self, jamo: str) -> None:
        if not self._cho and not self._jung:
            # Start: set as choseong
            self._cho = jamo
        elif not self._cho and self._jung:
            # Standalone vowel + consonant: commit vowel, start new
            self._commit()
            self._cho = jamo
        elif self._cho and not self._jung:
            # Already have choseong, no vowel: commit and start new
            self._commit()
            self._cho = jamo
        elif self._cho and self._jung and not self._jong:
            # Have cho+jung, add as jongseong
            if jamo in _JONGSEONG:
                self._jong = jamo
            else:
                self._commit()
                self._cho = jamo
        elif self._cho and self._jung and self._jong:
            # Already have jongseong, try compound
            compound = _COMPOUND_JONG.get((self._jong, jamo))
            if compound and compound in _JONGSEONG:
                self._jong = compound
            else:
                # Commit current and start new with this consonant
                self._commit()
                self._cho = jamo

    def _feed_vowel(self, jamo: str) -> None:
        if not self._cho and not self._jung:
            # Standalone vowel
            self._jung = jamo
        elif self._cho and not self._jung:
            # Add vowel to consonant
            self._jung = jamo
        elif self._jung and not self._cho:
            # Try compound vowel
            compound = _COMPOUND_VOWELS.get((self._jung, jamo))
            if compound:
                self._jung = compound
            else:
                self._commit()
                self._jung = jamo
        elif self._cho and self._jung and not self._jong:
            # Try compound vowel
            compound = _COMPOUND_VOWELS.get((self._jung, jamo))
            if compound:
                self._jung = compound
            else:
                self._commit()
                self._jung = jamo
        elif self._cho and self._jung and self._jong:
            # Vowel after jongseong: break off jongseong as next choseong
            if self._jong in _DECOMPOSE_JONG:
                # Compound jongseong: split
                first, second = _DECOMPOSE_JONG[self._jong]
                self._jong = first
                self._commit()
                self._cho = second
                self._jung = jamo
            elif self._jong in _JONGSEONG_TO_CHOSEONG:
                prev_jong = self._jong
                self._jong = ""
                self._commit()
                self._cho = _JONGSEONG_TO_CHOSEONG[prev_jong]
                self._jung = jamo
            else:
                self._commit()
                self._jung = jamo

    def _commit(self) -> None:
        """Commit current composing character to committed text."""
        composed = self.composing
        if composed:
            self.committed += composed
        self._cho = ""
        self._jung = ""
        self._jong = ""

    def backspace(self) -> None:
        """Delete one composition step."""
        if self._jong:
            # Remove jongseong (or decompose compound)
            if self._jong in _DECOMPOSE_JONG:
                self._jong = _DECOMPOSE_JONG[self._jong][0]
            else:
                self._jong = ""
        elif self._jung:
            # Check compound vowel
            for (v1, v2), compound in _COMPOUND_VOWELS.items():
                if compound == self._jung:
                    self._jung = v1
                    return
            self._jung = ""
        elif self._cho:
            self._cho = ""
        elif self.committed:
            self.committed = self.committed[:-1]

    def commit_all(self) -> str:
        """Commit everything and return full text."""
        self._commit()
        result = self.committed
        self.committed = ""
        return result

    def clear(self) -> None:
        """Clear all state."""
        self.committed = ""
        self._cho = ""
        self._jung = ""
        self._jong = ""

    def set_text(self, text: str) -> None:
        """Set committed text directly (for loading draft)."""
        self._commit()
        self.committed = text
