import os
from types import SimpleNamespace

from mklink import discovery
from mklink._types import MKLINK_IDENTITY_COMMAND, MKLINK_IDENTITY_TOKEN


def port(
    device,
    *,
    hwid="",
    vid=None,
    pid=None,
    manufacturer="",
    serial_number=None,
    location="",
    interface=None,
    description="",
):
    return SimpleNamespace(
        device=device,
        hwid=hwid,
        vid=vid,
        pid=pid,
        manufacturer=manufacturer,
        serial_number=serial_number,
        location=location,
        interface=interface,
        description=description,
    )


def test_discovery_selects_mi04_without_opening_other_interfaces(monkeypatch):
    ports = [
        port(
            "COM54",
            hwid="USB VID:PID=0D28:0202 LOCATION=1-2:x.2",
            vid=0x0D28,
            pid=0x0202,
            serial_number="probe-v4",
            location="1-2:x.2",
        ),
        port(
            "COM55",
            hwid="USB VID:PID=0D28:0202 LOCATION=1-2:x.4",
            vid=0x0D28,
            pid=0x0202,
            serial_number="probe-v4",
            location="1-2:x.4",
        ),
        port(
            "COM56",
            hwid="USB VID:PID=0D28:0202 LOCATION=1-2:x.6",
            vid=0x0D28,
            pid=0x0202,
            serial_number="probe-v4",
            location="1-2:x.6",
        ),
    ]
    monkeypatch.setattr(discovery.list_ports, "comports", lambda: ports)
    monkeypatch.setattr(
        discovery,
        "_probe_port",
        lambda _device: (_ for _ in ()).throw(
            AssertionError("descriptor-based discovery must not open a port")
        ),
    )

    assert discovery.find_mklink_cdc_port() == "COM55"
    assert discovery.find_mklink_cdc_port(serial_number="PROBE-V4") == "COM55"


def test_discover_all_command_ports_skips_non_command_and_bluetooth(monkeypatch):
    ports = [
        port(
            "COM227",
            hwid=r"USB\VID_0D28&PID_0202&MI_02",
            vid=0x0D28,
            pid=0x0202,
        ),
        port(
            "COM228",
            hwid=r"USB\VID_0D28&PID_0202&MI_04",
            vid=0x0D28,
            pid=0x0202,
        ),
        port(
            "COM229",
            hwid=r"USB\VID_0D28&PID_0202&MI_06",
            vid=0x0D28,
            pid=0x0202,
        ),
        port("COM98", hwid=r"BTHENUM\device"),
    ]
    monkeypatch.setattr(discovery.list_ports, "comports", lambda: ports)
    monkeypatch.setattr(
        discovery,
        "_probe_port",
        lambda _device: (_ for _ in ()).throw(
            AssertionError("known non-command and Bluetooth ports must not open")
        ),
    )

    assert [item.device for item in discovery.discover_mklink_command_ports()] == [
        "COM228"
    ]


def test_discover_all_command_ports_keeps_legacy_identity_fallback(monkeypatch):
    ports = [
        port("COM44", hwid="USB VID:PID=0D28:0202", vid=0x0D28, pid=0x0202),
        port("COM45", hwid="USB VID:PID=0D28:0202", vid=0x0D28, pid=0x0202),
    ]
    probed = []
    monkeypatch.setattr(discovery.list_ports, "comports", lambda: ports)
    monkeypatch.setattr(
        discovery,
        "_probe_port",
        lambda device: probed.append(device) or device == "COM45",
    )

    assert [item.device for item in discovery.discover_mklink_command_ports()] == [
        "COM45"
    ]
    assert probed == ["COM44", "COM45"]


