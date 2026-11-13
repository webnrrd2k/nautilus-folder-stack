"""
Folder Stack & Recent Folders — a nautilus-python extension for GNOME Files 43+

Right-click the empty background of any folder to get:

  Recent Folders ▸   folders you've browsed lately, plus folders holding files
                     you've recently opened or downloaded (newest first)
  Folder Stack   ▸   Push This Folder / Pop (go back to the last pushed folder) /
                     jump to any pushed folder / Clear Stack

Right-clicking a single selected folder also offers "Push Folder onto Stack".

Pushed folders also show up as 📌 bookmarks in the Nautilus sidebar and in
GTK file dialogs (e.g. a browser's "Save As…"), so you can save downloads straight
into the project you're working on. Remove a 📌 bookmark in the sidebar and it
drops off the stack too.

Install:  sudo dnf install nautilus-python
          mkdir -p ~/.local/share/nautilus-python/extensions
          cp folder_stack.py ~/.local/share/nautilus-python/extensions/
          nautilus -q        # then reopen Files
"""

import json
import os
import tempfile
import time
import urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime

import gi

# Nautilus 43–48 ship extension API 4.0; newer releases ship 4.1.
try:
    gi.require_version("Nautilus", "4.1")
except ValueError:
    gi.require_version("Nautilus", "4.0")
from gi.repository import Gio, GLib, GObject, Nautilus  # noqa: E402

# ----------------------------------------------------------------- settings --
MAX_RECENT_SHOWN = 15            # entries in the Recent Folders menu
MAX_HISTORY_KEPT = 300           # folders remembered on disk
INCLUDE_RECENT_FILE_FOLDERS = True   # also use folders of recently used files
STACK_IN_SIDEBAR = True          # mirror the stack as 📌 sidebar bookmarks
SIDEBAR_PREFIX = "📌 "           # marks the bookmarks this extension manages
ESCAPE_UNDERSCORES = True        # set False if menu labels show "__"
# Folders under these paths are never listed as recent ("~" is expanded).
IGNORED_PATH_PREFIXES = ["/tmp", "~/.cache", "~/.local/share/Trash"]
# Nautilus-internal locations that aren't real folders.
IGNORED_SCHEMES = {
    "trash", "recent", "starred", "x-nautilus-search", "other-locations",
    "network", "computer", "burn", "admin",
}
# -----------------------------------------------------------------------------

_HOME = os.path.expanduser("~")
_DATA_HOME = os.environ.get("XDG_DATA_HOME") or os.path.join(_HOME, ".local", "share")
_CONFIG_HOME = os.environ.get("XDG_CONFIG_HOME") or os.path.join(_HOME, ".config")

STATE_FILE = os.path.join(_DATA_HOME, "nautilus-folder-stack", "state.json")
BOOKMARKS_FILE = os.path.join(_CONFIG_HOME, "gtk-3.0", "bookmarks")
XBEL_FILE = os.path.join(_DATA_HOME, "recently-used.xbel")


# ------------------------------------------------------------------ helpers --
def _normalize(uri):
    if uri and uri.endswith("/") and not uri.endswith(":///"):
        uri = uri.rstrip("/")
    return uri


def _local_path(uri):
    """Filesystem path for a file:// URI, else None."""
    if not uri.startswith("file://"):
        return None
    return urllib.parse.unquote(urllib.parse.urlparse(uri).path) or "/"


def _is_trackable(uri):
    if not uri or ":" not in uri:
        return False
    if uri.split(":", 1)[0] in IGNORED_SCHEMES:
        return False
    path = _local_path(uri)
    if path is not None:
        for prefix in IGNORED_PATH_PREFIXES:
            prefix = os.path.expanduser(prefix).rstrip("/")
            if path == prefix or path.startswith(prefix + "/"):
                return False
    return True


def _still_exists(uri):
    path = _local_path(uri)
    return os.path.isdir(path) if path is not None else True


def _short_name(uri):
    path = _local_path(uri)
    if path is None:
        return urllib.parse.unquote(uri.rstrip("/").rsplit("/", 1)[-1]) or uri
    if path == _HOME:
        return "Home"
    return os.path.basename(path.rstrip("/")) or "/"


def _pretty(uri):
    """'report-3   (~/School/ENGL-1)' style label."""
    path = _local_path(uri)
    if path is None:
        return urllib.parse.unquote(uri)
    if path == _HOME:
        return "Home   (~)"
    parent = os.path.dirname(path.rstrip("/")) or "/"
    if parent == _HOME or parent.startswith(_HOME + "/"):
        parent = "~" + parent[len(_HOME):]
    return f"{_short_name(uri)}   ({parent})"


def _atomic_write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _parse_xbel_time(text):
    if not text:
        return 0.0
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


