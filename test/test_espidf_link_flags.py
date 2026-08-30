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

    def test_precompiled_archives_are_grouped_in_linkflags(self):
        # Verify that precompiled archives are wrapped in --start-group/--end-group
        # in LINKFLAGS rather than using _LIBFLAGS replacement
        source = ESPIDF_BUILDER.read_text(encoding="utf-8")
        self.assertIn("precompiled_libs = link_args.get", source, "precompiled_libs should be extracted from link_args")
        self.assertIn('link_args["LINKFLAGS"]', source, "link_args LINKFLAGS should be set")
        self.assertIn("--start-group", source, "start-group flag should be present")
        self.assertIn("--end-group", source, "end-group flag should be present")

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
