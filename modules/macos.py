import glob
import os
import tarfile

from pygemstones.io import file as f
from pygemstones.system import runner as r
from pygemstones.util import log as l

import modules.config as c
import modules.pdfium as p


# -----------------------------------------------------------------------------
def run_task_build_pdfium():
    p.get_pdfium_by_target("macos")


# -----------------------------------------------------------------------------
def run_task_patch():
    l.colored("Patching files...", l.YELLOW)

    source_dir = os.path.join("build", "macos", "pdfium")

    # zlib
    source_file = os.path.join(
        source_dir,
        "third_party",
        "zlib",
        "BUILD.gn",
    )

    line_content = "use_arm_neon_optimizations = false"
    line_number = f.get_file_line_number_with_content(
        source_file, line_content, strip=True
    )

    if line_number:
        content = 'use_arm_neon_optimizations = (current_cpu == "arm" || current_cpu == "arm64")'
        f.set_file_line_content(source_file, line_number, content, new_line=True)
        l.bullet("Applied: zlib", l.GREEN)
    else:
        l.bullet("Skipped: zlib", l.PURPLE)

    # zlib - skia
    source_file = os.path.join(
        source_dir,
        "third_party",
        "skia",
        "third_party",
        "zlib",
        "BUILD.gn",
    )

    line_content = (
        '(current_cpu == "arm" || current_cpu == "arm64") && !(is_win && !is_clang)'
    )
    line_number = f.get_file_line_number_with_content(
        source_file, line_content, strip=True
    )

    if line_number:
        content = '(current_cpu == "arm" || current_cpu == "arm64")'
        f.set_file_line_content(source_file, line_number, content, new_line=True)
        l.bullet("Applied: skia - zlib", l.GREEN)
    else:
        l.bullet("Skipped: skia - zlib", l.PURPLE)

    l.ok()


# -----------------------------------------------------------------------------
def run_task_build():
    l.colored("Building libraries...", l.YELLOW)

    current_dir = f.current_dir()

    # configs
    for config in c.configurations_macos:
        # targets
        for target in c.targets_macos:
            main_dir = os.path.join(
                "build",
                target["target_os"],
                "pdfium",
                "out",
                "{0}-{1}-{2}".format(target["target_os"], target["target_cpu"], config),
            )

            f.recreate_dir(main_dir)

            os.chdir(
                os.path.join(
                    "build",
                    target["target_os"],
                    "pdfium",
                )
            )

            # generating files...
            l.colored(
                'Generating files to arch "{0}" and configuration "{1}"...'.format(
                    target["target_cpu"], config
                ),
                l.YELLOW,
            )

            arg_is_debug = "true" if config == "debug" else "false"

            args = []
            args.append('target_os="{0}"'.format(target["pdfium_os"]))
            args.append('target_cpu="{0}"'.format(target["target_cpu"]))
            args.append("use_goma=false")
            args.append("is_debug={0}".format(arg_is_debug))
            args.append("pdf_use_skia=false")
            args.append("pdf_use_skia_paths=false")
            args.append("pdf_enable_xfa=false")
            args.append("pdf_enable_v8=false")
            args.append("is_component_build=false")
            args.append("clang_use_chrome_plugins=false")
            args.append("pdf_is_standalone=true")
            args.append("use_xcode_clang=false")
            args.append("pdf_is_complete_lib=true")
            args.append("use_custom_libcxx=false")
            args.append("use_sysroot=false")

            if config == "release":
                args.append("symbol_level=0")

            args_str = " ".join(args)

            command = [
                "gn",
                "gen",
                "out/{0}-{1}-{2}".format(
                    target["target_os"], target["target_cpu"], config
                ),
                "--args='{0}'".format(args_str),
            ]
            r.run_as_shell(" ".join(command))

            # generate an Xcode project
            command = [
                "gn",
                "gen",
                "out/{0}-{1}-{2}".format(
                    target["target_os"], target["target_cpu"], config
                ),
                "--ide=xcode",
            ]
            r.run_as_shell(" ".join(command))
            
            # compiling...
            l.colored(
                'Compiling to arch "{0}" and configuration "{1}"...'.format(
                    target["target_cpu"], config
                ),
                l.YELLOW,
            )

            command = [
                "ninja",
                "-C",
                "out/{0}-{1}-{2}".format(
                    target["target_os"], target["target_cpu"], config
                ),
                "pdfium",
                "-v",
            ]
            r.run(command)

            os.chdir(current_dir)

    l.ok()