def test_discovery_uses_mi04_from_the_requested_composite_device(monkeypatch):
    ports = [
        port(
            "COM739",
            vid=0x0D28,
            pid=0x0202,
            serial_number="probe-v3",
            location="1-1.2:x.4",
        ),
        port(
            "COM55",
            vid=0x0D28,
            pid=0x0202,
            serial_number="probe-v4",
            location="1-2:x.4",
        ),
    ]
    monkeypatch.setattr(discovery.list_ports, "comports", lambda: ports)

    assert discovery.find_mklink_cdc_port(serial_number="probe-v4") == "COM55"


def test_discovery_keeps_automatic_fallback_for_a_logical_probe_id(monkeypatch):
    ports = [
        port(
            "COM55",
            vid=0x0D28,
            pid=0x0202,
            serial_number="usb-serial",
            location="1-2:x.4",
        ),
    ]
    monkeypatch.setattr(discovery.list_ports, "comports", lambda: ports)

    assert discovery.find_mklink_cdc_port(serial_number="logical-probe-id") == "COM55"


def test_discovery_probes_usb_before_virtual_and_skips_bluetooth(monkeypatch):
    ports = [
        port("COM98", hwid="BTHENUM\\device", manufacturer="Microsoft"),
        port("COM9", hwid="VSBC\\device", manufacturer="ELTIMA Software"),
        port("COM228", hwid="USB VID:PID=0D28:0202", vid=0x0D28, pid=0x0202),
        port("COM227", hwid="USB VID:PID=0D28:0202", vid=0x0D28, pid=0x0202),
    ]
    probed = []
    monkeypatch.setattr(discovery.list_ports, "comports", lambda: ports)
    monkeypatch.setattr(
        discovery,
        "_probe_port",
        lambda device: probed.append(device) or device == "COM227",
    )

    assert discovery.find_mklink_cdc_port() == "COM227"
    assert probed == ["COM228", "COM227"]


def test_discovery_probes_composite_interfaces_with_same_serial(monkeypatch):
    ports = [
        port(
            "COM221",
            hwid="USB VID:PID=0D28:0202",
            vid=0x0D28,
            pid=0x0202,
            serial_number="probe-1",
        ),
        port(
            "COM220",
            hwid="USB VID:PID=0D28:0202",
            vid=0x0D28,
            pid=0x0202,
            serial_number="probe-1",
        ),
        port(
            "COM219",
            hwid="USB VID:PID=0D28:0202",
            vid=0x0D28,
            pid=0x0202,
            serial_number="probe-1",
        ),
    ]
    probed = []
    monkeypatch.setattr(discovery.list_ports, "comports", lambda: ports)
    monkeypatch.setattr(
        discovery,
        "_probe_port",
        lambda device: probed.append(device) or device == "COM220",
    )

    assert discovery.find_mklink_cdc_port(serial_number="probe-1") == "COM220"
    assert probed == ["COM221", "COM220"]


def test_discovery_excludes_a_cmd_port_claimed_by_another_instance(monkeypatch):
    ports = [
        port("COM46", hwid="USB VID:PID=0D28:0202"),
        port("COM47", hwid="USB VID:PID=0D28:0202"),
        port("COM228", hwid="USB VID:PID=0D28:0202"),
    ]
    probed = []
    monkeypatch.setattr(discovery.list_ports, "comports", lambda: ports)
    monkeypatch.setattr(
        discovery,
        "_probe_port",
        lambda device: probed.append(device) or device == "COM228",
    )

    assert discovery.find_mklink_cdc_port(exclude_ports={"com46"}) == "COM228"
    assert probed == ["COM47", "COM228"]


def test_identity_response_rejects_a_generic_target_uart_prompt():
    assert not discovery._is_mklink_identity_response(b"target log\r\n>>> ")
    assert not discovery._is_mklink_identity_response(
        b">>> print('__mklink_probe_7f3a__')\r\n"
    )
    assert discovery._is_mklink_identity_response(
        b">>> print('__mklink_probe_7f3a__')\r\n"
        b"__mklink_probe_7f3a__\r\n>>> "
    )


