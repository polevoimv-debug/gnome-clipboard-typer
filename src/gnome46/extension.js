import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as ModalDialog from 'resource:///org/gnome/shell/ui/modalDialog.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const MAX_HISTORY = 20;
const POLL_MS = 600;

function preview(text) {
    const oneLine = text.replace(/\r\n|\r|\n/g, ' ↵ ').replace(/\s+/g, ' ').trim();
    const chars = Array.from(oneLine);
    return chars.length > 72 ? `${chars.slice(0, 72).join('')}…` : oneLine;
}

const TextDialog = GObject.registerClass(
class TextDialog extends ModalDialog.ModalDialog {
    constructor(text, onCopy) {
        super({destroyOnClose: true});
        this.contentLayout.add_child(new St.Label({
            text: 'Полный текст',
            style_class: 'clipboard-typer-dialog-title',
        }));
        const scroll = new St.ScrollView({
            overlay_scrollbars: true,
            style_class: 'clipboard-typer-text-scroll',
        });
        const label = new St.Label({text, x_align: Clutter.ActorAlign.START});
        label.clutter_text.line_wrap = true;
        label.clutter_text.selectable = true;
        scroll.set_child(label);
        this.contentLayout.add_child(scroll);
        this.setButtons([
            {label: 'Закрыть', key: Clutter.KEY_Escape, action: () => this.close()},
            {label: 'Скопировать', default: true, action: () => { onCopy(); this.close(); }},
        ]);
    }
});

const NewlineDialog = GObject.registerClass(
class NewlineDialog extends ModalDialog.ModalDialog {
    constructor(onPreserve, onReplace) {
        super({destroyOnClose: true});
        const label = new St.Label({
            text: 'В тексте есть переносы строк. В терминале Enter может выполнить команду.\nКак напечатать текст?',
        });
        label.clutter_text.line_wrap = true;
        this.contentLayout.add_child(label);
        this.setButtons([
            {label: 'Отмена', key: Clutter.KEY_Escape, action: () => this.close()},
            {label: 'Заменить пробелами', action: () => { this.connect('closed', () => onReplace()); this.close(); }},
            {label: 'Сохранить переносы', default: true, action: () => { this.connect('closed', () => onPreserve()); this.close(); }},
        ]);
    }
});

