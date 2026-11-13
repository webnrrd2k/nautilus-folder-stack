# fstack.bash: bash side of the Nautilus Folder Stack. Source it from ~/.bashrc.
# Every command takes -h/--help; `nhelp` shows how they fit together.
#
#   npush [DIR]   push DIR (default: here) onto the Nautilus folder stack
#   npop          pop the top folder and cd into it
#   ncd [N]       cd to entry N (default 0 = top) without popping it
#   nstack        list the stack, top first
#   ndrop N       remove entry N
#   nclear        empty the stack
#   nopen [N]     open entry N (default: top) in Nautilus
#   nhere [DIR]   open DIR (default: here) in Nautilus
#   nhelp [CMD]   overview, or help for one command

command -v fstack >/dev/null || PATH="$HOME/.local/bin:$PATH"

# _fstack_help NAME ARG: print NAME's help and succeed if ARG is -h/--help
_fstack_help() {
    case "$2" in -h|--help) fstack help "$1"; return 0 ;; esac
    return 1
}

npush()  { _fstack_help npush  "$1" && return; fstack push "${1:-.}"; }
npop()   { _fstack_help npop   "$1" && return; local d; d=$(fstack pop) && cd -- "$d"; }
ncd()    { _fstack_help ncd    "$1" && return; local d; d=$(fstack get "${1:-0}") && cd -- "$d"; }
nstack() { _fstack_help nstack "$1" && return; fstack list; }
ndrop()  { _fstack_help ndrop  "$1" && return; fstack drop "$@"; }
nclear() { _fstack_help nclear "$1" && return; fstack clear; }
nopen()  { _fstack_help nopen  "$1" && return; fstack open "${1:-0}"; }
nhere()  { _fstack_help nhere  "$1" && return; ( nautilus "${1:-.}" >/dev/null 2>&1 & ); }
nhelp()  { _fstack_help nhelp  "$1" && return; fstack help "$@"; }

# Tab completion: directories for npush/nhere, stack positions for ncd/ndrop/nopen
complete -d npush nhere
complete -W "npush npop ncd nstack ndrop nclear nopen nhere nhelp push pop peek get drop list open clear help version" nhelp
_fstack_positions() {
    local n; n=$(fstack list 2>/dev/null | wc -l)
    (( n > 0 )) && COMPREPLY=( $(compgen -W "$(seq 0 $((n - 1)))" -- "${COMP_WORDS[COMP_CWORD]}") )
}
complete -F _fstack_positions ncd ndrop nopen
