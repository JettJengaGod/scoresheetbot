import asyncio
from os.path import dirname, realpath
import sys

# Add project folder to sys.path
_project_path = dirname(dirname(realpath(__file__)))
sys.path.append(_project_path)

from scoreSheetBot import main


asyncio.run(main())
