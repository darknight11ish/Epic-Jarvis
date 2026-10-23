"""test_mesh_tls_cert.py - tools/gen_mesh_tls_cert.py, and the blueprint's Bite 10.

    python3 backend/test_mesh_tls_cert.py

WHY THIS EXISTS

The Universal Jarvis PWA is served from this PC over NordVPN Meshnet / Tailscale,
which browsers treat as an insecure origin over plain HTTP. The blueprint's
Slice 4 gives the owner ONE command that makes the web app a secure context:
`tools/gen_mesh_tls_cert.py` writes a local Root CA, a <=397-day server
certificate whose Subject Alternative Names cover the mesh addresses this PC
actually has, and the Apple `.mobileconfig` profile that installs the root on an
iPad/iPhone. This file is Bite 10 of the blueprint - the mutation proof for that
tool. Each check below is a claim the tool makes in its own docstring; if the
tool drifts, one of them goes red.

WHAT IT PROVES (Bite 10 plus the honest edges)

  1. the Root CA really is a CA: BasicConstraints(ca=True, path_length=0),
     KeyUsage key_cert_sign + crl_sign, a SubjectKeyIdentifier, the documented
     CN, and ~10 years of validity;
  2. the leaf satisfies the browser/Apple limits: <= 397 days, ca=False,
     digital_signature + key_encipherment, ExtendedKeyUsage exactly SERVER_AUTH,
     CN = the injected mesh host, and its subject is distinct from the root's;
  3. the leaf chains: its AuthorityKeyIdentifier key id IS the root's
     SubjectKeyIdentifier, its issuer is the root's subject, and its signature
     verifies with the root's public key;
  4. the SANs include the injected `.nord` host, `localhost`, `127.0.0.1`,
     `::1` and the injected 100.x Meshnet address - and a host that is an IP is
     an IP SAN, not a DNS name;
  5. the `.mobileconfig` parses as XML/plist, its payload type is
     `com.apple.security.root`, and its `<data>` decodes to exactly the root
     certificate's DER;
  6. the CGNAT detection accepts exactly 100.64.0.0/10 (100.63.x and 100.128.x
     are outside it) and fails soft;
  7. a second run refuses and changes nothing; `--force` replaces only this
     tool's own files;
  8. an existing `tailscale cert` pair is reported and never overwritten, even
     with `--force`;
  9. no key material is printed (paths only), the private keys load and match
     their certificates, and the key files exist on disk;
 10. when the pinned `cryptography` package is absent the tool says so plainly
     and exits 3 instead of raising a traceback.

WHAT IT DOES NOT PROVE

  It does not install anything on an iPad/Android device, does not serve HTTPS
  (the `/api/tls/*` routes are a later slice), and does not start the backend.
  It never touches the real `~/.openjarvis`: every run writes into this suite's
  own temporary folder.

Needs `cryptography` only, which is already pinned in
`backend/requirements.lock` (no new dependency). No network; runs anywhere.
"""
from __future__ import annotations

import datetime
import hashlib
import importlib.util
import ipaddress
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import traceback
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
TOOL_PATH = REPO / "tools" / "gen_mesh_tls_cert.py"

FAILED, PASSED, SKIPPED = [], [], []

#: The injected mesh host and address: fixed values, so the SAN checks never
#: depend on what this PC's network happens to look like today.
HOST = "mariorelan11-alps.nord"
MESH_IP = "100.96.1.25"

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-mesh-tls-test-"))


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass. (A `check("SKIP - ...", True)` would be counted as a pass
    by this suite and by backend/run_suites.py; tools/check_vacuous_checks.py
    exists because that shape shipped.)"""
    SKIPPED.append(why)
    print(f"skip  {why}")


try:
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID
    CRYPTO_OK = True
except ImportError:  # the module-level checks below all need it
    CRYPTO_OK = False


def load_tool():
    spec = importlib.util.spec_from_file_location("gen_mesh_tls_cert", TOOL_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TOOL = load_tool()


# --------------------------------------------------------------- helpers --


def fresh_dir(name: str) -> Path:
    path = _TMP / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def tool_env(**overrides) -> dict:
    """The environment for a tool subprocess: the real one, minus anything that
    could make the run depend on this shell's Python setup."""
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update(overrides)
    return env


