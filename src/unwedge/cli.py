"""The `unwedge` command line."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time

from unwedge import __version__
from unwedge.config import Settings
from unwedge.providers import PROVIDER_NAMES, ProviderError, make_provider

DOCTOR_QUESTIONS = {"about_cats": {"type": "noul", "instructions": "Is this sentence about a cat?"}}


def _settings() -> Settings:
    try:
        return Settings.from_env()
    except ValueError as exc:
        print(f"unwedge: invalid settings: {exc}", file=sys.stderr)
        raise SystemExit(2) from None


def _provider_from_args(args: argparse.Namespace, settings: Settings):
    name = args.provider or settings.provider
    if name == settings.provider:
        return settings.make_provider()
    return make_provider(name, model=getattr(args, "model", None))


def cmd_hook(args: argparse.Namespace) -> int:
    from unwedge.hooks import main

    return main()


def cmd_scan(args: argparse.Namespace) -> int:
    from unwedge.replay import recent_transcripts, replay_file

    provider = make_provider(args.provider or "none", model=args.model)
    paths = recent_transcripts(limit=args.limit)
    if not paths:
        print("No Claude Code transcripts or Codex rollouts found.")
        return 0
    print(f"Scanning {len(paths)} recent sessions with provider={args.provider or 'none'} (shadow, nothing is sent "
          f"to the agent)\n")
    print(f"{'turns':>5} {'first alarm':>11} {'after alarm':>11}  harness      session")
    flagged = 0
    try:
        for path in paths:
            try:
                result = replay_file(path, provider)
            except (OSError, ValueError, UnicodeDecodeError):
                continue
            if not result.turns:
                continue
            first = result.first_intervention
            flagged += first is not None
            label = f"turn {first}" if first else "-"
            print(f"{len(result.turns):>5} {label:>11} {result.turns_after_first_intervention:>11}  "
                  f"{result.harness:<12} {path.name[:48]}")
    finally:
        if provider is not None:
            provider.close()
    print(f"\n{flagged} of {len(paths)} sessions show a loop alarm. Inspect one with: unwedge replay <path>")
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    from unwedge.replay import format_timeline, replay_file

    provider = make_provider(args.provider or "none", model=args.model)
    try:
        result = replay_file(args.path, provider, harness=args.harness)
    finally:
        if provider is not None:
            provider.close()
    for line in format_timeline(result):
        print(line)
    first = result.first_intervention
    print(f"\n{len(result.turns)} turns; first alarm: {f'turn {first}' if first else 'none'}; "
          f"{result.turns_after_first_intervention} turns ran after it.")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    from unwedge.report import format_report, load_ledger, summarize

    settings = _settings()
    for line in format_report(summarize(load_ledger(settings.home, days=args.days))):
        print(line)
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from unwedge.providers import LAYA_PROFILE
    from unwedge.providers.laya_local import LayaInProcess
    from unwedge.server import serve

    api_key = os.environ.get(args.api_key_env) if args.api_key_env else None
    if args.host not in ("127.0.0.1", "localhost", "::1") and not api_key:
        print("Refusing to listen on a non-loopback address without an API key (--api-key-env).", file=sys.stderr)
        return 2
    print(f"loading Laya checkpoint '{args.model}' (backend={args.backend}); the first run downloads it...",
          flush=True)
    provider = LayaInProcess(profile=LAYA_PROFILE, checkpoint=args.model, backend=args.backend, device=args.device)
    serve(provider, host=args.host, port=args.port, api_key=api_key)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    settings = _settings()
    print(f"unwedge {__version__} on Python {sys.version.split()[0]}")
    print(f"  unwedge on PATH : {shutil.which('unwedge') or 'NO (hooks call `unwedge`; install with uv/pipx/pip)'}")
    print(f"  mode            : {settings.mode}")
    print(f"  provider        : {args.provider or settings.provider}")
    print(f"  endpoint/model  : {settings.url or '(default)'} / {settings.model or '(default)'}")
    print(f"  api key         : {'set' if settings.api_key else 'not set'}")
    print(f"  state directory : {settings.home}")
    try:
        provider = _provider_from_args(args, settings)
    except ValueError as exc:
        print(f"  provider check  : FAILED ({exc})")
        return 1
    if provider is None:
        print("  provider check  : skipped (code-only tier; no model is called)")
        return 0
    started = time.perf_counter()
    try:
        result = provider.ask("The cat sat on the mat.", DOCTOR_QUESTIONS, timeout=args.timeout)
        answer = result.answers["about_cats"]["noul"]
        print(f"  provider check  : OK in {(time.perf_counter() - started) * 1000:.0f} ms "
              f"(model {result.model}, P(about a cat) = {answer:.2f})")
        return 0
    except ProviderError as exc:
        print(f"  provider check  : FAILED ({type(exc).__name__}: {exc})")
        return 1
    finally:
        provider.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="unwedge", description="Circuit breaker for AI agent doom loops.")
    parser.add_argument("--version", action="version", version=f"unwedge {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    hook = sub.add_parser("hook", help="handle a Claude Code or Codex hook event (JSON on stdin)")
    hook.add_argument("harness", nargs="?", choices=("claude-code", "codex"), help="optional; auto-detected")
    hook.set_defaults(func=cmd_hook)

    scan = sub.add_parser("scan", help="replay your recent Claude Code / Codex sessions and flag loops")
    scan.add_argument("--limit", type=int, default=20)
    scan.add_argument("--provider", choices=PROVIDER_NAMES, default=None, help="default: none (free, local)")
    scan.add_argument("--model", default=None)
    scan.set_defaults(func=cmd_scan)

    replay = sub.add_parser("replay", help="show turn by turn what the guard would have done in one session")
    replay.add_argument("path")
    replay.add_argument("--harness", choices=("claude-code", "codex"), default=None)
    replay.add_argument("--provider", choices=PROVIDER_NAMES, default=None, help="default: none (free, local)")
    replay.add_argument("--model", default=None)
    replay.set_defaults(func=cmd_replay)

    report = sub.add_parser("report", help="summarize what the hooks recorded")
    report.add_argument("--days", type=float, default=7.0)
    report.set_defaults(func=cmd_report)

    serve = sub.add_parser("serve", help="serve a local Laya model over the System One protocol")
    serve.add_argument("--backend", choices=("auto", "mlx", "torch"), default="auto")
    serve.add_argument("--model", default="english", choices=("english", "multilingual", "typed-decisions"))
    serve.add_argument("--device", default=None)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--api-key-env", default=None, help="name of an env var holding the bearer key")
    serve.set_defaults(func=cmd_serve)

    doctor = sub.add_parser("doctor", help="check configuration and provider connectivity")
    doctor.add_argument("--provider", choices=PROVIDER_NAMES, default=None)
    doctor.add_argument("--model", default=None)
    doctor.add_argument("--timeout", type=float, default=30.0)
    doctor.set_defaults(func=cmd_doctor)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())

