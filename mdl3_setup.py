"""MDL3Setup (dev.47): one program for installing MDL3's native component, fixing the EAC certificate, repairing the
EAC service, writing a report and removing everything. Built into MDL3Setup.exe with tools/installer/build_installer.py.

Run without arguments for the window. Command line (no window; results in %ProgramData%\\MDL3\\Logs\\MDL3Setup.log):
    MDL3Setup.exe --install [--game "D:\\...\\Helldivers 2"]      install / update
    MDL3Setup.exe --remove [--settings] [--cert]                  full removal (+ mod settings/logs, + certificate)
    MDL3Setup.exe --report                                         report on the Desktop
Internal (started elevated by the program itself): --cert-install, --cert-remove
"""
import json
import os
import sys
import threading
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mdl3setup_core as core   # noqa: E402

APP_VERSION = '1.0.0'
CERT_FILE = 'Certum_Code_Signing_2021_CA.cer'

T = {
    'title': ('MDL3 安装与修复工具', 'MDL3 Setup'),
    'game': ('游戏目录', 'Game folder'),
    'browse': ('选择…', 'Browse…'),
    'state': ('状态', 'Status'),
    'install': ('安装 / 更新', 'Install / Update'),
    'cert': ('修复 EAC 证书（需管理员）', 'Fix EAC certificate (admin)'),
    'eac': ('修复 EAC 服务（需管理员）', 'Repair EAC service (admin)'),
    'report': ('生成诊断报告', 'Write report'),
    'logs': ('打开日志文件夹', 'Open log folder'),
    'remove': ('彻底清除…', 'Remove everything…'),
    'not_found': ('没有找到 Helldivers 2，请点击“选择…”指定游戏目录（包含 bin 和 data 的文件夹）。',
                  'Helldivers 2 was not found. Click Browse… and pick the game folder (the one with bin and data).'),
    'many': ('找到多个游戏目录，请确认下面选中的是你正在用的那个。', 'More than one game folder was found; check the one selected below.'),
    'game_running': ('请先完全退出 Helldivers 2 再操作。', 'Please close Helldivers 2 first.'),
    'elevated': ('请直接双击运行本程序，不要“以管理员身份运行”：管理员创建的文件夹游戏写不进去。证书和 EAC 修复会自己请求管理员权限。',
                 'Please start this program normally, not "as administrator": folders made by an administrator are not writable '
                 'by the game. The certificate and EAC repairs ask for administrator rights themselves.'),
    'not_writable': ('文件夹 %s 不可写（可能是以前用管理员身份创建的）。请手动删除 C:\\ProgramData\\MDL3 后再安装。',
                     'The folder %s is not writable (perhaps made by an administrator before). Delete C:\\ProgramData\\MDL3 by hand and install again.'),
    'installed': ('安装完成：%s\n下一步：在 Arsenal 中替换/更新 MDL3 包并点击部署，然后启动游戏。',
                  'Installed to %s\nNext: replace / update the MDL3 package in Arsenal, Deploy, then start the game.'),
    'migrated': ('已从用户目录迁移：%s', 'Moved from the user folder: %s'),
    'cert_ok': ('证书已在系统中（本机“中间证书颁发机构”）。如果游戏仍提示不受信任，请重启电脑后再试。',
                'The certificate is installed (machine "Intermediate Certification Authorities"). Restart the PC if the game still says untrusted.'),
    'cert_fail': ('证书没有装上：%s', 'The certificate was not installed: %s'),
    'declined': ('已取消管理员授权。', 'The administrator prompt was declined.'),
    'eac_started': ('已打开 Easy Anti-Cheat 窗口：选择 HELLDIVERS 2，点左下角“修复服务”（Repair Service），完成后关闭窗口再启动游戏。',
                    'Easy Anti-Cheat opened: pick HELLDIVERS 2, click Repair Service at the bottom left, close it, then start the game.'),
    'eac_missing': ('没找到 EasyAntiCheat_EOS_Setup.exe。Steam 中右键 HELLDIVERS 2 → 管理 → 浏览本地文件 → EasyAntiCheat 文件夹 → 双击它。',
                    'EasyAntiCheat_EOS_Setup.exe was not found. Steam: right-click HELLDIVERS 2 → Manage → Browse local files → EasyAntiCheat → run it.'),
    'report_done': ('报告已保存到桌面：%s', 'Report saved on the Desktop: %s'),
    'remove_q': ('将删除 MDL3 组件和它的配置、日志（C:\\ProgramData\\MDL3 以及用户目录下的 MDL3 文件夹）。', 'This deletes MDL3\'s component, settings and logs (C:\\ProgramData\\MDL3 and the MDL3 folder in your user folder).'),
    'remove_settings': ('同时删除 MDL 模组设置、日志和散装模组（MDL\\Helldivers2、CowboyBingus、HD2Runtime\\mod_data）',
                        'Also delete MDL mod settings, logs and loose mods (MDL\\Helldivers2, CowboyBingus, HD2Runtime\\mod_data)'),
    'remove_cert': ('同时移除之前添加的证书（需管理员）', 'Also remove the certificate added before (admin)'),
    'remove_go': ('删除', 'Delete'),
    'cancel': ('取消', 'Cancel'),
    'removed': ('已清除。别忘了在 Arsenal 里移除 MDL3 包并重新部署。', 'Removed. Remember to remove the MDL3 package in Arsenal and Deploy again.'),
    'remove_failed': ('以下内容没能删除（可能正被占用）：\n%s', 'These could not be deleted (in use?):\n%s'),
    'error': ('出错了：%s', 'Error: %s'),
    'st_none': ('未安装', 'not installed'),
    'st_ok': ('已安装，与本工具版本一致', 'installed, matches this setup'),
    'st_old': ('已安装，但不是本工具的版本（点“安装 / 更新”）', 'installed, but a different version (click Install / Update)'),
    'st_legacy': ('；发现旧版（用户目录）安装，安装时会自动迁移', '; an older install in the user folder will be moved on install'),
    'st_cert_yes': ('证书：已安装', 'certificate: installed'),
    'st_cert_no': ('证书：未安装（若游戏提示 EAC 不受信任，点“修复 EAC 证书”）', 'certificate: not installed (click Fix EAC certificate if EAC says untrusted)'),
    'st_sig': ('签名检查：%s', 'signature check: %s'),
    'busy': ('正在处理…', 'Working…'),
}
LANG = 'both'   # both (default): Chinese then English; --zh / --en: one language


