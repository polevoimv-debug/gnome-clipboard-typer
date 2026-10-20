from __future__ import annotations

import importlib.machinery
import importlib.util
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import ModuleType
import unittest


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "src" / "helper" / "clipboard-typer-helper"


def load_helper() -> ModuleType:
    loader = importlib.machinery.SourceFileLoader("clipboard_typer_helper", str(HELPER))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module


helper = load_helper()

SHIFT_L, CAPS, RETURN, TAB, SPACE = 50, 66, 36, 23, 65
US_ROWS = ((10, "1234567890-=", "!@#$%^&*()_+"), (24, "qwertyuiop[]", "QWERTYUIOP{}"),
           (38, "asdfghjkl;'`", 'ASDFGHJKL:"~'), (51, "\\", "|"), (52, "zxcvbnm,./", "ZXCVBNM<>?"))
RU_ROWS = ((10, '1234567890-=', '!"№;%:?*()_+'), (24, "йцукенгшщзхъ", "ЙЦУКЕНГШЩЗХЪ"),
           (38, "фывапролджэё", "ФЫВАПРОЛДЖЭЁ"), (51, "\\", "/"), (52, "ячсмитьбю.", "ЯЧСМИТЬБЮ,"))
SPECIAL = {SHIFT_L: helper.XK_SHIFT_L, CAPS: helper.XK_CAPS_LOCK, RETURN: helper.XK_RETURN, TAB: helper.XK_TAB}
CYRILLIC = {char: keysym for keysym, char in helper.CYRILLIC_KEYSYMS.items()}


def keysym(char: str) -> int:
    return CYRILLIC.get(char, ord(char))


class FakeKeyboard:
    """An XKB keyboard with "us,ru" groups that records what an application would receive."""

    def __init__(self, layouts: tuple[str, ...] = ("us", "ru"), group: int = 0, caps: bool = False) -> None:
        rows = {"us": US_ROWS, "ru": RU_ROWS}
        self.keys: dict[int, list[tuple[int, int]]] = {}
        for layout in layouts:
            for start, low, high in rows[layout]:
                for index, (a, b) in enumerate(zip(low, high)):
                    self.keys.setdefault(start + index, []).append((keysym(a), keysym(b)))
        for code, sym in {**SPECIAL, SPACE: 0x20}.items():
            self.keys[code] = [(sym, sym)]
        self.group = group
        self.locked = helper.LOCK_MASK if caps else 0
        self.down: set[int] = set()
        self.typed: list[str] = []
        self.group_locks = 0
        self.remapped: dict[int, int] = {}

    def keycode_range(self) -> tuple[int, int]:
        return 8, 255

    def keysym_at(self, keycode: int, group: int, level: int) -> int:
        groups = self.keys.get(keycode, [])
        return groups[group][level] if group < len(groups) else 0

    def lookup(self, keycode: int, state: int) -> int:
        groups = self.keys.get(keycode)
        if not groups:
            return 0
        pair = groups[((state >> helper.GROUP_SHIFT) & 3) % len(groups)]
        upper = bool(state & helper.SHIFT_MASK) != bool(state & helper.LOCK_MASK and chr(pair[0] & 0xFF).isalpha())
        return pair[1] if upper else pair[0]

    def keycode_for(self, sym: int) -> int:
        return next((code for code, groups in self.keys.items() if groups[0][0] == sym), 0)

    def modifiers_for(self, sym: int) -> int:
        return helper.SHIFT_MASK if sym == helper.XK_SHIFT_L else 0

    def char_of(self, sym: int) -> str | None:
        return helper.keysym_to_char(sym)

    def state(self) -> object:
        return helper.KeyboardState(self.group, self.group, self.locked)

    def pressed_keycodes(self) -> list[int]:
        return sorted(self.down)

    def key(self, keycode: int, press: bool) -> None:
        if not press:
            self.down.discard(keycode)
            return
        self.down.add(keycode)
        if keycode == CAPS:
            self.locked ^= helper.LOCK_MASK
            return
        if keycode == SHIFT_L:
            return
        sym = self.remapped.get(keycode) or self.lookup(
            keycode, self.locked | (helper.SHIFT_MASK if SHIFT_L in self.down else 0) | self.group << helper.GROUP_SHIFT)
        self.typed.append({helper.XK_RETURN: "\n", helper.XK_TAB: "\t"}.get(sym) or helper.keysym_to_char(sym) or "?")

    def lock_group(self, group: int) -> None:
        self.group = group
        self.group_locks += 1

    def set_keysym(self, keycode: int, sym: int) -> None:
        if sym:
            self.remapped[keycode] = sym
        else:
            self.remapped.pop(keycode, None)

    def sync(self) -> None:
        pass


def type_with(keyboard: FakeKeyboard, text: str) -> str:
    helper.STOPPED.clear()
    typer = helper.Typer(keyboard, 0)
    typer.run(text)
    return "".join(keyboard.typed)


