import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

INSTALLER_DIR = Path(__file__).resolve().parents[1] / "installer"
INSTALLER = INSTALLER_DIR / "SetupMCP AutoCAD.cmd"
EXCEL_INSTALLER = INSTALLER_DIR / "SetupMCP Excel.cmd"

VERSION = r"(\d{4}\.\d{2}\.\d{2}\.\d{2})"


def _versions(text):
    shown = set(re.findall(r"^(?:title|echo) %\w+% v" + VERSION, text, re.M))
    variable = re.findall(r"^\$script:InstallerVersion = '" + VERSION + "'", text, re.M)
    return shown, variable


def test_installer_versions_are_in_sync():
    text = INSTALLER.read_text(encoding="utf-8")
    shown, variable = _versions(text)
    assert len(shown) == 1 and variable == list(shown)
    assert "raw.githubusercontent.com/Moorlack/best-cad-mcp/master/installer/SetupMCP%20AutoCAD.cmd" in text
    assert '\r' not in INSTALLER.read_bytes().decode("utf-8")  # bytes are served as committed


def test_excel_installer_versions_are_in_sync():
    text = EXCEL_INSTALLER.read_text(encoding="utf-8")
    shown, variable = _versions(text)
    assert len(shown) == 1 and variable == list(shown)
    # This copy is only the hand-over release for installers that still check best-cad-mcp;
    # the Excel installer itself is maintained in the Moorlack/Excel-mcp-server fork.
    assert "raw.githubusercontent.com/Moorlack/Excel-mcp-server/main/installer/SetupMCP%20Excel.cmd" in text
    assert '\r' not in EXCEL_INSTALLER.read_bytes().decode("utf-8")


def _payload_parse_errors(path):
    script = (
        "$lines = Get-Content -LiteralPath $env:INSTALLER -Encoding UTF8;"
        "$m = [Array]::IndexOf($lines, '# POWERSHELL_PAYLOAD');"
        "if ($m -lt 0) { exit 200 };"
        "$code = $lines[($m + 1)..($lines.Length - 1)] -join [Environment]::NewLine;"
        "$errors = $null;"
        "[void][System.Management.Automation.Language.Parser]::ParseInput($code, [ref]$null, [ref]$errors);"
        "$errors | ForEach-Object { Write-Output $_.Message };"
        "exit $errors.Count"
    )
    return subprocess.run(["powershell.exe", "-NoProfile", "-Command", script],
                          env={**os.environ, "INSTALLER": str(path)},
                          capture_output=True, text=True, timeout=120)


@pytest.mark.skipif(sys.platform != "win32" or not shutil.which("powershell.exe"),
                    reason="Windows PowerShell is required")
@pytest.mark.parametrize("name", ["autocad", "excel"])
def test_installer_payload_parses_in_windows_powershell(name, tmp_path):
    text = (EXCEL_INSTALLER if name == "excel" else INSTALLER).read_text(encoding="utf-8")
    path = tmp_path / f"{name}.cmd"
    path.write_bytes(text.encode("utf-8"))
    result = _payload_parse_errors(path)
    assert result.returncode == 0, result.stdout + result.stderr
