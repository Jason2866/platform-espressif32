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

    def test_extra_flags_stripped_of_group_markers(self):
        # Verify that extra_flags has --start-group/--end-group stripped
        # since we rely on double-lib ordering instead
        source = ESPIDF_BUILDER.read_text(encoding="utf-8")
        self.assertIn('if f not in ("-Wl,--start-group", "-Wl,--end-group")', source, 
                      "extra_flags should strip group markers")

    def test_libs_duplicated_for_circular_dependencies(self):
        # Verify that LIBS is duplicated (libs + libs) to handle circular dependencies
        libs_values = []
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr == "Prepend":
                libs_values.extend(
                    keyword.value for keyword in node.keywords if keyword.arg == "LIBS"
                )

        self.assertEqual(len(libs_values), 1)
        # Check that LIBS is libs + libs (a BinOp with Add)
        self.assertIsInstance(libs_values[0], ast.BinOp)
        self.assertIsInstance(libs_values[0].op, ast.Add)
        # Both operands should be the same 'libs' name
        self.assertIsInstance(libs_values[0].left, ast.Name)
        self.assertIsInstance(libs_values[0].right, ast.Name)
        self.assertEqual(libs_values[0].left.id, "libs")
        self.assertEqual(libs_values[0].right.id, "libs")


if __name__ == "__main__":
    unittest.main()
