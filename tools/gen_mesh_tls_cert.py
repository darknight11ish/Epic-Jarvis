#!/usr/bin/env python3
"""gen_mesh_tls_cert.py - a local Root CA, a mesh-served TLS certificate, and the
one Apple profile that makes both trusted, in one command.

    python3 tools/gen_mesh_tls_cert.py                    # ~/.openjarvis/tls, host = this PC's name
    python3 tools/gen_mesh_tls_cert.py --host my-pc.nord
    python3 tools/gen_mesh_tls_cert.py --out C:\\temp\\tls --force

WHY THIS EXISTS

The Universal Jarvis Web App is served from this PC over a private mesh
(NordVPN Meshnet's *.nord name, Tailscale's *.ts.net name, or a 100.x.y.z
address). Browsers treat those as ordinary "not secure" origins, so
`window.isSecureContext` is false over plain `http://` and Safari/Chrome switch
off the things the owner asked for: microphone capture (`getUserMedia`), screen
wake lock (`navigator.wakeLock`) and WebAuthn (Face ID / Touch ID / Windows
Hello). Served over `https://` with a certificate the device trusts, it is true
and all three unlock. (The desktop app and the local `http://127.0.0.1` are
already secure contexts.)

This is the mkcert-shaped answer for the Meshnet/`.nord` case: one local Root
CA, one server certificate whose Subject Alternative Names cover the mesh
addresses this PC actually has, and an Apple `.mobileconfig` profile that
installs the root on an iPad/iPhone in a tap or two (Settings -> Profile
Downloaded -> Install -> Certificate Trust Settings -> Full Trust ON). The two
read-only download routes a later slice adds on top are:

    GET /api/tls/jarvis-ca.mobileconfig     Content-Type: application/x-apple-aspen-config
    GET /api/tls/root-ca.crt                Content-Type: application/x-x509-ca-cert

(The Tailscale path needs none of this: `tailscale cert <pc>.<tailnet>.ts.net`
issues a publicly trusted certificate. This tool is for the machines that do
not have that, and it detects an existing `tailscale cert` pair rather than
overwriting it.)

WHAT IT WRITES (all under --out, default ~/.openjarvis/tls)

    jarvis-mesh-root-ca.crt   the 10-year local Root CA, CN=Jarvis Local Mesh Root CA
    jarvis-mesh-root-ca.key   its private key (0600 on POSIX; ACL-hardened on Windows)
    jarvis-mesh-server.crt    the <= 397-day leaf for --host (Apple's <825-day
                              limit for a private CA and Safari/Chrome's <=398-day
                              limit are both satisfied; 397 is chosen deliberately)
    jarvis-mesh-server.key    the leaf's private key
    jarvis-ca.mobileconfig    Apple profile: the Root CA DER, PayloadType
                              com.apple.security.root

The leaf's SANs are: --host (default: this PC's hostname), `localhost`,
`127.0.0.1`, `::1`, and every `100.64.0.0/10` address found on this machine
(that block is what Tailscale and NordVPN Meshnet hand out; detection is from
the local network configuration only, stdlib only, and fails soft - an empty
list is fine, the explicit ones above are always there).

SAFETY, SAID OUT LOUD

  * It never overwrites anything without `--force`. A second run refuses and
    lists the files already there.
  * A certificate/key pair in the folder that this tool did not write (for
    example from `tailscale cert`) is reported and left untouched: refuse by
    default, and `--force` writes beside it, never over it.
  * It prints the paths it wrote and the names the certificate covers. It never
    prints key material - no PEM body, no private key, nothing secret.
  * Existing private keys are not read except to prove they load; the only
    thing printed about them is their path.

EXIT CODES

    0  wrote the CA, the leaf and the profile
    1  another error (unwritable folder, unexpected crypto failure)
    2  refused: files already exist, or a foreign/tailscale certificate pair is
       in the folder, and --force was not given - nothing was written
    3  the `cryptography` package is missing

`cryptography` is already pinned in `backend/requirements.lock` (50.0.1 at the
time of writing) and installed by the project's own set-up; this tool adds NO
dependency. Re-run the project's install/update steps if it is missing.
"""
from __future__ import annotations

