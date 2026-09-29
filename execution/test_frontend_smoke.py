"""Run the packaging smoke under PowerShell 5 against synthetic Node servers."""
from __future__ import annotations

import os
from pathlib import Path
import socket
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "nt", "Windows packaging uses PowerShell 5")
class FrontendSmokeTests(unittest.TestCase):
    def run_smoke(self, server: str, *, old_deadline: bool = False):
        pin = (ROOT / "packaging/node-version.txt").read_text().strip()
        node = ROOT.parent / "tools/node-portable" / f"node-{pin}-win-x64/node.exe"
        self.assertTrue(node.is_file(), "Pinned portable Node must be available")
        with tempfile.TemporaryDirectory(prefix="mia-smoke-test-") as folder:
            temp = Path(folder)
            payload = temp / "payload"
            payload.mkdir()
            shutil.copyfile(node, payload / "node.exe")
            (payload / "server.js").write_text(server, encoding="utf-8")
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            source = (ROOT / "packaging/build_frontend.ps1").read_text(encoding="utf-8-sig")
            smoke = source[source.index("if ($SkipSmokeTest)"):source.index('Write-Host "Tamaño final del ensamblado:')]
            if old_deadline:
                smoke = smoke.replace("AddSeconds(180)", "AddSeconds(20)")
            prefix = ("$ErrorActionPreference='Stop'\n"
                      f"$DistDir='{payload}'\n$Port={port}\n$SkipSmokeTest=$false\n"
                      "$env:HOSTNAME='synthetic-host-before'\n$env:PORT='synthetic-port-before'\n"
                      "function Write-Step($msg) { Write-Host $msg }\n$failure=$null\ntry {\n")
            suffix = ("\n} catch { $failure=$_ }\n"
                      "if ($env:HOSTNAME -ne 'synthetic-host-before' -or $env:PORT -ne 'synthetic-port-before') "
                      "{ throw 'ENVIRONMENT_NOT_RESTORED' }\n"
                      "Write-Host 'ENVIRONMENT_RESTORED'\nif ($failure) { throw $failure }\n")
            script = temp / "smoke.ps1"
            script.write_text(prefix + smoke + suffix, encoding="utf-8-sig")
            env = dict(os.environ, TEMP=str(temp), TMP=str(temp))
            started = time.monotonic()
            result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                                    cwd=ROOT, env=env, capture_output=True, timeout=200)
            elapsed = time.monotonic() - started
            output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
            self.assertIn("ENVIRONMENT_RESTORED", output)
            with socket.socket() as probe:
                probe.settimeout(1)
                self.assertNotEqual(probe.connect_ex(("127.0.0.1", port)), 0, "Own Node must be stopped")
            logs = list(temp.glob("mia-frontend-smoke-*.log"))
            self.assertEqual(len(logs), 2, "Both runtime logs must remain outside payload")
            self.assertEqual(list(payload.glob("*.log")), [])
            log_text = "\n".join(p.read_text(errors="replace") for p in logs)
            return result.returncode, elapsed, output, log_text

    def test_delayed_readiness_passes_and_old_twenty_second_deadline_fails(self):
        server = """
const http=require('http');const started=Date.now();
http.createServer((req,res)=>{res.setHeader('X-Frame-Options','DENY');
res.setHeader('X-Content-Type-Options','nosniff');
res.statusCode=Date.now()-started<24000?503:200;res.end('SYNTHETIC_BODY_SENTINEL');
}).listen(Number(process.env.PORT),'127.0.0.1');
"""
        code, elapsed, output, _ = self.run_smoke(server)
        self.assertEqual(code, 0, output)
        self.assertGreater(elapsed, 20)
        self.assertLess(elapsed, 180)
        self.assertIn("PRUEBA DE HUMO: PASS", output)
        code, _, output, _ = self.run_smoke(server, old_deadline=True)
        self.assertNotEqual(code, 0)
        self.assertIn("HTTP=503", output)
        self.assertIn("status=ProtocolError", output)
        self.assertNotIn("SYNTHETIC_BODY_SENTINEL", output)

    def test_early_exit_fails_fast_and_preserves_runtime_logs(self):
        code, elapsed, output, logs = self.run_smoke(
            "console.log('synthetic stdout');console.error('synthetic stderr');process.exit(7);")
        self.assertNotEqual(code, 0)
        self.assertLess(elapsed, 15)
        self.assertIn("exit code 7", output)
        self.assertIn("synthetic stdout", logs)
        self.assertIn("synthetic stderr", logs)
        self.assertNotIn("PRUEBA DE HUMO: PASS", output)

    def test_wrong_headers_fail_after_owner_is_checked(self):
        code, _, output, _ = self.run_smoke("""
require('http').createServer((req,res)=>{res.end('synthetic');})
.listen(Number(process.env.PORT),'127.0.0.1');
""")
        self.assertNotEqual(code, 0)
        self.assertIn("PID", output)
        self.assertIn("cabeceras de seguridad", output)
        self.assertNotIn("PRUEBA DE HUMO: PASS", output)


if __name__ == "__main__":
    unittest.main()