const Indicator = GObject.registerClass(
class Indicator extends PanelMenu.Button {
    constructor(extension) {
        super(0.0, 'История буфера и ввод');
        this._extension = extension;
        this._icon = new St.Icon({icon_name: 'edit-paste-symbolic', style_class: 'system-status-icon'});
        this.add_child(this._icon);
        this.menu.connect('open-state-changed', (_menu, open) => {
            if (open)
                extension.rememberFocus();
        });
        this.rebuild();
    }

    setTyping(active) {
        this._icon.icon_name = active ? 'input-keyboard-symbolic' : 'edit-paste-symbolic';
        if (active)
            this._icon.add_style_pseudo_class('active');
        else
            this._icon.remove_style_pseudo_class('active');
    }

    rebuild() {
        this.menu.removeAll();
        const ext = this._extension;
        if (!ext.isX11()) {
            const warning = new PopupMenu.PopupMenuItem('Набор недоступен: нужен сеанс GNOME on Xorg', {reactive: false});
            warning.add_style_class_name('clipboard-typer-warning');
            this.menu.addMenuItem(warning);
            this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        }

        if (ext.history.length === 0) {
            this.menu.addMenuItem(new PopupMenu.PopupMenuItem(
                ext.settings.get_boolean('history-paused') ? 'Сохранение истории приостановлено' : 'История пока пуста',
                {reactive: false}
            ));
        } else {
            const historySection = new PopupMenu.PopupMenuSection();
            this.menu.addMenuItem(historySection);
            for (const text of ext.history) {
                const row = new PopupMenu.PopupSubMenuMenuItem(preview(text) || '(пустой текст)');
                const full = new PopupMenu.PopupMenuItem('Просмотреть полностью');
                full.connect('activate', () => ext.showText(text));
                row.menu.addMenuItem(full);
                const copy = new PopupMenu.PopupMenuItem('Скопировать');
                copy.connect('activate', () => ext.copy(text));
                row.menu.addMenuItem(copy);
                const type = new PopupMenu.PopupMenuItem('Напечатать');
                type.connect('activate', () => ext.requestTyping(text));
                row.menu.addMenuItem(type);
                historySection.addMenuItem(row);
            }
        }

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        const pause = new PopupMenu.PopupSwitchMenuItem('Пауза сохранения истории', ext.settings.get_boolean('history-paused'));
        pause.connect('toggled', (_item, state) => ext.setPaused(state));
        this.menu.addMenuItem(pause);

        const settingsMenu = new PopupMenu.PopupSubMenuMenuItem('Настройки');
        this._addNumberSetting(settingsMenu.menu, 'Задержка перед вводом', 'start-delay-ms', 250, 0, 15000, ' мс');
        this._addNumberSetting(settingsMenu.menu, 'Интервал символов', 'key-delay-ms', 10, 0, 1000, ' мс');
        const persist = new PopupMenu.PopupSwitchMenuItem('Хранить историю на диске', ext.settings.get_boolean('persist-history'));
        persist.connect('toggled', (_item, state) => ext.setPersistence(state));
        settingsMenu.menu.addMenuItem(persist);
        settingsMenu.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        settingsMenu.menu.addMenuItem(new PopupMenu.PopupMenuItem('Открыть: Super+V', {reactive: false}));
        settingsMenu.menu.addMenuItem(new PopupMenu.PopupMenuItem('Стоп: Super+Shift+Esc', {reactive: false}));
        this.menu.addMenuItem(settingsMenu);

        const clear = new PopupMenu.PopupMenuItem('Очистить историю');
        clear.connect('activate', () => ext.clearHistory());
        this.menu.addMenuItem(clear);
        if (ext.isTyping) {
            const stop = new PopupMenu.PopupMenuItem('Остановить набор');
            stop.connect('activate', () => ext.stopTyping(true));
            this.menu.addMenuItem(stop);
        }
    }

    _addNumberSetting(menu, title, key, step, min, max, suffix) {
        const item = new PopupMenu.PopupSubMenuMenuItem(`${title}: ${this._extension.settings.get_int(key)}${suffix}`);
        const minus = new PopupMenu.PopupMenuItem(`Уменьшить на ${step}${suffix}`);
        minus.connect('activate', () => {
            const value = Math.max(min, this._extension.settings.get_int(key) - step);
            this._extension.settings.set_int(key, value);
            this.rebuild();
        });
        item.menu.addMenuItem(minus);
        const plus = new PopupMenu.PopupMenuItem(`Увеличить на ${step}${suffix}`);
        plus.connect('activate', () => {
            const value = Math.min(max, this._extension.settings.get_int(key) + step);
            this._extension.settings.set_int(key, value);
            this.rebuild();
        });
        item.menu.addMenuItem(plus);
        menu.addMenuItem(item);
    }
});

export default class ClipboardTyperExtension extends Extension {
    enable() {
        this.settings = this.getSettings();
        this.history = this._loadHistory();
        this.isTyping = false;
        this._typingProcess = null;
        this._stopRequested = false;
        this._selfClipboardText = null;
        this._returnWindow = null;
        this._clipboard = St.Clipboard.get_default();
        this._indicator = new Indicator(this);
        Main.panel.addToStatusArea(this.uuid, this._indicator);
        this._bindKeys();
        this._pollSource = GLib.timeout_add(GLib.PRIORITY_DEFAULT, POLL_MS, () => {
            this._pollClipboard();
            return GLib.SOURCE_CONTINUE;
        });
        this._pollClipboard();
    }

    disable() {
        this.stopTyping(false);
        if (this._pollSource) {
            GLib.source_remove(this._pollSource);
            this._pollSource = 0;
        }
        Main.wm.removeKeybinding('open-history');
        Main.wm.removeKeybinding('stop-typing');
        this._indicator?.destroy();
        this._indicator = null;
        this.settings = null;
        this.history = [];
        this._clipboard = null;
    }

    isX11() {
        return (GLib.getenv('XDG_SESSION_TYPE') || '').toLowerCase() === 'x11' && !!GLib.getenv('DISPLAY');
    }

    rememberFocus() {
        const focused = global.display.focus_window;
        if (focused)
            this._returnWindow = focused;
    }

    _bindKeys() {
        Main.wm.addKeybinding('open-history', this.settings, Meta.KeyBindingFlags.NONE,
            Shell.ActionMode.NORMAL | Shell.ActionMode.OVERVIEW,
            () => this._indicator.menu.toggle());
        Main.wm.addKeybinding('stop-typing', this.settings, Meta.KeyBindingFlags.NONE,
            Shell.ActionMode.ALL, () => this.stopTyping(true));
    }