import argparse
import base64
import datetime
import ipaddress
import os
import re
import socket
import subprocess
import sys
import textwrap
import uuid
from pathlib import Path

#: The names this tool owns. A file with any other certificate-looking suffix
#: in the output folder is treated as somebody else's and reported, not touched.
ROOT_CRT = "jarvis-mesh-root-ca.crt"
ROOT_KEY = "jarvis-mesh-root-ca.key"
SERVER_CRT = "jarvis-mesh-server.crt"
SERVER_KEY = "jarvis-mesh-server.key"
MOBILECONFIG = "jarvis-ca.mobileconfig"
OWN_NAMES = (ROOT_CRT, ROOT_KEY, SERVER_CRT, SERVER_KEY, MOBILECONFIG)

ROOT_CN = "Jarvis Local Mesh Root CA"
ROOT_ORG = "Jarvis (local, non-commercial)"
ROOT_DAYS = 3650
#: 397, not 398: Apple's limit for a leaf under a private CA is 825 days and
#: Safari/Chrome's is 398, so 397 satisfies both with a day to spare.
LEAF_DAYS = 397
RSA_BITS = 2048

#: Tailscale and NordVPN Meshnet both hand out addresses from RFC 6598's
#: 100.64.0.0/10 block ("carrier-grade NAT"). The same constant is in
#: backend/jarvis_devices.py and backend/jarvis_local_http.py; this tool is a
#: standalone script, so it does not import either.
MESH_NET = ipaddress.ip_network("100.64.0.0/10")

