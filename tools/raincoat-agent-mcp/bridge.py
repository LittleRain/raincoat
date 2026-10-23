"""Compatibility entry for previously configured source checkouts."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent/'src'))
from raincoat_agent_mcp.cli import main
if __name__=='__main__':main()
