#!/usr/bin/env python3
"""
QMT-MCP - 游资打板助手
专注于游资打板需要的核心信息：龙虎榜、涨停板、成交量异动等
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import pandas as pd
from dotenv import load_dotenv
from fastmcp import FastMCP

# 加载环境变量
load_dotenv()

# 配置日志
os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/qmt_mcp.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ====================== 配置管理 ======================

class Config:
    """统一配置管理"""
    PORT = int(os.getenv("QMT_PORT", "8000"))

    # XTQuant配置
    QMT_PATH = os.getenv("QMT_PATH", r"D:\某券商QMT交易端\userdata_mini")
    SESSION_ID = int(os.getenv("QMT_SESSION_ID", "12345"))  # 随便一个整数
    ACCOUNT_ID = os.getenv("QMT_ACCOUNT_ID", "你的券商资金号")

    # 交易风控
    MAX_ORDER_VALUE = float(os.getenv("MAX_ORDER_VALUE", "100000"))
    MIN_ORDER_QUANTITY = int(os.getenv("MIN_ORDER_QUANTITY", "100"))


config = Config()

# ====================== XTQuant客户端 ======================

class XTQuantClient:
    """XTQuant数据接口封装"""

    def __init__(self):
        self._connected = False
        self._xt = None
        self._trader = None

    def connect(self) -> bool:
        """连接到XTQuant"""
        try:
            import xtquant.xtdata as xt
            self._xt = xt
            result = xt.connect()

            # 测试连接
            test_stocks = xt.get_trading_dates('SH')  
            if test_stocks and len(test_stocks) > 0:
                self._connected = True
                logger.info(f"✓ XTQuant连接成功，可访问 {len(test_stocks)} 只股票")
                return True
            return False
        except Exception as e:
            logger.error(f"✗ XTQuant连接失败: {e}")
            self._connected = False
            return False

    def is_connected(self) -> bool:
        return self._connected

    def get_market_data(self, symbol: str, days: int = 30) -> Optional[pd.DataFrame]:
        """获取股票行情数据"""
        if not self._connected:
            logger.warning("XTQuant未连接")
            return None

        try:
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')

            data = self._xt.get_market_data(
                stock_list=[symbol],
                period='1d',
                start_time=start_date,
                end_time=end_date,
                fill_data=True
            )

            if not data or 'close' not in data:
                return None

            # 重构数据为标准DataFrame
            dates = data['time'].columns
            result_data = {
                'time': [pd.to_datetime(str(date)) for date in dates],
                'open': data['open'].iloc[0].values,
                'high': data['high'].iloc[0].values,
                'low': data['low'].iloc[0].values,
                'close': data['close'].iloc[0].values,
                'volume': data['volume'].iloc[0].values,
            }

            df = pd.DataFrame(result_data)
            df.set_index('time', inplace=True)
            return df

        except Exception as e:
            logger.error(f"获取{symbol}数据失败: {e}")
            return None

    def get_stock_list(self, sector: str = '沪深A股') -> List[str]:
        """获取股票列表"""
        if not self._connected:
            return []
        try:
            return self._xt.get_stock_list_in_sector(sector) or []
        except:
            return []

    def get_sector_data(self, sector: str, days: int = 5) -> Optional[Dict]:
        """批量获取板块数据"""
        if not self._connected:
            return None

        try:
            stocks = self.get_stock_list(sector)
            if not stocks:
                return None

            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')

            data = self._xt.get_market_data(
                stock_list=stocks,
                period='1d',
                start_time=start_date,
                end_time=end_date,
                fill_data=True
            )

            return data
        except Exception as e:
            logger.error(f"获取板块数据失败: {e}")
            return None

    def disconnect(self):
        """断开连接"""
        if self._xt:
            try:
                self._xt.disconnect()
                logger.info("XTQuant连接已断开")
            except:
                pass
        self._connected = False

# 全局客户端实例
xt_client = XTQuantClient()

# ====================== 交易功能 ======================

class TradingTools:
    """交易执行工具"""

    def __init__(self):
        self.trader = None
        self.account = None
        self._init_trader()

    def _init_trader(self):
        """初始化交易器"""
        try:
            from xtquant.xttrader import XtQuantTrader
            from xtquant.xttype import StockAccount

            self.trader = XtQuantTrader(config.QMT_PATH, config.SESSION_ID)
            self.account = StockAccount(config.ACCOUNT_ID)
            logger.info("✓ 交易器初始化成功")
        except Exception as e:
            logger.warning(f"交易器初始化失败（将使用模拟模式）: {e}")

    def place_order(self, symbol: str, quantity: int, price: float, direction: str = "BUY") -> str:
        """下单"""
        try:
            # 参数验证
            if quantity % config.MIN_ORDER_QUANTITY != 0:
                return f"❌ 数量必须是{config.MIN_ORDER_QUANTITY}的整数倍"

            if price * quantity > config.MAX_ORDER_VALUE:
                return f"❌ 订单金额超过限额 {config.MAX_ORDER_VALUE}"

            # 模拟模式
            if not self.trader:
                order_id = f"SIM{datetime.now().strftime('%Y%m%d%H%M%S')}"
                return f"""✓ 订单已提交（模拟模式）
