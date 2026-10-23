"""Compatibility config preview; install the package before applying it."""
from pathlib import Path
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent/'src'))
from raincoat_agent_mcp.management import setup
if __name__=='__main__':print(json.dumps(setup(client='generic'),indent=2))
