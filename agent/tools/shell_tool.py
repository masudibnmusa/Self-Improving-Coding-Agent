import shlex

ALLOWED = {"ls", "cat", "head", "tail", "wc", "find", "python", "python3", "pytest", "git", "pwd"}
GIT_ALLOWED = {"status", "diff", "log", "show", "blame", "ls-files", "grep"}
FIND_FORBIDDEN = {"-delete", "-exec", "-execdir", "-ok", "-okdir"}


def run_shell(ctx, command):
    try:
        argv = shlex.split(command)
    except ValueError as e:
        return f"ERROR: could not parse command: {e}"
    if not argv:
        return "ERROR: empty command"

    if argv[0] not in ALLOWED:
        return f"ERROR: '{argv[0]}' is not allowed. Allowed: {', '.join(sorted(ALLOWED))}"
    if argv[0] == "git" and (len(argv) < 2 or argv[1] not in GIT_ALLOWED):
        return f"ERROR: only these git subcommands are allowed: {', '.join(sorted(GIT_ALLOWED))}"
    if argv[0] == "find" and any(a in FIND_FORBIDDEN for a in argv):
        return "ERROR: find with -exec/-delete is not allowed"

    # No shell is involved (argv list), so pipes, redirects and && do not work by design.
    code, out = ctx.sandbox.exec(argv, timeout=ctx.config.command_timeout)
    return f"[exit {code}]\n{out}"