def run_tool(*args, env=None, cwd=None):
    return subprocess.run([sys.executable, "-B", str(TOOL_PATH), *map(str, args)],
                          capture_output=True, text=True, timeout=180,
                          env=env or tool_env(), cwd=str(cwd) if cwd else None)


def read_cert(path: Path):
    return x509.load_pem_x509_certificate(Path(path).read_bytes())


def der(cert) -> bytes:
    return cert.public_bytes(serialization.Encoding.DER)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def all_files(out: Path) -> dict:
    return {name: sha256_file(out / name) for name in TOOL.OWN_NAMES}


def extension(cert, cls):
    return cert.extensions.get_extension_for_class(cls).value


def validity_days(cert) -> float:
    return (cert.not_valid_after_utc - cert.not_valid_before_utc).total_seconds() / 86400.0


def generate(out, **kwargs):
    """Call the tool in-process (the injection seam Bite 10 needs)."""
    kwargs.setdefault("host", HOST)
    kwargs.setdefault("mesh_ips", (MESH_IP,))
    return TOOL.generate(out, **kwargs)


# --------------------------------------------------------------- checks --

_CA = {}


def t_the_documented_files_are_the_ones_written():
    out = fresh_dir("names")
    generate(out)
    check("the five documented file names are exactly the ones written",
          sorted(p.name for p in out.iterdir()) == sorted(TOOL.OWN_NAMES),
          str(sorted(p.name for p in out.iterdir())))


def t_root_ca_is_a_real_ca():
    out = fresh_dir("ca-pair")
    _CA["out"] = out
    generate(out)
    root = read_cert(out / TOOL.ROOT_CRT)
    _CA["root"] = root
    bc = extension(root, x509.BasicConstraints)
    check("root CA BasicConstraints is ca=True with path_length=0",
          bc.ca is True and bc.path_length == 0, f"ca={bc.ca} path_length={bc.path_length}")
    ku = extension(root, x509.KeyUsage)
    check("root CA KeyUsage allows certificate and CRL signing",
          ku.key_cert_sign is True and ku.crl_sign is True,
          f"key_cert_sign={ku.key_cert_sign} crl_sign={ku.crl_sign}")
    check("root CA has a SubjectKeyIdentifier",
          len(extension(root, x509.SubjectKeyIdentifier).digest) > 0)
    cn = root.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0].value
    check("root CA CN is 'Jarvis Local Mesh Root CA'",
          cn == "Jarvis Local Mesh Root CA", cn)
    check("root CA is self-signed (issuer is its own subject)",
          root.issuer == root.subject)
    days = validity_days(root)
    check("root CA validity is about 10 years", 3600 <= days <= 3700, f"{days:.0f} days")
    check("root CA key is RSA 2048",
          isinstance(root.public_key(), rsa.RSAPublicKey)
          and root.public_key().key_size == 2048)


def t_leaf_is_within_the_browser_and_apple_limits():
    # The leaf and the root MUST come from one generated pair: a second
    # generate() call makes a different root, and a cross-pair comparison of
    # AKI/SKI and the signature would fail for a reason that is not a defect.
    out = _CA["out"]
    leaf = read_cert(out / TOOL.SERVER_CRT)
    root = _CA["root"]
    _CA["leaf"] = leaf
    days = validity_days(leaf)
    check("leaf validity is <= 397 days", 0 < days <= 397.0, f"{days:.1f} days")
    check("leaf validity is inside Safari/Chrome's <= 398-day limit", days <= 398.0,
          f"{days:.1f} days")
    check("leaf not-before is not in the future",
          leaf.not_valid_before_utc
          <= datetime.datetime.now(datetime.timezone.utc)
          + datetime.timedelta(minutes=1),
          str(leaf.not_valid_before_utc))
    bc = extension(leaf, x509.BasicConstraints)
    check("leaf BasicConstraints is ca=False", bc.ca is False)
    ku = extension(leaf, x509.KeyUsage)
    check("leaf KeyUsage is digital_signature + key_encipherment",
          ku.digital_signature is True and ku.key_encipherment is True
          and ku.key_cert_sign is False,
          f"digital_signature={ku.digital_signature} "
          f"key_encipherment={ku.key_encipherment} key_cert_sign={ku.key_cert_sign}")
    eku = extension(leaf, x509.ExtendedKeyUsage)
    check("leaf ExtendedKeyUsage is exactly SERVER_AUTH",
          list(eku) == [ExtendedKeyUsageOID.SERVER_AUTH], str([oid.dotted_string for oid in eku]))
    cn = leaf.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0].value
    check("leaf CN is the injected mesh host", cn == HOST, cn)
    check("leaf subject is distinct from the root subject", leaf.subject != root.subject)


