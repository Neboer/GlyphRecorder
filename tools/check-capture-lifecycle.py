#!/usr/bin/env python3
"""Run the debug-only capture probe on an attached rooted phone without installing it.

Usage: python3 tools/check-capture-lifecycle.py path/to/debug.apk
Requires an unlocked phone, root ADB authorization, and no active screen mirroring.
"""
import pathlib
import shlex
import subprocess
import sys
import tempfile
import time

CLASS = 'dev.aaa1115910.glyphrecorder.diagnostics.CaptureLifecycleProbe'
REMOTE = '/data/local/tmp/glyph-lifecycle-probe.apk'


def adb(*args):
    return subprocess.check_output(['adb', *args], text=True)


def displays():
    return adb('shell', 'dumpsys', 'display').count('DisplayDeviceInfo{"scrcpy"')


def wait_for(predicate, description, timeout=20):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(.2)
    raise AssertionError(description)


def kill_probe(name):
    # Select only our dedicated test process, never a production capture service.
    rows = adb('shell', 'ps', '-A', '-o', 'PID,NAME').splitlines()[1:]
    for row in rows:
        pid, process = row.split(maxsplit=1)
        if process == name:
            adb('shell', 'su', '-c', f'kill -TERM {int(pid)}')


def launch(mode, log):
    name = f'glyph-lifecycle-probe-{mode}'
    cmd = f'CLASSPATH={REMOTE} app_process /system/bin --nice-name={name} {CLASS} {mode}'
    return subprocess.Popen(['adb', 'shell', 'su', '-c', cmd], stdout=log, stderr=subprocess.STDOUT)


def main():
    assert len(sys.argv) == 2, __doc__
    assert displays() == 0, 'Stop active mirroring / clean existing leaked displays before testing'
    subprocess.run(['adb', 'push', sys.argv[1], REMOTE], check=True)
    try:
        with tempfile.TemporaryDirectory() as temp:
            temp = pathlib.Path(temp)
            for mode in ['cycles', 'death']:
                server_log = temp / f'{mode}-server.log'
                client_log = temp / f'{mode}-client.log'
                with server_log.open('w') as log:
                    server = launch('server', log)
                wait_for(lambda: 'SERVER_READY' in server_log.read_text(),
                         'Server failed to start: ' + str(server_log))
                with client_log.open('w') as log:
                    client = launch(mode, log)
                if mode == 'cycles':
                    code = client.wait(timeout=60)
                    assert code == 0, client_log.read_text()
                    assert 'CYCLES_PASSED' in client_log.read_text(), client_log.read_text()
                else:
                    wait_for(lambda: 'CLIENT_READY' in client_log.read_text(),
                             'Client failed to start capture')
                    assert displays() == 1, 'Capture must create exactly one display'
                    kill_probe('glyph-lifecycle-probe-death')
                    client.wait(timeout=20)
                server.wait(timeout=20)
                wait_for(lambda: displays() == 0, 'Capture display leaked after ' + mode)
                print(f'PASS {mode}: server exited and no capture displays remain')
    finally:
        for mode in ['server', 'cycles', 'death']:
            kill_probe(f'glyph-lifecycle-probe-{mode}')
        adb('shell', 'rm', '-f', REMOTE)


if __name__ == '__main__':
    main()
