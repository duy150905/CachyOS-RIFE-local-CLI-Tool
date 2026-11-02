import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rife_cli import cli, common, installer  # noqa: E402

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
FAKE = Path(__file__).with_name("fake_rife.py")


class UnitTests(unittest.TestCase):
    def test_parse_rate(self):
        self.assertEqual(common.parse_rate("30000/1001"), Fraction(30000, 1001))
        self.assertIsNone(common.parse_rate("0/0"))
        self.assertIsNone(common.parse_rate(None))

    def test_format_fps(self):
        self.assertEqual(common.format_fps(Fraction(60)), "60")
        self.assertEqual(common.format_fps(Fraction(60000, 1001)), "59.94")

    def test_asset_url_linux(self):
        with mock.patch.object(common, "IS_LINUX", True):
            url = installer.asset_url()
        self.assertTrue(url.endswith("-ubuntu.zip"))
        self.assertIn("nihui/rife-ncnn-vulkan/releases/download", url)

    def test_asset_url_rejects_non_linux(self):
        with mock.patch.object(common, "IS_LINUX", False):
            with self.assertRaises(common.RifeCliError):
                installer.asset_url()

    def test_install_hints_use_yay(self):
        self.assertEqual(common.ffmpeg_install_hint(), "yay -S ffmpeg")
        hint = common.vulkan_install_hint()
        for pkg in ("yay -S", "vulkan-icd-loader", "vulkan-tools", "vulkan-radeon", "nvidia-utils", "vulkan-intel"):
            self.assertIn(pkg, hint)
        self.assertNotIn("pacman", hint)

    def test_shared_lib_hint(self):
        self.assertEqual(common.shared_lib_hint(["libvulkan.so.1"]), "yay -S vulkan-icd-loader")
        self.assertEqual(common.shared_lib_hint(["libgomp.so.1", "libstdc++.so.6"]), "yay -S gcc-libs")

    def test_home_dir_override(self):
        with mock.patch.dict(os.environ, {"RIFE_CLI_HOME": "/tmp/x"}):
            self.assertEqual(common.home_dir(), Path("/tmp/x"))

    def test_cli_help_lists_tools(self):
        text = cli.build_parser().format_help()
        for name in ("interpolate", "setup", "doctor"):
            self.assertIn(name, text)


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg not installed")
class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        # fake rife launcher + fake model
        launcher = self.tmp / "fake-rife"
        launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n')
        launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)
        model = self.tmp / "models" / "fake-model"
        model.mkdir(parents=True)
        (model / "flownet.param").write_text("x")
        self.env = mock.patch.dict(os.environ, {"RIFE_NCNN_VULKAN": str(launcher),
                                                "RIFE_CLI_MODELS": str(self.tmp / "models")})
        self.env.start()
        self.addCleanup(self.env.stop)
        # 1 second, 10 fps test video with audio
        self.src = self.tmp / "src.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=128x72:rate=10:duration=1",
                        "-f", "lavfi", "-i", "sine=duration=1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-shortest", str(self.src)], check=True)

    def _probe(self, path):
        out = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                              "-show_entries", "stream=nb_read_frames,avg_frame_rate", "-of", "json",
                              str(path)], stdout=subprocess.PIPE, universal_newlines=True, check=True)
        s = json.loads(out.stdout)["streams"][0]
        return int(s["nb_read_frames"]), Fraction(s["avg_frame_rate"])

    def _run(self, *extra):
        out = self.tmp / "out.mp4"
        code = cli.main(["interpolate", "-i", str(self.src), "-o", str(out), "-m", "fake-model", "-y", *extra])
        self.assertEqual(code, 0)
        self.assertTrue(out.is_file())
        # no temp folders left behind
        self.assertEqual([p for p in self.tmp.iterdir() if p.name.startswith(".rife-cli-")], [])
        return out

    def test_x2(self):
        frames, fps = self._probe(self._run())
        self.assertEqual((frames, fps), (20, 20))

    def test_x4_two_passes(self):
        frames, fps = self._probe(self._run("-x", "4"))
        self.assertEqual((frames, fps), (40, 40))

    def test_loop_keeps_exact_count(self):
        frames, fps = self._probe(self._run("--loop"))
        self.assertEqual((frames, fps), (20, 20))

    def test_jpg_and_target_fps(self):
        frames, fps = self._probe(self._run("--frame-format", "jpg", "--target-fps", "10"))
        self.assertEqual(fps, 10)

    def test_audio_kept_by_default(self):
        out = self._run()
        res = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                              "stream=codec_name", "-of", "csv=p=0", str(out)],
                             stdout=subprocess.PIPE, universal_newlines=True)
        self.assertIn("aac", res.stdout)

    def test_refuses_to_overwrite(self):
        out = self.tmp / "exists.mp4"
        out.write_text("x")
        code = cli.main(["interpolate", "-i", str(self.src), "-o", str(out), "-m", "fake-model"])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
