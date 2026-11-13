#!/usr/bin/env bash
# Installs fstack, the bash side of the Nautilus Folder Stack. Run from this folder.
set -euo pipefail
cd "$(dirname "$0")"

data=~/.local/share
mkdir -p ~/.local/bin "$data/nautilus-folder-stack" "$data/man/man1"
install -m 755 fstack ~/.local/bin/fstack
install -m 644 fstack.bash "$data/nautilus-folder-stack/fstack.bash"

# man page; `man npush`, `man npop`, ... all open it
install -m 644 fstack.1 "$data/man/man1/fstack.1"
for c in npush npop ncd nstack ndrop nclear nopen nhere nhelp; do
    echo ".so man1/fstack.1" > "$data/man/man1/$c.1"
done
mandb -q --user-db 2>/dev/null || true

line='[ -f ~/.local/share/nautilus-folder-stack/fstack.bash ] && . ~/.local/share/nautilus-folder-stack/fstack.bash'
grep -qF "fstack.bash" ~/.bashrc 2>/dev/null || printf '\n# Nautilus folder stack from bash\n%s\n' "$line" >> ~/.bashrc

# Let an already-installed folder_stack.py see changes made from bash
ext=$data/nautilus-python/extensions/folder_stack.py
if [ -f folder_stack.py ]; then          # extension shipped alongside (repo checkout)
    mkdir -p "$(dirname "$ext")"
    install -m 644 folder_stack.py "$ext"
    rpm -q nautilus-python >/dev/null 2>&1 || echo "Note: the extension needs: sudo dnf install nautilus-python"
fi
if [ -f "$ext" ]; then
    python3 patch_folder_stack.py "$ext"
    nautilus -q 2>/dev/null || true
else
    echo "Note: $ext isn't installed yet. The bash commands work without it,"
    echo "but install the extension to see the stack in Nautilus."
fi

echo
echo "Done. Open a new terminal (or run: source ~/.bashrc), then try: nhelp"