def t_leaf_chains_to_the_root():
    leaf, root = _CA["leaf"], _CA["root"]
    ski = extension(root, x509.SubjectKeyIdentifier).digest
    aki = extension(leaf, x509.AuthorityKeyIdentifier)
    check("leaf AuthorityKeyIdentifier key id is the root's SubjectKeyIdentifier",
          aki.key_identifier == ski,
          f"aki={aki.key_identifier!r} ski={ski!r}")
    check("leaf issuer is the root subject", leaf.issuer == root.subject)
    verified = True
    try:
        root.public_key().verify(leaf.signature, leaf.tbs_certificate_bytes,
                                 padding.PKCS1v15(), leaf.signature_hash_algorithm)
    except Exception:  # noqa: BLE001 - the failure IS the finding
        verified = False
    check("leaf signature verifies with the root's public key", verified)


def t_sans_cover_the_mesh_and_the_loopbacks():
    leaf = _CA["leaf"]
    san = extension(leaf, x509.SubjectAlternativeName)
    dns = list(san.get_values_for_type(x509.DNSName))
    ips = list(san.get_values_for_type(x509.IPAddress))
    check("SAN has the injected .nord host as a DNS name", HOST in dns, str(dns))
    check("SAN has localhost as a DNS name", "localhost" in dns, str(dns))
    check("SAN has 127.0.0.1 as an IP address",
          ipaddress.ip_address("127.0.0.1") in ips, str(ips))
    check("SAN has ::1 as an IP address",
          ipaddress.ip_address("::1") in ips, str(ips))
    check("SAN has the injected 100.x Meshnet address",
          ipaddress.ip_address(MESH_IP) in ips, str(ips))
    mesh_like = [ip for ip in ips if ip in ipaddress.ip_network("100.64.0.0/10")]
    check("exactly one 100.64.0.0/10 SAN (the injected one, not this PC's)",
          [str(ip) for ip in mesh_like] == [MESH_IP], str([str(ip) for ip in mesh_like]))
    check("no wildcard DNS name sneaks in", not any("*" in name for name in dns), str(dns))


def t_a_host_that_is_an_ip_is_an_ip_san():
    out = fresh_dir("host-ip")
    generate(out, host=MESH_IP, mesh_ips=())
    leaf = read_cert(out / TOOL.SERVER_CRT)
    san = extension(leaf, x509.SubjectAlternativeName)
    dns = list(san.get_values_for_type(x509.DNSName))
    ips = list(san.get_values_for_type(x509.IPAddress))
    cn = leaf.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0].value
    check("an IP --host becomes the CN but not a DNS SAN",
          cn == MESH_IP and MESH_IP not in dns, f"cn={cn} dns={dns}")
    check("an IP --host is present as an IP SAN",
          ipaddress.ip_address(MESH_IP) in ips, str(ips))


def t_mobileconfig_is_a_root_ca_profile():
    out = fresh_dir("mobileconfig")
    generate(out)
    root = read_cert(out / TOOL.ROOT_CRT)
    path = out / TOOL.MOBILECONFIG
    raw = path.read_bytes()
    check("the profile starts as an XML document", raw.lstrip().startswith(b"<?xml"),
          raw[:40].decode("utf-8", "replace"))
    parsed = None
    try:
        ET.fromstring(raw)
        parsed = plistlib.loads(raw)
    except Exception:  # noqa: BLE001 - a profile that does not parse cannot install
        parsed = None
    check("the profile parses as XML and as a plist", isinstance(parsed, dict),
          "plistlib/ElementTree refused the bytes")
    if not isinstance(parsed, dict):
        return
    check("the profile's outer PayloadType is Configuration",
          parsed.get("PayloadType") == "Configuration", str(parsed.get("PayloadType")))
    payloads = parsed.get("PayloadContent")
    check("the profile carries exactly one payload",
          isinstance(payloads, list) and len(payloads) == 1,
          str(type(payloads).__name__))
    if not (isinstance(payloads, list) and payloads):
        return
    payload = payloads[0]
    check("the payload's PayloadType is com.apple.security.root",
          payload.get("PayloadType") == "com.apple.security.root",
          str(payload.get("PayloadType")))
    body = payload.get("PayloadContent")
    check("the payload carries the root certificate DER",
          isinstance(body, (bytes, bytearray)) and bytes(body) == der(root),
          f"bytes={len(body) if isinstance(body, (bytes, bytearray)) else 'not bytes'}")
    check("the payload names the certificate file for the user",
          payload.get("PayloadCertificateFileName") == TOOL.ROOT_CRT,
          str(payload.get("PayloadCertificateFileName")))
    check("the payload has its own PayloadIdentifier",
          bool(payload.get("PayloadIdentifier")), str(payload.get("PayloadIdentifier")))


