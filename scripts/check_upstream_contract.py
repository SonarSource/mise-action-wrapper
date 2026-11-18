#!/usr/bin/env python3
"""Check action.yaml against the pinned step-security/mise-action and upstream-inputs.yaml.

Usage: check_upstream_contract.py [UPSTREAM_ACTION_YML]

Without an argument, the upstream action.yml is downloaded at the commit pinned in
action.yaml. Requires yq (mikefarah) on PATH.
"""

import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UPSTREAM = "step-security/mise-action"


def load_yaml(text):
    out = subprocess.run(["yq", "-o=json", "."], input=text, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def norm(value):
    return "" if value is None else str(value).lower() if isinstance(value, bool) else str(value)


def mise_step(wrapper):
    steps = [s for s in wrapper["runs"]["steps"] if str(s.get("uses", "")).startswith(f"{UPSTREAM}@")]
    if len(steps) != 1:
        raise SystemExit(f"expected exactly one {UPSTREAM} step in action.yaml, found {len(steps)}")
    return steps[0]


def check(wrapper, upstream, contract, runs_text):
    errors = []
    up_inputs = upstream.get("inputs") or {}
    inputs = wrapper.get("inputs") or {}
    step_with = mise_step(wrapper).get("with") or {}

    forwarded = set(contract.get("forwarded") or [])
    handled = set(contract.get("handled") or {})
    unsupported = set(contract.get("unsupported") or {})
    own = set(contract.get("wrapper") or [])
    renamed = set(contract.get("renamed") or {})
    overrides = set(contract.get("default_overrides") or {})

    groups = {"forwarded": forwarded, "handled": handled, "unsupported": unsupported}
    seen = {}
    for group, names in groups.items():
        for name in names:
            if name in seen:
                errors.append(f"{name} is listed in both {seen[name]} and {group}")
            seen[name] = group
    for name in sorted(set(up_inputs) - set(seen)):
        errors.append(f"upstream input {name} is not classified in upstream-inputs.yaml")
    for name in sorted(set(seen) - set(up_inputs)):
        errors.append(f"{name} ({seen[name]}) is no longer an upstream input")
    for name in sorted((own | renamed) & set(up_inputs)):
        errors.append(f"{name} is listed as wrapper-only or renamed but is an upstream input")

    expected = forwarded | handled | unsupported | own | renamed
    for name in sorted(expected - set(inputs)):
        errors.append(f"{name} is missing from action.yaml inputs")
    for name in sorted(set(inputs) - expected):
        errors.append(f"action.yaml input {name} is not listed in upstream-inputs.yaml")

    for name in sorted(set(step_with) - set(up_inputs)):
        errors.append(f"{name} is passed to {UPSTREAM} but is not one of its inputs")
    for name in sorted(forwarded):
        if norm(step_with.get(name)) != f"${{{{ inputs.{name} }}}}":
            errors.append(f"forwarded input {name} must be passed as ${{{{ inputs.{name} }}}}")
    for name in sorted(handled & set(step_with)):
        if name == "cache" and norm(step_with[name]) == "false":
            continue
        errors.append(f"handled input {name} must not be passed through to {UPSTREAM}")
    if norm(step_with.get("cache")) != "false":
        errors.append(f"{UPSTREAM} must be called with cache: false")

    for name in sorted(forwarded & set(up_inputs) & set(inputs)):
        ours, theirs = norm(inputs[name].get("default")), norm(up_inputs[name].get("default"))
        if name in overrides:
            if ours == theirs:
                errors.append(f"{name} is in default_overrides but its default matches upstream ({theirs!r})")
        elif ours != theirs:
            errors.append(f"default of {name} is {ours!r}, upstream is {theirs!r}; align or add it to default_overrides")
    for name in sorted(overrides - forwarded):
        errors.append(f"default_overrides lists {name}, which is not forwarded")

    for name in sorted((unsupported | renamed) & set(inputs)):
        if "default" in inputs[name]:
            errors.append(f"{name} must have no default, so the check step only fails when a caller sets it")
    for name in sorted(set(inputs)):
        if not re.search(rf"inputs\.{re.escape(name)}\b(?!-)", runs_text):
            errors.append(f"input {name} is declared but never used")

    outputs = wrapper.get("outputs") or {}
    for name in sorted(set(upstream.get("outputs") or {}) - set(outputs)):
        errors.append(f"upstream output {name} is not exposed by the wrapper")
    return errors


def main():
    action_text = (ROOT / "action.yaml").read_text()
    wrapper = load_yaml(action_text)
    contract = load_yaml((ROOT / "upstream-inputs.yaml").read_text())
    ref = str(mise_step(wrapper)["uses"]).split("@", 1)[1]
    if len(sys.argv) > 1:
        upstream_text = Path(sys.argv[1]).read_text()
    else:
        url = f"https://raw.githubusercontent.com/{UPSTREAM}/{ref}/action.yml"
        with urllib.request.urlopen(url, timeout=30) as response:
            upstream_text = response.read().decode()
    runs_text = action_text.split("\nruns:", 1)[1]
    errors = check(wrapper, load_yaml(upstream_text), contract, runs_text)
    for error in errors:
        print(f"::error file=action.yaml::{error}")
    if errors:
        return 1
    print(f"action.yaml matches {UPSTREAM}@{ref} and upstream-inputs.yaml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
