from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class InstallTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("glib-compile-schemas"), "нужен glib-compile-schemas")
    def test_selects_matching_shell_build(self) -> None:
        for major, expected in (
            (44, "imports.misc.extensionUtils"),
            (46, "resource:///org/gnome/shell/"),
            (48, "resource:///org/gnome/shell/"),
        ):
            with self.subTest(major=major), tempfile.TemporaryDirectory() as directory:
                temp = Path(directory)
                fake_bin = temp / "bin"
                fake_bin.mkdir()
                self._command(fake_bin / "gnome-shell", f"printf 'GNOME Shell {major}.0\\n'\n")
                self._command(fake_bin / "gnome-extensions", "exit 0\n")
                env = os.environ.copy()
                env.update({
                    "PATH": f"{fake_bin}:{env['PATH']}",
                    "HOME": str(temp / "home"),
                    "XDG_DATA_HOME": str(temp / "data"),
                    "XDG_SESSION_TYPE": "x11",
                    "DISPLAY": ":99",
                })
                result = subprocess.run(
                    ["bash", str(ROOT / "install.sh")],
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                target = temp / "data" / "gnome-shell" / "extensions" / "clipboard-typer@local"
                self.assertIn(expected, (target / "extension.js").read_text(encoding="utf-8"))
                self.assertTrue((target / "schemas" / "gschemas.compiled").is_file())
                self.assertTrue(os.access(target / "helper" / "clipboard-typer-helper", os.X_OK))

    @staticmethod
    def _command(path: Path, body: str) -> None:
        path.write_text(f"#!/bin/sh\n{body}", encoding="utf-8")
        path.chmod(0o755)


if __name__ == "__main__":
    unittest.main()
