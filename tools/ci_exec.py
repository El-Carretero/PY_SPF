"""Run a Python module with the CI loopback guard already installed."""
import runpy
import sys

from ci_guard import install

install()
module = sys.argv.pop(1)
sys.argv[0] = module
runpy.run_module(module, run_name='__main__', alter_sys=True)