def t_a_second_run_refuses_and_changes_nothing():
    out = fresh_dir("second-run")
    first = run_tool("--out", out, "--host", HOST)
    check("first CLI run exits 0", first.returncode == 0,
          f"exit={first.returncode}\n{first.stdout}\n{first.stderr}")
    before = all_files(out)
    second = run_tool("--out", out, "--host", HOST)
    said = second.stdout + second.stderr
    check("a second run refuses with a nonzero exit", second.returncode != 0,
          f"exit={second.returncode}")
    check("the refusal names a file it would have overwritten",
          TOOL.ROOT_CRT in said, said[:300])
    check("the refusal says how to proceed (--force)", "--force" in said, said[:300])
    check("the refusal changed none of the files it refused to overwrite",
          all_files(out) == before)


def t_force_replaces_only_this_tools_own_files():
    out = fresh_dir("force")
    run_tool("--out", out, "--host", HOST)
    first_leaf = read_cert(out / TOOL.SERVER_CRT)
    first_root = read_cert(out / TOOL.ROOT_CRT)
    forced = run_tool("--out", out, "--host", HOST, "--force")
    check("--force exits 0", forced.returncode == 0,
          f"exit={forced.returncode}\n{forced.stdout}\n{forced.stderr}")
    leaf = read_cert(out / TOOL.SERVER_CRT)
    root = read_cert(out / TOOL.ROOT_CRT)
    check("--force wrote a new leaf certificate",
          leaf.serial_number != first_leaf.serial_number)
    check("--force wrote a new root CA", root.serial_number != first_root.serial_number)


def t_an_existing_tailscale_pair_is_reported_not_overwritten():
    out = fresh_dir("tailscale")
    foreign_crt = out / "my-pc.tailnet.ts.net.crt"
    foreign_key = out / "my-pc.tailnet.ts.net.key"
    foreign_crt.write_bytes(b"-----BEGIN CERTIFICATE-----\nnot really a cert\n-----END CERTIFICATE-----\n")
    foreign_key.write_bytes(b"-----BEGIN PRIVATE KEY-----\nnot really a key\n-----END PRIVATE KEY-----\n")
    refused = run_tool("--out", out, "--host", HOST)
    said = refused.stdout + refused.stderr
    check("a folder with a tailscale cert pair is refused", refused.returncode != 0,
          f"exit={refused.returncode}")
    check("the refusal names tailscale", "tailscale" in said.lower(), said[:300])
    check("the tailscale files are untouched by the refusal",
          foreign_crt.read_bytes().startswith(b"-----BEGIN CERTIFICATE-----")
          and foreign_key.read_bytes().startswith(b"-----BEGIN PRIVATE KEY-----"))
    check("the refusal wrote none of this tool's files",
          not any((out / name).exists() for name in TOOL.OWN_NAMES))
    forced = run_tool("--out", out, "--host", HOST, "--force")
    check("--force writes beside the tailscale pair (exit 0)", forced.returncode == 0,
          f"exit={forced.returncode}\n{forced.stdout}\n{forced.stderr}")
    check("even --force leaves the tailscale pair byte for byte",
          foreign_crt.read_bytes() == b"-----BEGIN CERTIFICATE-----\nnot really a cert\n"
          b"-----END CERTIFICATE-----\n"
          and foreign_key.read_bytes() == b"-----BEGIN PRIVATE KEY-----\nnot really a key\n"
          b"-----END PRIVATE KEY-----\n")
    check("with --force this tool's own files are written next to it",
          (out / TOOL.ROOT_CRT).exists() and (out / TOOL.MOBILECONFIG).exists())


