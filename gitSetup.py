# gitSetup.py
"""
Functionality:
    This script is used to manage the activation and deactivation of Git hooks.
    These hooks are stored in the `.githooks` directory and can be symlinked or copied to the `.git/hooks` directory.
    They are necessary for enforcing branch naming conventions and other repository policies.

Usage:
    python gitSetup.py ON   -> Explicitly enable hooks
    python gitSetup.py OFF  -> Explicitly disable hooks
    python gitSetup.py      -> Toggle hooks state
"""
import os
import sys
import shutil
import stat

# Append the project root directory so we can cleanly import from src/
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.utils.texthandler import TextHandler
from src.utils.constants import TERMINAL

HOOKS_SRC = ".githooks"
HOOKS_DEST = os.path.join(".git", "hooks")

# Instantiate the visual handler
logger = TextHandler()

def is_git_repository() -> bool:
    return os.path.isdir(".git")

def make_executable(filepath: str):
    """Ensures the hook script has execute permissions on Linux/macOS."""
    if os.name != 'nt':
        st = os.stat(filepath)
        os.chmod(filepath, st.st_mode | stat.S_IEXEC)

def enable_hooks():
    if not is_git_repository():
        logger.fail("Git Setup", "Not a git repository! Run this from your project root.")
        sys.exit(1)

    if not os.path.isdir(HOOKS_SRC):
        logger.fail("Git Setup", f"Source directory '{HOOKS_SRC}' not found.")
        sys.exit(1)

    os.makedirs(HOOKS_DEST, exist_ok=True)
    copied_any = False

    for filename in os.listdir(HOOKS_SRC):
        src_file = os.path.join(HOOKS_SRC, filename)
        dest_file = os.path.join(HOOKS_DEST, filename)

        if os.path.isdir(src_file) or filename.startswith('.'):
            continue

        if os.path.exists(dest_file) or os.path.islink(dest_file):
            if os.path.islink(dest_file):
                os.unlink(dest_file)
            else:
                os.remove(dest_file)

        try:
            os.symlink(os.path.abspath(src_file), dest_file)
        except (AttributeError, NotImplementedError, OSError):
            shutil.copy2(src_file, dest_file)
        
        make_executable(dest_file)
        copied_any = True
        logger.info("Git Setup", f"Activated hook: {filename}")

    if copied_any:
        logger.ok("Git Setup", "Git hooks successfully enabled!")
    else:
        logger.warn("Git Setup", "No hook files found to activate.")

def disable_hooks():
    if not is_git_repository() or not os.path.isdir(HOOKS_DEST):
        logger.warn("Git Setup", "Git hooks are already absent or this is not a git repo.")
        return

    if not os.path.isdir(HOOKS_SRC):
        logger.warn("Git Setup", f"Source '{HOOKS_SRC}' not found. Cleaving active targets blindly.")
        active_hooks = os.listdir(HOOKS_DEST)
    else:
        active_hooks = os.listdir(HOOKS_SRC)

    removed_any = False
    for filename in active_hooks:
        dest_file = os.path.join(HOOKS_DEST, filename)
        
        if os.path.exists(dest_file) or os.path.islink(dest_file):
            if os.path.islink(dest_file):
                os.unlink(dest_file)
            else:
                os.remove(dest_file)
            logger.info("Git Setup", f"Deactivated hook: {filename}")
            removed_any = True

    if removed_any:
        logger.ok("Git Setup", "Git hooks successfully disabled.")
    else:
        logger.info("Git Setup", "No custom hooks were active.")

def determine_current_state() -> str:
    if not is_git_repository() or not os.path.isdir(HOOKS_SRC):
        return "OFF"
    
    for filename in os.listdir(HOOKS_SRC):
        if filename.startswith('.') or os.path.isdir(os.path.join(HOOKS_SRC, filename)):
            continue
        if os.path.exists(os.path.join(HOOKS_DEST, filename)) or os.path.islink(os.path.join(HOOKS_DEST, filename)):
            return "ON"
            
    return "OFF"

def main():
    arg = sys.argv[1].upper() if len(sys.argv) > 1 else None

    if arg == "ON":
        enable_hooks()
    elif arg == "OFF":
        disable_hooks()
    elif arg is None:
        current_state = determine_current_state()
        if current_state == "ON":
            logger.info("Git Setup", "Hooks are currently ON. Toggling OFF...")
            disable_hooks()
        else:
            logger.info("Git Setup", "Hooks are currently OFF. Toggling ON...")
            enable_hooks()
    else:
        logger.fail("Git Setup", f"Unknown argument: '{sys.argv[1]}'")
        print("\nUsage:")
        print("  python gitSetup.py ON   -> Explicitly enable hooks")
        print("  python gitSetup.py OFF  -> Explicitly disable hooks")
        print("  python gitSetup.py      -> Toggle hooks state")
        sys.exit(1)

if __name__ == "__main__":
    main()