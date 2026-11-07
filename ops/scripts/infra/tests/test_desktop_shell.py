"""Desktop Shell 启动适配（Electron 单壳）的纯逻辑单测。

不拉起进程、不碰端口；命令构造与 env 组装在假目录树上验证。
"""
import sys
import unittest.mock as mock
from pathlib import Path

import pytest

NATIVE_DIR = Path(__file__).resolve().parents[1] / 'windows' / 'native'
sys.path.insert(0, str(NATIVE_DIR))

import desktop_shell  # noqa: E402


def make_fake_root(tmp_path):
    """构造带 Electron CLI 占位文件的假仓库根目录。"""
    root = tmp_path / 'repo'
    cli = root / 'apps/desktop/electron/node_modules/electron/cli.js'
    cli.parent.mkdir(parents=True)
    cli.write_text('// placeholder\n', encoding='utf-8')
    return root


class TestShellSelection:
    def test_default_is_electron(self):
        assert desktop_shell.current_shell({}) == 'electron'
        assert desktop_shell.current_shell({'KINLIN_DESKTOP_SHELL': ''}) == 'electron'

    def test_electron_selected_and_normalized(self):
        assert desktop_shell.current_shell({'KINLIN_DESKTOP_SHELL': 'electron'}) == 'electron'
        assert desktop_shell.current_shell({'KINLIN_DESKTOP_SHELL': ' Electron '}) == 'electron'

    def test_tauri_removed_and_fails_loudly(self):
        with pytest.raises(RuntimeError):
            desktop_shell.current_shell({'KINLIN_DESKTOP_SHELL': 'tauri'})

    def test_unknown_shell_fails_loudly(self):
        with pytest.raises(RuntimeError):
            desktop_shell.current_shell({'KINLIN_DESKTOP_SHELL': 'webview2'})

    def test_frontend_mode_and_window_classes(self):
        assert desktop_shell.frontend_mode('electron') == 'electron'
        assert 'Chrome_WidgetWin_1' in desktop_shell.window_classes('electron')
        with pytest.raises(RuntimeError):
            desktop_shell.frontend_mode('tauri')


class TestDesktopCommand:
    def test_electron_command_shape(self, tmp_path):
        root = make_fake_root(tmp_path)
        with mock.patch.object(desktop_shell.shutil, 'which', return_value='node.exe'):
            command, cwd = desktop_shell.desktop_command(root, 'electron', 'http://127.0.0.1:15200')
        assert command[1] == str(root / 'apps/desktop/electron/node_modules/electron/cli.js')
        assert '--dev-server=http://127.0.0.1:15200' in command
        assert '--remote-debugging-port=19222' in command
        assert cwd == root / 'apps/desktop/electron'

    def test_port_offset_environments_override_debug_port(self, tmp_path):
        root = make_fake_root(tmp_path)
        with mock.patch.object(desktop_shell.shutil, 'which', return_value='node.exe'):
            command, _ = desktop_shell.desktop_command(root, 'electron', 'http://127.0.0.1:15210',
                                                       debug_port=19223)
        assert '--remote-debugging-port=19223' in command

    def test_missing_runtime_fails_with_install_hint(self, tmp_path):
        root = tmp_path / 'repo'
        with mock.patch.object(desktop_shell.shutil, 'which', return_value='node.exe'):
            with pytest.raises(RuntimeError, match='apps/desktop/electron'):
                desktop_shell.desktop_command(root, 'electron', 'http://127.0.0.1:15200')

    def test_missing_node_fails(self, tmp_path):
        root = make_fake_root(tmp_path)
        with mock.patch.object(desktop_shell.shutil, 'which', return_value=None):
            with pytest.raises(RuntimeError, match='node'):
                desktop_shell.desktop_command(root, 'electron', 'http://127.0.0.1:15200')


class TestDesktopEnv:
    BASE = {'PATH': 'C:/windows', 'SYSTEMROOT': 'C:/windows'}

    def test_electron_env_is_restricted_copy(self):
        env = desktop_shell.desktop_env('electron', self.BASE)
        assert env == self.BASE
        assert 'WEBVIEW2_USER_DATA_FOLDER' not in env
        assert 'CARGO_HOME' not in env

    def test_unknown_shell_rejected(self):
        with pytest.raises(RuntimeError):
            desktop_shell.desktop_env('tauri', self.BASE)


class TestRuntimeWiring:
    """两个 runtime 对 desktop_shell 的接线：导入即验证签名兼容。"""

    def test_desktop_runtime_defaults_to_electron_window_classes(self):
        import desktop_runtime
        assert desktop_runtime.show_desktop.__defaults__ == (desktop_shell.ELECTRON_WINDOW_CLASSES,)
        assert desktop_runtime.close_desktop.__defaults__ == (desktop_shell.ELECTRON_WINDOW_CLASSES,)

    def test_persistent_runtime_defaults_cors_to_include_electron_origin(self):
        import persistent_runtime
        source = (NATIVE_DIR / 'persistent_runtime.py').read_text(encoding='utf-8')
        creds = {'token': 't', 'key': 'k', 'hmac': 'h', 'deepseek': 'd',
                 'db': 'db', 'redis': 'r', 'jwt': 'j'}
        origins = persistent_runtime.backend_environment(
            Path('C:/home'), {'workspace': 'C:/home/workspace'}, creds)['ZHIYI_BACKEND_TS_DEV_ORIGIN']
        assert 'http://127.0.0.1:15200' in origins
        assert 'tauri' not in origins
        assert 'desktop_shell.window_classes' in source

    def test_persistent_runtime_cors_and_debug_port_follow_port_offset(self):
        import persistent_runtime
        creds = {'token': 't', 'key': 'k', 'hmac': 'h', 'deepseek': 'd',
                 'db': 'db', 'redis': 'r', 'jwt': 'j'}
        info = {'workspace': 'C:/home/workspace', 'portOffset': 10}
        origins = persistent_runtime.backend_environment(Path('C:/home'), info, creds)['ZHIYI_BACKEND_TS_DEV_ORIGIN']
        assert 'http://127.0.0.1:15210' in origins
        assert 'http://127.0.0.1:15200' not in origins
        assert persistent_runtime.ports(info)['debug'] == 19232


def test_ready_check_returns_callable():
    probe = desktop_shell.ready_check()
    assert callable(probe)


def test_ready_check_uses_offset_debug_port():
    import native_runtime as native
    with mock.patch.object(native, 'health', return_value={'ok': True}) as health:
        probe = desktop_shell.ready_check(19223)
        assert probe()
    health.assert_called_once_with(19223, '/json/version')
