from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class StaticSafetyTests(unittest.TestCase):
    def test_both_extensions_enforce_limit_and_stdin(self) -> None:
        for version in ("gnome44", "gnome46"):
            source = (ROOT / "src" / version / "extension.js").read_text(encoding="utf-8")
            self.assertIn("const MAX_HISTORY = 20", source)
            self.assertIn("Gio.SubprocessFlags.STDIN_PIPE", source)
            self.assertIn("send_signal(15)", source)
            self.assertNotIn("eval(", source)

    def test_helper_does_not_use_shell(self) -> None:
        source = (ROOT / "src" / "helper" / "clipboard-typer-helper").read_text(encoding="utf-8")
        self.assertNotIn("shell=True", source)
        self.assertNotIn("subprocess", source)
        self.assertIn("XTestFakeKeyEvent", source)

    def test_rpm_targets_linux_system_paths(self) -> None:
        spec = (ROOT / "packaging" / "clipboard-typer.spec").read_text(encoding="utf-8")
        builder = (ROOT / "build-rpm.sh").read_text(encoding="utf-8")
        self.assertIn('%{_datadir}/gnome-shell/extensions/clipboard-typer@local/', spec)
        self.assertIn('Requires:       libXtst', spec)
        self.assertNotIn('Requires:       xdotool', spec)
        self.assertIn('--target noarch-linux', builder)
        self.assertIn('--define "_prefix /usr"', builder)
        self.assertIn('gnome44 gnome46 gnome48', builder)


if __name__ == "__main__":
    unittest.main()
