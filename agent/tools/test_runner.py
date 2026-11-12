from agent.analysis.test_output_parser import parse_pytest_output
from agent.tools.file_viewer import normalize


def run_tests(ctx, scope="targeted", paths=None):
    cfg = ctx.config
    cmd = ["python", "-m", "pytest", "-q", "--tb=short", "-p", "no:cacheprovider"]
    timeout = cfg.command_timeout

    if isinstance(paths, str):
        paths = [paths]

    if scope == "targeted":
        if not paths:
            return "ERROR: scope='targeted' requires `paths` (file or file::test)."
        paths = [normalize(p) for p in paths]
        if any(p.startswith("-") for p in paths):
            return "ERROR: paths must not start with '-'."
        cmd += ["--maxfail=10", *paths]
    elif scope == "full":
        # No --maxfail and keep going past collection errors: the run must be complete so its
        # failures can be compared against the pre-existing ones (see AgentState.verified).
        paths = []
        cmd += ["--continue-on-collection-errors"]
        timeout *= 3
    else:
        return "ERROR: scope must be 'targeted' or 'full'."

    # fresh=True: discard anything changed inside the sandbox so tests see exactly the host tree.
    code, out = ctx.sandbox.exec(cmd, timeout=timeout, fresh=True)
    result = parse_pytest_output(out, code)
    result.scope = scope
    ctx.state.record_test(result, paths)
    return result.render(cfg.tool_output_limit)
