"""CPU / GPU temperature readers (Linux hwmon + nvidia-smi)."""
import glob
import os
import shutil
import subprocess

# hwmon driver name -> preferred temperature label (None = first input)
CPU_HWMON = {
    "k10temp": "Tctl",        # AMD Zen
    "zenpower": "Tdie",       # AMD Zen (out-of-tree driver)
    "coretemp": "Package id 0",  # Intel
    "cpu_thermal": None,      # ARM SoCs
}
# Integrated GPUs share the CPU die; only treat amdgpu cards with at least this much VRAM as discrete
DISCRETE_VRAM_MIN = 3 * 1024 ** 3


def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def _hwmon_temp(hwmon_dir, label):
    inputs = sorted(glob.glob(os.path.join(hwmon_dir, "temp*_input")))
    if label is not None:
        for inp in inputs:
            if _read(inp.replace("_input", "_label")) == label:
                return inp
    return inputs[0] if inputs else None


def find_cpu_sensor(sysfs="/sys"):
    for hwmon in sorted(glob.glob(os.path.join(sysfs, "class/hwmon/hwmon*"))):
        name = _read(os.path.join(hwmon, "name"))
        if name in CPU_HWMON:
            path = _hwmon_temp(hwmon, CPU_HWMON[name])
            if path:
                return path
    return None


def find_amd_gpu_sensors(sysfs="/sys"):
    paths = []
    for hwmon in sorted(glob.glob(os.path.join(sysfs, "class/hwmon/hwmon*"))):
        if _read(os.path.join(hwmon, "name")) != "amdgpu":
            continue
        vram = _read(os.path.join(hwmon, "device/mem_info_vram_total"))
        if vram is None or int(vram) < DISCRETE_VRAM_MIN:
            continue
        path = _hwmon_temp(hwmon, "junction") or _hwmon_temp(hwmon, "edge")
        if path:
            paths.append(path)
    return paths


def read_millideg(path):
    raw = _read(path) if path else None
    try:
        return int(raw) / 1000
    except (TypeError, ValueError):
        return None


class Sensors:
    def __init__(self, sysfs="/sys"):
        self.cpu_path = find_cpu_sensor(sysfs)
        self.amd_gpu_paths = find_amd_gpu_sensors(sysfs)
        self.nvidia_smi = shutil.which("nvidia-smi")

    def cpu(self):
        return read_millideg(self.cpu_path)

    def gpu(self):
        temps = [t for t in (read_millideg(p) for p in self.amd_gpu_paths) if t is not None]
        if self.nvidia_smi:
            try:
                out = subprocess.run(
                    [self.nvidia_smi, "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=3,
                ).stdout
                temps += [float(x) for x in out.split()]
            except (OSError, ValueError, subprocess.SubprocessError):
                pass
        return max(temps) if temps else None

    def describe(self):
        return {
            "cpu": self.cpu_path,
            "gpu": self.amd_gpu_paths + (["nvidia-smi"] if self.nvidia_smi else []),
        }


class Overheat:
    """Hysteresis state machine: on at >= hot, off once every reading is below hot - hysteresis."""

    def __init__(self):
        self.active = False

    def update(self, cpu, gpu, cpu_hot, gpu_hot, hysteresis):
        hot = (cpu is not None and cpu >= cpu_hot) or (gpu is not None and gpu >= gpu_hot)
        cool = ((cpu is None or cpu < cpu_hot - hysteresis)
                and (gpu is None or gpu < gpu_hot - hysteresis))
        if not self.active and hot:
            self.active = True
            return True
        if self.active and cool:
            self.active = False
            return True
        return False