CERT_SUFFIXES = {".crt", ".pem", ".cer", ".key"}
IPV4 = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])")
#: A DNS name a browser will accept in a certificate: dot-separated labels of
#: letters/digits/hyphens, no leading or trailing hyphen, <= 253 characters.
#: `--host` may also be an IP address, which is checked first.
HOSTNAME = re.compile(
    r"^(?=.{1,253}$)"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$")


class ToolError(RuntimeError):
    """Something went wrong that is not a refusal (exit 1)."""


class Refused(RuntimeError):
    """Nothing was written on purpose (exit 2)."""


class MissingCryptography(ToolError):
    """The pinned `cryptography` package is not installed here (exit 3)."""


# --------------------------------------------------------------------------
#  The pieces this tool is built from, each one testable on its own
# --------------------------------------------------------------------------


def default_out_dir() -> Path:
    """Where the blueprint says the files live: ~/.openjarvis/tls."""
    return Path.home() / ".openjarvis" / "tls"


def this_pc_hostname() -> str:
    """This PC's hostname, which is the default CN/SAN.

    `socket.gethostname()` reads the local name only - no DNS lookup, so this is
    safe to call on a machine with no network at all."""
    name = (socket.gethostname() or "").strip()
    return name or "localhost"


def normalize_host(host: str) -> str:
    """`--host` as it goes into the certificate: a hostname or an IP address.

    The default is this PC's hostname. A value that is neither is refused with a
    plain sentence (exit 1) instead of writing a certificate no browser would
    accept - a certificate is not a good place to discover a typo."""
    host = (host or "").strip().rstrip(".")
    if not host:
        return this_pc_hostname()
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    if not HOSTNAME.match(host):
        raise ToolError(f"--host {host!r} is not a hostname or an IP address; pass "
                        f"the name the browser will open, e.g. my-pc.nord or "
                        f"my-pc.tailnet.ts.net")
    return host


def _is_mesh_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    return ip.version == 4 and ip in MESH_NET


def mesh_ips_from_text(text: str) -> list:
    """Every 100.64.0.0/10 IPv4 address written anywhere in `text`, sorted.

    Kept as a pure function so a test can feed a captured `ipconfig` block with
    the block's edges (100.63.x and 100.128.x are OUTSIDE it) and prove both
    directions. Duplicates are removed; anything that is not an address is
    ignored."""
    found = set()
    for raw in IPV4.findall(text or ""):
        if _is_mesh_ip(raw):
            found.add(str(ipaddress.ip_address(raw)))
    return sorted(found)


def _interface_config_text() -> str:
    """The machine's own network configuration as text, best effort.

    No `psutil` (not pinned) and no DNS: `ipconfig` on Windows, `ip`/`hostname`
    on POSIX. Any failure is an empty string - the explicit SANs (host,
    localhost, 127.0.0.1, ::1) are what the certificate must not lose."""
    if os.name == "nt":
        commands = [["ipconfig"]]
    else:
        commands = [["ip", "-o", "-4", "addr"], ["hostname", "-I"], ["ifconfig"]]
    kwargs = {}
    if os.name == "nt":
        # Do not flash a console window when the desktop app runs this later.
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    for command in commands:
        try:
            done = subprocess.run(command, capture_output=True, text=True,
                                  timeout=10, check=False, **kwargs)
        except (OSError, subprocess.SubprocessError):
            continue
        if done.returncode == 0 and (done.stdout or "").strip():
            return done.stdout
    return ""


def mesh_interface_ips() -> list:
    """The mesh addresses this PC currently has, detected locally and failing soft."""
    try:
        return mesh_ips_from_text(_interface_config_text())
    except Exception:  # noqa: BLE001 - detection is a convenience, never a blocker
        return []


def foreign_certificate_files(out: Path) -> list:
    """Certificate-looking files in `out` that this tool did not write.

    This is how an existing `tailscale cert` pair is found: the tool reports it
    and writes nothing over it. A missing folder simply has none."""
    try:
        if not out.is_dir():
            return []
        return sorted(p for p in out.iterdir()
                      if p.is_file() and p.name not in OWN_NAMES
                      and p.suffix.lower() in CERT_SUFFIXES)
    except OSError:
        return []


def _load_crypto():
    """Import `cryptography` lazily, with a plain message when it is absent.

    Lazy on purpose: the whole tool must still be usable as `--help` on a PC
    where the pinned package is not installed yet, and a test can simulate the
    absent case without uninstalling anything."""
    try:
        from types import SimpleNamespace

        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    except ImportError as exc:
        raise MissingCryptography(
            "the `cryptography` package is not installed, so no certificate can "
            "be made. It is already pinned in backend/requirements.lock (no new "
            "dependency is needed); run the project's own install/update steps "
            "and try again. Details: " + type(exc).__name__) from exc
    return SimpleNamespace(x509=x509, hashes=hashes,
                           serialization=serialization, rsa=rsa,
                           ExtendedKeyUsageOID=ExtendedKeyUsageOID, NameOID=NameOID)


def _name_attributes(crypto, host: str):
    return [crypto.x509.NameAttribute(crypto.NameOID.COMMON_NAME, host)]


def build_root_ca(crypto):
    """The local Root CA: 10 years, ca=True path_length=0, sign+crl, SKI.

    The subject and issuer are the same name (it signs itself), and a
    SubjectKeyIdentifier is written explicitly so the leaf's AuthorityKeyIdentifier
    has something exact to point at."""
    x509 = crypto.x509
    key = crypto.rsa.generate_private_key(public_exponent=65537, key_size=RSA_BITS)
    now = datetime.datetime.now(datetime.timezone.utc)
    subject = x509.Name([
        x509.NameAttribute(crypto.NameOID.COMMON_NAME, ROOT_CN),
        x509.NameAttribute(crypto.NameOID.ORGANIZATION_NAME, ROOT_ORG),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=ROOT_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(digital_signature=False, content_commitment=False,
                          key_encipherment=False, data_encipherment=False,
                          key_agreement=False, key_cert_sign=True, crl_sign=True,
                          encipher_only=False, decipher_only=False),
            critical=True)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
            critical=False)
        .sign(key, crypto.hashes.SHA256())
    )
    return key, cert


