#!/usr/bin/env python3
import copy
import unittest

from check_upstream_contract import check

UPSTREAM = {
    "inputs": {
        "version": {},
        "install_args": {},
        "persist_github_token": {"default": "false"},
        "cache": {"default": "true"},
        "mise_dir": {},
    },
    "outputs": {"versions": {}},
}

CONTRACT = {
    "forwarded": ["version", "install_args", "persist_github_token"],
    "default_overrides": {"version": "pinned", "persist_github_token": "kept"},
    "handled": {"cache": "S3"},
    "unsupported": {"mise_dir": "cache path"},
    "wrapper": ["vault_url"],
    "renamed": {"mise-version": "version"},
}

WRAPPER = {
    "inputs": {
        "version": {"default": "2026.8.15"},
        "install_args": {},
        "persist_github_token": {"default": "true"},
        "cache": {"default": "true"},
        "mise_dir": {},
        "vault_url": {"default": "https://vault"},
        "mise-version": {},
    },
    "outputs": {"versions": {}},
    "runs": {
        "steps": [
            {
                "uses": "step-security/mise-action@abc",
                "with": {
                    "cache": False,
                    "version": "${{ inputs.version }}",
                    "install_args": "${{ inputs.install_args }}",
                    "persist_github_token": "${{ inputs.persist_github_token }}",
                },
            }
        ]
    },
}

RUNS = " ".join(f"${{{{ inputs.{n} }}}}" for n in WRAPPER["inputs"])


class CheckTest(unittest.TestCase):
    def errors(self, wrapper=WRAPPER, upstream=UPSTREAM, contract=CONTRACT, runs=RUNS):
        return check(wrapper, upstream, contract, runs)

    def assertError(self, fragment, **kwargs):
        errors = self.errors(**kwargs)
        self.assertTrue(any(fragment in e for e in errors), errors)

    def test_aligned_wrapper_passes(self):
        self.assertEqual(self.errors(), [])

    def test_new_upstream_input_must_be_classified(self):
        upstream = copy.deepcopy(UPSTREAM)
        upstream["inputs"]["monorepo"] = {}
        self.assertError("monorepo is not classified", upstream=upstream)

    def test_removed_upstream_input_is_reported(self):
        upstream = copy.deepcopy(UPSTREAM)
        del upstream["inputs"]["install_args"]
        self.assertError("install_args (forwarded) is no longer an upstream input", upstream=upstream)
        self.assertError("install_args is passed to", upstream=upstream)

    def test_upstream_default_change_is_reported(self):
        upstream = copy.deepcopy(UPSTREAM)
        upstream["inputs"]["install_args"]["default"] = "--yes"
        self.assertError("default of install_args", upstream=upstream)

    def test_override_matching_upstream_is_stale(self):
        upstream = copy.deepcopy(UPSTREAM)
        upstream["inputs"]["persist_github_token"]["default"] = "true"
        self.assertError("persist_github_token is in default_overrides", upstream=upstream)

    def test_forwarded_input_must_reach_upstream(self):
        wrapper = copy.deepcopy(WRAPPER)
        del wrapper["runs"]["steps"][0]["with"]["install_args"]
        self.assertError("forwarded input install_args must be passed", wrapper=wrapper)

    def test_upstream_cache_must_stay_disabled(self):
        wrapper = copy.deepcopy(WRAPPER)
        wrapper["runs"]["steps"][0]["with"]["cache"] = "${{ inputs.cache }}"
        self.assertError("must be called with cache: false", wrapper=wrapper)

    def test_undeclared_wrapper_input_is_reported(self):
        wrapper = copy.deepcopy(WRAPPER)
        wrapper["inputs"]["extra"] = {}
        self.assertError("input extra is not listed", wrapper=wrapper)

    def test_rejected_input_must_have_no_default(self):
        wrapper = copy.deepcopy(WRAPPER)
        wrapper["inputs"]["mise-version"] = {"default": "2026.8.15"}
        self.assertError("mise-version must have no default", wrapper=wrapper)

    def test_unused_input_is_reported(self):
        runs = RUNS.replace("${{ inputs.mise-version }}", "")
        self.assertError("input mise-version is declared but never used", runs=runs)

    def test_prefix_of_another_input_does_not_count_as_used(self):
        runs = RUNS.replace("${{ inputs.version }}", "") + " ${{ inputs.version-extra }}"
        self.assertError("input version is declared but never used", runs=runs)

    def test_upstream_output_must_be_exposed(self):
        wrapper = copy.deepcopy(WRAPPER)
        wrapper["outputs"] = {}
        self.assertError("upstream output versions", wrapper=wrapper)


if __name__ == "__main__":
    unittest.main()
