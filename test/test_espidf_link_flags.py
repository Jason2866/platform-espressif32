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

    def test_static_libraries_are_grouped_without_duplication(self):
        libflags_values = []
        libs_values = []

        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr == "Replace":
                libflags_values.extend(
                    keyword.value
                    for keyword in node.keywords
                    if keyword.arg == "_LIBFLAGS"
                )
            elif node.func.attr == "Prepend":
                libs_values.extend(
                    keyword.value for keyword in node.keywords if keyword.arg == "LIBS"
                )

        self.assertEqual(len(libflags_values), 1)
        libflags = ast.unparse(libflags_values[0])
        self.assertIn("-Wl,--start-group", libflags)
        self.assertIn("_orig_libflags", libflags)
        self.assertIn("-Wl,--end-group", libflags)

        self.assertEqual(len(libs_values), 1)
        self.assertIsInstance(libs_values[0], ast.Name)
        self.assertEqual(libs_values[0].id, "libs")


if __name__ == "__main__":
    unittest.main()