def test_probe_port_terminates_a_partial_repl_line_before_identity(monkeypatch):
    class ProbeSerial:
        def __init__(self, *_args, timeout, **_kwargs):
            self.timeout = timeout
            self.is_open = True
            self.writes = []
            self.responses = [
                b"SyntaxError: invalid syntax\r\n>>> ",
                (
                    MKLINK_IDENTITY_COMMAND.encode("ascii")
                    + b"\r\n"
                    + MKLINK_IDENTITY_TOKEN.encode("ascii")
                    + b"\r\n>>> "
                ),
            ]

        def reset_input_buffer(self):
            pass

        def reset_output_buffer(self):
            pass

        def write(self, data):
            self.writes.append(data)

        def flush(self):
            pass

        def read_until(self, _expected, _size):
            return self.responses.pop(0)

        def close(self):
            self.is_open = False

    opened = []

    def open_serial(*args, **kwargs):
        instance = ProbeSerial(*args, **kwargs)
        opened.append(instance)
        return instance

    monkeypatch.setattr(discovery.serial, "Serial", open_serial)

    assert discovery._probe_port("TEST_CMD")
    assert opened[0].writes == [
        b"\n",
        (MKLINK_IDENTITY_COMMAND + "\n").encode("ascii"),
    ]


def test_microkeen_disk_reads_volume_labels_without_console_process(monkeypatch):
    monkeypatch.setattr(discovery.os, "name", "nt")
    monkeypatch.setattr(
        discovery.os.path,
        "exists",
        lambda path: path in {"C:\\", "G:\\"},
    )
    labels = []
    monkeypatch.setattr(
        discovery,
        "_windows_volume_label",
        lambda path: labels.append(path) or ("MICROKEEN" if path == "G:\\" else "System"),
    )

    assert discovery.find_microkeen_disk() == "G:\\"
    assert labels == ["C:\\", "G:\\"]


def test_microkeen_disk_accepts_only_a_label_verified_configured_root(monkeypatch):
    monkeypatch.setattr(discovery.os, "name", "nt")
    monkeypatch.setenv("MKLINK_MICROKEEN_DISK", "E:")
    monkeypatch.setattr(discovery.os.path, "isdir", lambda path: path == "E:\\")
    monkeypatch.setattr(
        discovery,
        "_windows_volume_label",
        lambda path: "MICROKEEN" if path == "E:\\" else None,
    )

    assert discovery.find_microkeen_disk() == "E:\\"

    monkeypatch.setattr(discovery, "_windows_volume_label", lambda _path: "OTHER")
    assert discovery.find_microkeen_disk() is None


def _posix_discovery(monkeypatch, *, lsblk=None, roots=None):
    monkeypatch.setattr(discovery.os, "name", "posix")
    monkeypatch.setattr(discovery, "_mount_points_from_lsblk", lambda: lsblk or [])
    monkeypatch.setattr(discovery, "_posix_mount_roots", lambda: roots or [])


def test_microkeen_disk_posix_matches_lsblk_label(monkeypatch, tmp_path):
    mount = tmp_path / "probe-volume"
    mount.mkdir()
    _posix_discovery(
        monkeypatch,
        lsblk=[("microkeen", str(mount)), ("OTHERDATA", str(tmp_path))],
    )

    assert discovery.find_microkeen_disk() == str(mount)


def test_microkeen_disk_posix_scans_mount_roots(monkeypatch, tmp_path):
    base = tmp_path / "media" / "dev"
    mount = base / "MICROKEEN"
    mount.mkdir(parents=True)
    _posix_discovery(monkeypatch, roots=[str(base)])

    assert discovery.find_microkeen_disk() == str(mount)


def test_microkeen_disk_posix_accepts_configured_root(monkeypatch, tmp_path):
    mount = tmp_path / "manual"
    mount.mkdir()
    _posix_discovery(monkeypatch, roots=[])
    monkeypatch.setenv("MKLINK_MICROKEEN_DISK", str(mount) + "/")

    assert discovery.find_microkeen_disk() == str(mount)


