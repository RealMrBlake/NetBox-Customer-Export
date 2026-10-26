"""Keeps the README compatibility table in sync with the PluginConfig version range."""
import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def plugin_versions():
    tree = ast.parse((ROOT / "netbox_customer_export" / "__init__.py").read_text())
    values = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ("min_version", "max_version"):
                    values[target.id] = node.value.value
    return values["min_version"], values["max_version"]


def readme_range(max_version):
    # "4.7.99" is documented as "4.7.x"
    major_minor, patch = max_version.rsplit(".", 1)
    return major_minor + ".x" if patch == "99" else max_version


class MetadataTest(unittest.TestCase):
    def test_readme_matches_plugin_config(self):
        min_version, max_version = plugin_versions()
        expected = f"`{min_version}` – `{readme_range(max_version)}`"
        readme = (ROOT / "README.md").read_text()
        self.assertIn(f"| **NetBox** | {expected} |", readme)
        self.assertRegex(readme, re.escape(f"- NetBox {expected}"))

    def test_package_ships_translations(self):
        pyproject = (ROOT / "pyproject.toml").read_text()
        self.assertIn("locale/*/LC_MESSAGES/*.mo", pyproject)
        self.assertTrue((ROOT / "netbox_customer_export" / "locale" / "de" / "LC_MESSAGES" / "django.mo").exists())


if __name__ == "__main__":
    unittest.main()
