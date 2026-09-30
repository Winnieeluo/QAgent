import os
import unittest
from unittest.mock import patch

from web.github_service import GithubTarget, allowed_hosts, parse_github_target


class GithubServiceTests(unittest.TestCase):
    def test_repository_and_pr_links(self):
        self.assertEqual(parse_github_target("octocat/Hello-World"),
                         GithubTarget("github.com", "octocat", "Hello-World"))
        self.assertEqual(parse_github_target("https://github.com/octocat/Hello-World/pull/42").number, 42)

    def test_rejects_unapproved_or_unsafe_urls(self):
        unsafe = ["http://github.com/a/b", "https://github.com.evil.test/a/b",
                  "https://user:secret@github.com/a/b", "https://github.com:444/a/b",
                  "https://github.com/a/b?token=secret", "file:///etc/passwd"]
        for value in unsafe:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_github_target(value)

    def test_enterprise_host_requires_explicit_allowlist(self):
        with patch.dict(os.environ, {"QAAGENT_GITHUB_HOSTS": "git.example.bank"}):
            self.assertIn("git.example.bank", allowed_hosts())
            target = parse_github_target("https://git.example.bank/team/project/pull/7")
            self.assertEqual(target.api_root, "https://git.example.bank/api/v3")
        with patch.dict(os.environ, {"QAAGENT_GITHUB_HOSTS": ""}):
            with self.assertRaises(ValueError):
                parse_github_target("https://git.example.bank/team/project")


if __name__ == "__main__":
    unittest.main()