class KeyChoiceTests(unittest.TestCase):
    def table(self, group: int, layouts: tuple[str, ...] = ("us", "ru")) -> object:
        return helper.read_keymap(FakeKeyboard(layouts, group), 0, None)

    def test_ascii_uses_latin_keys_even_when_russian_is_active(self) -> None:
        # A VM web console forwards physical keys: "." must be the US period key.
        for layouts, ru_group in ((("us", "ru"), 1), (("ru", "us"), 0)):
            with self.subTest(layouts=layouts):
                table = self.table(ru_group, layouts)
                latin = 1 - ru_group
                self.assertEqual(table.stroke_for(".").keycode, 60)
                self.assertEqual(table.stroke_for(".").group, latin)
                self.assertEqual(table.stroke_for(";"), helper.Stroke(47, latin, 0, frozenset({latin})))
                self.assertEqual(table.stroke_for("?").keycode, 61)
                self.assertEqual(table.stroke_for("/").keycode, 61)

    def test_cyrillic_uses_russian_group_and_shift(self) -> None:
        table = self.table(0)
        self.assertEqual(table.stroke_for("Д"), helper.Stroke(46, 1, helper.SHIFT_MASK, frozenset({1})))
        self.assertEqual(table.stroke_for("№"), helper.Stroke(12, 1, helper.SHIFT_MASK, frozenset({1})))

    def test_space_and_return_do_not_force_a_group_switch(self) -> None:
        table = self.table(1)
        self.assertEqual(table.stroke_for(" ").groups, frozenset({0, 1}))
        self.assertEqual(table.stroke_for("\n").keycode, RETURN)

    def test_plan_normalizes_line_breaks_and_spaces(self) -> None:
        table = self.table(0)
        strokes = list(helper.plan("a\r\nb\rc\u00a0d\u200be\x07✓", table))
        codes = [item.keycode if isinstance(item, helper.Stroke) else item for item in strokes]
        self.assertEqual(codes, [38, RETURN, 56, RETURN, 54, SPACE, 40, 26, 0x1002713])

    def test_cyrillic_keysym_table(self) -> None:
        self.assertEqual(helper.keysym_to_char(0x6C1), "а")
        self.assertEqual(helper.keysym_to_char(0x6E1), "А")
        self.assertEqual(helper.keysym_to_char(0x6A3), "ё")
        self.assertEqual(helper.keysym_to_char(0x6B3), "Ё")
        self.assertEqual(helper.keysym_to_char(0x6FF), "Ъ")
        self.assertEqual(helper.keysym_to_char(0x6B0), "№")


class TyperTests(unittest.TestCase):
    TEXT = ("Hello, world. sudo dnf install -y pkg; echo \"$HOME\" > /tmp/a.txt && ls ~/a\\b | grep '[x]'?\n"
            "Съешь же ещё этих мягких французских булок, да выпей чаю! №5\r\n\tEnd: {ok} <z> 100%_+=`@#^&*()\n")

    def test_types_long_mixed_text_exactly(self) -> None:
        text = self.TEXT * 300
        expected = text.replace("\r\n", "\n")
        for layouts in (("us", "ru"), ("ru", "us")):
            for group in (0, 1):
                with self.subTest(layouts=layouts, group=group):
                    keyboard = FakeKeyboard(layouts, group)
                    self.assertEqual(type_with(keyboard, text), expected)
                    self.assertEqual(keyboard.group, group)
                    self.assertEqual(keyboard.down, set())

    def test_caps_lock_is_disabled_while_typing_and_restored(self) -> None:
        keyboard = FakeKeyboard(caps=True)
        self.assertEqual(type_with(keyboard, "Abc Где"), "Abc Где")
        self.assertTrue(keyboard.locked & helper.LOCK_MASK)

    def test_missing_characters_use_a_spare_key_and_restore_it(self) -> None:
        keyboard = FakeKeyboard()
        self.assertEqual(type_with(keyboard, "a ✓ — b"), "a ✓ — b")
        self.assertEqual(keyboard.remapped, {})

    def test_held_modifiers_are_released_first(self) -> None:
        keyboard = FakeKeyboard()
        keyboard.down.add(SHIFT_L)
        self.assertEqual(type_with(keyboard, "ab"), "ab")

    def test_stop_releases_keys_and_restores_group(self) -> None:
        keyboard = FakeKeyboard(group=0)
        original_key = keyboard.key

        def key(keycode: int, press: bool) -> None:
            original_key(keycode, press)
            if len(keyboard.typed) == 3:
                helper.STOPPED.set()

        keyboard.key = key  # type: ignore[method-assign]
        helper.STOPPED.clear()
        helper.Typer(keyboard, 0).run("ДДДДДД")
        helper.STOPPED.clear()
        self.assertEqual(keyboard.typed, ["Д", "Д", "Д"])
        self.assertEqual(keyboard.down, set())
        self.assertEqual(keyboard.group, 0)


class HelperTests(unittest.TestCase):
    def test_rejects_missing_display_without_echoing_input(self) -> None:
        env = os.environ.copy()
        env.pop("DISPLAY", None)
        env["XDG_SESSION_TYPE"] = "x11"
        secret = b"SECRET-MUST-NOT-APPEAR"
        result = subprocess.run(
            [sys.executable, str(HELPER), "--start-delay-ms", "0"],
            input=secret,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 3)
        self.assertNotIn(secret, result.stdout + result.stderr)

    def test_cancel_during_start_delay(self) -> None:
        env = os.environ.copy()
        env.update({"DISPLAY": ":99", "XDG_SESSION_TYPE": "x11"})
        process = subprocess.Popen(
            [sys.executable, str(HELPER), "--start-delay-ms", "10000"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        assert process.stdin is not None
        process.stdin.write(b"not typed")
        process.stdin.close()
        process.stdin = None
        # Allow the interpreter to install its SIGTERM handler before signalling.
        time.sleep(1.0)
        process.send_signal(signal.SIGTERM)
        _stdout, _stderr = process.communicate(timeout=2)
        self.assertEqual(process.returncode, 130)

    def test_invalid_utf8_is_rejected(self) -> None:
        env = os.environ.copy()
        env.update({"DISPLAY": ":99", "XDG_SESSION_TYPE": "x11"})
        result = subprocess.run(
            [sys.executable, str(HELPER), "--start-delay-ms", "0"],
            input=b"\xff",
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
