"""Compile four UNO variants plus all unit sketches, enforcing stated RAM/flash budgets."""

import argparse
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cli")
    p.add_argument("--config")
    args = p.parse_args()
    local = ROOT / "build/arduino-cli/arduino-cli.exe"
    cli = (
        args.cli
        or shutil.which("arduino-cli")
        or (str(local) if local.exists() else None)
    )
    if not cli:
        raise SystemExit(
            "Install arduino-cli and AVR core 1.8.6 / MFRC522 1.4.12 first"
        )
    config = Path(args.config) if args.config else ROOT / "build/arduino-cli.json"
    base = (
        [cli, "compile"]
        + (["--config-file", str(config)] if config.exists() else [])
        + ["--fqbn", "arduino:avr:uno"]
    )

    def compile_one(path, label, flags="", budget=False):
        command = base + ["--output-dir", str(ROOT / "build/firmware-v2" / label)]
        if flags:
            command += ["--build-property", "compiler.cpp.extra_flags=" + flags]
        result = subprocess.run(command + [str(path)], capture_output=True, text=True)
        print(label, flush=True)
        print(result.stdout, flush=True)
        if result.returncode:
            print(result.stderr)
            raise SystemExit(result.returncode)
        if budget:
            flash = re.search(r"Sketch uses (\d+)", result.stdout)
            ram = re.search(r"Global variables use (\d+)", result.stdout)
            if not flash or not ram:
                raise SystemExit(
                    "Cannot parse compiler sizes; inspect output, do not assume budgets"
                )
            if int(flash[1]) >= 24 * 1024 or int(ram[1]) > 1100:
                raise SystemExit("Firmware exceeds v2 flash/RAM budget")

    for readers in [1, 2]:
        for active in [1, 0]:
            compile_one(
                ROOT / "firmware/arduino_gate",
                f"reader{readers}-" + ("active" if active else "passive"),
                f"-DREADER_COUNT={readers} -DBUZZER_ACTIVE={active}",
                True,
            )
    for sketch in sorted((ROOT / "firmware/tests").glob("*.ino")):
        directory = ROOT / "build/firmware-sketch-tests" / sketch.stem
        directory.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(sketch, directory / sketch.name)
        if sketch.stem == "eeprom_test":
            shutil.copyfile(
                ROOT / "firmware/tests/hash_vectors.h", directory / "hash_vectors.h"
            )
            shutil.copyfile(
                ROOT / "firmware/arduino_gate/protocol_core.h",
                directory / "protocol_core.h",
            )
        compile_one(directory, sketch.stem)
    print(
        "PASS: four main variants within budgets; all six unit sketches compile. Nothing flashed."
    )


if __name__ == "__main__":
    main()