def _san_entries(crypto, host: str, mesh_ips):
    """The certificate's names, in a stable order and without duplicates."""
    x509 = crypto.x509
    dns, ips = [], []
    try:
        parsed = ipaddress.ip_address(host)
    except ValueError:
        dns.append(host)
    else:
        ips.append(parsed)
    dns.append("localhost")
    ips.extend([ipaddress.ip_address("127.0.0.1"), ipaddress.ip_address("::1")])
    for raw in mesh_ips or ():
        try:
            ip = ipaddress.ip_address(str(raw))
        except ValueError:
            continue
        if ip not in ips:
            ips.append(ip)
    seen, out = set(), []
    for name in dns:
        if ("dns", name) not in seen:
            seen.add(("dns", name))
            out.append(x509.DNSName(name))
    for ip in ips:
        if ("ip", ip) not in seen:
            seen.add(("ip", ip))
            out.append(x509.IPAddress(ip))
    return out


def build_server_cert(crypto, root_key, root_cert, host: str, mesh_ips):
    """The leaf: <=397 days, distinct subject, serverAuth EKU, AKI -> root SKI, SANs."""
    x509 = crypto.x509
    key = crypto.rsa.generate_private_key(public_exponent=65537, key_size=RSA_BITS)
    now = datetime.datetime.now(datetime.timezone.utc)
    not_before = now - datetime.timedelta(minutes=5)
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name(_name_attributes(crypto, host)))
        .issuer_name(root_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_before + datetime.timedelta(days=LEAF_DAYS))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(digital_signature=True, content_commitment=False,
                          key_encipherment=True, data_encipherment=False,
                          key_agreement=False, key_cert_sign=False, crl_sign=False,
                          encipher_only=False, decipher_only=False),
            critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([crypto.ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(root_key.public_key()),
            critical=False)
        .add_extension(x509.SubjectAlternativeName(_san_entries(crypto, host, mesh_ips)),
                       critical=False)
        .sign(root_key, crypto.hashes.SHA256())
    )
    return key, cert


def _pem_private_key(crypto, key) -> bytes:
    return key.private_bytes(
        encoding=crypto.serialization.Encoding.PEM,
        format=crypto.serialization.PrivateFormat.PKCS8,
        encryption_algorithm=crypto.serialization.NoEncryption(),
    )


def _pem_certificate(crypto, cert) -> bytes:
    return cert.public_bytes(crypto.serialization.Encoding.PEM)