股票: {symbol}
方向: {direction}
数量: {quantity}股
价格: ¥{price:.2f}
订单号: {order_id}"""

            # 实盘交易
            from xtquant import xtconstant
            xt_direction = xtconstant.STOCK_BUY if direction == 'BUY' else xtconstant.STOCK_SELL

            order_id = self.trader.order_stock(
                self.account, symbol, xt_direction, quantity,
                xtconstant.FIX_PRICE, price, "QMT-MCP", "Auto"
            )

            if order_id > 0:
                return f"✓ 订单提交成功\n订单号: {order_id}"
            else:
                return f"❌ 订单提交失败，错误代码: {order_id}"

        except Exception as e:
            logger.error(f"下单失败: {e}")
            return f"❌ 下单失败: {str(e)}"

    def cancel_order(self, order_id: str) -> str:
        """撤单"""
        try:
            if not self.trader:
                return f"✓ 订单 {order_id} 撤单成功（模拟模式）"

            result = self.trader.cancel_order_stock(self.account, int(order_id))
            return "✓ 撤单成功" if result == 0 else "❌ 撤单失败"
        except Exception as e:
            return f"❌ 撤单失败: {str(e)}"

trading_tools = TradingTools()

# ====================== 数据分析工具 ======================

class DataAnalyzer:
    """数据分析工具：龙虎榜、涨停板、异动等"""

    @staticmethod
    def find_limit_up_stocks(date: Optional[str] = None) -> str:
        """查找涨停板股票"""
        if not xt_client.is_connected():
            return "❌ XTQuant未连接"

        try:
            # 获取所有A股数据
            data = xt_client.get_sector_data('沪深A股', days=2)
            if not data:
                return "❌ 获取数据失败"

            # 计算涨幅
            close_df = data['close']
            pre_close = close_df.iloc[:, -2]  # 前一日收盘
            current_close = close_df.iloc[:, -1]  # 当前收盘

            # 计算涨幅
            pct_change = ((current_close - pre_close) / pre_close * 100).round(2)

            # 筛选涨停板（涨幅 >= 9.5%）
            limit_up = pct_change[pct_change >= 9.5].sort_values(ascending=False)

            if len(limit_up) == 0:
                return "ℹ️ 今日暂无涨停股票"

            # 格式化输出
            result = f"📊 涨停板统计（共{len(limit_up)}只）\n"
            result += "=" * 50 + "\n"

            for i, (symbol, pct) in enumerate(limit_up.head(20).items(), 1):
                vol = data['volume'].loc[symbol].iloc[-1]
                result += f"{i}. {symbol:12s} +{pct:6.2f}%  成交量: {vol:,.0f}\n"

            if len(limit_up) > 20:
                result += f"\n... 还有 {len(limit_up) - 20} 只涨停股票\n"

            return result

        except Exception as e:
            logger.error(f"涨停板统计失败: {e}")
            return f"❌ 统计失败: {str(e)}"

    @staticmethod
    def find_volume_surge(threshold: float = 2.0, days: int = 5) -> str:
        """查找成交量异动股票"""
        if not xt_client.is_connected():
            return "❌ XTQuant未连接"

        try:
            data = xt_client.get_sector_data('沪深A股', days=days)
            if not data:
                return "❌ 获取数据失败"

            volume_df = data['volume']

            # 计算量比
            avg_volume = volume_df.iloc[:, :-1].mean(axis=1)  # 前几天平均量
            current_volume = volume_df.iloc[:, -1]  # 今日成交量

            volume_ratio = (current_volume / avg_volume).round(2)

            # 筛选量比大于阈值的股票
            surge_stocks = volume_ratio[volume_ratio >= threshold].sort_values(ascending=False)

            if len(surge_stocks) == 0:
                return f"ℹ️ 暂无量比超过{threshold}倍的股票"

            # 格式化输出
            result = f"📈 成交量异动（量比>={threshold}倍，共{len(surge_stocks)}只）\n"
            result += "=" * 50 + "\n"

            close_df = data['close']

            for i, (symbol, ratio) in enumerate(surge_stocks.head(20).items(), 1):
                price = close_df.loc[symbol].iloc[-1]
                vol = volume_df.loc[symbol].iloc[-1]
                result += f"{i}. {symbol:12s} 量比:{ratio:6.2f}x  价格:¥{price:7.2f}  量:{vol:,.0f}\n"

            if len(surge_stocks) > 20:
                result += f"\n... 还有 {len(surge_stocks) - 20} 只异动股票\n"

            return result

        except Exception as e:
            logger.error(f"成交量异动分析失败: {e}")
            return f"❌ 分析失败: {str(e)}"

    @staticmethod
    def get_stock_info(symbol: str, days: int = 30) -> str:
        """获取股票详细信息"""
        if not xt_client.is_connected():
            return "❌ XTQuant未连接"

        try:
            df = xt_client.get_market_data(symbol, days=days)
            if df is None or df.empty:
                return f"❌ 未找到股票 {symbol} 的数据"

            # 最新数据
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else latest

            # 计算指标
            pct_change = ((latest['close'] - prev['close']) / prev['close'] * 100)
            avg_volume = df['volume'].mean()
            volume_ratio = latest['volume'] / avg_volume

            # 计算5日和20日均线
            ma5 = df['close'].rolling(5).mean().iloc[-1] if len(df) >= 5 else latest['close']
            ma20 = df['close'].rolling(20).mean().iloc[-1] if len(df) >= 20 else latest['close']

            # 格式化输出
            result = f"""📊 股票信息: {symbol}
{'=' * 50}
最新价格: ¥{latest['close']:.2f}  ({pct_change:+.2f}%)
今日区间: ¥{latest['low']:.2f} - ¥{latest['high']:.2f}
成交量:   {latest['volume']:,.0f}
量比:     {volume_ratio:.2f}x

