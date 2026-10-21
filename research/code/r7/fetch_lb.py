"""Run 7: fetch 2025-26 skater + team per-game logs Mar 1 - Apr 20 2026 (lockbox period) into PC_R6_DIR/nhl, only for the
frozen LB2 look (T5 T=.01). Reuses fetch6.pull. python3 -I fetch_lb.py"""
import os, sys, runpy
from datetime import date
sys.argv = ["x"]
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "r6", "fetch6.py")).read()
src = src[:src.index('pull("team/summary", "20242025"')]
g = {"__name__": "f"}
exec(compile(src, "fetch6", "exec"), g)
g["pull"]("team/summary", "20252026", date(2026, 3, 1), date(2026, 4, 20), "team_2526_lb")
g["pull"]("skater/summary", "20252026", date(2026, 3, 1), date(2026, 4, 20), "skater_2526_lb")
