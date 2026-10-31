#!/usr/bin/env python3
"""Script de sondage TEMPORAIRE : corps des pages du moteur Divinum Officium (Perl) pour plusieurs dates."""
import os
import re
import subprocess

out = []


def sh(cmd, cwd=None, env=None, timeout=900):
    return subprocess.run(cmd, shell=True, cwd=cwd, env=env, capture_output=True,
                          text=True, timeout=timeout)


p = sh("rm -rf /tmp/dof && git clone --depth 1 -q https://github.com/DivinumOfficium/divinum-officium /tmp/dof")
out.append(f"clone code {p.returncode} {p.stderr[-300:]}")
p = sh("(sudo apt-get update -qq && sudo apt-get install -y -qq libcgi-pm-perl libwww-perl libdatetime-perl) 2>&1 | tail -1")
out.append(f"apt: {p.stdout.strip()[-200:]}")

DATES = ["10-31-2026", "11-1-2026", "11-4-2026", "12-6-2026", "2-17-2027", "4-5-2026"]
for script in ("missa", "horas"):
    for date in DATES:
        cmdp = "" if script == "missa" else "&command=prayLaudes"
        env = dict(os.environ, REQUEST_METHOD="GET",
                   QUERY_STRING=f"date={date}&version=Rubrics%201960%20-%201960&lang2=English{cmdp}",
                   SCRIPT_NAME=f"/cgi-bin/{script}/{'missa' if script == 'missa' else 'officium'}.pl")
        prog = "missa.pl" if script == "missa" else "officium.pl"
        p = sh(f"perl {prog}", cwd=f"/tmp/dof/web/cgi-bin/{script}", env=env)
        html = p.stdout
        out.append(f"===== {script} {date} (code {p.returncode}, {len(html)} octets)")
        if p.stderr.strip():
            out.append("stderr: " + p.stderr[-300:].replace("\n", " | "))
        m = re.search(r"(?is)<body.*", html)
        body = m.group(0) if m else html
        body = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", "", body)
        out.append("--- HTML corps (1800 premiers caractères) ---")
        out.append(re.sub(r"\n\s*\n+", "\n", body)[:1800])
        txt = re.sub(r"<[^>]+>", " ", body)
        txt = re.sub(r"\s+", " ", txt)
        out.append("--- TEXTE (600 premiers caractères) ---")
        out.append(txt[:600])
        out.append("")

with open("debug_dof.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out) + "\n")
print("debug_dof.txt écrit")
