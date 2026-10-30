from pathlib import Path

from pythonforandroid.recipes.pygame import Pygame2Recipe
from pythonforandroid.toolchain import current_directory


class Pygame261Recipe(Pygame2Recipe):
    version = "2.6.1"
    url = "https://github.com/pygame/pygame/archive/{version}.tar.gz"
    hostpython_prerequisites = ["setuptools", "cython>=3.1"]

    def prebuild_arch(self, arch):
        super().prebuild_arch(arch)

        with current_directory(self.get_build_dir(arch.arch)):
            for file in Path(".").rglob("_sprite.pyx"):
                file.unlink()

            template = Path("buildconfig/Setup.Android.SDL2.in")
            if not template.exists():
                raise RuntimeError("Android SDL2 template not found")

            lines = template.read_text(encoding="utf-8").splitlines()
            result = []

            for line in lines:
                if line.lstrip().startswith("_sprite "):
                    continue

                if line.lstrip().startswith("surface "):
                    line += " src_c/simd_blitters_sse2.c src_c/simd_blitters_avx2.c"

                result.append(line)

            template.write_text("\n".join(result) + "\n", encoding="utf-8")


recipe = Pygame261Recipe()
