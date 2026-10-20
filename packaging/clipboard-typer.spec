%{!?flavor:%global flavor gnome46}

Name:           gnome-shell-extension-clipboard-typer-%{flavor}
Version:        1.0.3
Release:        1%{?dist}
Summary:        GNOME clipboard history with X11 keyboard typing

License:        MIT
URL:            https://local.invalid/clipboard-typer
Source0:        clipboard-typer-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  glib2
Requires:       gnome-shell
Requires:       python3
Requires:       libX11
Requires:       libXtst
Recommends:     libxkbcommon
Provides:       gnome-shell-extension(clipboard-typer@local) = %{version}-%{release}

%if "%{flavor}" == "gnome44"
%global source_branch gnome44
Conflicts:      gnome-shell-extension-clipboard-typer-gnome46
Conflicts:      gnome-shell-extension-clipboard-typer-gnome48
%else
%global source_branch gnome46
Conflicts:      gnome-shell-extension-clipboard-typer-gnome44
%if "%{flavor}" == "gnome46"
Conflicts:      gnome-shell-extension-clipboard-typer-gnome48
%else
Conflicts:      gnome-shell-extension-clipboard-typer-gnome46
%endif
%endif

%description
A GNOME Shell panel extension that stores the last 20 unique CLIPBOARD texts
and types a selected item into the active X11 window through XTEST. Clipboard
contents are passed to the helper through standard input, never a shell command.

This package variant contains the %{flavor} extension implementation. Keyboard
typing is supported only in an X11/Xorg session.

%prep
%setup -q -n clipboard-typer-%{version}

%build
# JavaScript and Python sources do not require compilation.

%install
extension_dir="%{buildroot}%{_datadir}/gnome-shell/extensions/clipboard-typer@local"
mkdir -p "$extension_dir/helper" "$extension_dir/schemas" "%{buildroot}%{_bindir}"

install -m 0644 "src/%{source_branch}/metadata.json" "$extension_dir/metadata.json"
install -m 0644 "src/%{source_branch}/extension.js" "$extension_dir/extension.js"
install -m 0644 "src/%{source_branch}/stylesheet.css" "$extension_dir/stylesheet.css"
install -m 0755 "src/helper/clipboard-typer-helper" "$extension_dir/helper/clipboard-typer-helper"
install -m 0644 "src/schemas/org.gnome.shell.extensions.clipboard-typer.gschema.xml" \
    "$extension_dir/schemas/org.gnome.shell.extensions.clipboard-typer.gschema.xml"
glib-compile-schemas --strict "$extension_dir/schemas"
install -m 0755 diagnose.sh "%{buildroot}%{_bindir}/clipboard-typer-diagnose"
install -m 0755 packaging/clipboard-typer-enable "%{buildroot}%{_bindir}/clipboard-typer-enable"

%files
%license LICENSE
%doc README.md ARCHITECTURE.md
%{_datadir}/gnome-shell/extensions/clipboard-typer@local/
%{_bindir}/clipboard-typer-diagnose
%{_bindir}/clipboard-typer-enable

%post
printf '%s\n' 'Clipboard Typer установлен. Войдите в GNOME заново и выполните от обычного пользователя: clipboard-typer-enable'

%changelog
* Tue Oct 20 2026 Clipboard Typer Maintainers <noreply@local> - 1.0.3-1
- Replace xdotool type with a layout-aware XTEST typer: Latin keys for ASCII,
  correct line breaks, Caps Lock and layout group restored after typing

* Mon Oct 19 2026 Clipboard Typer Maintainers <noreply@local> - 1.0.2-1
- Register indicator and dialogs, repair history menu ownership and multiline focus

* Mon Oct 19 2026 Clipboard Typer Maintainers <noreply@local> - 1.0.1-1
- Add a dedicated GNOME Shell 48 package variant

* Mon Oct 19 2026 Clipboard Typer Maintainers <noreply@local> - 1.0.0-1
- Initial RPM release for GNOME Shell 44 and 45/46
