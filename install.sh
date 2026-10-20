#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly UUID="clipboard-typer@local"
readonly EXTENSIONS_ROOT="${XDG_DATA_HOME:-${HOME}/.local/share}/gnome-shell/extensions"
readonly TARGET_DIR="${EXTENSIONS_ROOT}/${UUID}"

log() { printf '%s\n' "$*" >&2; }
die() { log "ОШИБКА: $*"; exit 1; }

if [[ ${EUID} -eq 0 ]]; then
    die "Не запускайте установщик от root. Расширение устанавливается текущему пользователю."
fi

for command_name in gnome-shell gnome-extensions glib-compile-schemas python3; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        log "Не найдена команда: ${command_name}"
        log "Для РЕД ОС обычно подходят пакеты: gnome-shell, glib2, python3, libX11, libXtst."
        log "Установите отсутствующее системным менеджером пакетов и повторите запуск."
        exit 2
    fi
done
if ! python3 -c 'import ctypes; ctypes.CDLL("libX11.so.6"); ctypes.CDLL("libXtst.so.6")' >/dev/null 2>&1; then
    log "ВНИМАНИЕ: не найдены libX11 или libXtst, без них набор не заработает."
    log "Для РЕД ОС: sudo -E dnf install libX11 libXtst"
fi

shell_version="$(gnome-shell --version 2>/dev/null || true)"
if [[ "$shell_version" =~ ([0-9]+)(\.[0-9]+)? ]]; then
    shell_major="${BASH_REMATCH[1]}"
else
    die "Не удалось определить версию GNOME Shell: ${shell_version:-нет вывода}"
fi

case "$shell_major" in
    44) source_dir="${SCRIPT_DIR}/src/gnome44" ;;
    45|46|47|48) source_dir="${SCRIPT_DIR}/src/gnome46" ;;
    *) die "Поддерживаются GNOME Shell 44–48; обнаружена версия ${shell_major}. Совместимость не подтверждена." ;;
esac

stage_dir="$(mktemp -d)"
cleanup() { rm -rf -- "$stage_dir"; }
trap cleanup EXIT

mkdir -p -- "${stage_dir}/helper" "${stage_dir}/schemas"
install -m 0644 "${source_dir}/metadata.json" "${stage_dir}/metadata.json"
install -m 0644 "${source_dir}/extension.js" "${stage_dir}/extension.js"
install -m 0644 "${source_dir}/stylesheet.css" "${stage_dir}/stylesheet.css"
install -m 0755 "${SCRIPT_DIR}/src/helper/clipboard-typer-helper" "${stage_dir}/helper/clipboard-typer-helper"
install -m 0644 "${SCRIPT_DIR}/src/schemas/org.gnome.shell.extensions.clipboard-typer.gschema.xml" \
    "${stage_dir}/schemas/org.gnome.shell.extensions.clipboard-typer.gschema.xml"
glib-compile-schemas --strict "${stage_dir}/schemas"

if [[ -L "$TARGET_DIR" ]]; then
    die "Каталог назначения является символической ссылкой: ${TARGET_DIR}"
fi
if [[ -e "$TARGET_DIR" && ! -d "$TARGET_DIR" ]]; then
    die "Путь назначения существует и не является каталогом: ${TARGET_DIR}"
fi
mkdir -p -- "$EXTENSIONS_ROOT" "$TARGET_DIR"
find "$TARGET_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
cp -a "${stage_dir}/." "$TARGET_DIR/"

log "Установлена сборка для GNOME Shell ${shell_major}: ${TARGET_DIR}"
if gnome-extensions enable "$UUID" 2>/dev/null; then
    log "Расширение включено и будет запускаться после входа в GNOME."
else
    log "GNOME Shell ещё не увидел расширение. Выйдите из сеанса и войдите снова, затем выполните:"
    log "  gnome-extensions enable ${UUID}"
fi

session_type="${XDG_SESSION_TYPE:-не определён}"
if [[ "$session_type" != "x11" ]]; then
    log "ВНИМАНИЕ: текущий сеанс '${session_type}'. Набор поддерживается только в GNOME on Xorg (X11)."
fi
