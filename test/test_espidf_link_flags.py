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

        # The _LIBFLAGS replacement should exist (inside version check)
        self.assertEqual(len(libflags_values), 1)
        libflags = ast.unparse(libflags_values[0])
        self.assertIn("-Wl,--start-group", libflags)
        self.assertIn("_orig_libflags", libflags)
        self.assertIn("-Wl,--end-group", libflags)

        # LIBS should not be duplicated
        self.assertEqual(len(libs_values), 1)
        self.assertIsInstance(libs_values[0], ast.Name)
        self.assertEqual(libs_values[0].id, "libs")

    def test_libflags_replacement_has_version_check(self):
        # Verify that the _LIBFLAGS replacement is guarded by a version check
        for node in ast.walk(self.tree):
            if isinstance(node, ast.If):
                # Check if the if statement contains a version comparison
                test_str = ast.unparse(node.test)
                if "framework_version_list" in test_str and "[6, 0]" in test_str:
                    # Check if this if contains the _LIBFLAGS replacement
                    for child in ast.walk(node):
                        if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                            if child.func.attr == "Replace":
                                for keyword in child.keywords:
                                    if keyword.arg == "_LIBFLAGS":
                                        return  # Found version-guarded replacement
        self.fail("_LIBFLAGS replacement should be guarded by a version check for IDF 6.x")


if __name__ == "__main__":
    unittest.main()
