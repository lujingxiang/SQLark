# test_db.py

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# 添加虚拟环境的 site-packages 到路径
VENV_SITE_PACKAGES = ROOT_DIR / ".venv" / "Lib" / "site-packages"
if VENV_SITE_PACKAGES.exists() and str(VENV_SITE_PACKAGES) not in sys.path:
    sys.path.insert(0, str(VENV_SITE_PACKAGES))

from app.db.db_utils import execute_query

sql = """
SELECT * 
FROM StockData 
ORDER BY TradeTime DESC 
LIMIT 5;
"""

result = execute_query(sql)

print("查询结果：")
for row in result:
    print(row)
