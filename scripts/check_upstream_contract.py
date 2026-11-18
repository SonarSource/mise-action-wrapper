#!/usr/bin/env python3
"""Check action.yaml against the pinned step-security/mise-action and upstream-inputs.yaml.

Downloads the upstream action.yml at the commit pinned in action.yaml. Requires yq (mikefarah) on PATH.
"""

import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UPSTREAM = "step-security/mise-action"
GROUPS = ("forwarded", "handled", "unsupported")


def load_yaml(text):
    out = subprocess.run(["yq", "-o=json", "."], input=text, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def norm(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def mise_step(wrapper):
    steps = [s for s in wrapper["runs"]["steps"] if str(s.get("uses", "")).startswith(f"{UPSTREAM}@")]
    if len(steps) != 1:
        raise SystemExit(f"expected exactly one {UPSTREAM} step in action.yaml, found {len(steps)}")
    return steps[0]


def names(contract, key):
    return set(contract.get(key) or [])


def check_classification(up_inputs, contract):
    errors, seen = [], {}
    for group in GROUPS:
        for name in names(contract, group):
            if name in seen:
                errors.append(f"{name} is listed in both {seen[name]} and {group}")
            seen[name] = group
    errors += [f"upstream input {n} is not classified in upstream-inputs.yaml" for n in sorted(set(up_inputs) - set(seen))]
    errors += [f"{n} ({seen[n]}) is no longer an upstream input" for n in sorted(set(seen) - set(up_inputs))]
    local = names(contract, "wrapper") | names(contract, "renamed")
    errors += [f"{n} is listed as wrapper-only or renamed but is an upstream input" for n in sorted(local & set(up_inputs))]
    return errors


def check_declared(inputs, contract):
    expected = set().union(*(names(contract, k) for k in (*GROUPS, "wrapper", "renamed")))
    errors = [f"{n} is missing from action.yaml inputs" for n in sorted(expected - set(inputs))]
    errors += [f"action.yaml input {n} is not listed in upstream-inputs.yaml" for n in sorted(set(inputs) - expected)]
    return errors


def check_passthrough(step_with, up_inputs, contract):
    errors = [f"{n} is passed to {UPSTREAM} but is not one of its inputs" for n in sorted(set(step_with) - set(up_inputs))]
    for name in sorted(names(contract, "forwarded")):
        if norm(step_with.get(name)) != f"${{{{ inputs.{name} }}}}":
            errors.append(f"forwarded input {name} must be passed as ${{{{ inputs.{name} }}}}")
    errors += [f"handled input {n} must not be passed through to {UPSTREAM}"
               for n in sorted(names(contract, "handled") & set(step_with) - {"cache"})]
    if norm(step_with.get("cache")) != "false":
        errors.append(f"{UPSTREAM} must be called with cache: false")
    return errors


def check_defaults(inputs, up_inputs, contract):
    errors = []
    forwarded, overrides = names(contract, "forwarded"), names(contract, "default_overrides")
    for name in sorted(forwarded & set(up_inputs) & set(inputs)):
        ours, theirs = norm(inputs[name].get("default")), norm(up_inputs[name].get("default"))
        if name in overrides and ours == theirs:
            errors.append(f"{name} is in default_overrides but its default matches upstream ({theirs!r})")
        elif name not in overrides and ours != theirs:
            errors.append(f"default of {name} is {ours!r}, upstream is {theirs!r}; align or add it to default_overrides")
    errors += [f"default_overrides lists {n}, which is not forwarded" for n in sorted(overrides - forwarded)]
    rejected = names(contract, "unsupported") | names(contract, "renamed")
    errors += [f"{n} must have no default, so the check step only fails when a caller sets it"
               for n in sorted(rejected & set(inputs)) if "default" in inputs[n]]
    return errors


def check_usage(inputs, outputs, up_outputs, runs_text):
    errors = [f"input {n} is declared but never used" for n in sorted(inputs)
              if not re.search(rf"inputs\.{re.escape(n)}\b(?!-)", runs_text)]
    errors += [f"upstream output {n} is not exposed by the wrapper" for n in sorted(set(up_outputs) - set(outputs))]
    return errors


def check(wrapper, upstream, contract, runs_text):
    up_inputs = upstream.get("inputs") or {}
    inputs = wrapper.get("inputs") or {}
    step_with = mise_step(wrapper).get("with") or {}
    return (check_classification(up_inputs, contract)
            + check_declared(inputs, contract)
            + check_passthrough(step_with, up_inputs, contract)
            + check_defaults(inputs, up_inputs, contract)
            + check_usage(inputs, wrapper.get("outputs") or {}, upstream.get("outputs") or {}, runs_text))


def main():
    action_text = (ROOT / "action.yaml").read_text()
    wrapper = load_yaml(action_text)
    contract = load_yaml((ROOT / "upstream-inputs.yaml").read_text())
    ref = str(mise_step(wrapper)["uses"]).split("@", 1)[1]
    url = f"https://raw.githubusercontent.com/{UPSTREAM}/{ref}/action.yml"
    with urllib.request.urlopen(url, timeout=30) as response:
        upstream = load_yaml(response.read().decode())
    errors = check(wrapper, upstream, contract, action_text.split("\nruns:", 1)[1])
    for error in errors:
        print(f"::error file=action.yaml::{error}")
    if errors:
        return 1
    print(f"action.yaml matches {UPSTREAM}@{ref} and upstream-inputs.yaml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
