#!/usr/bin/env python3
"""
Patch folder_stack.py so the Nautilus extension notices stack changes made by
the `fstack` command (it re-reads state.json whenever the file has changed).

Usage: python3 patch_folder_stack.py [path/to/folder_stack.py]
Default path: ~/.local/share/nautilus-python/extensions/folder_stack.py
A backup is saved next to it as folder_stack.py.bak. Safe to run twice.
"""

import os
import shutil
import sys

DEFAULT = os.path.expanduser("~/.local/share/nautilus-python/extensions/folder_stack.py")

REFRESH = '''
    def _refresh(self):
        """Re-read state.json if something else (e.g. `fstack`) changed it."""
        try:
            st = os.stat(self.state_file)
        except OSError:
            return
        if (st.st_ino, st.st_mtime_ns) != getattr(self, "_state_sig", None):
            self._load()
'''

EDITS = [
    # remember which version of the file we loaded
    ("    def _load(self):\n        try:\n",
     "    def _load(self):\n"
     "        try:\n"
     "            _st = os.stat(self.state_file)\n"
     "            self._state_sig = (_st.st_ino, _st.st_mtime_ns)\n"
     "        except OSError:\n"
     "            self._state_sig = None\n"
     "        try:\n"),
    # ...and which version we wrote, then add _refresh()
    ('                {"history": self.history, "stack": self.stack}, indent=1))\n'
     "        except OSError:\n"
     "            pass\n",
     '                {"history": self.history, "stack": self.stack}, indent=1))\n'
     "            _st = os.stat(self.state_file)\n"
     "            self._state_sig = (_st.st_ino, _st.st_mtime_ns)\n"
     "        except OSError:\n"
     "            pass\n" + REFRESH),
    # refresh before anything reads or changes the stack
    ("    def record_visit(self, uri, when=None):\n",
     "    def record_visit(self, uri, when=None):\n        self._refresh()\n"),
    ("    def push(self, uri):\n",
     "    def push(self, uri):\n        self._refresh()\n"),
    ("    def pop(self):\n",
     "    def pop(self):\n        self._refresh()\n"),
    ("    def clear(self):\n",
     "    def clear(self):\n        self._refresh()\n"),
    ('        """If the user removed a 📌 bookmark in the sidebar, drop it from the stack."""\n',
     '        """If the user removed a 📌 bookmark in the sidebar, drop it from the stack."""\n'
     "        self._refresh()\n"),
]


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    try:
        with open(path, encoding="utf-8") as f:
            src = f.read()
    except OSError as e:
        sys.exit(f"Can't read {path}: {e}")

    if "def _refresh(self):" in src:
        print(f"{path} is already patched.")
        return

    missing = [old.splitlines()[0].strip() for old, _ in EDITS if src.count(old) != 1]
    if missing:
        sys.exit("Didn't change anything: this folder_stack.py doesn't look like the "
                 "expected version. Couldn't find exactly one match for:\n  "
                 + "\n  ".join(missing))

    for old, new in EDITS:
        src = src.replace(old, new, 1)
    compile(src, path, "exec")  # refuse to write a broken file

    shutil.copy2(path, path + ".bak")
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"Patched {path} (backup: {path}.bak). Restart Nautilus with: nautilus -q")


if __name__ == "__main__":
    main()