# -------------------------------------------------------------------- store --
class FolderStore:
    """History + stack, persisted as JSON. No GTK in here."""

    def __init__(self, state_file=STATE_FILE, bookmarks_file=BOOKMARKS_FILE,
                 xbel_file=XBEL_FILE):
        self.state_file = state_file
        self.bookmarks_file = bookmarks_file
        self.xbel_file = xbel_file
        self.history = {}   # uri -> last-visit timestamp
        self.stack = []     # uris, top of stack first
        self._xbel_cache = (None, {})
        self._load()

    # persistence
    def _load(self):
        try:
            _st = os.stat(self.state_file)
            self._state_sig = (_st.st_ino, _st.st_mtime_ns)
        except OSError:
            self._state_sig = None
        try:
            with open(self.state_file, encoding="utf-8") as f:
                data = json.load(f)
            self.history = {k: float(v) for k, v in data.get("history", {}).items()}
            self.stack = [u for u in data.get("stack", []) if isinstance(u, str)]
        except (OSError, ValueError, AttributeError):
            pass

    def _save(self):
        try:
            _atomic_write(self.state_file, json.dumps(
                {"history": self.history, "stack": self.stack}, indent=1))
            _st = os.stat(self.state_file)
            self._state_sig = (_st.st_ino, _st.st_mtime_ns)
        except OSError:
            pass

    def _refresh(self):
        """Re-read state.json if something else (e.g. `fstack`) changed it."""
        try:
            st = os.stat(self.state_file)
        except OSError:
            return
        if (st.st_ino, st.st_mtime_ns) != getattr(self, "_state_sig", None):
            self._load()

    # history
    def record_visit(self, uri, when=None):
        self._refresh()
        uri = _normalize(uri)
        if not _is_trackable(uri):
            return
        self.history[uri] = when if when is not None else time.time()
        if len(self.history) > MAX_HISTORY_KEPT:
            keep = sorted(self.history.items(), key=lambda kv: kv[1], reverse=True)
            self.history = dict(keep[:MAX_HISTORY_KEPT])
        self._save()

    def _recent_file_folders(self):
        """Parent folders of entries in GTK's recently-used.xbel."""
        try:
            mtime = os.stat(self.xbel_file).st_mtime
        except OSError:
            return {}
        if self._xbel_cache[0] == mtime:
            return self._xbel_cache[1]
        folders = {}
        try:
            for bm in ET.parse(self.xbel_file).getroot().iter("bookmark"):
                href = bm.get("href", "")
                if "/" not in href:
                    continue
                parent = _normalize(href.rsplit("/", 1)[0])
                if parent.endswith(":/") or parent.endswith(":"):
                    continue
                t = max(_parse_xbel_time(bm.get(k)) for k in ("added", "modified", "visited"))
                if t > folders.get(parent, 0.0):
                    folders[parent] = t
        except (ET.ParseError, OSError):
            folders = {}
        self._xbel_cache = (mtime, folders)
        return folders

    def recent(self, exclude=(), limit=MAX_RECENT_SHOWN):
        merged = dict(self.history)
        if INCLUDE_RECENT_FILE_FOLDERS:
            for uri, t in self._recent_file_folders().items():
                if t > merged.get(uri, 0.0):
                    merged[uri] = t
        exclude = {_normalize(u) for u in exclude}
        out = []
        for uri, _t in sorted(merged.items(), key=lambda kv: kv[1], reverse=True):
            if uri in exclude or not _is_trackable(uri) or not _still_exists(uri):
                continue
            out.append(uri)
            if len(out) >= limit:
                break
        return out

    # stack
    def push(self, uri):
        self._refresh()
        uri = _normalize(uri)
        if uri in self.stack:
            self.stack.remove(uri)
        self.stack.insert(0, uri)
        self._stack_changed()

    def pop(self):
        self._refresh()
        if not self.stack:
            return None
        uri = self.stack.pop(0)
        self._stack_changed()
        return uri

    def clear(self):
        self._refresh()
        self.stack = []
        self._stack_changed()

    def _stack_changed(self):
        self._save()
        if STACK_IN_SIDEBAR:
            self.sync_bookmarks()

    # sidebar bookmarks
    @staticmethod
    def _is_managed(line):
        parts = line.split(" ", 1)
        return len(parts) == 2 and parts[1].startswith(SIDEBAR_PREFIX)

    def _read_bookmarks(self):
        try:
            with open(self.bookmarks_file, encoding="utf-8") as f:
                return f.read().splitlines()
        except OSError:
            return None

    def sync_bookmarks(self):
        lines = self._read_bookmarks() or []
        kept = [l for l in lines if not self._is_managed(l)]
        managed = [f"{uri} {SIDEBAR_PREFIX}{_short_name(uri)}" for uri in self.stack]
        new = kept + managed
        if new != lines:
            try:
                _atomic_write(self.bookmarks_file, "\n".join(new) + ("\n" if new else ""))
            except OSError:
                pass

    def reconcile_with_sidebar(self):
        """If the user removed a 📌 bookmark in the sidebar, drop it from the stack."""
        self._refresh()
        if not STACK_IN_SIDEBAR or not self.stack:
            return
        lines = self._read_bookmarks()
        if lines is None:
            self.sync_bookmarks()
            return
        managed = {_normalize(l.split(" ", 1)[0]) for l in lines if self._is_managed(l)}
        new = [u for u in self.stack if u in managed]
        if new != self.stack:
            self.stack = new
            self._save()


