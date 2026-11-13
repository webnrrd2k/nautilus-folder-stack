# Nautilus Folder Stack

A `pushd`/`popd`-style folder stack for the GNOME Files app (Nautilus), shared
with your bash prompt.

When you're pulling files together from all over your computer for a report or
project, you end up navigating back to the same folders again and again.
Nautilus keeps a list of recent *files*, but not recent *folders*. The Folder
Stack lets you push a folder from Nautilus or from a terminal, then get back to
it from either place.

- **In Nautilus:** right-click a folder's background to push it, pop back to it, or jump to any folder on the stack. There's also a **Recent Folders** menu.
- **In the sidebar and file dialogs:** pushed folders appear as 📌 bookmarks, including in a browser's *Save As…* dialog, so downloads can go straight into the project you're working on.
- **In bash:** `npush` a folder, then later `npop` to cd back to it. Pushes made in Nautilus show up here too, and the other way round.

Built for Fedora (GNOME Files 43+, `nautilus-python`). It should work on any
distro with those.

## Contents

| File | What it is |
|---|---|
| `folder_stack.py` | The Nautilus extension (context menus, Recent Folders, 📌 bookmarks) |
| `fstack` | Command-line program that reads and changes the stack |
| `fstack.bash` | Bash functions (`npush`, `npop`, …) that wrap `fstack` |
| `fstack.1` | Man page |
| `patch_folder_stack.py` | Updates an older `folder_stack.py` so it sees changes made from bash |
| `install.sh` | Installs all of the above for the current user |

## Install

```bash
sudo dnf install nautilus-python        # needed for the Nautilus extension
git clone https://github.com/webnrrd2k/nautilus-folder-stack.git
cd nautilus-folder-stack
./install.sh
```

Then open a new terminal and run `nhelp`.

Everything installs under your home folder; no root needed apart from the
package above:

- `~/.local/bin/fstack`
- `~/.local/share/nautilus-folder-stack/fstack.bash`, plus one line added to `~/.bashrc` to load it
- `~/.local/share/man/man1/fstack.1` (also reachable as `man npush`, `man npop`, …)
- `~/.local/share/nautilus-python/extensions/folder_stack.py`

The installer restarts Nautilus (`nautilus -q`) so the extension loads.

## Using it in Nautilus

Right-click the empty background of any folder:

- **Folder Stack ▸ Push This Folder** puts the current folder on top of the stack.
- **Folder Stack ▸ Pop** goes back to the most recently pushed folder and removes it from the stack.
- **Folder Stack ▸ *folder name*** jumps to any folder on the stack.
- **Folder Stack ▸ Clear Stack** empties the stack.
- **Recent Folders ▸** lists folders you've browsed lately, plus folders holding files you've recently opened or downloaded.

Right-clicking a single selected folder also offers **Push Folder onto Stack**.

Pushed folders appear in the sidebar marked 📌. Remove a 📌 bookmark from the
sidebar and that folder drops off the stack.

## Using it from bash

| Command | What it does |
|---|---|
| `npush [DIR]` | Push DIR (default: the current directory) onto the stack |
| `npop` | Pop the top folder and `cd` into it |
| `ncd [N]` | `cd` to entry N (default 0, the top) without popping it |
| `nstack` | List the stack, top first, numbered |
| `ndrop N` | Remove entry N |
| `nclear` | Empty the stack |
| `nopen [N]` | Open entry N in a Nautilus window |
| `nhere [DIR]` | Open DIR (default: the current directory) in Nautilus |
| `nhelp [CMD]` | Overview, or help for one command |

Every command accepts `-h` / `--help`. Tab completion fills in folder names for
`npush` and `nhere`, and stack positions for `ncd`, `ndrop` and `nopen`.

### Example

```console
$ cd ~/school/physics/lab-report
$ npush
pushed ~/school/physics/lab-report  (1 on stack)
$ cd ~/Downloads
$ cp data.csv "$(fstack peek)"
$ npop
$ pwd
/home/jeff/school/physics/lab-report
```

Or push a folder in Nautilus, then go to it from the terminal:

```console
$ nstack
 0  ~/school/physics/lab-report
 1  ~/Documents/references
$ ncd 1
```

### In scripts: the `fstack` program

The `n…` commands are bash functions, because only a shell function can change
your shell's current directory. They call `fstack`, which you can use directly:

```
fstack push [DIR]    push DIR (default: .)
fstack pop           remove the top entry, print its path
fstack peek          print the top entry's path (alias: top)
fstack get N         print entry N's path
fstack drop N        remove entry N
fstack list          numbered list, ~ for home (alias: ls; the default)
fstack open [N]      open entry N in Nautilus
fstack clear         empty the stack
fstack help [CMD]    help for a subcommand or an n… command
fstack version       print the version
```

Paths go to stdout, while messages and errors go to stderr, so
`"$(fstack peek)"` captures just the path. Exit status is 0 on success, 1 if
the stack is empty or there's no entry with that number, and 2 for usage errors.

## How it works

The stack lives in `~/.local/share/nautilus-folder-stack/state.json`, which
both the extension and `fstack` read and write. Each side writes the whole file
at once, so it's never left half-written, and re-reads it whenever it has
changed. That way a push in one place is never overwritten by the other.

The 📌 sidebar entries are ordinary GTK bookmarks in
`~/.config/gtk-3.0/bookmarks`, told apart from your own bookmarks by the 📌
label. Your own bookmarks are never changed.

## Uninstall

```bash
rm ~/.local/bin/fstack
rm -r ~/.local/share/nautilus-folder-stack      # also deletes the saved stack
rm ~/.local/share/nautilus-python/extensions/folder_stack.py
rm ~/.local/share/man/man1/{fstack,npush,npop,ncd,nstack,ndrop,nclear,nopen,nhere,nhelp}.1
sed -i '/fstack.bash/d; /Nautilus folder stack from bash/d' ~/.bashrc
nautilus -q
```

Before uninstalling, run `nclear` first to remove the 📌 sidebar bookmarks, or
delete them from the sidebar afterwards.

## Troubleshooting

- **No Folder Stack menu in Nautilus:** check that `nautilus-python` is installed, then run `nautilus -q` and reopen Files. Running `nautilus` from a terminal shows any errors from the extension.
- **`fstack: command not found`:** `~/.local/bin` isn't on your `PATH`. Fedora adds it by default; `fstack.bash` also adds it when it loads.
- **`man fstack` finds nothing:** run `mandb --user-db`, or check that `manpath` includes `~/.local/share/man`.
- **Menu labels show doubled underscores:** set `ESCAPE_UNDERSCORES = False` at the top of `folder_stack.py`.

## License

MIT. See [LICENSE](LICENSE).
