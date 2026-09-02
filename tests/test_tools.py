import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import create_tools, truncate_middle


class ToolTests(unittest.TestCase):
    def setUp(self):
        tests_directory = Path(__file__).resolve().parent
        self.temporary_directory = tempfile.TemporaryDirectory(dir=tests_directory)
        self.external_directory = tempfile.TemporaryDirectory(dir=tests_directory)
        self.workspace = self.temporary_directory.name
        self.tools = create_tools(self.workspace)

    def tearDown(self):
        self.temporary_directory.cleanup()
        self.external_directory.cleanup()

    def test_write_edit_and_paginated_read(self):
        write_result = self.tools["write_file"].execute(
            path="sample.txt",
            content="abcdef",
        )
        self.assertTrue(write_result["ok"])
        self.assertTrue(write_result["created"])

        edit_result = self.tools["edit_file"].execute(
            path="sample.txt",
            old_text="cd",
            new_text="XY",
        )
        self.assertTrue(edit_result["ok"])

        read_result = self.tools["read_file"].execute(
            path="sample.txt",
            offset=1,
            max_chars=3,
        )
        self.assertTrue(read_result["ok"])
        self.assertEqual(read_result["content"], "bXY")
        self.assertTrue(read_result["truncated"])
        self.assertEqual(read_result["next_offset"], 4)

    def test_edit_rejects_ambiguous_match_without_changing_file(self):
        path = Path(self.workspace, "sample.txt")
        path.write_text("same same", encoding="utf-8")

        result = self.tools["edit_file"].execute(
            path="sample.txt",
            old_text="same",
            new_text="changed",
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["type"], "ambiguous_match")
        self.assertEqual(path.read_text(encoding="utf-8"), "same same")

    def test_list_files_returns_structured_entries(self):
        Path(self.workspace, "a.txt").write_text("a", encoding="utf-8")
        Path(self.workspace, "folder").mkdir()

        result = self.tools["list_files"].execute()

        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 2)
        self.assertEqual(
            result["entries"],
            [
                {"name": "a.txt", "type": "file"},
                {"name": "folder", "type": "directory"},
            ],
        )

    def test_run_command_does_not_use_a_shell(self):
        result = self.tools["run_command"].execute(
            program=sys.executable,
            args=["--version"],
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["exit_code"], 0)
        self.assertFalse(result["timed_out"])

    def test_executable_outside_workspace_is_allowed_on_allowed_drive(self):
        executable = Path(self.external_directory.name, "sample.exe")
        executable.write_bytes(b"MZ")

        resolved = self.tools["run_command"]._resolve_program(str(executable))

        self.assertEqual(resolved, str(executable.resolve()))

    def test_explicit_executable_path_cannot_bypass_denied_drive(self):
        executable = Path(self.external_directory.name, "python.exe")
        executable.write_bytes(b"MZ")
        drive = os.path.splitdrive(str(executable))[0]
        tools = create_tools(self.workspace, denied_drives=[drive])

        with self.assertRaisesRegex(ValueError, "not allowed"):
            tools["run_command"]._resolve_program(str(executable))

    def test_trusted_path_executable_is_allowed_on_denied_drive(self):
        executable = Path(self.external_directory.name, "python.exe")
        executable.write_bytes(b"MZ")
        drive = os.path.splitdrive(str(executable))[0]
        tools = create_tools(self.workspace, denied_drives=[drive])

        with patch("tools.shutil.which", return_value=str(executable)):
            resolved = tools["run_command"]._resolve_program(str(executable))

        self.assertEqual(resolved, str(executable.resolve()))

    def test_shell_program_error_explains_direct_execution(self):
        result = self.tools["run_command"].execute(
            program="powershell",
            args=["-Command", "echo test"],
        )

        self.assertFalse(result["ok"])
        self.assertIn("Run the target program directly", result["error"]["message"])

    def test_shell_builtin_error_explains_it_is_not_executable(self):
        result = self.tools["run_command"].execute(
            program="echo",
            args=["test"],
        )

        self.assertFalse(result["ok"])
        self.assertIn("Shell built-in", result["error"]["message"])

    def test_trusted_executable_cannot_receive_denied_drive_argument(self):
        executable = Path(self.external_directory.name, "python.exe")
        executable.write_bytes(b"MZ")
        drive = os.path.splitdrive(str(executable))[0]
        tools = create_tools(self.workspace, denied_drives=[drive])

        with patch("tools.shutil.which", return_value=str(executable)):
            result = tools["run_command"].execute(
                program=str(executable),
                args=[f"{drive}\\private.txt"],
            )

        self.assertFalse(result["ok"])
        self.assertIn("Argument references denied drive", result["error"]["message"])

    def test_denied_drive_is_rejected(self):
        drive = os.path.splitdrive(self.workspace)[0]
        tools = create_tools(self.workspace, denied_drives=[drive])

        result = tools["read_file"].execute(path=self.workspace)

        self.assertFalse(result["ok"])
        self.assertIn("not allowed", result["error"]["message"])

    def test_middle_truncation_preserves_head_and_tail(self):
        result, truncated, original_chars = truncate_middle("0123456789", 8)

        self.assertTrue(truncated)
        self.assertEqual(original_chars, 10)
        self.assertEqual(len(result), 8)
        self.assertTrue(result.startswith("\n\n...["))


if __name__ == "__main__":
    unittest.main()