def build_mobileconfig(root_der: bytes) -> bytes:
    """The Apple profile: a Configuration payload whose single payload is the root CA.

    Written as a plain XML plist with the Apple DOCTYPE. `PayloadType` is
    `com.apple.security.root` and the DER certificate is the `<data>` body,
    base64 (Apple's format for a trust payload). A test proves the bytes parse
    as XML/plist and that the data decodes back to exactly the root DER."""
    der_b64 = base64.b64encode(root_der).decode("ascii")
    wrapped = "\n".join(textwrap.wrap(der_b64, 64))
    inner_uuid = str(uuid.uuid4()).upper()
    outer_uuid = str(uuid.uuid4()).upper()
    identifier = "local.jarvis.mesh.root-ca"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        '<dict>\n'
        '    <key>PayloadContent</key>\n'
        '    <array>\n'
        '        <dict>\n'
        '            <key>PayloadCertificateFileName</key>\n'
        '            <string>jarvis-mesh-root-ca.crt</string>\n'
        '            <key>PayloadContent</key>\n'
        '            <data>\n'
        f'{wrapped}\n'
        '            </data>\n'
        '            <key>PayloadDescription</key>\n'
        f'            <string>Trusts the private {ROOT_CN} that signs this PC\u2019s '
        'Jarvis web server certificate.</string>\n'
        '            <key>PayloadDisplayName</key>\n'
        f'            <string>{ROOT_CN}</string>\n'
        '            <key>PayloadIdentifier</key>\n'
        f'            <string>{identifier}.payload</string>\n'
        '            <key>PayloadType</key>\n'
        '            <string>com.apple.security.root</string>\n'
        '            <key>PayloadUUID</key>\n'
        f'            <string>{inner_uuid}</string>\n'
        '            <key>PayloadVersion</key>\n'
        '            <integer>1</integer>\n'
        '        </dict>\n'
        '    </array>\n'
        '    <key>PayloadDisplayName</key>\n'
        f'    <string>{ROOT_CN} (Jarvis local mesh)</string>\n'
        '    <key>PayloadIdentifier</key>\n'
        f'    <string>{identifier}</string>\n'
        '    <key>PayloadRemovalDisallowed</key>\n'
        '    <false/>\n'
        '    <key>PayloadType</key>\n'
        '    <string>Configuration</string>\n'
        '    <key>PayloadUUID</key>\n'
        f'    <string>{outer_uuid}</string>\n'
        '    <key>PayloadVersion</key>\n'
        '    <integer>1</integer>\n'
        '</dict>\n'
        '</plist>\n'
    ).encode("utf-8")


# --------------------------------------------------------------------------
#  Writing, permissions and the one refusal rule
# --------------------------------------------------------------------------


def _no_window_kwargs() -> dict:
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {}


def _restrict_key_permissions(path: Path) -> bool:
    """Make a private key readable only by its owner, best effort.

    POSIX: chmod 0600. Windows: inherited ACLs are replaced with one full-control
    grant to the current user (`icacls /inheritance:r /grant:r <user>:F`). A
    failure is reported to the caller and never fatal - the certificate files
    are already written by then, and a permissions warning is better than a
    half-deleted run."""
    try:
        if os.name != "nt":
            os.chmod(path, 0o600)
            return True
        user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
        if not user:
            return False
        done = subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:(F)"],
            capture_output=True, text=True, timeout=15, check=False,
            **_no_window_kwargs())
        return done.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _write(path: Path, data: bytes) -> None:
    path.write_bytes(data)


def generate(out, host: str = "", force: bool = False, mesh_ips=None) -> dict:
    """Write the CA, the leaf and the profile under `out`; return what was written.

    Raises Refused (nothing written) when this tool's own files, or another
    certificate pair, already exist and `force` is false. Raises
    MissingCryptography when the pinned package is absent. `mesh_ips` is an
    injection seam for tests: None means "detect them on this machine"."""
    out = Path(out).expanduser()
    host = normalize_host(host)
    ours = [out / name for name in OWN_NAMES]
    existing = [p for p in ours if p.exists()]
    foreign = foreign_certificate_files(out)
    if (existing or foreign) and not force:
        lines = []
        if existing:
            lines.append(f"REFUSED: {len(existing)} file(s) this tool would write "
                         f"already exist under {out}:")
            lines += [f"  {p}" for p in existing]
        if foreign:
            lines.append(f"REFUSED: {len(foreign)} certificate file(s) this tool did "
                         f"not write are under {out}:")
            lines += [f"  {p}" for p in foreign]
            lines.append("  (a pair like this is usually from `tailscale cert` - if this "
                         "PC is on Tailscale, that certificate needs no profile; this "
                         "tool will not overwrite it)")
        lines.append("Nothing was written. Pass --force to replace this tool's own "
                     "files and/or write beside the files it did not write.")
        raise Refused("\n".join(lines))

    crypto = _load_crypto()
    try:
        out.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ToolError(f"could not create {out}: {exc}") from exc

    mesh_ips = mesh_interface_ips() if mesh_ips is None else list(mesh_ips)
    root_key, root_cert = build_root_ca(crypto)
    leaf_key, leaf_cert = build_server_cert(crypto, root_key, root_cert, host, mesh_ips)
    root_der = root_cert.public_bytes(crypto.serialization.Encoding.DER)
    mobileconfig = build_mobileconfig(root_der)

    written = {
        ROOT_CRT: _pem_certificate(crypto, root_cert),
        ROOT_KEY: _pem_private_key(crypto, root_key),
        SERVER_CRT: _pem_certificate(crypto, leaf_cert),
        SERVER_KEY: _pem_private_key(crypto, leaf_key),
        MOBILECONFIG: mobileconfig,
    }
    paths = {}
    for name, data in written.items():
        path = out / name
        try:
            _write(path, data)
        except OSError as exc:
            raise ToolError(f"could not write {path}: {exc}") from exc
        paths[name] = path
    hardened = {}
    for name in (ROOT_KEY, SERVER_KEY):
        hardened[name] = _restrict_key_permissions(paths[name])

    sans = [str(entry.value) for entry in
            leaf_cert.extensions.get_extension_for_class(crypto.x509.SubjectAlternativeName).value]
    return {"out": out, "host": host, "sans": sans, "files": paths,
            "hardened": hardened, "foreign": foreign}


