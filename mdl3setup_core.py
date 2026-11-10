"""MDL3Setup core (dev.47): install / update, migration, grants, report and full removal.

Plain Python (stdlib only), no Windows calls: everything that needs Windows comes in through `host`
(see mdl3setup_win.Host; tests pass a fake). Paths are str with the platform's separator.

Layout (dev.47, every user name):
    %ProgramData%\\MDL3\\                mdl_native_bridge.dll, config.json, install-state.json, Logs\\, Backups\\
    %ProgramData%\\MDL\\Helldivers2\\    Mods\\, Logs\\, Languages\\Options\\   (MDL mod settings)
    %ProgramData%\\CowboyBingus\\Helldivers2\\Logs\\, %ProgramData%\\HD2Runtime\\mod_data\\
    %LOCALAPPDATA%\\MDL3\\sys-paths.txt   tells the native host about the two ProgramData folders above
The game's boot picks %ProgramData% when MDL3\\config.json is there (templates/boot7.lua.in, dev.47).
"""
import hashlib
import json
import os
import re
import shutil
import time
import uuid

PRODUCT = 'MDL3'
STEAM_APP = '553850'
CERT_THUMB = '8d57e2b4008bbe461470a69f3492bc5ae362a7a9'   # Certum Code Signing 2021 CA (intermediate)
DLL_NAME = 'mdl_native_bridge.dll'
GRANT_LIMIT = 32
FOLDERS = ('MDL\\Helldivers2\\Mods', 'MDL\\Helldivers2\\Logs', 'MDL\\Helldivers2\\Languages\\Options',
           'CowboyBingus\\Helldivers2\\Logs', 'HD2Runtime\\mod_data')
MIGRATE = ('MDL\\Helldivers2', 'HD2Runtime\\mod_data')
# full removal: always / only with "also remove mod settings and logs"
REMOVE_ALWAYS = ('MDL3',)
REMOVE_SETTINGS = ('MDL\\Helldivers2', 'CowboyBingus\\Helldivers2', 'HD2Runtime\\mod_data')


class SetupError(Exception):
    pass


def join(*parts):
    return os.path.join(*parts) if os.sep == '\\' else os.path.join(*[p.replace('\\', os.sep) for p in parts])


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''): h.update(block)
    return h.hexdigest()


def plain_ascii(path):
    return bool(path) and '?' not in path and all(32 <= ord(c) < 127 for c in path)


def same_path(a, b):
    if not a or not b: return False
    norm = lambda p: os.path.normcase(os.path.normpath(os.path.abspath(str(p))))
    return norm(a) == norm(b)


def read_json(path):
    with open(path, 'r', encoding='utf-8-sig') as f: return json.load(f)


def write_atomic(path, data):
    """Write through a temporary file in the same folder, then replace (no half-written file left behind)."""
    tmp = path + '.' + uuid.uuid4().hex[:8] + '.tmp'
    try:
        with open(tmp, 'wb') as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.remove(tmp)


