#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly VERSION="1.0.3"
readonly SOURCE_NAME="clipboard-typer-${VERSION}"
readonly DIST_DIR="${SCRIPT_DIR}/dist"

log() { printf '%s\n' "$*" >&2; }
die() { log "ОШИБКА: $*"; exit 1; }

command -v rpmbuild >/dev/null 2>&1 || die "Не найден rpmbuild. На РЕД ОС установите пакет rpm-build."
command -v tar >/dev/null 2>&1 || die "Не найден tar."

work_dir="$(mktemp -d "${TMPDIR:-/tmp}/clipboard-typer-rpm.XXXXXX")"
cleanup() { rm -rf -- "$work_dir"; }
trap cleanup EXIT

top_dir="${work_dir}/rpmbuild"
source_dir="${work_dir}/${SOURCE_NAME}"
mkdir -p "$top_dir/BUILD" "$top_dir/BUILDROOT" "$top_dir/RPMS" "$top_dir/SOURCES" "$top_dir/SPECS" "$top_dir/SRPMS"
mkdir -p "$source_dir"

for path in ARCHITECTURE.md LICENSE README.md diagnose.sh packaging src; do
    cp -a "${SCRIPT_DIR}/${path}" "$source_dir/"
done

COPYFILE_DISABLE=1 tar -C "$work_dir" -czf "$top_dir/SOURCES/${SOURCE_NAME}.tar.gz" "$SOURCE_NAME"
install -m 0644 "${SCRIPT_DIR}/packaging/clipboard-typer.spec" "$top_dir/SPECS/clipboard-typer.spec"

declare -a rpmbuild_options=(
    -bb
    --target noarch-linux
    --define "_topdir ${top_dir}"
    --define "_prefix /usr"
    --define "_bindir /usr/bin"
    --define "_datadir /usr/share"
    --define "_docdir /usr/share/doc"
    --define "_licensedir /usr/share/licenses"
)
if [[ "$(uname -s)" == "Darwin" || "${RPMBUILD_NODEPS:-0}" == "1" ]]; then
    rpmbuild_options+=(--nodeps)
fi

for flavor in gnome44 gnome46 gnome48; do
    log "Сборка RPM: ${flavor}"
    rpmbuild "${rpmbuild_options[@]}" --define "flavor ${flavor}" "$top_dir/SPECS/clipboard-typer.spec"
done

mkdir -p "$DIST_DIR"
while IFS= read -r -d '' rpm_file; do
    install -m 0644 "$rpm_file" "$DIST_DIR/$(basename -- "$rpm_file")"
done < <(find "$top_dir/RPMS" -type f -name '*.rpm' -print0)

rpm_count="$(find "$DIST_DIR" -maxdepth 1 -type f -name "*-${VERSION}-*.rpm" | wc -l | tr -d ' ')"
[[ "$rpm_count" -ge 3 ]] || die "Ожидалось три RPM, найдено: ${rpm_count}"
if command -v sha256sum >/dev/null 2>&1; then
    (cd "$DIST_DIR" && sha256sum ./*-"${VERSION}"-*.rpm) > "$DIST_DIR/SHA256SUMS"
elif command -v shasum >/dev/null 2>&1; then
    (cd "$DIST_DIR" && shasum -a 256 ./*-"${VERSION}"-*.rpm) > "$DIST_DIR/SHA256SUMS"
else
    die "Не найдена утилита sha256sum или shasum для контрольных сумм."
fi
log "Готово. Пакеты находятся в ${DIST_DIR}"