def t_no_key_material_is_printed():
    out = fresh_dir("print")
    result = run_tool("--out", out, "--host", HOST)
    said = result.stdout + result.stderr
    key_texts = [(out / TOOL.ROOT_KEY).read_text(encoding="utf-8"),
                 (out / TOOL.SERVER_KEY).read_text(encoding="utf-8")]
    check("the successful run printed no private-key marker",
          "PRIVATE KEY" not in said and "BEGIN RSA" not in said, said[:300])
    check("the successful run printed no private-key body",
          not any(line in said for key_text in key_texts
                  for line in key_text.splitlines() if len(line) >= 40),
          "a key body line appeared in the output")
    check("the printed output is paths, not certificate bodies",
          "BEGIN CERTIFICATE" not in said, said[:300])
    for path in (out / TOOL.ROOT_CRT, out / TOOL.SERVER_CRT, out / TOOL.MOBILECONFIG):
        check(f"the output names the written path {path.name}", str(path) in said,
              said[:400])
    check("the output names the host and the SANs it covers",
          HOST in said and "127.0.0.1" in said, said[:400])


def t_private_keys_exist_load_and_match_their_certificates():
    out = fresh_dir("keys")
    generate(out)
    root = read_cert(out / TOOL.ROOT_CRT)
    leaf = read_cert(out / TOOL.SERVER_CRT)
    root_key = serialization.load_pem_private_key(
        (out / TOOL.ROOT_KEY).read_bytes(), password=None)
    leaf_key = serialization.load_pem_private_key(
        (out / TOOL.SERVER_KEY).read_bytes(), password=None)
    check("the root private key is RSA 2048",
          isinstance(root_key, rsa.RSAPrivateKey) and root_key.key_size == 2048)
    check("the root private key matches the root certificate",
          root_key.public_key().public_numbers() == root.public_key().public_numbers())
    check("the leaf private key is RSA 2048",
          isinstance(leaf_key, rsa.RSAPrivateKey) and leaf_key.key_size == 2048)
    check("the leaf private key matches the server certificate",
          leaf_key.public_key().public_numbers() == leaf.public_key().public_numbers())
    if os.name == "posix":
        for name in (TOOL.ROOT_KEY, TOOL.SERVER_KEY):
            mode = (out / name).stat().st_mode & 0o777
            check(f"{name} is readable only by its owner (0600)", mode == 0o600,
                  f"mode={mode:o}")
    else:
        skip("Windows does not expose POSIX modes; the tool hardens the key ACLs with "
             "icacls instead, and the run's own harden result is checked below")
    result = generate(fresh_dir("keys-hardened"))
    check("the tool reports that it hardened both private keys",
          set(result["hardened"]) == {TOOL.ROOT_KEY, TOOL.SERVER_KEY},
          str(result["hardened"]))


def t_cgnat_detection_accepts_exactly_the_mesh_block():
    sample = (
        "Ethernet adapter Tailscale:\n"
        "   IPv4 Address. . . . . . . . . . . : 100.96.1.25\n"
        "   IPv4 Address. . . . . . . . . . . : 100.127.255.254\n"
        "   IPv4 Address. . . . . . . . . . . : 100.63.255.255\n"
        "   IPv4 Address. . . . . . . . . . . : 100.128.0.1\n"
        "   IPv4 Address. . . . . . . . . . . : 192.168.1.20\n"
        "   Subnet Mask . . . . . . . . . . . : 255.255.255.0\n")
    got = TOOL.mesh_ips_from_text(sample)
    check("the two in-block addresses are found and the others are not",
          got == ["100.127.255.254", "100.96.1.25"], str(got))
    check("100.64.0.1 (the block's first address) is inside",
          TOOL.mesh_ips_from_text("100.64.0.1") == ["100.64.0.1"])
    check("100.127.255.254 (the block's last address) is inside",
          TOOL.mesh_ips_from_text("100.127.255.254") == ["100.127.255.254"])
    check("100.63.255.255 and 100.128.0.0 are outside the block",
          TOOL.mesh_ips_from_text("100.63.255.255 100.128.0.0") == [])
    check("duplicate addresses are removed",
          TOOL.mesh_ips_from_text("100.96.1.25 x 100.96.1.25") == ["100.96.1.25"])
    check("empty configuration text is an empty list, not an error",
          TOOL.mesh_ips_from_text("") == [])
    check("the detection fails soft when there is no configuration to read",
          isinstance(TOOL.mesh_interface_ips(), list))