def dump_json(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


# --------------------------------------------------------------------------------------------------------- game
def vdf_value(value):
    return value.replace('\\\\', '\\').replace('\\"', '"')


def is_game(path):
    try: return bool(path) and os.path.isfile(join(path, 'bin', 'helldivers2.exe')) and os.path.isdir(join(path, 'data'))
    except OSError: return False


def find_game(steam_roots, uninstall_locations=()):
    """All Helldivers 2 folders found from Steam roots (libraryfolders.vdf, appmanifest) and Uninstall entries."""
    found, libraries = [], []
    for root in steam_roots:
        if root and root not in libraries: libraries.append(root)
    for root in list(libraries):
        for rel in (('steamapps', 'libraryfolders.vdf'), ('config', 'libraryfolders.vdf')):
            try:
                with open(join(root, *rel), 'r', encoding='utf-8', errors='replace') as f: text = f.read()
            except OSError:
                continue
            for m in re.finditer(r'"(?:path|[0-9]+)"\s*"((?:\\.|[^"\\])*)"', text):
                value = vdf_value(m.group(1))
                if os.path.isabs(value) or re.match(r'^[A-Za-z]:[\\/]', value):
                    if value not in libraries: libraries.append(value)
    for library in libraries:
        apps = join(library, 'steamapps')
        try:
            with open(join(apps, 'appmanifest_%s.acf' % STEAM_APP), 'r', encoding='utf-8', errors='replace') as f: acf = f.read()
        except OSError:
            continue   # a library on a drive that is gone is skipped
        m = re.search(r'"installdir"\s*"((?:\\.|[^"\\])*)"', acf)
        if not m: continue
        folder = vdf_value(m.group(1))
        if os.path.isabs(folder) or '..' in folder.replace('/', '\\').split('\\'): continue
        candidate = join(apps, 'common', folder)
        if is_game(candidate): found.append(os.path.normpath(candidate))
    for location in uninstall_locations:
        if location and is_game(location): found.append(os.path.normpath(location))
    unique = []
    for p in found:
        if not any(same_path(p, q) for q in unique): unique.append(p)
    return unique


def eac_setup(game):
    """The game's EasyAntiCheat_EOS_Setup.exe (EasyAntiCheat\\ first, then 3 levels down)."""
    direct = join(game, 'EasyAntiCheat', 'EasyAntiCheat_EOS_Setup.exe')
    if os.path.isfile(direct): return direct
    base_depth = game.rstrip('\\/').count(os.sep)
    for folder, dirs, files in os.walk(game):
        if folder.count(os.sep) - base_depth >= 3: dirs[:] = []
        for name in files:
            if name.lower() == 'easyanticheat_eos_setup.exe': return join(folder, name)
        dirs[:] = [d for d in dirs if d.lower() not in ('data',)]
    return None


# ------------------------------------------------------------------------------------------------------ settings
def current_settings(old, native, game):
    """The installer's config.json: the DLL and game folder, plus the user's own settings kept from `old`."""
    out = {'schema': 1, 'dll': native, 'game_dir': game}
    if not isinstance(old, dict): return out
    if old.get('task_jit') in ('on', 'off'): out['task_jit'] = old['task_jit']
    for name in ('native_memory_mb', 'native_memory_reserve_mb', 'native_owner_quota_mb'):
        v = old.get(name)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v == int(v) and 8 <= v <= 16384: out[name] = int(v)
    if isinstance(old.get('native_auto_reconnect'), bool): out['native_auto_reconnect'] = old['native_auto_reconnect']
    if old.get('bridge_transport') in ('memory', 'file', 'auto'): out['bridge_transport'] = old['bridge_transport']
    for name in ('ui', 'performance', 'memory_guard', 'boot_native', 'perf_diag'):
        if isinstance(old.get(name), dict): out[name] = old[name]
    return out


# --------------------------------------------------------------------------------------------------------- setup
class Setup:
    """host: local_appdata, program_data (str), game_running() -> bool, is_reparse(path) -> bool,
    log(str), and for the Windows-only parts (not used by install/remove) the methods in mdl3setup_win.Host."""

    def __init__(self, host, payload):
        self.host = host
        self.payload = payload            # {'dll': path, 'meta': dict}
        self.local = host.local_appdata
        shared = host.program_data
        if not plain_ascii(shared):
            raise SetupError('ProgramData folder is not plain ASCII: ' + repr(shared))
        if not self.local:
            raise SetupError('LOCALAPPDATA is unavailable')
        self.root = shared
        self.data = join(shared, 'MDL3')
        self.native = join(self.data, DLL_NAME)
        self.config_path = join(self.data, 'config.json')
        self.state_path = join(self.data, 'install-state.json')
        self.legacy = join(self.local, 'MDL3')
        self.grant_path = join(self.legacy, 'sys-paths.txt')

    def log(self, text):
        self.host.log(text)

    # -- safety
    def no_links(self, path):
        """Refuse a path that is (or lies below) a symbolic link / junction below its root."""
        p = os.path.abspath(path)
        while True:
            if os.path.lexists(p) and (os.path.islink(p) or self.host.is_reparse(p)):
                raise SetupError('A linked folder is in the way: ' + p)
            parent = os.path.dirname(p)
            if parent == p or same_path(parent, self.root) or same_path(parent, self.local): return
            p = parent

    def closed_game(self):
        if self.host.game_running(): raise SetupError('game_running')

    # -- payload
    def check_payload(self):
        meta, dll = self.payload['meta'], self.payload['dll']
        want = meta.get('native_sha256')
        if not want or meta.get('native_path') != DLL_NAME: raise SetupError('The setup files are incomplete (BUILD.json).')
        if not os.path.isfile(dll) or sha256(dll) != want: raise SetupError('The embedded component does not match BUILD.json.')
        return want

    # -- state
    def read_state(self):
        if not os.path.isfile(self.state_path): return None
        try: state = read_json(self.state_path)
        except (OSError, ValueError):
            self.log('WARN the installation record cannot be read; it will be backed up and replaced')
            return None
        if isinstance(state, dict) and state.get('product') not in (None, PRODUCT):
            raise SetupError('The installation record belongs to another product.')
        return state if isinstance(state, dict) else None

    def status(self):
        """What is installed where (for the window and the report)."""
        out = {'data': self.data, 'installed': os.path.isfile(self.native), 'legacy': os.path.isfile(join(self.legacy, 'config.json'))}
        state = self.read_state() if os.path.isfile(self.state_path) else None
        out['version'] = state and state.get('version')
        out['game'] = state and state.get('game')
        if out['installed']:
            try: out['current'] = sha256(self.native) == self.payload['meta'].get('native_sha256')
            except OSError: out['current'] = False
        return out

    # -- grants
    def grant_lines(self):
        return ['mkdir=' + join(self.root, 'MDL3'), 'mkdir=' + join(self.root, 'MDL', 'Helldivers2')]

    def write_grants(self):
        os.makedirs(self.legacy, exist_ok=True)
        self.no_links(self.grant_path)
        lines = []
        if os.path.isfile(self.grant_path):
            with open(self.grant_path, 'r', encoding='utf-8-sig', errors='replace') as f:
                lines = [l.rstrip('\r\n') for l in f]
        have = {l.strip().lower() for l in lines}
        add = [l for l in self.grant_lines() if l.lower() not in have]
        if not add: return False
        if len([l for l in lines if l.strip()]) + len(add) > GRANT_LIMIT:
            raise SetupError('sys-paths.txt is full (%d lines); remove lines you no longer need' % GRANT_LIMIT)
        write_atomic(self.grant_path, ('\r\n'.join([l for l in lines if l.strip()] + add) + '\r\n').encode('utf-8'))
        self.log('Granted the native host: ' + ', '.join(add))
        return True

    def remove_grants(self):
        if not os.path.isfile(self.grant_path): return
        with open(self.grant_path, 'r', encoding='utf-8-sig', errors='replace') as f:
            lines = [l.rstrip('\r\n') for l in f]
        mine = {l.lower() for l in self.grant_lines()}
        keep = [l for l in lines if l.strip() and l.strip().lower() not in mine]
        if keep: write_atomic(self.grant_path, ('\r\n'.join(keep) + '\r\n').encode('utf-8'))
        else: os.remove(self.grant_path)

    # -- backup
    def backup(self, paths):
        stamp = time.strftime('%Y%m%d_%H%M%S', time.gmtime()) + '_' + uuid.uuid4().hex[:6]
        folder = join(self.data, 'Backups', stamp)
        os.makedirs(folder, exist_ok=True)
        rows = []
        for p in paths:
            row = {'path': p, 'exists': os.path.isfile(p)}
            if row['exists']:
                row['sha256'] = sha256(p); shutil.copy2(p, join(folder, os.path.basename(p)))
            rows.append(row)
        with open(join(folder, 'backup.json'), 'wb') as f: f.write(dump_json({'files': rows}))
        # keep the newest 5 backups
        root = join(self.data, 'Backups')
        old = sorted(d for d in os.listdir(root) if os.path.isdir(join(root, d)))[:-5]
        for d in old: shutil.rmtree(join(root, d), ignore_errors=True)
        return folder

    def restore(self, folder):
        with open(join(folder, 'backup.json'), 'r', encoding='utf-8') as f: rows = json.load(f)['files']
        for row in rows:
            target = row['path']
            if not any(same_path(target, p) for p in (self.native, self.config_path, self.state_path)):
                raise SetupError('Invalid backup target.')
            if row['exists']:
                src = join(folder, os.path.basename(target))
                if sha256(src) != row['sha256']: raise SetupError('Backup verification failed.')
                with open(src, 'rb') as f: write_atomic(target, f.read())
            elif os.path.exists(target):
                os.remove(target)

    # -- writable probe (a folder made by an elevated process is not writable by the game)
    def probe_writable(self, folder):
        probe = join(folder, '.mdl3-probe-' + uuid.uuid4().hex[:8])
        try:
            with open(probe, 'wb') as f: f.write(b'x')
            os.remove(probe); return True
        except OSError:
            return False

    # -- install / update
    def install(self, game):
        want = self.check_payload()
        if not is_game(game): raise SetupError('The selected game folder is invalid. Select the folder containing bin and data.')
        if same_path(game, self.data) or os.path.normcase(os.path.abspath(self.data)).startswith(os.path.normcase(os.path.abspath(game)) + os.sep):
            raise SetupError('Please install outside the game folder.')
        self.closed_game()
        for p in (self.data, self.native, self.config_path, self.state_path): self.no_links(p)
        os.makedirs(self.data, exist_ok=True)
        if not self.probe_writable(self.data):
            raise SetupError('not_writable:' + self.data)
        state = self.read_state()
        old = None
        if os.path.isfile(self.config_path):
            try: old = read_json(self.config_path)
            except (OSError, ValueError): self.log('WARN the existing config.json cannot be read; it is backed up and replaced')
        # an older install in the user folder (dev.31-46): bring its settings and MDL's folders (never overwrite)
        legacy_config = join(self.legacy, 'config.json')
        migrated = []
        if os.path.isfile(legacy_config):
            if old is None:
                try: old = read_json(legacy_config)
                except (OSError, ValueError): pass
            for rel in MIGRATE:
                src, dst = join(self.local, rel), join(self.root, rel)
                if os.path.isdir(src) and not os.path.exists(dst):
                    try:
                        self.no_links(dst); shutil.copytree(src, dst, symlinks=True); migrated.append(rel)
                    except (OSError, shutil.Error) as e:
                        self.log('WARN could not copy %s: %s' % (rel, e))
        self.write_grants()
        backup = self.backup([self.native, self.config_path, self.state_path])
        try:
            with open(self.payload['dll'], 'rb') as f: dll = f.read()
            if not (os.path.isfile(self.native) and sha256(self.native) == want):
                write_atomic(self.native, dll)
            if sha256(self.native) != want: raise SetupError('Installed file verification failed.')
            meta = self.payload['meta']
            write_atomic(self.config_path, dump_json(current_settings(old, self.native, os.path.normpath(game))))
            write_atomic(self.state_path, dump_json({'schema': 2, 'product': PRODUCT, 'version': meta.get('version'),
                'native_version': meta.get('native_version'), 'data': self.data, 'game': os.path.normpath(game),
                'files': [{'path': self.native, 'sha256': want}], 'installed_by': 'MDL3Setup',
                'installed_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}))
            if not same_path(read_json(self.config_path).get('dll'), self.native): raise SetupError('Installed settings verification failed.')
            os.makedirs(join(self.data, 'Logs'), exist_ok=True)
            for rel in FOLDERS:
                p = join(self.root, rel); self.no_links(p); os.makedirs(p, exist_ok=True)
        except Exception:
            try: self.restore(backup)
            except Exception as e: raise SetupError('Installation failed; restore the files from ' + backup + ' (' + str(e) + ')')
            raise
        # the old user-folder install steps aside (its config would only confuse a reader; the boot prefers this one)
        if os.path.isfile(legacy_config):
            moved = legacy_config + '.moved-to-ProgramData'
            try:
                if os.path.exists(moved): os.remove(moved)
                os.replace(legacy_config, moved)
            except OSError as e:
                self.log('WARN could not rename the old config.json: %s' % e)
        legacy_dll = join(self.legacy, DLL_NAME)
        for p in (legacy_dll, join(self.legacy, 'install-state.json')):
            if os.path.isfile(p):
                try: os.replace(p, p + '.old')
                except OSError: pass
        unwritable = [p for p in [self.data] + [join(self.root, r) for r in FOLDERS] if not self.probe_writable(p)]
        return {'data': self.data, 'game': os.path.normpath(game), 'backup': backup, 'migrated': migrated,
                'state_before': bool(state), 'unwritable': unwritable}

    # -- full removal
    def remove(self, settings=False):
        """Deletes MDL3's own folders (both roots). settings=True also deletes MDL mod settings, logs and loose mods."""
        self.closed_game()
        removed, failed = [], []
        targets = []
        for root in (self.root, self.local):
            for rel in REMOVE_ALWAYS + (REMOVE_SETTINGS if settings else ()):
                targets.append(join(root, rel))
        for p in targets:
            if not os.path.lexists(p): continue
            try:
                self.no_links(p)
                if os.path.islink(p) or self.host.is_reparse(p): raise SetupError('linked folder')
                shutil.rmtree(p, onerror=_force_remove)
                removed.append(p)
            except (OSError, SetupError) as e:
                failed.append('%s (%s)' % (p, e))
        # empty parents (MDL, CowboyBingus, HD2Runtime) go too
        for root in (self.root, self.local):
            for parent in ('MDL', 'CowboyBingus', 'HD2Runtime'):
                p = join(root, parent)
                try:
                    if os.path.isdir(p) and not os.listdir(p) and not os.path.islink(p): os.rmdir(p)
                except OSError:
                    pass
        return {'removed': removed, 'failed': failed}

    # -- report
    def report(self, extra=()):
        lines = ['MDL3Setup report ' + time.strftime('%Y-%m-%d %H:%M:%S'),
                 'package version: %s' % self.payload['meta'].get('version'),
                 'ProgramData data folder: ' + self.data,
                 'user folder (grants): ' + self.legacy]
        st = self.status()
        lines.append('installed: %s  current: %s  version: %s' % (st['installed'], st.get('current'), st.get('version')))
        lines.append('older user-folder install: %s' % st['legacy'])
        lines.append('game (record): %s' % st.get('game'))
        if os.path.isfile(self.grant_path):
            with open(self.grant_path, 'r', encoding='utf-8-sig', errors='replace') as f: lines.append('sys-paths.txt: ' + ' | '.join(l.strip() for l in f if l.strip()))
        else:
            lines.append('sys-paths.txt: (none)')
        for p in [self.data] + [join(self.root, r) for r in FOLDERS]:
            if os.path.isdir(p): lines.append('writable %s: %s' % (p, self.probe_writable(p)))
        lines += list(extra)
        for name in ('MDL3.log', 'MDL.log'):
            for folder in (join(self.data, 'Logs'), join(self.root, 'MDL', 'Helldivers2', 'Logs'), join(self.legacy, 'Logs')):
                p = join(folder, name)
                if os.path.isfile(p):
                    try:
                        with open(p, 'rb') as f:
                            f.seek(max(0, os.path.getsize(p) - 12000)); tail = f.read().decode('utf-8', 'replace')
                        lines += ['', '---- tail of ' + p + ' ----', tail]
                    except OSError:
                        pass
        return '\n'.join(lines) + '\n'


def _force_remove(func, path, exc_info):
    """rmtree helper: clear read-only and retry once."""
    try:
        os.chmod(path, 0o666 if os.path.isfile(path) else 0o777); func(path)
    except OSError:
        raise exc_info[1]