# ---------------------------------------------------------------- extension --
def _label(text):
    return text.replace("_", "__") if ESCAPE_UNDERSCORES else text


def _open(uri):
    try:
        Gio.Subprocess.new(["nautilus", uri], Gio.SubprocessFlags.NONE)
    except GLib.Error:
        Gio.AppInfo.launch_default_for_uri(uri, None)


class FolderStackExtension(GObject.GObject, Nautilus.MenuProvider, Nautilus.InfoProvider):
    def __init__(self):
        super().__init__()
        self.store = FolderStore()
        self._pending = Counter()
        self._flush_id = 0

    # --- visit tracking -------------------------------------------------------
    # Nautilus asks info providers about every file it shows. A burst of calls
    # whose files mostly share one parent means "the user is looking at that
    # folder". Search results and the Recent view spread across many parents
    # and don't pass the threshold.
    def update_file_info(self, file):
        try:
            parent = file.get_parent_uri()
        except Exception:
            parent = None
        if parent:
            self._pending[parent] += 1
            if not self._flush_id:
                self._flush_id = GLib.timeout_add(1500, self._flush)
        return Nautilus.OperationResult.COMPLETE

    def _flush(self):
        self._flush_id = 0
        total = sum(self._pending.values())
        if total:
            top, count = self._pending.most_common(1)[0]
            if count / total >= 0.6:
                self.store.record_visit(top)
        self._pending.clear()
        return False

    # --- menus ----------------------------------------------------------------
    def get_background_items(self, *args):
        current_folder = args[-1]  # API 4.0: (folder); API 3.0: (window, folder)
        here = _normalize(current_folder.get_uri())
        self.store.record_visit(here)
        self.store.reconcile_with_sidebar()
        return [self._recent_menu(here), self._stack_menu(here)]

    def get_file_items(self, *args):
        files = args[-1]
        if len(files) != 1 or not files[0].is_directory():
            return []
        uri = files[0].get_uri()
        item = Nautilus.MenuItem(name="FolderStack::push_selected",
                                 label="Push Folder onto Stack",
                                 tip="Remember this folder (also pinned in the sidebar)")
        item.connect("activate", lambda *_: self.store.push(uri))
        return [item]

    def _recent_menu(self, here):
        top = Nautilus.MenuItem(name="FolderStack::recent", label="Recent Folders")
        sub = Nautilus.Menu()
        top.set_submenu(sub)
        recent = self.store.recent(exclude=[here])
        if not recent:
            sub.append_item(Nautilus.MenuItem(name="FolderStack::recent_none",
                                              label="(nothing yet)", sensitive=False))
        for i, uri in enumerate(recent):
            item = Nautilus.MenuItem(name=f"FolderStack::recent_{i}",
                                     label=_label(_pretty(uri)),
                                     tip=urllib.parse.unquote(uri))
            item.connect("activate", self._on_open, uri)
            sub.append_item(item)
        return top

    def _stack_menu(self, here):
        stack = self.store.stack
        top = Nautilus.MenuItem(name="FolderStack::stack",
                                label=f"Folder Stack ({len(stack)})" if stack else "Folder Stack")
        sub = Nautilus.Menu()
        top.set_submenu(sub)

        push = Nautilus.MenuItem(name="FolderStack::push", label="Push This Folder",
                                 tip="Remember this folder (also pinned in the sidebar)")
        push.connect("activate", self._on_push, here)
        sub.append_item(push)

        if stack:
            pop = Nautilus.MenuItem(name="FolderStack::pop",
                                    label=_label(f"Pop → {_short_name(stack[0])}"),
                                    tip="Go to the most recently pushed folder and remove it from the stack")
            pop.connect("activate", self._on_pop)
            sub.append_item(pop)
            for i, uri in enumerate(stack):
                item = Nautilus.MenuItem(name=f"FolderStack::stack_{i}",
                                         label=_label(f"{i + 1}.  {_pretty(uri)}"),
                                         tip="Go there (stays on the stack)")
                item.connect("activate", self._on_open, uri)
                sub.append_item(item)
            clear = Nautilus.MenuItem(name="FolderStack::clear", label="Clear Stack")
            clear.connect("activate", self._on_clear)
            sub.append_item(clear)
        return top

    # --- callbacks ------------------------------------------------------------
    def _on_open(self, _item, uri):
        _open(uri)

    def _on_push(self, _item, uri):
        self.store.push(uri)

    def _on_pop(self, _item):
        uri = self.store.pop()
        if uri:
            _open(uri)

    def _on_clear(self, _item):
        self.store.clear()