    _loadHistory() {
        if (!this.settings.get_boolean('persist-history'))
            return [];
        try {
            const value = JSON.parse(this.settings.get_string('history-json'));
            if (!Array.isArray(value))
                return [];
            return value.filter(item => typeof item === 'string' && item.length > 0).filter((item, i, all) => all.indexOf(item) === i).slice(0, MAX_HISTORY);
        } catch (_error) {
            return [];
        }
    }

    _saveHistory() {
        if (this.settings.get_boolean('persist-history'))
            this.settings.set_string('history-json', JSON.stringify(this.history.slice(0, MAX_HISTORY)));
    }

    _pollClipboard() {
        if (!this._clipboard || this.settings.get_boolean('history-paused'))
            return;
        this._clipboard.get_text(St.ClipboardType.CLIPBOARD, (_clipboard, text) => {
            if (!this._indicator || typeof text !== 'string' || text.length === 0)
                return;
            if (this._ignoreClipboardOnResume) {
                this._ignoreClipboardOnResume = false;
                return;
            }
            if (this._selfClipboardText === text) {
                this._selfClipboardText = null;
                return;
            }
            this._selfClipboardText = null;
            const index = this.history.indexOf(text);
            if (index === 0)
                return;
            if (index > 0)
                this.history.splice(index, 1);
            this.history.unshift(text);
            this.history.length = Math.min(this.history.length, MAX_HISTORY);
            this._saveHistory();
            this._indicator.rebuild();
        });
    }

    copy(text) {
        this._selfClipboardText = text;
        this._clipboard.set_text(St.ClipboardType.CLIPBOARD, text);
    }

    showText(text) {
        new TextDialog(text, () => this.copy(text)).open();
    }

    clearHistory() {
        this.history = [];
        this.settings.set_string('history-json', '[]');
        this._indicator.rebuild();
    }

    setPersistence(state) {
        this.settings.set_boolean('persist-history', state);
        if (state)
            this._saveHistory();
        else
            this.settings.set_string('history-json', '[]');
    }

    setPaused(state) {
        this.settings.set_boolean('history-paused', state);
        this._ignoreClipboardOnResume = state;
        if (!state)
            this._pollClipboard();
    }

    requestTyping(text) {
        this._indicator.menu.close();
        if (/\r|\n/.test(text)) {
            new NewlineDialog(
                () => this._startTyping(text),
                () => this._startTyping(text.replace(/\r\n|\r|\n/g, ' '))
            ).open();
        } else {
            this._startTyping(text);
        }
    }

    _startTyping(text) {
        if (this.isTyping) {
            Main.notify('История буфера', 'Набор уже выполняется. Для остановки: Super+Shift+Esc.');
            return;
        }
        if (!this.isX11()) {
            Main.notifyError('Набор недоступен', 'Текущий сеанс не X11. Войдите в GNOME on Xorg; ввод через XTEST не работает в Wayland.');
            return;
        }
        this._indicator.menu.close();
        this._returnWindow?.activate(global.get_current_time());
        const helper = GLib.build_filenamev([this.path, 'helper', 'clipboard-typer-helper']);
        const argv = [helper,
            '--start-delay-ms', String(this.settings.get_int('start-delay-ms')),
            '--key-delay-ms', String(this.settings.get_int('key-delay-ms'))];
        try {
            this._typingProcess = Gio.Subprocess.new(argv,
                Gio.SubprocessFlags.STDIN_PIPE | Gio.SubprocessFlags.STDERR_PIPE);
        } catch (error) {
            Main.notifyError('Не удалось начать набор', error.message);
            return;
        }
        this.isTyping = true;
        this._stopRequested = false;
        this._indicator.setTyping(true);
        this._indicator.rebuild();
        this._typingProcess.communicate_utf8_async(text, null, (process, result) => {
            let stderr = '';
            let ok = false;
            try {
                const [, , errorText] = process.communicate_utf8_finish(result);
                stderr = errorText || '';
                ok = process.get_successful();
            } catch (error) {
                stderr = error.message;
            }
            if (process !== this._typingProcess)
                return;
            this._typingProcess = null;
            this.isTyping = false;
            if (this._indicator) {
                this._indicator.setTyping(false);
                this._indicator.rebuild();
            }
            const wasStopped = this._stopRequested;
            this._stopRequested = false;
            if (!ok && !wasStopped)
                Main.notifyError('Ошибка набора', stderr.trim().slice(0, 300) || 'Помощник завершился с ошибкой.');
        });
    }

    stopTyping(notify) {
        if (!this._typingProcess)
            return;
        this._stopRequested = true;
        this._typingProcess.send_signal(15);
        if (notify)
            Main.notify('История буфера', 'Остановка набора запрошена.');
    }
}