def tr(key, *args, sep='\n'):
    zh, en = T[key]
    if args: zh, en = zh % args, en % args
    if LANG == 'zh': return zh
    if LANG == 'en': return en
    return zh + sep + en


# ---------------------------------------------------------------------------------------------------- payload
def payload_dir(argv):
    if '--payload' in argv: return argv[argv.index('--payload') + 1]
    if getattr(sys, '_MEIPASS', None): return os.path.join(sys._MEIPASS, 'payload')
    return os.path.join(HERE, 'payload')


def load_payload(folder):
    with open(os.path.join(folder, 'BUILD.json'), 'r', encoding='utf-8-sig') as f: meta = json.load(f)
    return {'dll': os.path.join(folder, core.DLL_NAME), 'meta': meta, 'cert': os.path.join(folder, CERT_FILE), 'dir': folder}


# ---------------------------------------------------------------------------------------------------- logging
class Log:
    def __init__(self):
        self.lines, self.path, self.sink = [], None, None

    def open(self, folder):
        try:
            os.makedirs(folder, exist_ok=True); self.path = os.path.join(folder, 'MDL3Setup.log')
            with open(self.path, 'a', encoding='utf-8') as f: f.write(''.join(self.lines))
        except OSError:
            self.path = None

    def __call__(self, text):
        line = time.strftime('%Y-%m-%d %H:%M:%S ') + str(text) + '\n'
        self.lines.append(line)
        if self.path:
            try:
                with open(self.path, 'a', encoding='utf-8') as f: f.write(line)
            except OSError:
                pass
        if self.sink: self.sink(str(text))