均线系统:
  MA5:  ¥{ma5:.2f}
  MA20: ¥{ma20:.2f}

{days}日统计:
  最高: ¥{df['high'].max():.2f}
  最低: ¥{df['low'].min():.2f}
  平均成交量: {avg_volume:,.0f}
"""
            return result

        except Exception as e:
            logger.error(f"获取股票信息失败: {e}")
            return f"❌ 查询失败: {str(e)}"

    @staticmethod
    def get_dragon_tiger_info(symbol: str) -> str:
        """
        龙虎榜信息
        """
        if not xt_client.is_connected():
            return "❌ XTQuant未连接"

        try:
            # 获取股票基本数据
            df = xt_client.get_market_data(symbol, days=5)
            if df is None or df.empty:
                return f"❌ 未找到股票 {symbol} 的数据"

            # 简化分析：基于成交量和涨幅判断
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else latest

            pct_change = ((latest['close'] - prev['close']) / prev['close'] * 100)
            avg_volume = df['volume'].mean()
            volume_ratio = latest['volume'] / avg_volume

            result = f"""🐉 龙虎榜分析: {symbol}
{'=' * 50}
最新涨幅: {pct_change:+.2f}%
量比:     {volume_ratio:.2f}x

"""

            # 判断是否可能上榜
            if abs(pct_change) >= 7:
                result += "⚠️ 涨跌幅较大，可能上榜\n"
            if volume_ratio >= 2:
                result += "⚠️ 成交量显著放大，可能上榜\n"

            if abs(pct_change) < 7 and volume_ratio < 2:
                result += "ℹ️ 暂无明显上榜特征\n"

            result += """
