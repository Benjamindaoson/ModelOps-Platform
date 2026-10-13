"""Hold the project/shared GPU lease for an owned serving process group."""
import argparse,subprocess
from ops.gpu_lease import gpu_lease
p=argparse.ArgumentParser();p.add_argument("command",nargs=argparse.REMAINDER)
a=p.parse_args();cmd=a.command[1:] if a.command[:1]==["--"] else a.command
if not cmd:raise SystemExit("Expected command")
with gpu_lease():raise SystemExit(subprocess.run(cmd).returncode)