def t_default_output_folder_is_the_documented_one():
    check("the default output folder is ~/.openjarvis/tls",
          TOOL.default_out_dir() == Path.home() / ".openjarvis" / "tls",
          str(TOOL.default_out_dir()))
    check("the default hostname fallback is never empty",
          bool(TOOL.this_pc_hostname().strip()))
    check("this suite's own runs all wrote inside a temporary folder",
          _TMP.name.startswith("jarvis-mesh-tls-test-") and _TMP.is_dir(), str(_TMP))
    check("an empty --host uses this PC's hostname",
          generate(fresh_dir("default-host"), host="")["host"] == TOOL.this_pc_hostname())


def t_a_malformed_host_is_refused_with_plain_words():
    out = fresh_dir("bad-host")
    result = run_tool("--out", out, "--host", "not a host name")
    said = result.stdout + result.stderr
    check("a malformed --host exits 1", result.returncode == 1,
          f"exit={result.returncode}\n{said[:400]}")
    check("the message names the bad value", "not a host name" in said, said[:400])
    check("the message says what a host looks like", "hostname" in said, said[:400])
    check("the message is plain words, not a traceback", "Traceback" not in said,
          said[:400])
    check("nothing was written for a malformed host",
          not any((out / name).exists() for name in TOOL.OWN_NAMES))


def t_missing_cryptography_exits_three_with_plain_words():
    shim = fresh_dir("crypto-shim")
    (shim / "cryptography.py").write_text(
        'raise ImportError("simulated: cryptography is not installed for this test")\n',
        encoding="utf-8")
    out = fresh_dir("missing-crypto-out")
    env = tool_env(PYTHONPATH=str(shim))
    result = run_tool("--out", out, "--host", HOST, env=env)
    said = result.stdout + result.stderr
    check("with cryptography absent the tool exits 3", result.returncode == 3,
          f"exit={result.returncode}\n{said[:400]}")
    check("the message names the missing package", "cryptography" in said, said[:400])
    check("the message points at the pinned dependency file",
          "requirements.lock" in said, said[:400])
    check("the message is plain words, not a traceback", "Traceback" not in said,
          said[:400])
    check("nothing was written when the dependency is missing",
          not any((out / name).exists() for name in TOOL.OWN_NAMES))


RUN = (
    t_the_documented_files_are_the_ones_written,
    t_root_ca_is_a_real_ca,
    t_leaf_is_within_the_browser_and_apple_limits,
    t_leaf_chains_to_the_root,
    t_sans_cover_the_mesh_and_the_loopbacks,
    t_a_host_that_is_an_ip_is_an_ip_san,
    t_mobileconfig_is_a_root_ca_profile,
    t_a_second_run_refuses_and_changes_nothing,
    t_force_replaces_only_this_tools_own_files,
    t_an_existing_tailscale_pair_is_reported_not_overwritten,
    t_no_key_material_is_printed,
    t_private_keys_exist_load_and_match_their_certificates,
    t_cgnat_detection_accepts_exactly_the_mesh_block,
    t_default_output_folder_is_the_documented_one,
    t_a_malformed_host_is_refused_with_plain_words,
    t_missing_cryptography_exits_three_with_plain_words,
)


def main() -> int:
    if not CRYPTO_OK:
        skip("the certificate checks need `cryptography`, which is already pinned in "
             "backend/requirements.lock; CI installs it (nothing here was tested)")
        print(f"\n0 passed, {len(SKIPPED)} skipped, 0 failed")
        print("skipped (never counted as a pass): " + "; ".join(SKIPPED))
        shutil.rmtree(_TMP, ignore_errors=True)
        return 0
    for fn in RUN:
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:  # noqa: BLE001 - a check that dies is a failure
            FAILED.append(fn.__name__)
            traceback.print_exc()
    # A t_ function written but never listed would report nothing at all, so the
    # harness checks its own list rather than trusting it.
    defined = {name for name, value in list(globals().items())
               if name.startswith("t_") and callable(value)
               and getattr(value, "__module__", None) == __name__}
    unlisted = sorted(defined - {fn.__name__ for fn in RUN})
    if unlisted:
        FAILED.append("every t_ function in this file is in RUN")
        print(f"\nFAIL  a t_ function that never runs is dead code: {unlisted}")
    shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if SKIPPED:
        print("skipped (never counted as a pass): " + "; ".join(SKIPPED))
    if FAILED:
        print("failed: " + ", ".join(FAILED))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
