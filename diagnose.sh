#!/usr/bin/env bash
set -Eeuo pipefail

readonly UUID="clipboard-typer@local"

check_command() {
    local command_name="$1"
    if command -v "$command_name" >/dev/null 2>&1; then
        printf 'OK   %-24s %s\n' "$command_name" "$(command -v "$command_name")"
    else
        printf 'FAIL %-24s не найдено\n' "$command_name"
    fi
}

printf 'Система: %s\n' "$(sed -n 's/^PRETTY_NAME=//p' /etc/os-release 2>/dev/null | tr -d '"' || true)"
printf 'GNOME:   %s\n' "$(gnome-shell --version 2>/dev/null || printf 'не найден')"
printf 'Сеанс:   %s\n' "${XDG_SESSION_TYPE:-не определён}"
printf 'DISPLAY: %s\n' "${DISPLAY:+задан}"
printf 'Язык:    %s\n' "${LANG:-не задан}"
printf '\nЗависимости (содержимое буфера не читается):\n'
for command_name in gnome-shell gnome-extensions glib-compile-schemas python3; do
    check_command "$command_name"
done
for library in libX11.so.6 libXtst.so.6 libxkbcommon.so.0; do
    if python3 -c "import ctypes, sys; ctypes.CDLL(sys.argv[1])" "$library" >/dev/null 2>&1; then
        printf 'OK   %-24s\n' "$library"
    elif [[ "$library" == libxkbcommon.so.0 ]]; then
        printf 'WARN %-24s не найдена: символы вне латиницы и кириллицы могут не печататься\n' "$library"
    else
        printf 'FAIL %-24s не найдена\n' "$library"
    fi
done

printf '\nРасширение:\n'
gnome-extensions info "$UUID" 2>&1 || printf '%s\n' "Не установлено или GNOME Shell ещё не перечитал расширения."

if [[ "${XDG_SESSION_TYPE:-}" != "x11" ]]; then
    printf '\nВНИМАНИЕ: для набора необходимо выбрать «GNOME on Xorg» на экране входа.\n'
elif python3 - <<'PY' >/dev/null 2>&1
import ctypes
x11 = ctypes.CDLL("libX11.so.6")
xtst = ctypes.CDLL("libXtst.so.6")
x11.XOpenDisplay.restype = ctypes.c_void_p
display = ctypes.c_void_p(x11.XOpenDisplay(None))
values = [ctypes.c_int() for _ in range(4)]
raise SystemExit(0 if display and xtst.XTestQueryExtension(display, *map(ctypes.byref, values)) else 1)
PY
then
    printf '\nOK: X-сервер доступен, расширение XTEST включено.\n'
else
    printf '\nFAIL: нет доступа к X-серверу или XTEST; проверьте DISPLAY и X11-сеанс.\n'
fi

printf '\nОшибки расширения можно посмотреть без вывода содержимого истории:\n'
printf '%s\n' "journalctl --user -b --no-pager | grep -F '${UUID}'"

