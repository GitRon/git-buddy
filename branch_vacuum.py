#!/usr/bin/env python3
import subprocess
import argparse
import sys

def run_git_command(args: list[str], repo_dir: str, silent: bool = False, capture: bool = True) -> list[str]:
    result = subprocess.run(
        ["git", "-C", repo_dir] + args,
        capture_output=capture,
        text=True,
        check=True
    )

    if capture:
        return result.stdout.strip().splitlines()
    return []

def get_local_branches(repo_dir: str) -> list[str]:
    return run_git_command(["branch", "--format", "%(refname:short)"], repo_dir)

def get_remote_branches(repo_dir: str) -> list[str]:
    branches = run_git_command(["branch", "-r", "--format", "%(refname:short)"], repo_dir)
    return [b.strip().replace("origin/", "", 1) for b in branches if b.strip().startswith("origin/")]

def delete_branch(branch: str, repo_dir: str, force: bool = True) -> None:
    cmd = ["git", "-C", repo_dir, "branch", "-D" if force else "-d", branch]
    try:
        subprocess.run(cmd, check=True)
        print(f"✅ Deleted branch: {branch}")
    except subprocess.CalledProcessError as e:
        print(f"❌ Could not delete branch '{branch}'. Maybe it's the current branch?")

def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive cleanup of local-only git branches.")
    parser.add_argument("repo", help="Path to the git repository")
    parser.add_argument(
        "--safe",
        action="store_true",
        help="Use safe delete (-d) instead of force delete (-D)."
    )
    args = parser.parse_args()

    repo_dir = args.repo

    try:
        run_git_command(["rev-parse", "--is-inside-work-tree"], repo_dir)
    except subprocess.CalledProcessError:
        print(f"❌ {repo_dir} is not a valid git repository.")
        sys.exit(1)

    print("🔄 Fetching latest remote info...")
    run_git_command(["fetch", "--prune"], repo_dir, capture=False)
    print("✅ Fetch complete.")

    local_branches = get_local_branches(repo_dir)
    remote_branches = get_remote_branches(repo_dir)

    only_local = [b for b in local_branches if b not in remote_branches and b not in ("main", "master")]

    if not only_local:
        print("🎉 No local-only branches found.")
        return

    for branch in only_local:
        while True:
            choice = input(f"Branch '{branch}' exists only locally. Delete? [y/N]: ").strip().lower()
            if choice == "y":
                delete_branch(branch, repo_dir, force=not args.safe)
                break
            elif choice in ("n", ""):
                print(f"➡️ Keeping branch: {branch}")
                break
            else:
                print("Please answer with 'y' or 'n'.")

if __name__ == "__main__":
    main()
