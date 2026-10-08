from agent.analysis.test_output_parser import parse_pytest_output


def run_tests(ctx, scope="targeted", paths=None):
    cfg = ctx.config
    cmd = ["python", "-m", "pytest", "-q", "--tb=short", "-p", "no:cacheprovider", "--maxfail=10"]
    timeout = cfg.command_timeout

    if isinstance(paths, str):
        paths = [paths]

    if scope == "targeted":
        if not paths:
            return "ERROR: scope='targeted' requires `paths` (file or file::test)."
        if any(str(p).startswith("-") for p in paths):
            return "ERROR: paths must not start with '-'."
        cmd += list(paths)
    elif scope == "full":
        timeout *= 3
    else:
        return "ERROR: scope must be 'targeted' or 'full'."

    code, out = ctx.sandbox.exec(cmd, timeout=timeout)
    result = parse_pytest_output(out, code)
    result.scope = scope
    ctx.state.record_test(result)
    return result.render(cfg.tool_output_limit)