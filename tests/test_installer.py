import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

INSTALLER = Path(__file__).resolve().parents[1] / "installer" / "SetupMCP AutoCAD.cmd"


def test_installer_versions_are_in_sync():
    text = INSTALLER.read_text(encoding="utf-8")
    versions = set(re.findall(r"AutoCAD MCP setup v(\d{4}\.\d{2}\.\d{2}\.\d{2})", text))
    variable = re.findall(r"^\$script:InstallerVersion = '(\d{4}\.\d{2}\.\d{2}\.\d{2})'", text, re.M)
    assert len(versions) == 1 and variable == list(versions)
    assert "raw.githubusercontent.com/Moorlack/best-cad-mcp/master/installer/SetupMCP%20AutoCAD.cmd" in text
    assert '\r' not in INSTALLER.read_bytes().decode("utf-8")  # bytes are served as committed


@pytest.mark.skipif(sys.platform != "win32" or not shutil.which("powershell.exe"),
                    reason="Windows PowerShell is required")
def test_installer_payload_parses_in_windows_powershell():
    script = (
        "$lines = Get-Content -LiteralPath $env:INSTALLER;"
        "$m = [Array]::IndexOf($lines, '# POWERSHELL_PAYLOAD');"
        "if ($m -lt 0) { exit 2 };"
        "$code = $lines[($m + 1)..($lines.Length - 1)] -join [Environment]::NewLine;"
        "$errors = $null;"
        "[void][System.Management.Automation.Language.Parser]::ParseInput($code, [ref]$null, [ref]$errors);"
        "exit $errors.Count"
    )
    result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", script],
                            env={**os.environ, "INSTALLER": str(INSTALLER)},
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