# -----------------------------------------------------------------------------
def run_task_install():
    l.colored("Installing libraries...", l.YELLOW)

    # configs
    for config in c.configurations_macos:
        f.recreate_dir(os.path.join("build", "macos", config))
        f.create_dir(os.path.join("build", "macos", config, "lib"))

        # targets
        for target in c.targets_macos:
            source_lib_path = os.path.join(
                "build",
                target["target_os"],
                "pdfium",
                "out",
                "{0}-{1}-{2}".format(target["target_os"], target["target_cpu"], config),
                "obj",
                "libpdfium.a",
            )

            target_lib_path = os.path.join(
                "build",
                target["target_os"],
                config,
                "lib",
                "libpdfium_{0}.a".format(target["target_cpu"]),
            )

            f.copy_file(source_lib_path, target_lib_path)

        # universal
        folder = os.path.join("build", "macos", config, "lib", "*.a")
        files = glob.glob(folder)
        files_str = " ".join(files)
        lib_file_out = os.path.join("build", "macos", config, "lib", "libpdfium.a")

        l.colored("Merging libraries (lipo)...", l.YELLOW)
        command = ["lipo", "-create", files_str, "-o", lib_file_out]
        r.run_as_shell(" ".join(command))

        l.colored("File data...", l.YELLOW)
        command = ["file", lib_file_out]
        r.run_as_shell(" ".join(command))

        l.colored("File size...", l.YELLOW)
        command = ["ls", "-lh ", lib_file_out]
        r.run_as_shell(" ".join(command))

        # include
        include_dir = os.path.join("build", "macos", "pdfium", "public")
        target_include_dir = os.path.join("build", "macos", config, "include")

        f.recreate_dir(target_include_dir)

        for basename in os.listdir(include_dir):
            if basename.endswith(".h"):
                pathname = os.path.join(include_dir, basename)

                if os.path.isfile(pathname):
                    f.copy_file(pathname, os.path.join(target_include_dir, basename))

    l.ok()


# -----------------------------------------------------------------------------
def run_task_test():
    l.colored("Testing...", l.YELLOW)

    current_dir = os.getcwd()
    sample_dir = os.path.join(current_dir, "sample")
    build_dir = os.path.join(sample_dir, "build")

    f.recreate_dir(build_dir)

    os.chdir(build_dir)

    # generate project
    command = ["cmake", "../"]
    r.run(command)

    # build
    command = ["cmake", "--build", "."]
    r.run(command)

    # copy assets
    f.copy_file(
        os.path.join(sample_dir, "assets", "f1.pdf"),
        os.path.join(build_dir, "f1.pdf"),
    )

    # run
    command = ["./sample"]
    r.run(command)

    # finish
    os.chdir(current_dir)

    l.ok()


# -----------------------------------------------------------------------------
def run_task_archive():
    l.colored("Archiving...", l.YELLOW)

    current_dir = f.current_dir()
    lib_dir = os.path.join(current_dir, "build", "macos")
    output_filename = os.path.join(current_dir, "macos.tgz")

    tar = tarfile.open(output_filename, "w:gz")

    for configuration in c.configurations_macos:
        tar.add(
            name=os.path.join(lib_dir, configuration),
            arcname=os.path.basename(os.path.join(lib_dir, configuration)),
            filter=lambda x: (
                None if "_" in x.name and not x.name.endswith(".h") else x
            ),
        )

    tar.close()

    l.ok()