def test_microkeen_disk_posix_returns_none_without_matches(monkeypatch):
    _posix_discovery(monkeypatch)
    monkeypatch.delenv("MKLINK_MICROKEEN_DISK", raising=False)

    assert discovery.find_microkeen_disk() is None


def test_lsblk_mount_points_flatten_nested_children():
    payload = {
        "blockdevices": [
            {
                "label": "MICROKEEN",
                "mountpoint": "/media/dev/MICROKEEN",
                "children": [
                    {"label": "", "mountpoint": None},
                ],
            },
            {"label": "root", "mountpoint": "/"},
        ]
    }

    assert discovery._lsblk_mount_points(payload["blockdevices"]) == [
        ("MICROKEEN", "/media/dev/MICROKEEN"),
        ("root", "/"),
    ]


def test_first_usable_mount_prefers_writable_over_readonly(monkeypatch, tmp_path):
    writable = tmp_path / "writable"
    readonly = tmp_path / "readonly"
    writable.mkdir()
    readonly.mkdir()
    def fake_access(path, mode):
        root = str(path).rstrip("/")
        if root == str(writable):
            return True
        if root == str(readonly):
            return not (mode & os.W_OK)
        return False

    monkeypatch.setattr(discovery.os, "access", fake_access)

    assert discovery._first_usable_mount([str(readonly), str(writable)]) == str(
        writable
    )
    assert discovery._first_usable_mount([str(readonly)]) == str(readonly)
    assert discovery._first_usable_mount([]) is None


def test_describe_microkeen_disk_reports_found_volume(monkeypatch, tmp_path):
    mount = tmp_path / "MICROKEEN"
    flm = mount / "FLM"
    flm.mkdir(parents=True)
    _posix_discovery(monkeypatch, lsblk=[("MICROKEEN", str(mount))])

    report = discovery.describe_microkeen_disk()

    assert report["platform"] == "posix"
    assert report["available"] is True
    assert report["reason"] == "found"
    assert report["disk_path"] == str(mount)
    assert report["flm_dir"] == str(flm)
    assert report["writable"] is True
    assert report["candidates"] == [str(mount)]
    assert report["mounted_volumes"] == [str(mount)]


def test_describe_microkeen_disk_reports_no_mount(monkeypatch):
    _posix_discovery(monkeypatch)
    monkeypatch.delenv("MKLINK_MICROKEEN_DISK", raising=False)

    report = discovery.describe_microkeen_disk()

    assert report["available"] is False
    assert report["reason"] == "no-mount"
    assert report["candidates"] == []


def test_describe_microkeen_disk_reports_configured_root_missing(monkeypatch, tmp_path):
    _posix_discovery(monkeypatch)
    monkeypatch.setenv("MKLINK_MICROKEEN_DISK", str(tmp_path / "absent"))

    report = discovery.describe_microkeen_disk()

    assert report["available"] is False
    assert report["reason"] == "configured-root-missing"


def test_describe_microkeen_disk_reports_read_only_volume(monkeypatch, tmp_path):
    mount = tmp_path / "MICROKEEN"
    mount.mkdir()
    _posix_discovery(monkeypatch, lsblk=[("MICROKEEN", str(mount))])
    monkeypatch.setattr(
        discovery.os, "access", lambda path, mode: not (mode & os.W_OK)
    )

    report = discovery.describe_microkeen_disk()

    assert report["available"] is True
    assert report["reason"] == "read-only"
    assert report["writable"] is False


def test_describe_microkeen_disk_windows_reports_not_found(monkeypatch):
    monkeypatch.setattr(discovery.os, "name", "nt")
    monkeypatch.setattr(discovery, "_find_microkeen_disk_windows", lambda: None)
    monkeypatch.delenv("MKLINK_MICROKEEN_DISK", raising=False)

    report = discovery.describe_microkeen_disk()

    assert report["platform"] == "windows"
    assert report["reason"] == "not-found"