# --------------------------------------------------------------------------
#  Command line
# --------------------------------------------------------------------------


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="gen_mesh_tls_cert.py",
        description=("Make a local Root CA, a <=397-day TLS certificate for this PC's "
                     "mesh name, and an Apple .mobileconfig profile that trusts the CA."),
        epilog=("Exit codes: 0 wrote everything; 2 refused because files already exist "
                "or a certificate pair this tool did not write is in the folder (pass "
                "--force to write anyway); 3 the `cryptography` package is missing; "
                "1 any other error. No key material is ever printed."))
    parser.add_argument("--out", default=str(default_out_dir()),
                        help=f"folder for the five files (default: {default_out_dir()})")
    parser.add_argument("--host", default="",
                        help="the mesh name to put in the certificate (default: this "
                             "PC's hostname)")
    parser.add_argument("--force", action="store_true",
                        help="replace this tool's own files and write beside any "
                             "certificate pair it did not write (never over it)")
    args = parser.parse_args(argv)

    if not str(args.out).strip():
        print("ERROR: --out is empty; pass the folder to write the five files into "
              "(default: ~/.openjarvis/tls)", file=sys.stderr)
        return 1

    try:
        result = generate(args.out, host=args.host, force=args.force)
    except MissingCryptography as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3
    except Refused as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except ToolError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    files = result["files"]
    print(f"Jarvis local mesh HTTPS material in {result['out']}")
    for name in (ROOT_CRT, ROOT_KEY, SERVER_CRT, SERVER_KEY, MOBILECONFIG):
        print(f"  wrote {files[name]}")
    print(f"\nCertificate CN: {result['host']}")
    print("SANs: " + ", ".join(result["sans"]))
    for name, ok in result["hardened"].items():
        if not ok:
            print(f"  note: could not restrict permissions on {files[name]} - it is "
                  f"protected by the folder's own permissions on this PC")
    if result["foreign"]:
        print("  note: left these files alone (this tool did not write them): "
              + ", ".join(str(p) for p in result["foreign"]))
    print("\nOn an iPad/iPhone: download jarvis-ca.mobileconfig, Settings -> "
          "Profile Downloaded -> Install, then Settings -> General -> About -> "
          "Certificate Trust Settings -> Full Trust ON.")
    print("On Android/Windows: install jarvis-mesh-root-ca.crt as a trusted CA.")
    print("Then open https://<the name above>:4719/ - the microphone, wake lock "
          "and WebAuthn become available because the page is a secure context.")
    print("If this PC is on Tailscale: `tailscale cert <pc>.<tailnet>.ts.net` is "
          "the zero-profile alternative; this tool leaves an existing pair alone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
