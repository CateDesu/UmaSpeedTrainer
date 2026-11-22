"""Remove superseded trainer binaries after publishing a stable release."""

import json
import os
import re
import subprocess


BINARIES = {"UmaSpeedTrainer-linux-x86_64", "uma_speed_trainer.exe", "uma_hook.dll"}
REQUIRED = BINARIES | {"UmaSpeedTrainer-linux-source.tar.gz"}


def version(tag):
    match = re.fullmatch(r"v([0-9]+)\.([0-9]+)\.([0-9]+)", tag)
    return tuple(map(int, match.groups())) if match else None


def obsolete_builds(tag, latest, releases):
    current = version(tag)
    if not current or latest["tag_name"] != tag or latest["draft"] or latest["prerelease"]:
        return
    uploaded = {a["name"] for a in latest["assets"] if a["state"] == "uploaded" and a["size"] > 0}
    if not REQUIRED <= uploaded:
        raise ValueError("The latest release is missing a complete download.")

    for release in releases:
        previous = version(release["tag_name"])
        if not previous or previous >= current or release["draft"] or release["prerelease"]:
            continue
        for asset in release["assets"]:
            if asset["name"] in BINARIES:
                yield release["tag_name"], asset


def main():
    tag = os.environ["GITHUB_REF_NAME"]
    if not version(tag):
        return
    base = f"repos/{os.environ['GITHUB_REPOSITORY']}/releases"
    latest = json.loads(subprocess.check_output(["gh", "api", f"{base}/latest"]))
    pages = json.loads(subprocess.check_output(["gh", "api", "--paginate", "--slurp", f"{base}?per_page=100"]))
    releases = (release for page in pages for release in page)
    for older_tag, asset in obsolete_builds(tag, latest, releases):
        subprocess.run(["gh", "api", "--method", "DELETE", f"{base}/assets/{asset['id']}"], check=True)
        print(f"Removed {asset['name']} from {older_tag}", flush=True)


if __name__ == "__main__":
    main()
