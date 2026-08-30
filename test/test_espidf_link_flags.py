#!/usr/bin/env python3
"""Regression tests for the ESP-IDF linker configuration."""

import ast
from pathlib import Path
import unittest


ESPIDF_BUILDER = (
    Path(__file__).resolve().parents[1] / "builder" / "frameworks" / "espidf.py"
)


class TestEspIdfLinkFlags(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = ast.parse(ESPIDF_BUILDER.read_text(encoding="utf-8"))

    def test_libflags_wrapped_with_group_markers(self):
        # Verify that _LIBFLAGS is wrapped with --start-group/--end-group
        source = ESPIDF_BUILDER.read_text(encoding="utf-8")
        self.assertIn('env.Replace(_LIBFLAGS="-Wl,--start-group', source, "_LIBFLAGS should be wrapped with start-group")
        self.assertIn("-Wl,--end-group", source, "end-group flag should be present")

    def test_extra_flags_stripped_of_group_markers(self):
        # Verify that extra_flags has --start-group/--end-group stripped to avoid double-wrapping
        source = ESPIDF_BUILDER.read_text(encoding="utf-8")
        self.assertIn('if f not in ("-Wl,--start-group", "-Wl,--end-group")', source, 
                      "extra_flags should strip group markers to avoid double-wrapping")

    def test_libs_not_duplicated(self):
        # Verify that LIBS is not duplicated (no libs + libs)
        libs_values = []
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr == "Prepend":
                libs_values.extend(
                    keyword.value for keyword in node.keywords if keyword.arg == "LIBS"
                )

        self.assertEqual(len(libs_values), 1)
        self.assertIsInstance(libs_values[0], ast.Name)
        self.assertEqual(libs_values[0].id, "libs")


if __name__ == "__main__":
    unittest.main()
