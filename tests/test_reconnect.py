import sys
import types
import unittest
from unittest import mock

import drive_utils


class FakeWin32Cred(types.SimpleNamespace):
    CRED_TYPE_DOMAIN_PASSWORD = 2
    CRED_PERSIST_LOCAL_MACHINE = 2

    def __init__(self):
        super().__init__()
        self.items = {}

    def CredWrite(self, credential, flags):
        self.items[(credential["TargetName"], credential["Type"])] = dict(credential)

    def CredRead(self, target, credential_type, flags):
        return dict(self.items[(target, credential_type)])

    def CredDelete(self, target, credential_type, flags=0):
        del self.items[(target, credential_type)]

    def CredEnumerate(self, filter_value, flags):
        return [dict(value) for value in self.items.values()]


class CredentialTests(unittest.TestCase):
    def test_save_credential_uses_exact_server_without_subprocess(self):
        fake = FakeWin32Cred()
        with mock.patch.dict(sys.modules, {"win32cred": fake}):
            with mock.patch.object(drive_utils.subprocess, "run") as run:
                ok, message = drive_utils.save_windows_credential(
                    "192.168.72.253", r"NAS\user", "secret-value"
                )

        self.assertTrue(ok, message)
        saved = fake.items[("192.168.72.253", 2)]
        self.assertEqual(saved["UserName"], r"NAS\user")
        self.assertEqual(saved["CredentialBlob"], "secret-value")
        run.assert_not_called()
        self.assertNotIn("secret-value", message)

    def test_save_credential_requires_complete_input(self):
        ok, message = drive_utils.save_windows_credential("server", "", "secret")
        self.assertFalse(ok)
        self.assertIn("用户名和密码", message)


class DiagnosisTests(unittest.TestCase):
    def diagnose(self, *, persistent=True, credentials=None, identities=None, port=True):
        credentials = credentials if credentials is not None else [
            {"target": "192.168.72.253", "username": r"NAS\user", "exact": True}
        ]
        identities = identities if identities is not None else [
            {"UserName": r"NAS\user"}
        ]
        patches = [
            mock.patch.object(drive_utils, "drive_to_unc", return_value=r"\\192.168.72.253\data"),
            mock.patch.object(drive_utils, "_persistent_mapping_details",
                              return_value=(persistent, r"\\192.168.72.253\data")),
            mock.patch.object(drive_utils, "_credential_details_for_server",
                              return_value=credentials),
            mock.patch.object(drive_utils, "_get_smb_connections_for_server",
                              return_value=(identities, "")),
            mock.patch.object(drive_utils, "_tcp_port_open", return_value=port),
            mock.patch.object(drive_utils, "get_mapped_drives",
                              return_value=[("Z:", r"\\192.168.72.253\data")]),
        ]
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            return drive_utils.diagnose_drive_reconnect("Z:")

    def test_healthy_mapping(self):
        ok, diagnosis = self.diagnose()
        self.assertTrue(ok)
        self.assertTrue(diagnosis.healthy)
        self.assertTrue(diagnosis.credential_target_match)

    def test_missing_credential_and_nonpersistent_mapping(self):
        ok, diagnosis = self.diagnose(persistent=False, credentials=[])
        self.assertTrue(ok)
        self.assertFalse(diagnosis.healthy)
        self.assertTrue(any("持久映射" in issue for issue in diagnosis.issues))
        self.assertTrue(any("Windows 凭据" in issue for issue in diagnosis.issues))

    def test_identity_mismatch_and_closed_port(self):
        ok, diagnosis = self.diagnose(
            identities=[{"UserName": r"NAS\other"}],
            port=False,
        )
        self.assertTrue(ok)
        self.assertEqual(diagnosis.conflicting_identities, [r"NAS\other"])
        self.assertTrue(any("1219" in issue for issue in diagnosis.issues))
        self.assertTrue(any("445" in issue for issue in diagnosis.issues))


class AddAndRepairTests(unittest.TestCase):
    def test_disconnect_for_repair_forces_open_drive(self):
        with mock.patch.object(
            drive_utils,
            "disconnect_drive",
            side_effect=[
                (False, "驱动器 Z: 有文件正在使用，请关闭相关文件后重试"),
                (True, "已断开驱动器 Z:"),
            ],
        ) as disconnect:
            ok, message = drive_utils._disconnect_drive_for_repair("Z:")

        self.assertTrue(ok)
        self.assertIn("已强制断开", message)
        self.assertEqual(disconnect.call_args_list, [
            mock.call("Z:", force=False),
            mock.call("Z:", force=True),
        ])

    def test_add_requires_credentials_when_save_selected(self):
        ok, message = drive_utils.add_network_drive_or_location(
            r"\\server\share",
            mode="drive",
            drive_letter="Z:",
            username="user",
            password="",
            save_credential=True,
        )
        self.assertFalse(ok)
        self.assertIn("用户名和密码", message)

    def test_repair_restores_old_credential_when_mapping_fails(self):
        diagnosis = drive_utils.DriveReconnectDiagnosis(
            drive_letter="Z:",
            unc_path=r"\\server\share",
            server="server",
            persistent=True,
        )
        old = {"TargetName": "server", "Type": 2, "UserName": "old"}
        map_results = [
            (False, "new mapping failed"),
            (True, "old mapping restored"),
        ]
        with (
            mock.patch.object(drive_utils, "diagnose_drive_reconnect",
                              return_value=(True, diagnosis)),
            mock.patch.object(drive_utils, "_read_windows_credential", return_value=old),
            mock.patch.object(drive_utils, "_disconnect_drive_for_repair",
                              return_value=(True, "disconnected")),
            mock.patch.object(drive_utils, "disconnect_server_sessions",
                              return_value=(True, "sessions cleared", [])),
            mock.patch.object(drive_utils, "save_windows_credential",
                              return_value=(True, "credential saved")),
            mock.patch.object(drive_utils, "map_network_drive_with_credentials",
                              side_effect=map_results),
            mock.patch.object(drive_utils, "_restore_windows_credential",
                              return_value=True) as restore,
        ):
            ok, message = drive_utils.repair_drive_reconnect(
                "Z:", "new-user", "new-password"
            )

        self.assertFalse(ok)
        restore.assert_called_once_with("server", old)
        self.assertIn("old mapping restored", message)
        self.assertNotIn("new-password", message)


if __name__ == "__main__":
    unittest.main()