# ---------------------------------------------------------------------------------------------------- actions
class App:
    def __init__(self, argv):
        global LANG
        import mdl3setup_win as win
        self.win = win
        LANG = 'zh' if '--zh' in argv else 'en' if '--en' in argv else 'both'
        self.log = Log()
        self.payload = load_payload(payload_dir(argv))
        self.host = win.Host(self.log)
        self.setup = core.Setup(self.host, self.payload)
        self.log.open(os.path.join(self.setup.data, 'Logs') if os.path.isdir(self.setup.data) else os.environ.get('TEMP', HERE))
        self.log('MDL3Setup %s package %s (ACP %s, elevation %s)' % (APP_VERSION, self.payload['meta'].get('version'),
                 win.ansi_code_page(), win.elevation_type()))

    def child_args(self, action):
        # a frozen exe unpacks its own copy of the payload; the script passes its folder on
        return [action] if getattr(sys, 'frozen', False) else [action, '--payload', self.payload['dir']]

    def games(self):
        return core.find_game(self.win.steam_roots(), self.win.uninstall_locations())

    def explain(self, e):
        text = str(e)
        if text == 'game_running': return tr('game_running')
        if text.startswith('not_writable:'): return tr('not_writable', text.split(':', 1)[1])
        return tr('error', text)

    def install(self, game):
        if self.win.elevation_type() == 2: return False, tr('elevated')
        try:
            r = self.setup.install(game)
        except Exception as e:
            self.log('INSTALL failed: ' + traceback.format_exc()); return False, self.explain(e)
        self.log.open(os.path.join(self.setup.data, 'Logs'))
        self.log('INSTALL ok %s' % json.dumps(r, ensure_ascii=False))
        msg = tr('installed', r['data'])
        if r['migrated']: msg += '\n' + tr('migrated', ', '.join(r['migrated']))
        if r['unwritable']: msg += '\n' + tr('not_writable', ', '.join(r['unwritable']))
        return not r['unwritable'], msg

    def cert_fix(self):
        if self.win.cert_present(core.CERT_THUMB): return True, tr('cert_ok')
        started, code = self.win.run_elevated(self.child_args('--cert-install'))
        self.log('CERT elevated started=%s code=%s' % (started, code))
        if not started: return False, tr('declined')
        if self.win.cert_present(core.CERT_THUMB): return True, tr('cert_ok')
        return False, tr('cert_fail', 'exit %s' % code)

    def eac_repair(self, game):
        exe = core.eac_setup(game) if game and core.is_game(game) else None
        if not exe:
            for g in self.games():
                exe = core.eac_setup(g)
                if exe: break
        if not exe: return False, tr('eac_missing')
        if self.host.game_running(): return False, tr('game_running')
        started, _ = self.win.shell_run(exe, verb='runas', directory=os.path.dirname(exe))
        self.log('EAC setup %s started=%s' % (exe, started))
        return (True, tr('eac_started')) if started else (False, tr('declined'))

    def extra_report(self):
        w = self.win
        out = ['windows: %s' % sys.getwindowsversion().__repr__(), 'ACP: %s' % w.ansi_code_page(),
               'elevation type: %s' % w.elevation_type(),
               'cert machine CA: %s, user CA: %s' % (w.cert_present(core.CERT_THUMB), w.cert_present(core.CERT_THUMB, machine=False))]
        for label, path in (('payload', self.payload['dll']), ('installed', self.setup.native)):
            if os.path.isfile(path):
                code, text = w.verify_signature(path)
                out.append('signature %s: %s (0x%08X) sha256 %s' % (label, text, code, core.sha256(path)))
        try:
            games = self.games(); out.append('games: %s' % games)
            for g in games: out.append('EAC setup: %s' % core.eac_setup(g))
        except Exception as e:
            out.append('games: error %s' % e)
        import winreg
        svc = w.reg_value(winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Services\EasyAntiCheat_EOS', 'ImagePath')
        out.append('EAC service: %s' % (svc or 'not installed'))
        out.append('game running: %s' % self.host.game_running())
        return out

    def report(self):
        text = self.setup.report(self.extra_report())
        desk = self.win.known_folder('{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}') or os.path.expanduser('~')
        path = os.path.join(desk, 'MDL3-report-%s.txt' % time.strftime('%Y%m%d-%H%M%S'))
        with open(path, 'w', encoding='utf-8-sig') as f: f.write(text)
        self.win.shell_run(path)
        return True, tr('report_done', path)

    def remove(self, settings, cert):
        try:
            r = self.setup.remove(settings=settings)
        except Exception as e:
            return False, self.explain(e)
        self.log.path = None   # its folder is gone
        msg = tr('removed')
        if r['failed']: msg += '\n' + tr('remove_failed', '\n'.join(r['failed']))
        if cert and self.win.cert_present(core.CERT_THUMB):
            started, code = self.win.run_elevated(self.child_args('--cert-remove'))
            if not started: msg += '\n' + tr('declined')
        return not r['failed'], msg

    def status_text(self):
        st = self.setup.status()
        line = tr('st_none') if not st['installed'] else tr('st_ok') if st.get('current') else tr('st_old')
        if st['legacy'] and not st['installed']:
            zh, en = T['st_none'][0] + T['st_legacy'][0], T['st_none'][1] + T['st_legacy'][1]
            line = zh if LANG == 'zh' else en if LANG == 'en' else zh + '\n' + en
        line += '\n' + (tr('st_cert_yes') if self.win.cert_present(core.CERT_THUMB) else tr('st_cert_no'))
        if st['installed']:
            try: line += '\n' + tr('st_sig', self.win.verify_signature(self.setup.native)[1])
            except Exception: pass
        return line


# ------------------------------------------------------------------------------------------------- elevated child
def child(argv):
    """--cert-install / --cert-remove, started elevated by the window. Exit code 0 = done."""
    import mdl3setup_win as win
    folder = payload_dir(argv)
    try:
        if '--cert-install' in argv:
            with open(os.path.join(folder, CERT_FILE), 'rb') as f: der = f.read()
            return 0 if win.cert_add(der, core.CERT_THUMB) else 3
        if '--cert-remove' in argv:
            return 0 if win.cert_remove(core.CERT_THUMB) else 3
    except Exception:
        return 2
    return 1


# ---------------------------------------------------------------------------------------------------- window
def window(app):
    try: __import__('ctypes').windll.shcore.SetProcessDpiAwareness(1)
    except Exception: pass
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    root = tk.Tk(); root.title(tr('title', sep=' / ') + ' ' + APP_VERSION + '  ·  MDL3 ' + str(app.payload['meta'].get('version')))
    root.minsize(760, 560)
    frm = ttk.Frame(root, padding=12); frm.pack(fill='both', expand=True)
    ttk.Label(frm, text=tr('game', sep=' / ')).grid(row=0, column=0, sticky='w')
    game = tk.StringVar()
    box = ttk.Combobox(frm, textvariable=game, width=70); box.grid(row=0, column=1, sticky='we', padx=6)
    frm.columnconfigure(1, weight=1)

    def browse():
        d = filedialog.askdirectory()
        if d: game.set(os.path.normpath(d))
    ttk.Button(frm, text=tr('browse', sep=' / '), command=browse).grid(row=0, column=2)
    state = tk.StringVar(value='…')
    ttk.Label(frm, text=tr('state', sep=' / ')).grid(row=1, column=0, sticky='nw', pady=(8, 0))
    ttk.Label(frm, textvariable=state, wraplength=640, justify='left').grid(row=1, column=1, columnspan=2, sticky='w', pady=(8, 0))
    btns = ttk.Frame(frm); btns.grid(row=2, column=0, columnspan=3, sticky='we', pady=10)
    out = tk.Text(frm, height=12, wrap='word', state='disabled'); out.grid(row=3, column=0, columnspan=3, sticky='nsew')
    frm.rowconfigure(3, weight=1)
    buttons = []

    def say(text):
        def put():
            out.configure(state='normal'); out.insert('end', text + '\n\n'); out.see('end'); out.configure(state='disabled')
        root.after(0, put)

    def refresh():
        try: s = app.status_text()
        except Exception as e: s = str(e)
        root.after(0, lambda: state.set(s))

    def work(fn, *args):
        def run():
            try: ok, msg = fn(*args)
            except Exception as e:
                app.log(traceback.format_exc()); ok, msg = False, tr('error', e)
            say(('✔ ' if ok else '✖ ') + msg); refresh()
            root.after(0, lambda: [b.configure(state='normal') for b in buttons])
        for b in buttons: b.configure(state='disabled')
        say(tr('busy')); threading.Thread(target=run, daemon=True).start()

    def need_game():
        g = game.get().strip()
        if not core.is_game(g): messagebox.showwarning(tr('title', sep=' / '), tr('not_found')); return None
        return g

    def do_install():
        g = need_game()
        if g: work(app.install, g)

    def do_remove():
        dlg = tk.Toplevel(root); dlg.title(tr('remove', sep=' / ')); dlg.transient(root); dlg.grab_set()
        f = ttk.Frame(dlg, padding=12); f.pack(fill='both')
        ttk.Label(f, text=tr('remove_q'), wraplength=560, justify='left').pack(anchor='w')
        a, c = tk.BooleanVar(value=False), tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text=tr('remove_settings'), variable=a).pack(anchor='w', pady=(8, 0))
        ttk.Checkbutton(f, text=tr('remove_cert'), variable=c).pack(anchor='w')
        row = ttk.Frame(f); row.pack(anchor='e', pady=(10, 0))

        def go():
            dlg.destroy(); work(app.remove, a.get(), c.get())
        ttk.Button(row, text=tr('remove_go', sep=' / '), command=go).pack(side='left', padx=4)
        ttk.Button(row, text=tr('cancel', sep=' / '), command=dlg.destroy).pack(side='left')

    def open_logs():
        for p in (os.path.join(app.setup.data, 'Logs'), app.setup.data, app.setup.root):
            if os.path.isdir(p): app.win.shell_run(p); return

    for i, (key, fn) in enumerate((('install', do_install), ('cert', lambda: work(app.cert_fix)),
                                    ('eac', lambda: work(app.eac_repair, game.get().strip())), ('report', lambda: work(app.report)),
                                    ('logs', open_logs), ('remove', do_remove))):
        b = ttk.Button(btns, text=tr(key), command=fn); b.grid(row=i // 3, column=i % 3, sticky='we', padx=3, pady=3)
        btns.columnconfigure(i % 3, weight=1); buttons.append(b)

    def first():
        try: found = app.games()
        except Exception as e: found = []; app.log('find_game: %s' % e)
        def put():
            box['values'] = found
            if found: game.set(found[0])
            if not found: say(tr('not_found'))
            elif len(found) > 1: say(tr('many'))
            if app.win.elevation_type() == 2: say(tr('elevated'))
        root.after(0, put); refresh()
    threading.Thread(target=first, daemon=True).start()
    root.mainloop()


# ---------------------------------------------------------------------------------------------------- main
def main(argv):
    if '--cert-install' in argv or '--cert-remove' in argv: return child(argv)
    app = App(argv)
    if '--install' in argv:
        game = argv[argv.index('--game') + 1] if '--game' in argv else None
        if not game:
            found = app.games()
            if len(found) != 1: app.log(tr('not_found') if not found else tr('many')); return 4
            game = found[0]
        ok, msg = app.install(game); app.log(msg); return 0 if ok else 1
    if '--remove' in argv:
        ok, msg = app.remove('--settings' in argv, '--cert' in argv); app.log(msg); return 0 if ok else 1
    if '--report' in argv:
        ok, msg = app.report(); app.log(msg); return 0 if ok else 1
    window(app)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception:
        # last resort: a message box (the exe has no console)
        text = traceback.format_exc()
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, text[-1500:], 'MDL3Setup', 0x10)
        except Exception:
            print(text)
        sys.exit(9)
