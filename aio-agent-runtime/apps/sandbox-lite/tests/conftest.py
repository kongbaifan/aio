import sys
from pathlib import Path

# Sandbox 是单文件应用，测试需要显式加入应用目录才能导入 server。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

