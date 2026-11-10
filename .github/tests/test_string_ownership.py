"""Compile the bundled SDK/helpers and the actual callback body, without a 4D host."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(sys.platform == "darwin", "bundled SDK requires macOS frameworks")
class StringOwnershipTests(unittest.TestCase):
    def test_engine_shim(self):
        revision = os.environ.get("OWNERSHIP_SOURCE_REVISION")

        def source_text(path):
            if revision:
                return subprocess.run(
                    ["git", "show", f"{revision}:{path}"], cwd=ROOT, check=True,
                    stdout=subprocess.PIPE, text=True).stdout
            return (ROOT / path).read_text()

        source = source_text("4DPlugin.cpp")
        start = source.index("void listenerLoopExecuteMethod()\n{")
        end = source.index("\n#pragma mark -", start)
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            callback = directory / "callback.mm"
            callback.write_text(
                '#include "4DPluginAPI.h"\n'
                '#include "4DPlugin.h"\n'
                "namespace SR { C_TEXT LISTENER_METHOD; "
                "std::vector<CUTF16String> RECOGNIZED_COMMANDS; }\n"
                + source[start:end]
            )
            sdk = ROOT / "4D Plugin API"
            picture = directory / "C_PICTURE.cpp"
            picture.write_text(source_text("4D Plugin API/Classes/C_PICTURE.cpp"))
            binary = directory / "ownership"
            compilation = subprocess.run([
                "xcrun", "clang++", "-std=c++11", "-x", "objective-c++",
                "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-g",
                "-Wno-deprecated-declarations", "-Wno-ignored-attributes",
                "-include", "Carbon/Carbon.h", "-I", str(sdk),
                "-I", str(sdk / "Classes"),
                "-I", str(ROOT), "-I", str(ROOT / "include"),
                str(ROOT / ".github/tests/string_ownership.mm"), str(callback),
                str(sdk / "4DPluginAPI.c"), str(picture),
                *(str(sdk / "Classes" / name) for name in (
                    "C_TEXT.cpp", "C_BLOB.cpp", "ARRAY_TEXT.cpp")),
                "-framework", "Cocoa", "-framework", "Carbon",
                "-o", str(binary),
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertEqual(compilation.returncode, 0,
                             compilation.stdout + compilation.stderr)
            environment = dict(os.environ, ASAN_OPTIONS="detect_leaks=0",
                               UBSAN_OPTIONS="halt_on_error=1")
            for empty in ("allocated", "null"):
                for case in ("method", "command", "path", "copy", "array"):
                    with self.subTest(empty=empty, case=case):
                        result = subprocess.run(
                            [str(binary), empty, case], env=environment,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                        self.assertEqual(result.returncode, 0,
                                         result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
