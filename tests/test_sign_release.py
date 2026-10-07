"""Offline signing refusal checks; no certificates, registry writes or real installers."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'sign-release.ps1'
POWERSHELL = shutil.which('powershell.exe')


@unittest.skipUnless(POWERSHELL, 'Windows PowerShell is required')
class SigningRefusalTests(unittest.TestCase):
    def run_script(self, *arguments):
        return subprocess.run([POWERSHELL, '-NoProfile', '-NonInteractive', '-File', str(SCRIPT),
                               *map(str, arguments)], capture_output=True, text=True, timeout=30)

    def test_unknown_identity_refuses_without_touching_input_or_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'synthetic.exe'
            target = Path(directory) / 'signed.exe'
            source.write_bytes(b'synthetic executable placeholder')
            result = self.run_script('-InputFile', source, '-OutputFile', target,
                                     '-CertificateThumbprint', '0' * 40)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('No matching certificate', result.stderr)
            self.assertEqual(source.read_bytes(), b'synthetic executable placeholder')
            self.assertFalse(target.exists())
            self.assertEqual(sorted(p.name for p in Path(directory).iterdir()), ['synthetic.exe'])

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'synthetic.exe'
            target = Path(directory) / 'signed.exe'
            source.write_bytes(b'source bytes')
            target.write_bytes(b'existing output bytes')
            result = self.run_script('-InputFile', source, '-OutputFile', target,
                                     '-CertificateThumbprint', '0' * 40)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Output already exists', result.stderr)
            self.assertEqual(source.read_bytes(), b'source bytes')
            self.assertEqual(target.read_bytes(), b'existing output bytes')

    def test_timestamp_requires_explicit_network_authority(self):
        result = self.run_script('-InputFile', 'unused.exe', '-OutputFile', 'unused-signed.exe',
                                 '-CertificateThumbprint', '0' * 40,
                                 '-TimestampServer', 'https://timestamp.example.invalid')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Timestamp server requires -AllowTimestampNetwork', result.stderr)

    def test_preflight_requires_real_certificate(self):
        result = self.run_script('-Preflight', '-CertificateThumbprint', '0' * 40)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('No matching certificate', result.stderr)

    def test_timestamp_cannot_use_file_or_credential_url(self):
        for url in ('file:///C:/timestamp', 'https://user:secret@example.invalid'):
            result = self.run_script('-InputFile', 'unused.exe', '-OutputFile', 'unused-signed.exe',
                                     '-CertificateThumbprint', '0' * 40,
                                     '-TimestampServer', url, '-AllowTimestampNetwork')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('TimestampServer must be an approved HTTP/HTTPS URL', result.stderr)

    def test_malformed_thumbprint_is_refused(self):
        result = self.run_script('-Preflight', '-CertificateThumbprint', 'not-an-identity')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('exact 40-character certificate thumbprint', result.stderr)

    def test_same_path_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'synthetic.exe'
            source.write_bytes(b'source bytes')
            result = self.run_script('-InputFile', source, '-OutputFile', source,
                                     '-CertificateThumbprint', '0' * 40)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('different from the input', result.stderr)
            self.assertEqual(source.read_bytes(), b'source bytes')

    def test_unsigned_file_cannot_pass_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'synthetic.exe'
            source.write_bytes(b'synthetic executable placeholder')
            result = self.run_script('-VerifyOnly', '-InputFile', source,
                                     '-CertificateThumbprint', '0' * 40)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Signature verification failed', result.stderr)
            self.assertEqual(source.read_bytes(), b'synthetic executable placeholder')