注意：完整龙虎榜数据需要接入专门的数据源
当前仅提供基础技术分析参考
"""

            return result

        except Exception as e:
            logger.error(f"龙虎榜分析失败: {e}")
            return f"❌ 分析失败: {str(e)}"

analyzer = DataAnalyzer()

# ====================== FastMCP服务 ======================

mcp = FastMCP("QMT游资打板助手")

@mcp.tool()
def place_order(symbol: str, quantity: int, price: float, direction: str = "BUY") -> str:
    """
    下单交易

    Args:
        symbol: 股票代码 (如 000001.SZ)
        quantity: 数量（必须是100的整数倍）
        price: 价格
        direction: 方向 (BUY/SELL)
    """
    logger.info(f"下单: {symbol} {direction} {quantity}@{price}")
    return trading_tools.place_order(symbol, quantity, price, direction)

@mcp.tool()
def cancel_order(order_id: str) -> str:
    """
    撤单

    Args:
        order_id: 订单号
    """
    logger.info(f"撤单: {order_id}")
    return trading_tools.cancel_order(order_id)

@mcp.tool()
def find_limit_up() -> str:
    """查找今日涨停板股票"""
    logger.info("查询涨停板")
    return analyzer.find_limit_up_stocks()

@mcp.tool()
def find_volume_surge(threshold: float = 2.0) -> str:
    """
    查找成交量异动股票

    Args:
        threshold: 量比阈值（默认2倍）
    """
    logger.info(f"查询成交量异动（阈值={threshold}）")
    return analyzer.find_volume_surge(threshold)

@mcp.tool()
def get_stock_info(symbol: str, days: int = 30) -> str:
    """
    获取股票详细信息

    Args:
        symbol: 股票代码
        days: 查询天数（默认30天）
    """
    logger.info(f"查询股票信息: {symbol}")
    return analyzer.get_stock_info(symbol, days)

@mcp.tool()
def get_dragon_tiger_info(symbol: str) -> str:
    """
    龙虎榜信息
    
    Args:
        symbol: 股票代码
    """
    logger.info(f"龙虎榜分析: {symbol}")
    return analyzer.get_dragon_tiger_info(symbol)

# ====================== 主程序 ======================

def main():
    """主函数"""
    try:
        logger.info("=" * 60)
        logger.info("QMT-MCP 游资打板助手 v3.0")
        logger.info("=" * 60)

        # 初始化XTQuant连接
        logger.info("正在连接XTQuant...")
        if xt_client.connect():
            logger.info("✓ XTQuant连接成功")
        else:
            logger.warning("⚠ XTQuant连接失败，部分功能将不可用")

        # 获取实际绑定地址
        bind_host = "0.0.0.0"

        # 启动MCP服务
        logger.info(f"✓ MCP服务启动: http://{bind_host}:{config.PORT} (远程访问模式)")

        logger.info("=" * 60)

        mcp.run(transport="sse", host=bind_host, port=config.PORT)

    except KeyboardInterrupt:
        logger.info("\n用户中断，正在关闭...")
    except Exception as e:
        logger.error(f"服务错误: {e}", exc_info=True)
    finally:
        xt_client.disconnect()
        logger.info("✓ 服务已关闭")

if __name__ == "__main__":
    main()
