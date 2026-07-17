import time
from functools import wraps
from src.utils.texthandler import TextHandler

texthandler = TextHandler()

def succeed(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs, success=True)
    return wrapper


def fail(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs, success=False)
    return wrapper


@succeed
def installPackage(texthandler, category, *, success=True):
    texthandler.info(category, "Installing {} library".format(category))
    successMsg = "Successfully installed {} package".format(category)
    for i in range(101):
        texthandler.loadingPercentage(category, i, success=success, successMsg=successMsg)
        time.sleep(0.03)


@fail
def brokenInstall(texthandler, category, *, success=True):
    texthandler.info(category, "Installing {} library".format(category))
    errorMsg = "Installation failed for {} package: connection timeout".format(category)
    for i in range(101):
        texthandler.loadingPercentage(category, i, success=success, errorMsg=errorMsg)
        time.sleep(0.03)


if __name__ == "__main__":
    texthandler.info("Test", "All tests completed successfully")
    texthandler.fail("Test", "Some tests failed")
    texthandler.warn("Test", "This is a warning message")
    texthandler.info("Test", "This is an informational message")
    print()
    installPackage(texthandler, "Tikz")
    brokenInstall(texthandler, "Pgf")
