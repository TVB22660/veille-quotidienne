#!/usr/bin/env python3
"""Script de sondage TEMPORAIRE : fait tourner le moteur Divinum Officium (Perl) sur le robot."""
import os
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo

now = datetime.now(ZoneInfo("Europe/Paris"))
DATE = f"{now.month}-{now.day}-{now.year}"
out = []


def run(cmd, cwd=None, env=None, timeout=600, head=3000):
    out.append(f"$ {cmd}")
    try:
        p = subprocess.run(cmd, shell=True, cwd=cwd, env=env, capture_output=True,
                           text=True, timeout=timeout)
        out.append(f"[code {p.returncode}]")
        if p.stdout.strip():
            out.append("--- stdout ---")
            out.append(p.stdout[:head])
        if p.stderr.strip():
            out.append("--- stderr ---")
            out.append(p.stderr[-1500:])
    except Exception as e:
        out.append(f"ERREUR {type(e).__name__} {e}")
    out.append("")


run("rm -rf /tmp/dof && git clone --depth 1 -q https://github.com/DivinumOfficium/divinum-officium /tmp/dof && du -sh /tmp/dof", head=500)
run("find /tmp/dof -path '*Kalendaria*' -name '*1960*' | head; ls /tmp/dof/web/cgi-bin 2>&1 | head -20", head=1500)
run("(sudo apt-get update -qq && sudo apt-get install -y -qq libcgi-pm-perl libwww-perl libdatetime-perl) 2>&1 | tail -3", head=800)
run("grep -rn 'Rubrics 1960' /tmp/dof/web/cgi-bin/horas/*.pl /tmp/dof/web/cgi-bin/horas/*.pm 2>/dev/null | head -5", head=1200)

for script, cmd_param in (("missa/missa.pl", ""), ("horas/officium.pl", "&command=prayLaudes")):
    cwd = f"/tmp/dof/web/cgi-bin/{script.split('/')[0]}"
    env = dict(os.environ,
               REQUEST_METHOD="GET",
               QUERY_STRING=f"date={DATE}&version=Rubrics%201960%20-%201960&lang2=English{cmd_param}",
               SCRIPT_NAME=f"/cgi-bin/{script}")
    out.append(f"===== {script} date={DATE}")
    run(f"perl {script.split('/')[1]}", cwd=cwd, env=env, head=5000)

with open("debug_dof.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out) + "\n")
print("debug_dof.txt écrit")
